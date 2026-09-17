"""Targeted operating-point refinement after a sealed-confirmation miss."""

import json
import math
import statistics
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import constants as const
from .artifacts import atomic_json, atomic_jsonl, canonical_sha256, sha256_file
from .config import coarse_candidates, load_frozen
from .engine import Figure2Engines
from .formal import Checkpoints, FormalRunner, timing_attempt_records
from .statistics import percentile_bootstrap, wilson


REFINEMENT_PROTOCOL = "figure2-operating-point-refinement-v1"
TARGETS = (
    ("project_iblt", 100),
    ("external_iblt", 1_000),
    ("xyz", 3_000),
    ("xyz", 10_000),
    ("external_iblt", 10_000),
    ("xyz", 30_000),
    ("external_iblt", 100_000),
)


def _read(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _candidate_sequence(
    source: Path, algorithm: str, d: int, selected_resource: int
) -> List[Dict[str, Any]]:
    fine_path = source / "fine_manifests" / algorithm / ("d%07d.json" % d)
    fine = _read(fine_path)["candidates"]
    candidates = [dict(row, phase="fine") for row in fine]
    candidates.extend(dict(row, phase="coarse") for row in coarse_candidates(algorithm, d))
    by_resource: Dict[int, Dict[str, Any]] = {}
    for row in candidates:
        resource = int(row["resource"])
        if resource > selected_resource and resource not in by_resource:
            by_resource[resource] = row
    return [by_resource[resource] for resource in sorted(by_resource)]


def build_refinement_plan(source_run: Path) -> Dict[str, Any]:
    source = source_run.resolve()
    if _read(source / "run_state.json").get("status") != "complete":
        raise ValueError("refinement requires a complete source run")
    aggregate = _read(source / "aggregate.json")
    points = {(row["algorithm"], int(row["d"])): row for row in aggregate["points"]}
    operating = {
        (row["algorithm"], int(row["d"])): row
        for row in _read(source / "operating_points_discovery.json")["operating_points"]
    }
    targets = []
    for algorithm, d in TARGETS:
        point = points[(algorithm, d)]
        if point.get("status") != "confirmation_failed":
            raise ValueError("refinement target is not a confirmation failure: %s d=%d" % (algorithm, d))
        selected = operating[(algorithm, d)]
        candidates = _candidate_sequence(source, algorithm, d, int(selected["resource"]))
        if not candidates:
            raise ValueError("refinement target has no larger preregistered candidate")
        targets.append({
            "algorithm": algorithm,
            "d": d,
            "original_resource": int(selected["resource"]),
            "original_candidate_id": selected["candidate_id"],
            "original_confirmation_successes": int(point["successes"]),
            "candidates": candidates,
        })
    return {
        "protocol_version": REFINEMENT_PROTOCOL,
        "source_run": str(source),
        "source_aggregate_sha256": sha256_file(source / "aggregate.json"),
        "policy": (
            "after confirmation failure, test successively larger preregistered resources "
            "on independent 100-trial blocks and stop at the first block with at least 90 successes"
        ),
        "confirmation_trials_per_candidate": const.CONFIRMATION_TRIALS,
        "timing_successful_datasets": const.TIMING_DATASETS,
        "timing_repetitions_per_dataset": const.TIMING_REPETITIONS,
        "targets": targets,
    }


class RefinementRunner:
    def __init__(
        self,
        *,
        source_run: Path,
        results_root: Path,
        resume: Optional[Path] = None,
    ) -> None:
        self.source = source_run.resolve()
        self.plan = build_refinement_plan(self.source)
        self.source_config = _read(self.source / "run_config.json")
        self.limits = self.source_config["resource_limits"]
        for algorithm, expected in self.source_config["gate"]["executable_sha256"].items():
            if sha256_file(const.EXECUTABLES[algorithm]) != expected:
                raise ValueError("executable differs from the source formal run: %s" % algorithm)
        profile_path = const.EXPERIMENT_DIR / "implementation" / "profile_manifest.json"
        if sha256_file(profile_path) != self.source_config["profile_manifest_sha256"]:
            raise ValueError("profile manifest differs from the source formal run")
        self.profiles = _read(profile_path)
        self.frozen, frozen_sha = load_frozen()
        if frozen_sha != self.source_config["gate"]["frozen_parameters_sha256"]:
            raise ValueError("frozen parameters differ from the source formal run")

        config = {
            **self.plan,
            "source_run_config_sha256": sha256_file(self.source / "run_config.json"),
            "source_confirmation_summary_sha256": sha256_file(self.source / "confirmation_summary.json"),
            "source_timing_summary_sha256": sha256_file(self.source / "timing_summary.json"),
            "executable_sha256": self.source_config["gate"]["executable_sha256"],
            "profile_manifest_sha256": self.source_config["profile_manifest_sha256"],
            "worker_policy": self.limits["worker_policy"],
        }
        self.config_sha = canonical_sha256(config)
        if resume is None:
            timestamp = subprocess.run(
                ["date", "-u", "+%Y%m%dT%H%M%SZ"], check=True,
                stdout=subprocess.PIPE, text=True,
            ).stdout.strip()
            self.path = results_root.resolve() / (
                "figure2-refinement-%s-%s" % (timestamp, self.config_sha[:12])
            )
            self.path.mkdir(parents=True, exist_ok=False)
            atomic_json(self.path / "run_config.json", config)
            atomic_json(self.path / "run_state.json", {"sequence": 0, "status": "confirmation_running"})
        else:
            self.path = resume.resolve()
            if _read(self.path / "run_config.json") != config:
                raise ValueError("refinement resume configuration differs")
        self.checkpoints = Checkpoints(self.path)
        self.helper = object.__new__(FormalRunner)
        self.helper.path = self.path
        self.helper.limits = self.limits
        self.helper.worker_policy = self.limits["worker_policy"]
        self.helper.profiles = self.profiles
        self.helper.frozen = self.frozen
        self.helper.memory_limit_bytes = int(float(self.limits["memory_limit_gib"]) * (1024 ** 3))
        self.helper.checkpoints = self.checkpoints
        timing_cpu = int(self.limits["worker_policy"]["timing"]["physical_cpu_affinity"][0])
        self.helper.engines = Figure2Engines(
            cpu_affinity=timing_cpu,
            memory_limit_bytes=self.helper.memory_limit_bytes,
        )

    def _state(self, status: str, **extra: Any) -> None:
        current = _read(self.path / "run_state.json")
        atomic_json(self.path / "run_state.json", {
            "sequence": int(current["sequence"]) + 1,
            "status": status,
            **extra,
        })

    def _target_key(self, row: Mapping[str, Any]) -> Tuple[str, int]:
        return str(row["algorithm"]), int(row["d"])

    def _candidate_for_attempt(self, target: Mapping[str, Any], attempt: int) -> Dict[str, Any]:
        candidates = target["candidates"]
        if attempt >= len(candidates):
            raise RuntimeError(
                "larger preregistered candidates exhausted: %s d=%d" % self._target_key(target)
            )
        return dict(candidates[attempt])

    def _confirmation_rows(
        self, algorithm: str, d: int, candidate_id: str
    ) -> List[Dict[str, Any]]:
        return [
            row for row in self.checkpoints.rows("confirmation_refinement")
            if row["algorithm"] == algorithm and int(row["d"]) == d
            and row["candidate_id"] == candidate_id
        ]

    def run_confirmation(self) -> None:
        selected_path = self.path / "refined_operating_points.json"
        selected_rows = _read(selected_path)["points"] if selected_path.exists() else []
        selected = {self._target_key(row): row for row in selected_rows}
        attempts_path = self.path / "confirmation_attempts.json"
        attempt_rows = _read(attempts_path)["attempts"] if attempts_path.exists() else []
        attempts_by_target: Dict[Tuple[str, int], int] = {}
        for row in attempt_rows:
            key = self._target_key(row)
            attempts_by_target[key] = max(attempts_by_target.get(key, 0), int(row["attempt"]) + 1)

        targets = {self._target_key(row): row for row in self.plan["targets"]}
        while len(selected) != len(targets):
            active: Dict[Tuple[str, int], Tuple[Dict[str, Any], int, str]] = {}
            for key, target in targets.items():
                if key in selected:
                    continue
                attempt = attempts_by_target.get(key, 0)
                candidate = self._candidate_for_attempt(target, attempt)
                candidate_id = "retry-%02d-%s-%d" % (
                    attempt + 1, candidate["phase"], int(candidate["resource"])
                )
                active[key] = (candidate, attempt, candidate_id)

            jobs = []
            for d in sorted({key[1] for key in active}):
                for trial in range(const.CONFIRMATION_TRIALS):
                    jobs.append((d, trial))

            def evaluate(engine: Figure2Engines, batch: Sequence[Tuple[int, int]]) -> None:
                with tempfile.TemporaryDirectory(prefix="figure2-refinement-confirmation-") as temporary:
                    dataset_path = Path(temporary) / "dataset.bin"
                    for d, trial in batch:
                        point_jobs = [
                            (key, value) for key, value in active.items() if key[1] == d
                        ]
                        missing = [
                            (key, value) for key, value in point_jobs
                            if self.checkpoints.load(
                                "confirmation_refinement", key[0], d, value[2], trial
                            ) is None
                        ]
                        if not missing:
                            continue
                        attempt = missing[0][1][1]
                        domain = "sealed_confirmation_refinement_%02d" % (attempt + 1)
                        dataset, seeds = self.helper._dataset(
                            engine, dataset_path, domain, d, trial, full=True
                        )
                        for (algorithm, _), (candidate, _, candidate_id) in missing:
                            result, terminal = self.helper._safe_engine(
                                engine, algorithm, dataset_path,
                                self.helper._arguments(
                                    algorithm, d, trial, domain, int(candidate["resource"])
                                ),
                            )
                            self.checkpoints.save(self.helper._result_row(
                                stage="confirmation_refinement",
                                domain=domain,
                                algorithm=algorithm,
                                d=d,
                                trial=trial,
                                candidate_id=candidate_id,
                                resource=int(candidate["resource"]),
                                dataset=dataset,
                                seeds=seeds,
                                result=result,
                                terminal_status=terminal,
                                cpu_affinity=engine.cpu_affinity,
                            ))

            self.helper._parallel_batches("sealed_confirmation", jobs, evaluate)
            for key, (candidate, attempt, candidate_id) in active.items():
                rows = self._confirmation_rows(key[0], key[1], candidate_id)
                if len(rows) != const.CONFIRMATION_TRIALS:
                    raise RuntimeError("refinement confirmation block is incomplete")
                if any(row.get("failure_reason") == "process_error" for row in rows):
                    raise RuntimeError("refinement engine process_error")
                terminal = {row.get("failure_reason") for row in rows} & {"timeout", "oom"}
                successes = sum(bool(row["success"]) for row in rows)
                summary = {
                    "algorithm": key[0],
                    "d": key[1],
                    "attempt": attempt,
                    "candidate_id": candidate_id,
                    "resource": int(candidate["resource"]),
                    "successes": successes,
                    "trials": len(rows),
                    "success_rate": successes / len(rows),
                    "status": "resource_failure" if terminal else (
                        "confirmed" if successes >= 90 else "confirmation_failed"
                    ),
                    "terminal_status": sorted(terminal)[0] if terminal else None,
                }
                attempt_rows.append(summary)
                attempts_by_target[key] = attempt + 1
                if summary["status"] == "confirmed":
                    selected[key] = summary
            ordered_attempts = sorted(
                attempt_rows,
                key=lambda row: (int(row["d"]), str(row["algorithm"]), int(row["attempt"])),
            )
            atomic_json(attempts_path, {"attempts": ordered_attempts})
            atomic_json(selected_path, {"points": sorted(
                selected.values(), key=lambda row: (int(row["d"]), str(row["algorithm"]))
            )})
            atomic_jsonl(
                self.path / "confirmation_refinement.jsonl",
                self.checkpoints.rows("confirmation_refinement"),
            )
            self._state(
                "confirmation_running" if len(selected) != len(targets) else "timing_running",
                confirmed_targets=len(selected),
                total_targets=len(targets),
                confirmation_attempts=len(attempt_rows),
            )

    def run_timing(self) -> None:
        selected = {
            self._target_key(row): row
            for row in _read(self.path / "refined_operating_points.json")["points"]
        }
        with tempfile.TemporaryDirectory(prefix="figure2-refinement-timing-") as temporary:
            dataset_path = Path(temporary) / "dataset.bin"
            for d in sorted({key[1] for key in selected}):
                algorithms = sorted(key[0] for key in selected if key[1] == d)
                while True:
                    rows = self.checkpoints.rows("timing_refinement")
                    attempts = timing_attempt_records(rows)
                    completed = {
                        algorithm: sum(
                            row["algorithm"] == algorithm and int(row["d"]) == d
                            and row["status"] == "successful"
                            for row in attempts
                        )
                        for algorithm in algorithms
                    }
                    pending = [alg for alg in algorithms if completed[alg] < const.TIMING_DATASETS]
                    if not pending:
                        break
                    trial = min(
                        max(
                            [int(row["trial_index"]) for row in attempts
                             if row["algorithm"] == algorithm and int(row["d"]) == d],
                            default=-1,
                        ) + 1
                        for algorithm in pending
                    )
                    domain = "timing_refinement"
                    dataset, seeds = self.helper._dataset(
                        self.helper.engines, dataset_path, domain, d, trial, full=True
                    )
                    for algorithm in pending:
                        point = selected[(algorithm, d)]
                        if any(
                            row["algorithm"] == algorithm and int(row["d"]) == d
                            and int(row["trial_index"]) == trial
                            for row in attempts
                        ):
                            continue
                        stop_reason: Optional[str] = None
                        for repetition in range(const.TIMING_REPETITIONS):
                            identity = "refined-%d-rep%d" % (int(point["resource"]), repetition)
                            if stop_reason is None:
                                result, terminal = self.helper._safe_engine(
                                    self.helper.engines, algorithm, dataset_path,
                                    self.helper._arguments(
                                        algorithm, d, trial, domain, int(point["resource"])
                                    ),
                                )
                                if terminal is not None:
                                    stop_reason = terminal
                            else:
                                result, terminal = None, "not_run_after_resource_limit"
                            self.checkpoints.save(self.helper._result_row(
                                stage="timing_refinement",
                                domain=domain,
                                algorithm=algorithm,
                                d=d,
                                trial=trial,
                                candidate_id=identity,
                                resource=int(point["resource"]),
                                dataset=dataset,
                                seeds=seeds,
                                result=result,
                                terminal_status=terminal,
                                repetition=repetition,
                                cpu_affinity=self.helper.engines.cpu_affinity,
                            ))
                        if stop_reason in {"process_error", "timeout", "oom"}:
                            raise RuntimeError(
                                "refinement timing failed: %s d=%d %s" % (algorithm, d, stop_reason)
                            )
                self._state("timing_running", completed_d=d)

        timing_rows = self.checkpoints.rows("timing_refinement")
        attempts = timing_attempt_records(timing_rows)
        summaries = []
        for key, point in sorted(selected.items(), key=lambda item: (item[0][1], item[0][0])):
            algorithm, d = key
            successful = [
                row for row in attempts
                if row["algorithm"] == algorithm and int(row["d"]) == d
                and row["status"] == "successful"
            ]
            if len(successful) != const.TIMING_DATASETS:
                raise RuntimeError("refinement timing point is incomplete")
            updates = [float(row["update_ns_per_input"]) for row in successful]
            decodes = [float(row["decode_ns_per_difference"]) for row in successful]
            update_ci = percentile_bootstrap(
                updates,
                seed_material="figure2_refinement|%s|%d|update" % key,
                estimator="mean",
            )
            decode_ci = percentile_bootstrap(
                decodes,
                seed_material="figure2_refinement|%s|%d|decode" % key,
                estimator="mean",
            )
            summaries.append({
                "algorithm": algorithm,
                "d": d,
                "timing_status": "complete",
                "estimand": "conditional_mean_given_decode_success",
                "attempted_datasets": len([
                    row for row in attempts if row["algorithm"] == algorithm and int(row["d"]) == d
                ]),
                "failed_datasets": len([
                    row for row in attempts if row["algorithm"] == algorithm and int(row["d"]) == d
                    and row["status"] != "successful"
                ]),
                "successful_datasets": len(successful),
                "successful_datasets_target": const.TIMING_DATASETS,
                "update_ns_per_input_conditional_mean": statistics.fmean(updates),
                "update_ci_low": update_ci[0],
                "update_ci_high": update_ci[1],
                "decode_ns_per_difference_conditional_mean": statistics.fmean(decodes),
                "decode_ci_low": decode_ci[0],
                "decode_ci_high": decode_ci[1],
            })
        atomic_jsonl(self.path / "timing_refinement.jsonl", timing_rows)
        atomic_jsonl(self.path / "timing_attempts.jsonl", attempts)
        atomic_json(self.path / "timing_summary.json", {"points": summaries})

    def finalize(self) -> None:
        source_aggregate = _read(self.source / "aggregate.json")
        points = {
            (row["algorithm"], int(row["d"])): dict(row)
            for row in source_aggregate["points"]
        }
        selected = {
            self._target_key(row): row
            for row in _read(self.path / "refined_operating_points.json")["points"]
        }
        timing = {
            self._target_key(row): row for row in _read(self.path / "timing_summary.json")["points"]
        }
        confirmation_rows = self.checkpoints.rows("confirmation_refinement")
        for key, selected_point in selected.items():
            candidate_rows = [
                row for row in confirmation_rows
                if row["algorithm"] == key[0] and int(row["d"]) == key[1]
                and row["candidate_id"] == selected_point["candidate_id"]
            ]
            successes = [
                row for row in candidate_rows
                if row.get("success") is True and row.get("failure_reason") == "success"
            ]
            count = len(successes)
            interval = wilson(count, len(candidate_rows))
            def mean(field: str) -> Any:
                value = statistics.fmean(int(row[field]) for row in successes)
                return int(value) if value.is_integer() else value
            payload = mean("total_payload_bits")
            points[key].update({
                "trials": len(candidate_rows),
                "successes": count,
                "success_rate": count / len(candidate_rows),
                "ci_low": interval[0],
                "ci_high": interval[1],
                "status": "confirmed",
                "state_bits": mean("state_bits"),
                "control_bits": mean("control_bits"),
                "total_payload_bits": payload,
                "R_w30": payload / (30.0 * key[1]),
                **timing[key],
            })
        merged = {
            **source_aggregate,
            "refinement_protocol": REFINEMENT_PROTOCOL,
            "source_aggregate_sha256": self.plan["source_aggregate_sha256"],
            "points": [points[(row["algorithm"], int(row["d"]))] for row in source_aggregate["points"]],
        }
        atomic_json(self.path / "aggregate.json", merged)
        atomic_json(self.path / "refinement_manifest.json", {
            "status": "complete",
            "protocol_version": REFINEMENT_PROTOCOL,
            "source_run": str(self.source),
            "source_aggregate_sha256": self.plan["source_aggregate_sha256"],
            "aggregate_sha256": sha256_file(self.path / "aggregate.json"),
            "refined_operating_points_sha256": sha256_file(
                self.path / "refined_operating_points.json"
            ),
            "confirmation_refinement_sha256": sha256_file(
                self.path / "confirmation_refinement.jsonl"
            ),
            "timing_refinement_sha256": sha256_file(self.path / "timing_refinement.jsonl"),
        })
        self._state("complete", aggregate_sha256=sha256_file(self.path / "aggregate.json"))

    def run(self) -> Path:
        status = _read(self.path / "run_state.json")["status"]
        if status == "confirmation_running":
            self.run_confirmation()
            status = _read(self.path / "run_state.json")["status"]
        if status == "timing_running":
            if not (self.path / "timing_summary.json").exists():
                self.run_timing()
            self.finalize()
        return self.path
