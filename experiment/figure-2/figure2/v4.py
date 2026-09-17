"""Figure 2 v4 conventional-IBLT and Rateless-IBLT wire correction runner."""

import json
import math
import statistics
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import constants as const
from .artifacts import atomic_json, atomic_jsonl, canonical_sha256, sha256_file, source_tree_sha256
from .config import actual_external_cells, derive_internal_seed, derive_seed, profile_manifest
from .engine import EngineExecutionError, EngineResult, Figure2Engines
from .formal import Checkpoints, next_timing_trial, timing_attempt_records, worker_batches
from .statistics import percentile_bootstrap, wilson


CHANGED_ALGORITHMS = ("external_iblt", "riblt")
FRESH_PROBABILITY_ALGORITHMS = ("riblt",)
MIGRATED_ALGORITHMS = ("xyz", "minisketch", "external_iblt", "project_iblt", "cpisync")
TIMEOUT_SECONDS = {"external_iblt": 600.0, "riblt": 1800.0}
MEMORY_LIMIT_BYTES = 80 * (1024 ** 3)


def _read(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _mean_or_int(values: Sequence[float]) -> Any:
    value = statistics.fmean(values)
    return int(value) if value.is_integer() else value


class V4Runner:
    @classmethod
    def create(cls, parent_run: Path, results_root: Path) -> Path:
        parent = parent_run.resolve()
        if _read(parent / "run_state.json").get("status") != "complete":
            raise ValueError("v4 parent run is not complete")
        parent_aggregate = _read(parent / "aggregate.json")
        if parent_aggregate.get("protocol_version") != "figure2-v3":
            raise ValueError("v4 requires the completed v3 correction aggregate")
        profiles = profile_manifest()
        executables = {
            name: sha256_file(path) for name, path in const.EXECUTABLES.items()
        }
        config = {
            "protocol_version": const.PROTOCOL_VERSION,
            "kind": "figure2-v4-wire-correction",
            "parent_run": str(parent),
            "parent_aggregate_sha256": sha256_file(parent / "aggregate.json"),
            "d_values": list(const.DIFFERENCES),
            "set_size_A": const.SET_SIZE,
            "set_size_B": const.SET_SIZE,
            "discovery_trials": const.DISCOVERY_TRIALS,
            "confirmation_trials": const.CONFIRMATION_TRIALS,
            "timing_successful_datasets_target": const.TIMING_DATASETS,
            "timing_repetitions": const.TIMING_REPETITIONS,
            "timing_warmups": 0,
            "timing_bootstraps": const.TIMING_BOOTSTRAPS,
            "timing_estimand": "conditional_mean_given_decode_success",
            "fresh_probability_algorithms": list(FRESH_PROBABILITY_ALGORITHMS),
            "fresh_timing_algorithms": list(CHANGED_ALGORITHMS),
            "migrated_algorithms": list(MIGRATED_ALGORITHMS),
            "worker_policy": {
                "probability": {"workers": 8, "physical_cpu_affinity": list(range(8))},
                "timing": {"workers": 1, "physical_cpu_affinity": [0]},
            },
            "memory_limit_gib": 80,
            "timeout_seconds": TIMEOUT_SECONDS,
            "figure2_source_tree_sha256": source_tree_sha256(const.EXPERIMENT_DIR),
            "profile_manifest": profiles,
            "executable_sha256": executables,
        }
        config_sha = canonical_sha256(config)
        timestamp = subprocess.run(
            ["date", "-u", "+%Y%m%dT%H%M%SZ"], check=True,
            stdout=subprocess.PIPE, text=True,
        ).stdout.strip()
        path = results_root.resolve() / ("figure2-v4-%s-%s" % (timestamp, config_sha[:12]))
        path.mkdir(parents=True, exist_ok=False)
        atomic_json(path / "run_config.json", config)
        atomic_json(path / "profile_manifest.json", profiles)
        atomic_json(path / "run_state.json", {"sequence": 0, "status": "created"})
        (path / "errors.log").touch(exist_ok=False)
        return path

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.config = _read(self.path / "run_config.json")
        if self.config.get("protocol_version") != const.PROTOCOL_VERSION:
            raise ValueError("v4 run protocol mismatch")
        current_source_sha = source_tree_sha256(const.EXPERIMENT_DIR)
        if self.config.get("figure2_source_tree_sha256") != current_source_sha:
            amendment_path = self.path / "source_amendment_manifest.json"
            if not amendment_path.is_file():
                raise ValueError("Figure 2 source tree changed after v4 run creation")
            amendment = _read(amendment_path)
            if amendment != {
                "protocol_version": const.PROTOCOL_VERSION,
                "reason": "add_independent_riblt_confirmation_refinement",
                "original_source_tree_sha256": self.config["figure2_source_tree_sha256"],
                "amended_source_tree_sha256": current_source_sha,
                "executables_unchanged": True,
                "profiles_unchanged": True,
            }:
                raise ValueError("invalid v4 source amendment manifest")
        for name, executable in const.EXECUTABLES.items():
            if self.config["executable_sha256"].get(name) != sha256_file(executable):
                raise ValueError("v4 executable changed: %s" % name)
        self.parent = Path(self.config["parent_run"])
        if sha256_file(self.parent / "aggregate.json") != self.config["parent_aggregate_sha256"]:
            raise ValueError("v4 parent aggregate changed")
        self.profiles = self.config["profile_manifest"]
        self.checkpoints = Checkpoints(self.path)
        self.timing_engine = Figure2Engines(
            cpu_affinity=0, memory_limit_bytes=MEMORY_LIMIT_BYTES
        )

    def _transition(self, expected: str, new: str) -> None:
        state = _read(self.path / "run_state.json")
        if state.get("status") != expected:
            raise RuntimeError("expected v4 state %s, found %s" % (expected, state.get("status")))
        atomic_json(self.path / "run_state.json", {
            "sequence": int(state["sequence"]) + 1,
            "status": new,
        })

    def _seeds(self, domain: str, d: int, trial: int) -> Dict[str, int]:
        return {
            role: derive_seed(domain, d, trial, role)
            for role in ("identity", "alice_order", "bob_order")
        }

    def _dataset(
        self, engine: Figure2Engines, path: Path, domain: str, d: int, trial: int,
        *, full: bool,
    ) -> Tuple[Dict[str, Any], Dict[str, int]]:
        seeds = self._seeds(domain, d, trial)
        manifest = engine.create_dataset(
            path, full=full, d=d, set_size=const.SET_SIZE if full else 0,
            identity_seed=seeds["identity"], alice_seed=seeds["alice_order"],
            bob_seed=seeds["bob_order"],
        )
        return manifest, seeds

    def _arguments(
        self, algorithm: str, domain: str, d: int, trial: int, resource: int
    ) -> Dict[str, Any]:
        if algorithm == "external_iblt":
            return {"resource": resource}
        if algorithm == "riblt":
            profile_hash = self.profiles["profiles"][algorithm]["profile_hash"]
            return {
                "resource": resource,
                "siphash_k0": derive_internal_seed(
                    domain, d, trial, algorithm, profile_hash, "siphash_k0"
                ),
                "siphash_k1": derive_internal_seed(
                    domain, d, trial, algorithm, profile_hash, "siphash_k1"
                ),
                "internal_seed": derive_internal_seed(
                    domain, d, trial, algorithm, profile_hash, "primary"
                ),
            }
        raise ValueError("unsupported v4 algorithm")

    def _run_engine(
        self, engine: Figure2Engines, algorithm: str, dataset: Path,
        arguments: Mapping[str, Any], *, discover_riblt: bool = False,
    ) -> EngineResult:
        try:
            return engine.run(
                algorithm, dataset, timeout=TIMEOUT_SECONDS[algorithm],
                discover_riblt=discover_riblt, **arguments
            )
        except (EngineExecutionError, subprocess.TimeoutExpired) as error:
            with (self.path / "errors.log").open("a", encoding="utf-8") as stream:
                stream.write("%s\n" % error)
            raise

    def _row(
        self, *, stage: str, algorithm: str, d: int, trial: int,
        candidate_id: str, resource: int, dataset: Mapping[str, Any],
        seeds: Mapping[str, int], result: EngineResult,
        repetition: Optional[int] = None, cpu_affinity: Optional[int] = None,
    ) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "protocol_version": const.PROTOCOL_VERSION,
            "stage": stage,
            "domain": stage,
            "algorithm": algorithm,
            "d": d,
            "trial_index": trial,
            "candidate_id": candidate_id,
            "resource": resource,
            "profile_hash": self.profiles["profiles"][algorithm]["profile_hash"],
            "dataset": dict(dataset),
            "dataset_seeds": dict(seeds),
            "cpu_affinity": cpu_affinity,
            "success": result.success,
            "failure_reason": result.failure_reason,
            "terminal_status": None,
            "logical_state_bits": result.logical_state_bits,
            "state_bits": result.state_bits,
            "control_bits": result.control_bits,
            "total_payload_bits": result.total_payload_bits,
            "R_w30": result.total_payload_bits / (30.0 * d) if result.total_payload_bits else 0.0,
            "update_alice_cpu": result.update_alice_cpu,
            "update_bob_cpu": result.update_bob_cpu,
            "sender_cpu": result.sender_cpu,
            "transfer_cpu": result.transfer_cpu,
            "receiver_cpu": result.receiver_cpu,
            "decode_cpu": result.decode_cpu,
            "alice_output_sha256": result.alice_output_sha256,
            "bob_output_sha256": result.bob_output_sha256,
            "residual_sha256": result.residual_sha256,
            "required_symbols": result.required_symbols,
        }
        if repetition is not None:
            row["repetition"] = repetition
        return row

    def run_discovery(self) -> Path:
        state = _read(self.path / "run_state.json")["status"]
        if state == "created":
            self._transition("created", "discovery_running")
        elif state != "discovery_running":
            raise RuntimeError("v4 discovery is not active")

        def evaluate(cpu: int, items: Sequence[Tuple[int, int]]) -> None:
            engine = Figure2Engines(cpu_affinity=cpu, memory_limit_bytes=MEMORY_LIMIT_BYTES)
            with tempfile.TemporaryDirectory(prefix="figure2-v4-discovery-") as temporary:
                dataset_path = Path(temporary) / "dataset.bin"
                for d, trial in items:
                    if self.checkpoints.load(
                        "resource_discovery", "riblt", d, "required-symbols-v4", trial
                    ):
                        continue
                    dataset, seeds = self._dataset(
                        engine, dataset_path, "resource_discovery_v4", d, trial, full=False
                    )
                    maximum = 3 * d
                    result = self._run_engine(
                        engine, "riblt", dataset_path,
                        self._arguments("riblt", "resource_discovery_v4", d, trial, maximum),
                        discover_riblt=True,
                    )
                    self.checkpoints.save(self._row(
                        stage="resource_discovery", algorithm="riblt", d=d, trial=trial,
                        candidate_id="required-symbols-v4", resource=maximum,
                        dataset=dataset, seeds=seeds, result=result, cpu_affinity=cpu,
                    ))

        items = tuple(
            (d, trial) for d in const.DIFFERENCES for trial in range(const.DISCOVERY_TRIALS)
        )
        batches = worker_batches(items, tuple(range(8)))
        with ThreadPoolExecutor(max_workers=len(batches)) as pool:
            futures = [pool.submit(evaluate, cpu, batch) for cpu, batch in batches]
            for future in futures:
                future.result()

        rows = self.checkpoints.rows("resource_discovery")
        operating = []
        for d in const.DIFFERENCES:
            point_rows = [row for row in rows if row["d"] == d]
            if len(point_rows) != const.DISCOVERY_TRIALS:
                raise RuntimeError("v4 RIBLT discovery point is incomplete")
            required = sorted(int(row["required_symbols"]) for row in point_rows)
            cap = required[89]
            if cap > 3 * d:
                raise RuntimeError("v4 RIBLT cap exceeds discovery range")
            operating.append({
                "algorithm": "riblt", "d": d, "status": "selected",
                "resource": cap, "candidate_id": "q90-v4",
                "required_symbols_sorted": required,
            })
        parent_points = _read(self.parent / "aggregate.json")["points"]
        for row in parent_points:
            if row["algorithm"] == "external_iblt":
                operating.append({
                    "algorithm": "external_iblt", "d": row["d"], "status": row["status"],
                    "resource": row["resource"], "candidate_id": row["candidate_id"],
                })
        atomic_jsonl(self.path / "resource_discovery.jsonl", rows)
        atomic_json(self.path / "operating_points.json", {
            "status": "selected", "operating_points": operating,
        })
        self._transition("discovery_running", "discovery_complete")
        return self.path

    def _operating(self) -> Dict[Tuple[str, int], Dict[str, Any]]:
        rows = _read(self.path / "operating_points.json")["operating_points"]
        return {(row["algorithm"], int(row["d"])): row for row in rows}

    def run_confirmation(self) -> Path:
        state = _read(self.path / "run_state.json")["status"]
        if state == "discovery_complete":
            self._transition("discovery_complete", "confirmation_running")
        elif state != "confirmation_running":
            raise RuntimeError("v4 confirmation is not active")
        operating = self._operating()

        def evaluate(cpu: int, items: Sequence[Tuple[int, int]]) -> None:
            engine = Figure2Engines(cpu_affinity=cpu, memory_limit_bytes=MEMORY_LIMIT_BYTES)
            with tempfile.TemporaryDirectory(prefix="figure2-v4-confirmation-") as temporary:
                dataset_path = Path(temporary) / "dataset.bin"
                for d, trial in items:
                    missing = []
                    for algorithm in FRESH_PROBABILITY_ALGORITHMS:
                        point = operating[(algorithm, d)]
                        if not self.checkpoints.load(
                            "sealed_confirmation", algorithm, d, point["candidate_id"], trial
                        ):
                            missing.append((algorithm, point))
                    if not missing:
                        continue
                    dataset, seeds = self._dataset(
                        engine, dataset_path, "sealed_confirmation_v4", d, trial, full=True
                    )
                    for algorithm, point in missing:
                        result = self._run_engine(
                            engine, algorithm, dataset_path,
                            self._arguments(
                                algorithm, "sealed_confirmation_v4", d, trial,
                                int(point["resource"]),
                            ),
                        )
                        self.checkpoints.save(self._row(
                            stage="sealed_confirmation", algorithm=algorithm, d=d, trial=trial,
                            candidate_id=point["candidate_id"], resource=int(point["resource"]),
                            dataset=dataset, seeds=seeds, result=result, cpu_affinity=cpu,
                        ))

        items = tuple(
            (d, trial) for d in const.DIFFERENCES for trial in range(const.CONFIRMATION_TRIALS)
        )
        batches = worker_batches(items, tuple(range(8)))
        with ThreadPoolExecutor(max_workers=len(batches)) as pool:
            futures = [pool.submit(evaluate, cpu, batch) for cpu, batch in batches]
            for future in futures:
                future.result()

        rows = self.checkpoints.rows("sealed_confirmation")
        refinement_steps = (
            ("q95-v4-refinement1", 94),
            ("q99-v4-refinement2", 98),
            ("q100-v4-refinement3", 99),
            ("max3d-v4-refinement4", None),
        )
        for candidate_id, quantile_index in refinement_steps:
            failing = []
            for d in const.DIFFERENCES:
                point = operating[("riblt", d)]
                point_rows = [
                    row for row in rows
                    if row["algorithm"] == "riblt" and row["d"] == d
                    and row["candidate_id"] == point["candidate_id"]
                ]
                if len(point_rows) != const.CONFIRMATION_TRIALS:
                    raise RuntimeError("v4 RIBLT confirmation block is incomplete")
                if sum(row["success"] is True for row in point_rows) < 90:
                    required = point.get("required_symbols_sorted")
                    if not isinstance(required, list) or len(required) != const.DISCOVERY_TRIALS:
                        raise RuntimeError("v4 RIBLT refinement lacks discovery order statistics")
                    resource = 3 * d if quantile_index is None else int(required[quantile_index])
                    if resource <= int(point["resource"]):
                        continue
                    failing.append((d, resource))
            if not failing:
                continue

            for d, resource in failing:
                operating[("riblt", d)] = {
                    **operating[("riblt", d)],
                    "resource": resource,
                    "candidate_id": candidate_id,
                    "refinement_from": operating[("riblt", d)]["candidate_id"],
                }
            operating_rows = list(operating.values())
            atomic_json(self.path / "operating_points.json", {
                "status": "selected", "operating_points": operating_rows,
            })

            refinement_domain = "sealed_confirmation_%s" % candidate_id.replace("-", "_")

            def evaluate_refinement(cpu: int, items: Sequence[Tuple[int, int]]) -> None:
                engine = Figure2Engines(cpu_affinity=cpu, memory_limit_bytes=MEMORY_LIMIT_BYTES)
                with tempfile.TemporaryDirectory(prefix="figure2-v4-refinement-") as temporary:
                    dataset_path = Path(temporary) / "dataset.bin"
                    for d, trial in items:
                        point = operating[("riblt", d)]
                        if self.checkpoints.load(
                            "sealed_confirmation", "riblt", d, point["candidate_id"], trial
                        ):
                            continue
                        dataset, seeds = self._dataset(
                            engine, dataset_path, refinement_domain, d, trial, full=True
                        )
                        result = self._run_engine(
                            engine, "riblt", dataset_path,
                            self._arguments(
                                "riblt", refinement_domain, d, trial, int(point["resource"])
                            ),
                        )
                        self.checkpoints.save(self._row(
                            stage="sealed_confirmation", algorithm="riblt", d=d, trial=trial,
                            candidate_id=point["candidate_id"], resource=int(point["resource"]),
                            dataset=dataset, seeds=seeds, result=result, cpu_affinity=cpu,
                        ))

            refinement_items = tuple(
                (d, trial) for d, _resource in failing
                for trial in range(const.CONFIRMATION_TRIALS)
            )
            refinement_batches = worker_batches(refinement_items, tuple(range(8)))
            with ThreadPoolExecutor(max_workers=len(refinement_batches)) as pool:
                futures = [
                    pool.submit(evaluate_refinement, cpu, batch)
                    for cpu, batch in refinement_batches
                ]
                for future in futures:
                    future.result()
            rows = self.checkpoints.rows("sealed_confirmation")

        summary = []
        for d in const.DIFFERENCES:
            for algorithm in FRESH_PROBABILITY_ALGORITHMS:
                selected_candidate = operating[(algorithm, d)]["candidate_id"]
                point_rows = [
                    row for row in rows if row["algorithm"] == algorithm and row["d"] == d
                    and row["candidate_id"] == selected_candidate
                ]
                if len(point_rows) != const.CONFIRMATION_TRIALS:
                    raise RuntimeError("v4 confirmation point is incomplete")
                successes = sum(row["success"] is True for row in point_rows)
                low, high = wilson(successes, len(point_rows))
                summary.append({
                    "algorithm": algorithm, "d": d,
                    "status": "confirmed" if successes >= 90 else "confirmation_failed",
                    "trials": len(point_rows), "successes": successes,
                    "success_rate": successes / len(point_rows),
                    "ci_low": low, "ci_high": high,
                })
        atomic_jsonl(self.path / "confirmation.jsonl", rows)
        atomic_json(self.path / "confirmation_summary.json", {"points": summary})
        self._transition("confirmation_running", "confirmation_complete")
        return self.path

    def _timing_summary(self, rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        attempts = timing_attempt_records(rows)
        summaries = []
        confirmation = {
            (row["algorithm"], int(row["d"])): row["status"] == "confirmed"
            for row in _read(self.path / "confirmation_summary.json")["points"]
        }
        parent = {
            (row["algorithm"], int(row["d"])): row
            for row in _read(self.parent / "aggregate.json")["points"]
        }
        for d in const.DIFFERENCES:
            for algorithm in CHANGED_ALGORITHMS:
                point_attempts = [
                    row for row in attempts
                    if row["algorithm"] == algorithm and int(row["d"]) == d
                ]
                successful = [row for row in point_attempts if row["status"] == "successful"]
                confirmed = (
                    parent[(algorithm, d)]["status"] == "confirmed"
                    if algorithm == "external_iblt" else confirmation[(algorithm, d)]
                )
                complete = confirmed and len(successful) == const.TIMING_DATASETS
                updates = [float(row["update_ns_per_input"]) for row in successful] if complete else []
                decodes = [float(row["decode_ns_per_difference"]) for row in successful] if complete else []
                update_ci = percentile_bootstrap(
                    updates, seed_material="figure2_v4|%s|%d|update" % (algorithm, d),
                    estimator="mean",
                ) if updates else (None, None)
                decode_ci = percentile_bootstrap(
                    decodes, seed_material="figure2_v4|%s|%d|decode" % (algorithm, d),
                    estimator="mean",
                ) if decodes else (None, None)
                summaries.append({
                    "algorithm": algorithm, "d": d,
                    "timing_status": "complete" if complete else "not_run_not_confirmed",
                    "estimand": "conditional_mean_given_decode_success",
                    "attempted_datasets": len(point_attempts),
                    "failed_datasets": len(point_attempts) - len(successful),
                    "successful_datasets": len(successful),
                    "successful_datasets_target": const.TIMING_DATASETS,
                    "update_ns_per_input_conditional_mean": statistics.fmean(updates) if updates else None,
                    "update_ci_low": update_ci[0], "update_ci_high": update_ci[1],
                    "decode_ns_per_difference_conditional_mean": statistics.fmean(decodes) if decodes else None,
                    "decode_ci_low": decode_ci[0], "decode_ci_high": decode_ci[1],
                })
        return summaries

    def run_timing(self) -> Path:
        state = _read(self.path / "run_state.json")["status"]
        if state == "confirmation_complete":
            self._transition("confirmation_complete", "timing_running")
        elif state != "timing_running":
            raise RuntimeError("v4 timing is not active")
        operating = self._operating()
        confirmation = {
            (row["algorithm"], int(row["d"])): row["status"] == "confirmed"
            for row in _read(self.path / "confirmation_summary.json")["points"]
        }
        parent = {
            (row["algorithm"], int(row["d"])): row
            for row in _read(self.parent / "aggregate.json")["points"]
        }

        with tempfile.TemporaryDirectory(prefix="figure2-v4-timing-") as temporary:
            dataset_path = Path(temporary) / "dataset.bin"
            for d in const.DIFFERENCES:
                while True:
                    rows = self.checkpoints.rows("timing")
                    attempts = timing_attempt_records(rows)
                    by_algorithm = {
                        algorithm: [
                            row for row in attempts
                            if row["algorithm"] == algorithm and int(row["d"]) == d
                        ]
                        for algorithm in CHANGED_ALGORITHMS
                    }
                    pending = []
                    for algorithm in CHANGED_ALGORITHMS:
                        confirmed = (
                            parent[(algorithm, d)]["status"] == "confirmed"
                            if algorithm == "external_iblt" else confirmation[(algorithm, d)]
                        )
                        if confirmed and sum(
                            row["status"] == "successful" for row in by_algorithm[algorithm]
                        ) < const.TIMING_DATASETS:
                            pending.append(algorithm)
                    if not pending:
                        break
                    next_trials = {
                        algorithm: next_timing_trial(by_algorithm[algorithm])
                        for algorithm in pending
                    }
                    trial = min(next_trials.values())
                    trial_algorithms = [
                        algorithm for algorithm in pending if next_trials[algorithm] == trial
                    ]
                    dataset, seeds = self._dataset(
                        self.timing_engine, dataset_path, "timing_v4", d, trial, full=True
                    )
                    for algorithm in trial_algorithms:
                        point = operating[(algorithm, d)]
                        arguments = self._arguments(
                            algorithm, "timing_v4", d, trial, int(point["resource"])
                        )
                        for repetition in range(const.TIMING_REPETITIONS):
                            identity = "%s-rep%d" % (point["candidate_id"], repetition)
                            if self.checkpoints.load("timing", algorithm, d, identity, trial):
                                continue
                            result = self._run_engine(
                                self.timing_engine, algorithm, dataset_path, arguments
                            )
                            self.checkpoints.save(self._row(
                                stage="timing", algorithm=algorithm, d=d, trial=trial,
                                candidate_id=identity, resource=int(point["resource"]),
                                dataset=dataset, seeds=seeds, result=result,
                                repetition=repetition, cpu_affinity=0,
                            ))
                            print(
                                "v4 timing %s d=%d dataset=%d repetition=%d: %s" % (
                                    algorithm, d, trial, repetition, result.failure_reason
                                ),
                                flush=True,
                            )

        rows = self.checkpoints.rows("timing")
        attempts = timing_attempt_records(rows)
        summaries = self._timing_summary(rows)
        atomic_jsonl(self.path / "timing.jsonl", rows)
        atomic_jsonl(self.path / "timing_attempts.jsonl", attempts)
        atomic_json(self.path / "timing_summary.json", {
            "estimand": "E[runtime | decode success]",
            "successful_datasets_target_per_point": const.TIMING_DATASETS,
            "points": summaries,
        })
        self._aggregate(summaries)
        self._transition("timing_running", "complete")
        return self.path

    def _aggregate(self, timing_summaries: Sequence[Mapping[str, Any]]) -> None:
        parent_rows = _read(self.parent / "aggregate.json")["points"]
        parent = {(row["algorithm"], int(row["d"])): row for row in parent_rows}
        timing = {(row["algorithm"], int(row["d"])): row for row in timing_summaries}
        confirmation_rows = self.checkpoints.rows("sealed_confirmation")
        confirmation = {
            (row["algorithm"], int(row["d"])): row
            for row in _read(self.path / "confirmation_summary.json")["points"]
        }
        operating = self._operating()
        points = []
        for d in const.DIFFERENCES:
            for algorithm in const.ALGORITHMS:
                key = (algorithm, d)
                if algorithm not in CHANGED_ALGORITHMS:
                    row = dict(parent[key])
                    row.update({
                        "protocol_version": const.PROTOCOL_VERSION,
                        "probability_reused": True,
                        "timing_reused": True,
                    })
                    points.append(row)
                    continue

                if algorithm == "external_iblt":
                    row = dict(parent[key])
                    cells = actual_external_cells(int(row["resource"]))
                    state_bits = ((cells * 87 + 7) // 8) * 8
                    row.update({
                        "protocol_version": const.PROTOCOL_VERSION,
                        "state_bits": state_bits,
                        "control_bits": 0,
                        "total_payload_bits": state_bits,
                        "R_w30": state_bits / (30.0 * d),
                        "probability_reused": True,
                        "timing_reused": False,
                        **timing[key],
                    })
                    points.append(row)
                    continue

                summary = confirmation[key]
                point = operating[key]
                successful_rows = [
                    row for row in confirmation_rows
                    if row["algorithm"] == algorithm and int(row["d"]) == d
                    and row["success"] is True
                ]
                if summary["status"] == "confirmed":
                    state_bits = _mean_or_int([
                        float(row["state_bits"]) for row in successful_rows
                    ])
                    total_bits = state_bits
                    rate = total_bits / (30.0 * d)
                else:
                    state_bits = total_bits = rate = None
                points.append({
                    **summary,
                    "protocol_version": const.PROTOCOL_VERSION,
                    "candidate_id": point["candidate_id"],
                    "resource": point["resource"],
                    "state_bits": state_bits,
                    "control_bits": 0 if state_bits is not None else None,
                    "total_payload_bits": total_bits,
                    "R_w30": rate,
                    "probability_reused": False,
                    "timing_reused": False,
                    **timing[key],
                })
        migration = {
            "protocol_version": const.PROTOCOL_VERSION,
            "parent_aggregate_sha256": self.config["parent_aggregate_sha256"],
            "migrated_algorithms": list(MIGRATED_ALGORITHMS),
            "external_iblt_probability_reused": True,
            "external_iblt_payload_transform": "128_to_87_bits_per_cell",
            "riblt_probability_reused": False,
        }
        atomic_json(self.path / "migration_manifest.json", migration)
        aggregate = {
            "protocol_version": const.PROTOCOL_VERSION,
            "kind": "figure2-v4-wire-correction",
            "payload_estimand": "E[algorithm-owned payload bits | decode success]",
            "timing_estimand": "E[runtime | decode success]",
            "migration_manifest_sha256": sha256_file(self.path / "migration_manifest.json"),
            "timing_summary_sha256": sha256_file(self.path / "timing_summary.json"),
            "points": points,
        }
        atomic_json(self.path / "aggregate.json", aggregate)

    def run_all(self) -> Path:
        state = _read(self.path / "run_state.json")["status"]
        if state in {"created", "discovery_running"}:
            self.run_discovery()
        state = _read(self.path / "run_state.json")["status"]
        if state in {"discovery_complete", "confirmation_running"}:
            self.run_confirmation()
        state = _read(self.path / "run_state.json")["status"]
        if state in {"confirmation_complete", "timing_running"}:
            self.run_timing()
        return self.path
