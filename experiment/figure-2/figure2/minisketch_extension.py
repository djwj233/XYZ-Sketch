"""Timing-only deterministic MiniSketch extension at d=10,000."""

import json
import statistics
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from . import constants as const
from .artifacts import atomic_json, atomic_jsonl, sha256_file, source_tree_sha256
from .config import derive_internal_seed, derive_seed, profile_manifest
from .engine import EngineExecutionError, EngineResult, Figure2Engines
from .formal import Checkpoints, next_timing_trial, timing_attempt_records
from .statistics import percentile_bootstrap


ALGORITHM = "minisketch"
D = 10_000
DOMAIN = "timing_minisketch_d10000_extension"
CANDIDATE_ID = "exact-d-deterministic"
TIMEOUT_SECONDS = 3600.0
MEMORY_LIMIT_BYTES = 80 * (1024 ** 3)


def _read(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def deterministic_point(
    source: Mapping[str, Any], timing: Mapping[str, Any]
) -> Dict[str, Any]:
    state_bits = ((D * 30 + 7) // 8) * 8
    return {
        **dict(source),
        "status": "confirmed",
        "probability_basis": "deterministic_exact_bound",
        "success_rate": 1.0,
        "successes": 0,
        "trials": 0,
        "ci_low": None,
        "ci_high": None,
        "candidate_id": CANDIDATE_ID,
        "resource": D,
        "state_bits": state_bits,
        "control_bits": 0,
        "total_payload_bits": state_bits,
        "R_w30": state_bits / (30.0 * D),
        "probability_reused": False,
        "timing_reused": False,
        **dict(timing),
    }


class MiniSketchTimingExtension:
    def __init__(self, run: Path) -> None:
        self.run = run.resolve()
        if _read(self.run / "run_state.json").get("status") != "complete":
            raise ValueError("MiniSketch timing extension requires a complete parent run")
        self.aggregate_path = self.run / "aggregate.json"
        self.extension_root = self.run / "minisketch-d10000-extension"
        self.config_path = self.extension_root / "config.json"
        self.state_path = self.extension_root / "state.json"
        self.errors_path = self.extension_root / "errors.log"
        self.profiles = profile_manifest()
        self.profile_hash = self.profiles["profiles"][ALGORITHM]["profile_hash"]
        self.checkpoints = Checkpoints(self.extension_root)
        self.engine = Figure2Engines(
            cpu_affinity=0, memory_limit_bytes=MEMORY_LIMIT_BYTES
        )

    def _initialize(self) -> Dict[str, Any]:
        if self.config_path.exists():
            config = _read(self.config_path)
            if config["source_tree_sha256"] != source_tree_sha256(const.EXPERIMENT_DIR):
                raise ValueError("Figure 2 source tree changed after MiniSketch extension creation")
            if config["dataset_executable_sha256"] != sha256_file(const.EXECUTABLES["dataset"]):
                raise ValueError("dataset executable changed after MiniSketch extension creation")
            if config["minisketch_executable_sha256"] != sha256_file(
                const.EXECUTABLES[ALGORITHM]
            ):
                raise ValueError("MiniSketch executable changed after extension creation")
            if config["profile_hash"] != self.profile_hash:
                raise ValueError("MiniSketch profile changed after extension creation")
            return config

        aggregate = _read(self.aggregate_path)
        source = next(
            row for row in aggregate["points"]
            if row["algorithm"] == ALGORITHM and int(row["d"]) == D
        )
        if source.get("timing_status") == "complete":
            raise ValueError("MiniSketch d=10,000 timing is already complete")
        config = {
            "status": "created",
            "algorithm": ALGORITHM,
            "d": D,
            "domain": DOMAIN,
            "candidate_id": CANDIDATE_ID,
            "probability_basis": "deterministic_exact_bound",
            "parent_aggregate_sha256": sha256_file(self.aggregate_path),
            "source_tree_sha256": source_tree_sha256(const.EXPERIMENT_DIR),
            "profile_hash": self.profile_hash,
            "dataset_executable_sha256": sha256_file(const.EXECUTABLES["dataset"]),
            "minisketch_executable_sha256": sha256_file(const.EXECUTABLES[ALGORITHM]),
            "set_size_A": const.SET_SIZE,
            "set_size_B": const.SET_SIZE,
            "successful_datasets_target": const.TIMING_DATASETS,
            "repetitions": const.TIMING_REPETITIONS,
            "warmups": 0,
            "cpu_affinity": 0,
            "timeout_seconds": TIMEOUT_SECONDS,
        }
        self.extension_root.mkdir(parents=True, exist_ok=False)
        atomic_json(self.config_path, config)
        atomic_json(self.state_path, {"sequence": 0, "status": "created"})
        self.errors_path.touch(exist_ok=False)
        return config

    def _state(self, status: str) -> None:
        current = _read(self.state_path)
        atomic_json(self.state_path, {
            "sequence": int(current["sequence"]) + 1,
            "status": status,
        })

    @staticmethod
    def _seeds(trial: int) -> Dict[str, int]:
        return {
            role: derive_seed(DOMAIN, D, trial, role)
            for role in ("identity", "alice_order", "bob_order")
        }

    def _run_engine(self, dataset: Path, internal_seed: int) -> EngineResult:
        try:
            return self.engine.run(
                ALGORITHM, dataset, internal_seed=internal_seed,
                timeout=TIMEOUT_SECONDS,
            )
        except (EngineExecutionError, subprocess.TimeoutExpired) as error:
            with self.errors_path.open("a", encoding="utf-8") as stream:
                stream.write("%s\n" % error)
            raise

    def _row(
        self, *, trial: int, repetition: int, dataset: Mapping[str, Any],
        seeds: Mapping[str, int], result: EngineResult,
    ) -> Dict[str, Any]:
        return {
            "protocol_version": "figure2-v4-minisketch-d10000-extension",
            "stage": "timing_extension",
            "domain": DOMAIN,
            "algorithm": ALGORITHM,
            "d": D,
            "trial_index": trial,
            "candidate_id": "%s-rep%d" % (CANDIDATE_ID, repetition),
            "resource": D,
            "profile_hash": self.profile_hash,
            "dataset": dict(dataset),
            "dataset_seeds": dict(seeds),
            "cpu_affinity": 0,
            "repetition": repetition,
            "success": result.success,
            "failure_reason": result.failure_reason,
            "terminal_status": None,
            "logical_state_bits": result.logical_state_bits,
            "state_bits": result.state_bits,
            "control_bits": result.control_bits,
            "total_payload_bits": result.total_payload_bits,
            "R_w30": result.total_payload_bits / (30.0 * D),
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

    @staticmethod
    def _summary(attempts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        successful = [row for row in attempts if row["status"] == "successful"]
        if len(successful) != const.TIMING_DATASETS:
            raise RuntimeError("MiniSketch extension lacks five successful datasets")
        updates = [float(row["update_ns_per_input"]) for row in successful]
        decodes = [float(row["decode_ns_per_difference"]) for row in successful]
        update_ci = percentile_bootstrap(
            updates, seed_material=DOMAIN + "|update", estimator="mean"
        )
        decode_ci = percentile_bootstrap(
            decodes, seed_material=DOMAIN + "|decode", estimator="mean"
        )
        return {
            "algorithm": ALGORITHM,
            "d": D,
            "timing_status": "complete",
            "estimand": "conditional_mean_given_decode_success",
            "attempted_datasets": len(attempts),
            "failed_datasets": len(attempts) - len(successful),
            "successful_datasets": len(successful),
            "successful_datasets_target": const.TIMING_DATASETS,
            "update_ns_per_input_conditional_mean": statistics.fmean(updates),
            "update_ci_low": update_ci[0],
            "update_ci_high": update_ci[1],
            "decode_ns_per_difference_conditional_mean": statistics.fmean(decodes),
            "decode_ci_low": decode_ci[0],
            "decode_ci_high": decode_ci[1],
        }

    def _merge(self, summary: Mapping[str, Any]) -> None:
        aggregate = _read(self.aggregate_path)
        replaced = 0
        points = []
        for row in aggregate["points"]:
            if row["algorithm"] == ALGORITHM and int(row["d"]) == D:
                points.append(deterministic_point(row, summary))
                replaced += 1
            else:
                points.append(row)
        if replaced != 1:
            raise RuntimeError("MiniSketch extension aggregate replacement is not unique")
        aggregate["points"] = points
        aggregate["minisketch_d10000_extension_config_sha256"] = sha256_file(
            self.config_path
        )
        atomic_json(self.aggregate_path, aggregate)

        timing_path = self.run / "timing_summary.json"
        timing = _read(timing_path)
        timing["points"] = [
            dict(summary) if row["algorithm"] == ALGORITHM and int(row["d"]) == D
            else row
            for row in timing["points"]
        ]
        atomic_json(timing_path, timing)

        migration_path = self.run / "migration_manifest.json"
        migration = _read(migration_path)
        migration.update({
            "minisketch_d10000_probability_basis": "deterministic_exact_bound",
            "minisketch_d10000_extension_config_sha256": sha256_file(self.config_path),
        })
        atomic_json(migration_path, migration)

    def _update_artifact_manifest(self) -> None:
        manifest_path = self.run / "artifact_manifest.json"
        if not manifest_path.exists():
            return
        manifest = _read(manifest_path)
        for name in (
            "aggregate.json", "timing_summary.json", "migration_manifest.json"
        ):
            manifest["files"][name] = sha256_file(self.run / name)
        manifest["minisketch_d10000_extension"] = {
            name: sha256_file(self.extension_root / name)
            for name in (
                "config.json", "state.json", "timing.jsonl",
                "timing_attempts.jsonl", "timing_summary.json",
            )
        }
        atomic_json(manifest_path, manifest)

    def run_timing(self) -> Path:
        self._initialize()
        state = _read(self.state_path)["status"]
        if state == "created":
            self._state("timing_running")
        elif state == "complete":
            return self.run
        elif state != "timing_running":
            raise RuntimeError("MiniSketch extension is not runnable")

        with tempfile.TemporaryDirectory(
            prefix="figure2-minisketch-d10000-timing-"
        ) as temporary:
            dataset_path = Path(temporary) / "dataset.bin"
            while True:
                rows = self.checkpoints.rows("timing_extension")
                attempts = timing_attempt_records(rows)
                successful = [row for row in attempts if row["status"] == "successful"]
                if len(successful) >= const.TIMING_DATASETS:
                    break
                trial = next_timing_trial(attempts)
                seeds = self._seeds(trial)
                dataset = self.engine.create_dataset(
                    dataset_path, full=True, d=D, set_size=const.SET_SIZE,
                    identity_seed=seeds["identity"], alice_seed=seeds["alice_order"],
                    bob_seed=seeds["bob_order"],
                )
                internal_seed = derive_internal_seed(
                    DOMAIN, D, trial, ALGORITHM, self.profile_hash, "primary"
                )
                for repetition in range(const.TIMING_REPETITIONS):
                    identity = "%s-rep%d" % (CANDIDATE_ID, repetition)
                    if self.checkpoints.load(
                        "timing_extension", ALGORITHM, D, identity, trial
                    ):
                        continue
                    result = self._run_engine(dataset_path, internal_seed)
                    self.checkpoints.save(self._row(
                        trial=trial, repetition=repetition, dataset=dataset,
                        seeds=seeds, result=result,
                    ))
                    print(
                        "MiniSketch d=10000 timing dataset=%d repetition=%d: %s" % (
                            trial, repetition, result.failure_reason
                        ),
                        flush=True,
                    )

        rows = self.checkpoints.rows("timing_extension")
        attempts = timing_attempt_records(rows)
        for row in attempts:
            row["protocol_version"] = "figure2-v4-minisketch-d10000-extension"
            row["domain"] = DOMAIN
        summary = self._summary(attempts)
        atomic_jsonl(self.extension_root / "timing.jsonl", rows)
        atomic_jsonl(self.extension_root / "timing_attempts.jsonl", attempts)
        atomic_json(self.extension_root / "timing_summary.json", {"points": [summary]})
        self._merge(summary)
        self._state("complete")
        self._update_artifact_manifest()
        return self.run
