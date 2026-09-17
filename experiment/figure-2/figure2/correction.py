"""Protocol-v3 payload correction and timing-only rerun."""

import json
import statistics
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import constants as const
from .artifacts import (
    atomic_json,
    atomic_jsonl,
    canonical_sha256,
    sha256_file,
    source_tree_sha256,
)
from .config import load_frozen
from .engine import Figure2Engines
from .formal import (
    Checkpoints,
    FormalRunner,
    TIMING_STATISTICAL_FAILURES,
    next_timing_trial,
    timing_attempt_records,
    validate_worker_policy,
)
from .statistics import percentile_bootstrap


CORRECTION_KIND = "figure2-v3-payload-correction-and-timing-rerun"
TIMING_FIELDS = (
    "timing_status",
    "estimand",
    "attempted_datasets",
    "failed_datasets",
    "successful_datasets",
    "successful_datasets_target",
    "update_ns_per_input_conditional_mean",
    "update_ci_low",
    "update_ci_high",
    "decode_ns_per_difference_conditional_mean",
    "decode_ci_low",
    "decode_ci_high",
)


def _read(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _operating_points(source: Path, parent: Path) -> List[Dict[str, Any]]:
    rows = _read(source / "operating_points_discovery.json")["operating_points"]
    by_key = {(str(row["algorithm"]), int(row["d"])): dict(row) for row in rows}
    refined = parent / "refined_operating_points.json"
    if refined.exists():
        for row in _read(refined)["points"]:
            key = str(row["algorithm"]), int(row["d"])
            by_key[key] = {**by_key[key], **row}
    expected = {(algorithm, d) for d in const.DIFFERENCES for algorithm in const.ALGORITHMS}
    if set(by_key) != expected:
        raise ValueError("operating-point source does not cover the registered grid")
    return [by_key[(algorithm, d)] for d in const.DIFFERENCES for algorithm in const.ALGORITHMS]


def corrected_payload(algorithm: str, state_bits: float) -> Tuple[float, float]:
    control_bits = 328.0 if algorithm == "cpisync" else 0.0
    return control_bits, state_bits + control_bits


def migrate_points(
    parent_aggregate: Mapping[str, Any], operating: Sequence[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    operating_map = {
        (str(row["algorithm"]), int(row["d"])): row for row in operating
    }
    points = []
    for source in parent_aggregate["points"]:
        row = dict(source)
        key = str(row["algorithm"]), int(row["d"])
        selected = operating_map[key]
        row.update({
            "protocol_version": const.PROTOCOL_VERSION,
            "resource": int(selected["resource"]),
            "candidate_id": str(selected["candidate_id"]),
            "probability_reused": True,
        })
        for field in TIMING_FIELDS:
            row.pop(field, None)
        if row.get("status") == "confirmed":
            state_bits = float(row["state_bits"])
            control_bits, payload_bits = corrected_payload(key[0], state_bits)
            row.update({
                "control_bits": int(control_bits),
                "total_payload_bits": int(payload_bits)
                if payload_bits.is_integer() else payload_bits,
                "R_w30": payload_bits / (30.0 * key[1]),
                "timing_status": "pending_v3_rerun",
            })
        else:
            row.update({
                "state_bits": None,
                "control_bits": None,
                "total_payload_bits": None,
                "R_w30": None,
                "timing_status": "not_run_not_confirmed",
            })
        points.append(row)
    expected_order = [
        (algorithm, d) for d in const.DIFFERENCES for algorithm in const.ALGORITHMS
    ]
    if [(row["algorithm"], row["d"]) for row in points] != expected_order:
        raise ValueError("parent aggregate point order differs from the registered grid")
    return points


class CorrectionRunner:
    @classmethod
    def create(
        cls,
        *,
        parent_run: Path,
        operating_source_run: Path,
        implementation_dir: Path,
        limits_path: Path,
        results_root: Path,
    ) -> Path:
        parent = parent_run.resolve()
        operating_source = operating_source_run.resolve()
        implementation = implementation_dir.resolve()
        limits_file = limits_path.resolve()
        parent_aggregate_path = parent / "aggregate.json"
        required = (
            parent_aggregate_path,
            parent / "refinement_manifest.json",
            operating_source / "operating_points_discovery.json",
            implementation / "profile_manifest.json",
            implementation / "wire_golden_results.json",
            implementation / "equivalence_golden_results.json",
            implementation / "build_manifest.json",
            limits_file,
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("missing correction input: %s" % ", ".join(missing))
        profiles = _read(implementation / "profile_manifest.json")
        if profiles.get("protocol_version") != const.PROTOCOL_VERSION:
            raise ValueError("implementation profile is not protocol v3")
        old_profile_path = const.EXPERIMENT_DIR / "implementation" / "profile_manifest.json"
        old_config = _read(operating_source / "run_config.json")
        if sha256_file(old_profile_path) != old_config["profile_manifest_sha256"]:
            raise ValueError("parent implementation profile no longer matches the source run")
        old_profiles = _read(old_profile_path)
        profile_continuity = {
            algorithm: {
                "old": old_profiles["profiles"][algorithm]["profile_hash"],
                "new": profiles["profiles"][algorithm]["profile_hash"],
            }
            for algorithm in const.ALGORITHMS
        }
        if any(row["old"] != row["new"] for row in profile_continuity.values()):
            raise ValueError("core profile hashes changed; probability artifacts cannot be reused")
        golden = _read(implementation / "wire_golden_results.json")
        riblt_golden = golden["tests"]["riblt"]
        if riblt_golden.get("encoder_sketch_equivalent") is not True \
                or int(riblt_golden.get("encoder_sketch_equivalence_cases", 0)) != 18:
            raise ValueError("RIBLT fixed-cap API equivalence evidence is missing")
        build = _read(implementation / "build_manifest.json")
        if build.get("core_algorithm_modified") is not False:
            raise ValueError("core algorithm modification is not permitted")
        limits = _read(limits_file)
        validate_worker_policy(limits)
        operating = _operating_points(operating_source, parent)
        parent_aggregate = _read(parent_aggregate_path)
        points = migrate_points(parent_aggregate, operating)
        executable_sha = {
            name: sha256_file(path)
            for name, path in const.EXECUTABLES.items()
        }
        config = {
            "protocol_version": const.PROTOCOL_VERSION,
            "kind": CORRECTION_KIND,
            "authorization_basis": "user_direct_correction_and_rerun",
            "parent_run": str(parent),
            "parent_aggregate_sha256": sha256_file(parent_aggregate_path),
            "parent_refinement_manifest_sha256": sha256_file(parent / "refinement_manifest.json"),
            "operating_source_run": str(operating_source),
            "operating_points_sha256": sha256_file(
                operating_source / "operating_points_discovery.json"
            ),
            "implementation_dir": str(implementation),
            "profile_manifest_sha256": sha256_file(implementation / "profile_manifest.json"),
            "golden_results_sha256": sha256_file(implementation / "wire_golden_results.json"),
            "equivalence_results_sha256": sha256_file(
                implementation / "equivalence_golden_results.json"
            ),
            "build_manifest_sha256": sha256_file(implementation / "build_manifest.json"),
            "figure2_source_tree_sha256": source_tree_sha256(const.EXPERIMENT_DIR),
            "executable_sha256": executable_sha,
            "resource_limits": limits,
            "set_size_A": const.SET_SIZE,
            "set_size_B": const.SET_SIZE,
            "timing_successful_datasets_target": const.TIMING_DATASETS,
            "timing_repetitions": const.TIMING_REPETITIONS,
            "timing_warmups": 0,
            "timing_bootstraps": const.TIMING_BOOTSTRAPS,
            "timing_estimand": "conditional_mean_given_decode_success",
        }
        config_sha = canonical_sha256(config)
        timestamp = subprocess.run(
            ["date", "-u", "+%Y%m%dT%H%M%SZ"], check=True,
            stdout=subprocess.PIPE, text=True,
        ).stdout.strip()
        path = results_root.resolve() / (
            "figure2-v3-correction-%s-%s" % (timestamp, config_sha[:12])
        )
        path.mkdir(parents=True, exist_ok=False)
        atomic_json(path / "run_config.json", config)
        atomic_json(path / "profile_manifest.json", profiles)
        atomic_json(path / "operating_points.json", {"points": operating})
        migration = {
            "status": "passed",
            "protocol_version": const.PROTOCOL_VERSION,
            "probability_trials_rerun": False,
            "probability_reuse_scope": "statuses, success counts, intervals, and selected resources",
            "profile_hash_continuity": profile_continuity,
            "payload_transform": {
                "xyz": "state_bits",
                "minisketch": "state_bits",
                "external_iblt": "state_bits",
                "project_iblt": "state_bits",
                "riblt": "state_bits",
                "cpisync": "state_bits + 328 upstream control bits",
            },
            "riblt_encoder_sketch_equivalence_cases": 18,
            "core_algorithm_modified": False,
            "parent_aggregate_sha256": config["parent_aggregate_sha256"],
            "new_source_tree_sha256": config["figure2_source_tree_sha256"],
            "new_executable_sha256": executable_sha,
        }
        atomic_json(path / "migration_manifest.json", migration)
        migrated = {
            "protocol_version": const.PROTOCOL_VERSION,
            "kind": CORRECTION_KIND,
            "payload_estimand": "E[algorithm-owned payload bits | decode success]",
            "probability_source_aggregate_sha256": config["parent_aggregate_sha256"],
            "migration_manifest_sha256": sha256_file(path / "migration_manifest.json"),
            "points": points,
        }
        atomic_json(path / "migrated_probability_aggregate.json", migrated)
        atomic_json(path / "aggregate.json", migrated)
        atomic_json(path / "run_state.json", {"sequence": 0, "status": "timing_pending"})
        (path / "errors.log").touch(exist_ok=False)
        return path

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.config = _read(self.path / "run_config.json")
        if self.config.get("protocol_version") != const.PROTOCOL_VERSION \
                or self.config.get("kind") != CORRECTION_KIND:
            raise ValueError("not a protocol-v3 correction run")
        if source_tree_sha256(const.EXPERIMENT_DIR) != self.config["figure2_source_tree_sha256"]:
            raise ValueError("Figure 2 source tree changed after correction run creation")
        for name, expected in self.config["executable_sha256"].items():
            if sha256_file(const.EXECUTABLES[name]) != expected:
                raise ValueError("executable changed after correction run creation: %s" % name)
        profile_path = self.path / "profile_manifest.json"
        if sha256_file(profile_path) != self.config["profile_manifest_sha256"]:
            raise ValueError("profile manifest changed after correction run creation")
        self.profiles = _read(profile_path)
        self.limits = self.config["resource_limits"]
        self.worker_policy = validate_worker_policy(self.limits)
        self.frozen, _ = load_frozen()
        self.memory_limit_bytes = int(float(self.limits["memory_limit_gib"]) * (1024 ** 3))
        timing_cpu = int(self.worker_policy["timing"]["physical_cpu_affinity"][0])
        self.engines = Figure2Engines(
            cpu_affinity=timing_cpu, memory_limit_bytes=self.memory_limit_bytes,
        )
        self.checkpoints = Checkpoints(self.path)
        self.helper = object.__new__(FormalRunner)
        self.helper.path = self.path
        self.helper.limits = self.limits
        self.helper.worker_policy = self.worker_policy
        self.helper.profiles = self.profiles
        self.helper.frozen = self.frozen
        self.helper.memory_limit_bytes = self.memory_limit_bytes
        self.helper.engines = self.engines
        self.helper.checkpoints = self.checkpoints
        self.points = _read(self.path / "migrated_probability_aggregate.json")["points"]
        self.operating = {
            (str(row["algorithm"]), int(row["d"])): row
            for row in _read(self.path / "operating_points.json")["points"]
        }

    def _state(self, status: str, **extra: Any) -> None:
        current = _read(self.path / "run_state.json")
        atomic_json(self.path / "run_state.json", {
            "sequence": int(current["sequence"]) + 1,
            "status": status,
            **extra,
        })

    def _resource_failures(self) -> Dict[str, Tuple[int, str]]:
        failures: Dict[str, Tuple[int, str]] = {}
        for row in self.checkpoints.rows("timing"):
            reason = row.get("failure_reason")
            if reason not in {"timeout", "oom"}:
                continue
            algorithm, d = str(row["algorithm"]), int(row["d"])
            if algorithm not in failures or d < failures[algorithm][0]:
                failures[algorithm] = d, str(reason)
        return failures

    def _summaries(self) -> List[Dict[str, Any]]:
        attempts = timing_attempt_records(self.checkpoints.rows("timing"))
        failures = self._resource_failures()
        confirmed = {
            (str(row["algorithm"]), int(row["d"])): row.get("status") == "confirmed"
            for row in self.points
        }
        summaries = []
        for d in const.DIFFERENCES:
            for algorithm in const.ALGORITHMS:
                point_attempts = [
                    row for row in attempts
                    if row["algorithm"] == algorithm and int(row["d"]) == d
                    and row["status"] != "incomplete"
                ]
                successful = [row for row in point_attempts if row["status"] == "successful"]
                if not confirmed[(algorithm, d)]:
                    status = "not_run_not_confirmed"
                elif algorithm in failures and d == failures[algorithm][0]:
                    status = failures[algorithm][1]
                elif algorithm in failures and d > failures[algorithm][0]:
                    status = "not_run_after_resource_limit"
                elif len(successful) == const.TIMING_DATASETS:
                    status = "complete"
                else:
                    status = "incomplete"
                plottable = status == "complete"
                updates = [float(row["update_ns_per_input"]) for row in successful] if plottable else []
                decodes = [float(row["decode_ns_per_difference"]) for row in successful] if plottable else []
                update_ci = percentile_bootstrap(
                    updates,
                    seed_material="figure2_v3_timing_bootstrap|%s|%d|update" % (algorithm, d),
                    estimator="mean",
                ) if updates else (None, None)
                decode_ci = percentile_bootstrap(
                    decodes,
                    seed_material="figure2_v3_timing_bootstrap|%s|%d|decode" % (algorithm, d),
                    estimator="mean",
                ) if decodes else (None, None)
                summaries.append({
                    "algorithm": algorithm,
                    "d": d,
                    "timing_status": status,
                    "estimand": "conditional_mean_given_decode_success",
                    "attempted_datasets": len(point_attempts),
                    "failed_datasets": len(point_attempts) - len(successful),
                    "successful_datasets": len(successful),
                    "successful_datasets_target": const.TIMING_DATASETS,
                    "update_ns_per_input_conditional_mean": statistics.fmean(updates) if updates else None,
                    "update_ci_low": update_ci[0],
                    "update_ci_high": update_ci[1],
                    "decode_ns_per_difference_conditional_mean": statistics.fmean(decodes) if decodes else None,
                    "decode_ci_low": decode_ci[0],
                    "decode_ci_high": decode_ci[1],
                })
        return summaries

    def run_timing(self) -> Path:
        state = _read(self.path / "run_state.json")["status"]
        if state == "timing_pending":
            self._state("timing_running")
        elif state == "complete":
            return self.path
        elif state != "timing_running":
            raise RuntimeError("correction timing is not runnable from state %s" % state)
        confirmed = {
            (str(row["algorithm"]), int(row["d"])): row.get("status") == "confirmed"
            for row in self.points
        }
        with tempfile.TemporaryDirectory(prefix="figure2-v3-timing-") as temporary:
            dataset_path = Path(temporary) / "dataset.bin"
            for d in const.DIFFERENCES:
                while True:
                    failures = self._resource_failures()
                    attempts = timing_attempt_records(self.checkpoints.rows("timing"))
                    by_algorithm = {
                        algorithm: [
                            row for row in attempts
                            if row["algorithm"] == algorithm and int(row["d"]) == d
                        ]
                        for algorithm in const.ALGORITHMS
                    }
                    pending = [
                        algorithm for algorithm in const.ALGORITHMS
                        if confirmed[(algorithm, d)]
                        and not (algorithm in failures and d >= failures[algorithm][0])
                        and sum(row["status"] == "successful" for row in by_algorithm[algorithm])
                        < const.TIMING_DATASETS
                    ]
                    if not pending:
                        break
                    next_trials = {
                        algorithm: next_timing_trial(by_algorithm[algorithm])
                        for algorithm in pending
                    }
                    trial = min(next_trials.values())
                    active = [algorithm for algorithm in pending if next_trials[algorithm] == trial]
                    dataset, seeds = self.helper._dataset(
                        self.engines, dataset_path, "timing", d, trial, full=True
                    )
                    for algorithm in active:
                        point = self.operating[(algorithm, d)]
                        arguments = self.helper._arguments(
                            algorithm, d, trial, "timing", int(point["resource"])
                        )
                        stop_reason: Optional[str] = None
                        for repetition in range(const.TIMING_REPETITIONS):
                            identity = "%s-v3-rep%d" % (point["candidate_id"], repetition)
                            if self.checkpoints.load("timing", algorithm, d, identity, trial):
                                continue
                            if stop_reason is None:
                                result, terminal = self.helper._safe_engine(
                                    self.engines, algorithm, dataset_path, arguments
                                )
                            else:
                                result, terminal = None, (
                                    "not_run_after_resource_limit"
                                    if stop_reason in {"timeout", "oom"}
                                    else "not_run_after_process_error"
                                )
                            if result is not None and not result.success \
                                    and result.failure_reason not in TIMING_STATISTICAL_FAILURES:
                                terminal = "process_error"
                            row = self.helper._result_row(
                                stage="timing", domain="timing", algorithm=algorithm,
                                d=d, trial=trial, candidate_id=identity,
                                resource=int(point["resource"]), dataset=dataset,
                                seeds=seeds, result=result, terminal_status=terminal,
                                repetition=repetition, cpu_affinity=self.engines.cpu_affinity,
                            )
                            self.checkpoints.save(row)
                            print(
                                "v3 timing %s d=%d dataset=%d repetition=%d: %s" % (
                                    algorithm, d, trial, repetition,
                                    row.get("failure_reason", "unknown"),
                                ),
                                flush=True,
                            )
                            if terminal in {"timeout", "oom", "process_error"}:
                                stop_reason = str(terminal)
                        if stop_reason == "process_error":
                            self._state(
                                "failed", failure_reason="process_error",
                                failed_algorithm=algorithm, failed_d=d,
                            )
                            raise RuntimeError("v3 timing process error: %s d=%d" % (algorithm, d))
        timing = self.checkpoints.rows("timing")
        attempts = timing_attempt_records(timing)
        summaries = self._summaries()
        if any(row["timing_status"] == "incomplete" for row in summaries):
            raise RuntimeError("v3 timing ended with incomplete confirmed points")
        atomic_jsonl(self.path / "timing.jsonl", timing)
        atomic_jsonl(self.path / "timing_attempts.jsonl", attempts)
        atomic_json(self.path / "timing_summary.json", {
            "estimand": "E[runtime | decode success]",
            "successful_datasets_target_per_point": const.TIMING_DATASETS,
            "points": summaries,
        })
        timing_map = {(row["algorithm"], int(row["d"])): row for row in summaries}
        merged_points = []
        for point in self.points:
            row = dict(point)
            row.update(timing_map[(row["algorithm"], int(row["d"]))])
            merged_points.append(row)
        aggregate = {
            "protocol_version": const.PROTOCOL_VERSION,
            "kind": CORRECTION_KIND,
            "payload_estimand": "E[algorithm-owned payload bits | decode success]",
            "timing_estimand": "E[runtime | decode success]",
            "migration_manifest_sha256": sha256_file(self.path / "migration_manifest.json"),
            "timing_summary_sha256": sha256_file(self.path / "timing_summary.json"),
            "points": merged_points,
        }
        atomic_json(self.path / "aggregate.json", aggregate)
        self._state("complete", aggregate_sha256=sha256_file(self.path / "aggregate.json"))
        return self.path
