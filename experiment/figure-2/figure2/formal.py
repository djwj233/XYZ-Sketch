import json
import math
import statistics
import subprocess
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import constants as const
from .artifacts import (
    atomic_json,
    atomic_jsonl,
    canonical_sha256,
    sha256_file,
    source_tree_sha256,
)
from .config import (
    coarse_candidates,
    derive_internal_seed,
    derive_seed,
    load_frozen,
    possible_fine_candidates,
    profile_manifest,
)
from .engine import EngineExecutionError, EngineResult, Figure2Engines
from .statistics import percentile_bootstrap, wilson


def _read(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


PARALLEL_STAGES = ("resource_discovery", "sealed_confirmation")
WORKER_STAGES = PARALLEL_STAGES + ("timing",)
TIMING_STATISTICAL_FAILURES = frozenset({"decode_failed", "wrong_output"})
PROBABILITY_NONSTATISTICAL_FAILURES = frozenset({"process_error", "timeout", "oom"})
PROCESS_ERROR_LABELS = frozenset({"process_error", "not_run_after_process_error"})


def timing_attempt_record(
    rows: Sequence[Mapping[str, Any]],
    repetitions: int = const.TIMING_REPETITIONS,
) -> Dict[str, Any]:
    by_repetition: Dict[int, Mapping[str, Any]] = {}
    for row in rows:
        repetition = row.get("repetition")
        if not isinstance(repetition, int) or not 0 <= repetition < repetitions:
            raise RuntimeError("timing row has an invalid repetition index")
        if repetition in by_repetition:
            raise RuntimeError("timing attempt has a duplicate repetition")
        by_repetition[repetition] = row
    complete = set(by_repetition) == set(range(repetitions))
    fatal = any(
        row.get("failure_reason") in PROCESS_ERROR_LABELS
        or row.get("terminal_status") in PROCESS_ERROR_LABELS
        for row in by_repetition.values()
    )
    successful = not fatal and complete and all(
        row.get("success") is True
        and row.get("failure_reason") == "success"
        and all(
            isinstance(row.get(field), (int, float)) and float(row[field]) >= 0.0
            for field in ("update_alice_cpu", "update_bob_cpu", "decode_cpu")
        )
        for row in by_repetition.values()
    )
    record: Dict[str, Any] = {
        "status": (
            "fatal" if fatal else
            ("successful" if successful else ("failed" if complete else "incomplete"))
        ),
        "measured_repetitions": len(by_repetition),
        "successful_repetitions": sum(
            row.get("success") is True and row.get("failure_reason") == "success"
            for row in by_repetition.values()
        ),
        "failure_reasons": sorted({
            str(row.get("failure_reason"))
            for row in by_repetition.values()
            if row.get("success") is not True or row.get("failure_reason") != "success"
        }),
    }
    if successful:
        ordered = [by_repetition[index] for index in range(repetitions)]
        record.update({
            "update_ns_per_input": statistics.fmean(
                (float(row["update_alice_cpu"]) + float(row["update_bob_cpu"])) * 1e9
                / (2 * const.SET_SIZE)
                for row in ordered
            ),
            "decode_ns_per_difference": statistics.fmean(
                float(row["decode_cpu"]) * 1e9 / int(row["d"])
                for row in ordered
            ),
        })
    return record


def timing_attempt_records(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, int, int], List[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["algorithm"]), int(row["d"]), int(row["trial_index"]))].append(row)
    records = []
    for (algorithm, d, trial), attempt_rows in sorted(grouped.items()):
        record = timing_attempt_record(attempt_rows)
        record.update({
            "protocol_version": const.PROTOCOL_VERSION,
            "domain": "timing",
            "algorithm": algorithm,
            "d": d,
            "trial_index": trial,
            "resource": attempt_rows[0].get("resource"),
            "dataset_seeds": attempt_rows[0].get("dataset_seeds"),
        })
        records.append(record)
    return records


def next_timing_trial(records: Sequence[Mapping[str, Any]]) -> int:
    if any(row.get("status") == "fatal" for row in records):
        raise RuntimeError("fatal timing attempt cannot be retried")
    completed = {
        int(row["trial_index"])
        for row in records
        if row.get("status") in {"successful", "failed"}
    }
    trial = 0
    while trial in completed:
        trial += 1
    return trial


def validate_worker_policy(limits: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    policy = limits.get("worker_policy")
    if not isinstance(policy, dict) or set(policy) != set(WORKER_STAGES):
        raise ValueError("formal worker policy must cover discovery, confirmation, and timing")
    validated: Dict[str, Dict[str, Any]] = {}
    for stage in WORKER_STAGES:
        row = policy[stage]
        if not isinstance(row, dict) or set(row) != {"workers", "physical_cpu_affinity"}:
            raise ValueError("invalid worker policy for %s" % stage)
        workers = row["workers"]
        cpus = row["physical_cpu_affinity"]
        if not isinstance(workers, int) or workers <= 0:
            raise ValueError("worker count must be a positive integer")
        if not isinstance(cpus, list) or len(cpus) != workers or any(
            not isinstance(cpu, int) or cpu < 0 for cpu in cpus
        ) or len(set(cpus)) != len(cpus):
            raise ValueError("CPU affinity list must contain one distinct CPU per worker")
        validated[stage] = {"workers": workers, "physical_cpu_affinity": list(cpus)}
    if validated["timing"]["workers"] != 1:
        raise ValueError("formal timing must use exactly one worker")
    expected = {
        "resource_discovery": list(range(8)),
        "sealed_confirmation": list(range(8)),
        "timing": [0],
    }
    for stage, cpus in expected.items():
        if validated[stage]["workers"] != len(cpus) \
                or validated[stage]["physical_cpu_affinity"] != cpus:
            raise ValueError("formal %s worker policy differs from the frozen CPU list" % stage)
    return validated


def worker_batches(items: Sequence[Any], cpus: Sequence[int]) -> List[Tuple[int, Tuple[Any, ...]]]:
    if not cpus:
        raise ValueError("at least one worker CPU is required")
    return [
        (cpu, tuple(items[index::len(cpus)]))
        for index, cpu in enumerate(cpus)
        if index < len(items)
    ]


def validate_machine_affinity(policy: Mapping[str, Mapping[str, Any]]) -> None:
    output = subprocess.run(
        ["lscpu", "--parse=CPU,CORE,SOCKET,ONLINE"], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout
    topology = {}
    for line in output.splitlines():
        if not line or line.startswith("#"):
            continue
        cpu_text, core_text, socket_text, online = line.split(",")
        if online == "Y":
            topology[int(cpu_text)] = (int(socket_text), int(core_text))
    for stage, row in policy.items():
        cpus = row["physical_cpu_affinity"]
        if any(cpu not in topology for cpu in cpus):
            raise ValueError("worker policy references an offline or missing CPU")
        cores = [topology[cpu] for cpu in cpus]
        if len(set(cores)) != len(cores):
            raise ValueError("worker policy assigns sibling threads of one physical core")


def validate_audited_executables(
    build_manifest: Mapping[str, Any],
    executables: Mapping[str, Path] = const.EXECUTABLES,
) -> Dict[str, str]:
    audited = build_manifest.get("executables")
    if not isinstance(audited, dict) or set(audited) != set(executables):
        raise ValueError("audited executable manifest is incomplete")
    hashes = {}
    for name, configured_path in executables.items():
        path = configured_path.resolve()
        row = audited[name]
        if not isinstance(row, dict) or Path(str(row.get("path", ""))).resolve() != path:
            raise ValueError("audited executable path differs: %s" % name)
        if not path.is_file():
            raise ValueError("audited executable is missing: %s" % name)
        actual = sha256_file(path)
        if row.get("sha256") != actual:
            raise ValueError("audited executable hash differs: %s" % name)
        hashes[name] = actual
    return hashes


def validate_formal_gate(
    implementation_dir: Path,
    implementation_audit: Path,
    limits_path: Path,
    frozen_path: Path,
    holdout_path: Path,
) -> Dict[str, Any]:
    summary_path = implementation_dir / "implementation_summary.json"
    summary = _read(summary_path)
    if summary.get("status") != "implementation_ready_for_audit" \
            or summary.get("formal_trials_executed") is not False:
        raise ValueError("implementation artifact is not ready for audit")
    for name, expected in summary["artifacts"].items():
        if sha256_file(implementation_dir / name) != expected:
            raise ValueError("implementation artifact hash mismatch: %s" % name)
    build_manifest_path = implementation_dir / "build_manifest.json"
    build_manifest = _read(build_manifest_path)
    current_source_tree_sha256 = source_tree_sha256(const.EXPERIMENT_DIR)
    if build_manifest.get("figure2_source_tree_sha256") != current_source_tree_sha256:
        raise ValueError("audited Figure 2 source-tree hash differs")
    executable_hashes = validate_audited_executables(build_manifest)
    audit = _read(implementation_audit)
    if audit.get("status") != "implementation_audited" \
            or audit.get("implementation_summary_sha256") != sha256_file(summary_path):
        raise ValueError("independent implementation audit has not passed")
    limits = _read(limits_path)
    required_limits = {"worker_policy", "memory_limit_gib", "timeout_seconds"}
    if required_limits - set(limits):
        raise ValueError("formal resource limits are incomplete")
    if limits.get("status") != "approved":
        raise ValueError("formal resource limits have not been approved")
    if set(limits["timeout_seconds"]) != set(const.ALGORITHMS):
        raise ValueError("formal timeout map must cover every algorithm")
    worker_policy = validate_worker_policy(limits)
    validate_machine_affinity(worker_policy)
    if float(limits["memory_limit_gib"]) <= 0:
        raise ValueError("formal memory limit is invalid")
    if any(float(value) <= 0 for value in limits["timeout_seconds"].values()):
        raise ValueError("formal timeout must be positive")
    frozen, frozen_sha = load_frozen(frozen_path)
    holdout = _read(holdout_path / "holdout_summary.json")
    if holdout.get("status") != "complete" or not holdout.get("downstream_experiments_unlocked") \
            or holdout.get("frozen_parameters_sha256") != frozen_sha:
        raise ValueError("sealed holdout gate is closed")
    return {
        "status": "passed",
        "implementation_summary_sha256": sha256_file(summary_path),
        "implementation_audit_sha256": sha256_file(implementation_audit),
        "build_manifest_sha256": sha256_file(build_manifest_path),
        "figure2_source_tree_sha256": current_source_tree_sha256,
        "executable_sha256": executable_hashes,
        "limits_sha256": sha256_file(limits_path),
        "frozen_parameters_sha256": frozen_sha,
        "holdout_summary_sha256": sha256_file(holdout_path / "holdout_summary.json"),
    }


class Checkpoints:
    def __init__(self, root: Path) -> None:
        self.root = root / "checkpoints"

    def path(self, stage: str, algorithm: str, d: int, identity: str, trial: int) -> Path:
        return self.root / stage / algorithm / ("d%07d" % d) / identity / ("trial-%09d.json" % trial)

    def load(self, stage: str, algorithm: str, d: int, identity: str, trial: int) -> Optional[Dict[str, Any]]:
        path = self.path(stage, algorithm, d, identity, trial)
        return _read(path) if path.exists() else None

    def save(self, row: Mapping[str, Any]) -> None:
        path = self.path(
            str(row["stage"]), str(row["algorithm"]), int(row["d"]),
            str(row["candidate_id"]), int(row["trial_index"]),
        )
        if path.exists():
            if _read(path) != dict(row):
                raise RuntimeError("checkpoint collision")
            return
        atomic_json(path, dict(row))

    def rows(self, stage: str) -> List[Dict[str, Any]]:
        path = self.root / stage
        return [_read(item) for item in sorted(path.rglob("trial-*.json"))] if path.exists() else []


class FormalRunner:
    def __init__(
        self,
        *,
        results_root: Path,
        implementation_dir: Path,
        implementation_audit: Path,
        limits_path: Path,
        frozen_path: Path = const.DEFAULT_FROZEN,
        holdout_path: Path = const.DEFAULT_HOLDOUT,
        resume: Optional[Path] = None,
    ) -> None:
        self.implementation_dir = implementation_dir.resolve()
        self.limits = _read(limits_path.resolve())
        self.worker_policy = validate_worker_policy(self.limits)
        self.gate = validate_formal_gate(
            self.implementation_dir, implementation_audit.resolve(), limits_path.resolve(),
            frozen_path.resolve(), holdout_path.resolve(),
        )
        self.profiles = _read(self.implementation_dir / "profile_manifest.json")
        self.frozen, self.frozen_sha = load_frozen(frozen_path.resolve())
        self.memory_limit_bytes = int(float(self.limits["memory_limit_gib"]) * (1024 ** 3))
        self.engines = self._engine_for_cpu(
            int(self.worker_policy["timing"]["physical_cpu_affinity"][0])
        )
        self.config = {
            "protocol_version": const.PROTOCOL_VERSION,
            "kind": "formal_figure2",
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
            "timing_statistical_retry_limit": None,
            "figure2_source_tree_sha256": self.gate["figure2_source_tree_sha256"],
            "profile_manifest_sha256": sha256_file(self.implementation_dir / "profile_manifest.json"),
            "candidate_budget_sha256": sha256_file(self.implementation_dir / "candidate_budget.json"),
            "gate": self.gate,
            "resource_limits": self.limits,
            "presentation": None,
            "presentation_affects_trials": False,
        }
        self.config_sha = canonical_sha256(self.config)
        if resume is None:
            timestamp = subprocess.run(
                ["date", "-u", "+%Y%m%dT%H%M%SZ"], check=True,
                stdout=subprocess.PIPE, text=True,
            ).stdout.strip()
            path = results_root.resolve() / ("figure2-%s-%s" % (timestamp, self.config_sha[:12]))
            path.mkdir(parents=True, exist_ok=False)
            self.path = path
            atomic_json(path / "run_config.json", self.config)
            atomic_json(path / "run_state.json", {"sequence": 0, "status": "created"})
            atomic_json(path / "formal_gate.json", self.gate)
            (path / "errors.log").touch(exist_ok=False)
        else:
            self.path = resume.resolve()
            if _read(self.path / "run_config.json") != self.config:
                raise ValueError("resume configuration differs")
            if _read(self.path / "run_state.json").get("status") == "failed":
                raise RuntimeError("cannot resume a failed formal run")
        self.checkpoints = Checkpoints(self.path)

    def _transition(self, expected: str, new: str, **extra: Any) -> None:
        state = _read(self.path / "run_state.json")
        if state["status"] != expected:
            raise RuntimeError("expected state %s, found %s" % (expected, state["status"]))
        atomic_json(self.path / "run_state.json", {
            "sequence": int(state["sequence"]) + 1, "status": new, **extra,
        })

    def _timeout(self, algorithm: str) -> float:
        return float(self.limits["timeout_seconds"][algorithm])

    def _engine_for_cpu(self, cpu: int) -> Figure2Engines:
        return Figure2Engines(cpu_affinity=cpu, memory_limit_bytes=self.memory_limit_bytes)

    def _parallel_batches(self, stage: str, items: Sequence[Any], function: Any) -> None:
        cpus = self.worker_policy[stage]["physical_cpu_affinity"]
        batches = worker_batches(items, cpus)
        with ThreadPoolExecutor(max_workers=len(batches)) as pool:
            futures = [
                pool.submit(function, self._engine_for_cpu(cpu), batch)
                for cpu, batch in batches
            ]
            for future in futures:
                future.result()

    def _dataset(
        self, engine: Figure2Engines, path: Path, domain: str, d: int, trial: int, full: bool
    ) -> Tuple[Dict[str, Any], Dict[str, int]]:
        seeds = {
            role: derive_seed(domain, d, trial, role)
            for role in ("identity", "alice_order", "bob_order")
        }
        manifest = engine.create_dataset(
            path, full=full, d=d, set_size=const.SET_SIZE if full else 0,
            identity_seed=seeds["identity"], alice_seed=seeds["alice_order"],
            bob_seed=seeds["bob_order"],
        )
        return manifest, seeds

    def _arguments(
        self, algorithm: str, d: int, trial: int, domain: str, resource: Optional[int]
    ) -> Dict[str, Any]:
        profile_hash = self.profiles["profiles"][algorithm]["profile_hash"]
        internal = derive_internal_seed(domain, d, trial, algorithm, profile_hash, "primary")
        if algorithm == "xyz":
            a = float(self.profiles["profiles"]["xyz"]["a"])
            z_raw = float(self.frozen["gamma_cal"]) * (1.0 - a) ** (2.0 / 3.0) * resource ** (1.0 / 3.0)
            return {"resource": resource, "a": a, "z": math.floor(z_raw + 0.5), "internal_seed": internal}
        if algorithm == "minisketch":
            return {"internal_seed": internal}
        if algorithm in {"external_iblt", "project_iblt"}:
            return {"resource": resource}
        if algorithm == "riblt":
            return {
                "resource": resource,
                "siphash_k0": derive_internal_seed(domain, d, trial, algorithm, profile_hash, "siphash_k0"),
                "siphash_k1": derive_internal_seed(domain, d, trial, algorithm, profile_hash, "siphash_k1"),
                "internal_seed": internal,
            }
        return {}

    def _result_row(
        self,
        *,
        stage: str,
        domain: str,
        algorithm: str,
        d: int,
        trial: int,
        candidate_id: str,
        resource: Optional[int],
        dataset: Mapping[str, Any],
        seeds: Mapping[str, int],
        result: Optional[EngineResult],
        terminal_status: Optional[str] = None,
        repetition: Optional[int] = None,
        cpu_affinity: Optional[int] = None,
    ) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "protocol_version": const.PROTOCOL_VERSION,
            "stage": stage,
            "domain": domain,
            "algorithm": algorithm,
            "profile_hash": self.profiles["profiles"][algorithm]["profile_hash"],
            "d": d,
            "trial_index": trial,
            "candidate_id": candidate_id,
            "resource": resource,
            "repetition": repetition,
            "cpu_affinity": cpu_affinity,
            "dataset": dict(dataset),
            "dataset_seeds": dict(seeds),
            "terminal_status": terminal_status,
        }
        if result is None:
            row.update({"success": False, "failure_reason": terminal_status})
        else:
            row.update({
                "success": result.success,
                "failure_reason": result.failure_reason,
                "logical_state_bits": result.logical_state_bits,
                "state_bits": result.state_bits,
                "control_bits": result.control_bits,
                "total_payload_bits": result.total_payload_bits,
                "R_w30": result.total_payload_bits / (30.0 * d),
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
            })
        return row

    def _safe_engine(
        self, engine: Figure2Engines, algorithm: str, dataset_path: Path,
        arguments: Mapping[str, Any], *, discover_riblt: bool = False,
    ) -> Tuple[Optional[EngineResult], Optional[str]]:
        try:
            result = engine.run(
                algorithm, dataset_path, timeout=self._timeout(algorithm),
                discover_riblt=discover_riblt, **arguments
            )
            return result, ("process_error" if
                            not result.success and result.failure_reason == "process_error"
                            else None)
        except subprocess.TimeoutExpired:
            return None, "timeout"
        except EngineExecutionError as error:
            lowered = error.stderr.lower()
            if error.returncode in {-9, 137} or any(
                marker in lowered for marker in ("bad_alloc", "out of memory", "cannot allocate")
            ):
                return None, "oom"
            return None, "process_error"
        except (OSError, RuntimeError, ValueError):
            return None, "process_error"

    @staticmethod
    def _rate(rows: Sequence[Mapping[str, Any]]) -> float:
        failures = {
            str(row.get("failure_reason")) for row in rows
            if row.get("failure_reason") in PROBABILITY_NONSTATISTICAL_FAILURES
        }
        if failures:
            raise RuntimeError(
                "non-statistical failure cannot enter a probability rate: %s" %
                ",".join(sorted(failures))
            )
        if not rows:
            raise ValueError("probability rate requires rows")
        return sum(bool(row["success"]) for row in rows) / len(rows)

    @staticmethod
    def _resource_failure(rows: Sequence[Mapping[str, Any]]) -> Optional[str]:
        failures = {str(row.get("failure_reason")) for row in rows}
        if "oom" in failures:
            return "oom"
        if "timeout" in failures:
            return "timeout"
        return None

    def _raise_on_process_error(
        self, rows: Sequence[Mapping[str, Any]], stage: str
    ) -> None:
        failures = [
            row for row in rows
            if row.get("failure_reason") in PROCESS_ERROR_LABELS
            or row.get("terminal_status") in PROCESS_ERROR_LABELS
        ]
        if not failures:
            return
        first = failures[0]
        message = (
            "%s process_error: algorithm=%s d=%s trial=%s candidate=%s" % (
                stage, first.get("algorithm"), first.get("d"), first.get("trial_index"),
                first.get("candidate_id"),
            )
        )
        with (self.path / "errors.log").open("a", encoding="utf-8") as stream:
            stream.write(message + "\n")
        state = _read(self.path / "run_state.json")
        if state.get("status") != "failed":
            atomic_json(self.path / "run_state.json", {
                "sequence": int(state["sequence"]) + 1,
                "status": "failed",
                "failure_reason": "process_error",
                "failed_stage": stage,
            })
        raise RuntimeError(message)

    @classmethod
    def _confirmation_point_summary(
        cls, rows: Sequence[Mapping[str, Any]], algorithm: str, d: int
    ) -> Dict[str, Any]:
        if any(row.get("failure_reason") == "process_error" for row in rows):
            raise RuntimeError("process_error invalidates sealed confirmation")
        valid = [row for row in rows if row.get("failure_reason") not in {
            "resource_out_of_grid", "not_run_after_resource_limit"
        }]
        successes = sum(bool(row["success"]) for row in valid)
        resource_failure = cls._resource_failure(valid)
        if resource_failure is not None:
            return {
                "algorithm": algorithm, "d": d, "trials": len(valid),
                "successes": successes, "success_rate": None,
                "ci_low": None, "ci_high": None, "status": resource_failure,
            }
        if valid:
            rate = cls._rate(valid)
            interval = wilson(successes, len(valid))
            status = "confirmed" if rate >= 0.9 else "confirmation_failed"
        else:
            rate = None
            interval = (None, None)
            status = str(rows[0]["failure_reason"]) if rows else "missing"
        return {
            "algorithm": algorithm, "d": d, "trials": len(valid),
            "successes": successes, "success_rate": rate,
            "ci_low": interval[0], "ci_high": interval[1], "status": status,
        }

    @staticmethod
    def _candidate_payload_bits(rows: Sequence[Mapping[str, Any]]) -> int:
        successful = [row for row in rows if bool(row.get("success"))]
        if not successful:
            raise ValueError("passing candidate has no successful accounting row")
        accounting = {
            (
                int(row["logical_state_bits"]), int(row["state_bits"]),
                int(row["control_bits"]), int(row["total_payload_bits"]),
            )
            for row in successful
        }
        if len(accounting) != 1:
            raise RuntimeError("candidate wire accounting differs across successful trials")
        logical, state, control, total = next(iter(accounting))
        if state + control != total or logical > state:
            raise RuntimeError("candidate wire accounting is invalid")
        return total

    @staticmethod
    def _mean_payload_accounting(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        successful = [
            row for row in rows
            if row.get("success") is True and row.get("failure_reason") == "success"
        ]
        if not successful:
            raise ValueError("confirmed point has no successful accounting row")
        for row in successful:
            logical = int(row["logical_state_bits"])
            state = int(row["state_bits"])
            control = int(row["control_bits"])
            total = int(row["total_payload_bits"])
            if state + control != total or logical > state:
                raise RuntimeError("confirmation wire accounting is invalid")

        def mean(field: str) -> Any:
            value = statistics.fmean(int(row[field]) for row in successful)
            return int(value) if value.is_integer() else value

        return {
            "state_bits": mean("state_bits"),
            "control_bits": mean("control_bits"),
            "total_payload_bits": mean("total_payload_bits"),
        }

    @classmethod
    def _aggregate_points(
        cls,
        confirmation_points: Sequence[Mapping[str, Any]],
        confirmation_rows: Sequence[Mapping[str, Any]],
        timing_summaries: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        timing_map = {
            (row["algorithm"], row["d"]): row for row in timing_summaries
        }
        aggregate = []
        for point in confirmation_points:
            key = (point["algorithm"], point["d"])
            if key not in timing_map:
                raise RuntimeError("timing summary is missing a registered point")
            payload_rows = [
                row for row in confirmation_rows
                if (row["algorithm"], row["d"]) == key
                and row.get("success") is True
                and row.get("failure_reason") == "success"
                and row.get("total_payload_bits") is not None
            ]
            if point["status"] == "confirmed":
                accounting = cls._mean_payload_accounting(payload_rows)
                state_bits = accounting["state_bits"]
                control_bits = accounting["control_bits"]
                payload_bits = accounting["total_payload_bits"]
            else:
                payload_bits = None
                state_bits = None
                control_bits = None
            aggregate.append({
                **point,
                "state_bits": state_bits,
                "control_bits": control_bits,
                "total_payload_bits": payload_bits,
                "R_w30": payload_bits / (30.0 * point["d"])
                if payload_bits is not None else None,
                **timing_map[key],
            })
        return {
            "payload_estimand": "E[actual payload bits | decode success]",
            "payload_aggregation": "arithmetic_mean_over_successful_confirmation_trials",
            "points": aggregate,
        }

    def _evaluate_discovery_candidates(
        self, algorithm: str, d: int, candidates: Sequence[Mapping[str, Any]], phase: str
    ) -> Optional[str]:
        for candidate in candidates:
            candidate_id = "%s-%d" % (phase, candidate["resource"])
            existing = self._candidate_rows(algorithm, d, candidate_id)
            self._raise_on_process_error(existing, "resource_discovery")
            existing_terminal = self._resource_failure(existing)
            if existing_terminal is not None:
                return existing_terminal
            stop = Event()

            def evaluate(engine: Figure2Engines, trials: Sequence[int]) -> None:
                with tempfile.TemporaryDirectory(prefix="figure2-discovery-") as temporary:
                    dataset_path = Path(temporary) / "dataset.bin"
                    for trial in trials:
                        if stop.is_set():
                            break
                        if self.checkpoints.load(
                            "resource_discovery", algorithm, d, candidate_id, trial
                        ) is not None:
                            continue
                        dataset, seeds = self._dataset(
                            engine, dataset_path, "resource_discovery", d, trial, full=False
                        )
                        result, terminal = self._safe_engine(
                            engine, algorithm, dataset_path,
                            self._arguments(
                                algorithm, d, trial, "resource_discovery", candidate["resource"]
                            ),
                        )
                        self.checkpoints.save(self._result_row(
                            stage="resource_discovery", domain="resource_discovery",
                            algorithm=algorithm, d=d, trial=trial, candidate_id=candidate_id,
                            resource=int(candidate["resource"]), dataset=dataset, seeds=seeds,
                            result=result, terminal_status=terminal,
                            cpu_affinity=engine.cpu_affinity,
                        ))
                        if terminal in PROBABILITY_NONSTATISTICAL_FAILURES:
                            stop.set()
                            break

            self._parallel_batches("resource_discovery", range(const.DISCOVERY_TRIALS), evaluate)
            rows = self._candidate_rows(algorithm, d, candidate_id)
            self._raise_on_process_error(rows, "resource_discovery")
            terminal = self._resource_failure(rows)
            if terminal:
                return terminal
        return None

    def _candidate_rows(self, algorithm: str, d: int, candidate_id: str) -> List[Dict[str, Any]]:
        return [row for row in self.checkpoints.rows("resource_discovery") if
                row["algorithm"] == algorithm and row["d"] == d and row["candidate_id"] == candidate_id]

    def _discover_fixed_sketch(self, algorithm: str, d: int) -> Dict[str, Any]:
        coarse = list(coarse_candidates(algorithm, d))
        terminal = self._evaluate_discovery_candidates(algorithm, d, coarse, "coarse")
        if terminal:
            return {
                "algorithm": algorithm, "d": d, "status": "resource_limit",
                "failure_reason": terminal,
            }
        rates = []
        for candidate in coarse:
            identity = "coarse-%d" % candidate["resource"]
            rows = self._candidate_rows(algorithm, d, identity)
            rates.append((candidate, self._rate(rows)))
        first_pass = next((index for index, (_candidate, rate) in enumerate(rates) if rate >= 0.9), None)
        fine: List[Mapping[str, Any]] = []
        if first_pass is not None and first_pass > 0:
            left = coarse[first_pass - 1]["grid_ratio_units"]
            interval = next(row for row in possible_fine_candidates(algorithm, d)
                            if row["left_ratio_units"] == left)
            fine = list(interval["candidates"])
            atomic_json(self.path / "fine_manifests" / algorithm / ("d%07d.json" % d), {
                "algorithm": algorithm, "d": d, "left_ratio_units": left,
                "right_ratio_units": coarse[first_pass]["grid_ratio_units"], "candidates": fine,
            })
            terminal = self._evaluate_discovery_candidates(algorithm, d, fine, "fine")
            if terminal:
                return {
                    "algorithm": algorithm, "d": d, "status": "resource_limit",
                    "failure_reason": terminal,
                }
        passing = []
        for phase, candidates in (("coarse", coarse), ("fine", fine)):
            for candidate in candidates:
                identity = "%s-%d" % (phase, candidate["resource"])
                rows = self._candidate_rows(algorithm, d, identity)
                rate = self._rate(rows)
                if rate >= 0.9:
                    passing.append((
                        self._candidate_payload_bits(rows), int(candidate["resource"]), rate, identity
                    ))
        if not passing:
            return {"algorithm": algorithm, "d": d, "status": "resource_out_of_grid"}
        bits, resource, rate, candidate_id = min(passing)
        return {
            "algorithm": algorithm, "d": d, "status": "selected",
            "resource": resource, "candidate_id": candidate_id,
            "discovery_success_rate": rate, "total_payload_bits": bits,
        }

    def _discover_riblt(self, d: int) -> Dict[str, Any]:
        algorithm = "riblt"
        maximum = 3 * d
        identity = "required-symbols"
        existing = self._candidate_rows(algorithm, d, identity)
        self._raise_on_process_error(existing, "resource_discovery")
        existing_terminal = self._resource_failure(existing)
        if existing_terminal is not None:
            return {
                "algorithm": algorithm, "d": d, "status": "resource_limit",
                "failure_reason": existing_terminal,
            }
        stop = Event()
        def evaluate(engine: Figure2Engines, trials: Sequence[int]) -> None:
            with tempfile.TemporaryDirectory(prefix="figure2-riblt-discovery-") as temporary:
                dataset_path = Path(temporary) / "dataset.bin"
                for trial in trials:
                    if stop.is_set():
                        break
                    if self.checkpoints.load("resource_discovery", algorithm, d, identity, trial):
                        continue
                    dataset, seeds = self._dataset(
                        engine, dataset_path, "resource_discovery", d, trial, full=False
                    )
                    arguments = self._arguments(
                        algorithm, d, trial, "resource_discovery", maximum
                    )
                    result, terminal = self._safe_engine(
                        engine, algorithm, dataset_path, arguments, discover_riblt=True
                    )
                    self.checkpoints.save(self._result_row(
                        stage="resource_discovery", domain="resource_discovery", algorithm=algorithm,
                        d=d, trial=trial, candidate_id=identity, resource=maximum,
                        dataset=dataset, seeds=seeds, result=result, terminal_status=terminal,
                        cpu_affinity=engine.cpu_affinity,
                    ))
                    if terminal in PROBABILITY_NONSTATISTICAL_FAILURES:
                        stop.set()
                        break

        self._parallel_batches("resource_discovery", range(const.DISCOVERY_TRIALS), evaluate)
        rows = self._candidate_rows(algorithm, d, identity)
        self._raise_on_process_error(rows, "resource_discovery")
        terminal = self._resource_failure(rows)
        if terminal:
            return {
                "algorithm": algorithm, "d": d, "status": "resource_limit",
                "failure_reason": terminal,
            }
        required = sorted(int(row.get("required_symbols", maximum + 1)) for row in rows)
        cap = required[89]
        return ({"algorithm": algorithm, "d": d, "status": "selected", "resource": cap,
                 "candidate_id": "q90", "required_symbols_sorted": required}
                if cap <= maximum else
                {"algorithm": algorithm, "d": d, "status": "resource_out_of_grid"})

    def run_discovery(self) -> Path:
        state = _read(self.path / "run_state.json")["status"]
        if state == "created": self._transition("created", "discovery_running")
        elif state != "discovery_running": raise RuntimeError("discovery state is not active")
        operating = []
        resource_limited: Dict[str, str] = {}
        for d in const.DIFFERENCES:
            for algorithm in ("xyz", "external_iblt", "project_iblt"):
                if algorithm in resource_limited:
                    point = {
                        "algorithm": algorithm, "d": d,
                        "status": "not_run_after_resource_limit",
                        "failure_reason": resource_limited[algorithm],
                    }
                else:
                    point = self._discover_fixed_sketch(algorithm, d)
                    if point["status"] == "resource_limit":
                        resource_limited[algorithm] = str(point["failure_reason"])
                operating.append(point)
            if "riblt" in resource_limited:
                riblt_point = {
                    "algorithm": "riblt", "d": d,
                    "status": "not_run_after_resource_limit",
                    "failure_reason": resource_limited["riblt"],
                }
            else:
                riblt_point = self._discover_riblt(d)
                if riblt_point["status"] == "resource_limit":
                    resource_limited["riblt"] = str(riblt_point["failure_reason"])
            operating.append(riblt_point)
            operating.append({"algorithm": "minisketch", "d": d, "status": "selected", "resource": d, "candidate_id": "exact-d"})
            operating.append({"algorithm": "cpisync", "d": d, "status": "selected", "resource": d, "candidate_id": "mbar-d"})
        atomic_json(self.path / "operating_points_discovery.json", {
            "status": "discovery_complete", "operating_points": operating,
        })
        atomic_jsonl(self.path / "resource_discovery.jsonl", self.checkpoints.rows("resource_discovery"))
        self._transition("discovery_running", "discovery_complete")
        return self.path

    def _operating_map(self) -> Dict[Tuple[str, int], Dict[str, Any]]:
        rows = _read(self.path / "operating_points_discovery.json")["operating_points"]
        return {(row["algorithm"], row["d"]): row for row in rows}

    def run_confirmation(self) -> Path:
        state = _read(self.path / "run_state.json")["status"]
        if state == "discovery_complete": self._transition("discovery_complete", "confirmation_running")
        elif state != "confirmation_running": raise RuntimeError("confirmation state is not active")
        operating = self._operating_map()
        existing_confirmation = self.checkpoints.rows("sealed_confirmation")
        self._raise_on_process_error(existing_confirmation, "sealed_confirmation")
        resource_limited: Dict[str, str] = {}
        for d in const.DIFFERENCES:
            existing = self.checkpoints.rows("sealed_confirmation")
            for algorithm in const.ALGORITHMS:
                prior_failures = {
                    str(row["failure_reason"]) for row in existing
                    if row["algorithm"] == algorithm and row["d"] < d
                    and row.get("failure_reason") in {"timeout", "oom"}
                }
                if prior_failures:
                    resource_limited[algorithm] = "oom" if "oom" in prior_failures else "timeout"
            limited_before_d = frozenset(resource_limited)
            resource_stops = {algorithm: Event() for algorithm in const.ALGORITHMS}
            for algorithm in const.ALGORITHMS:
                operating_point = operating[(algorithm, d)]
                if operating_point["status"] == "resource_limit":
                    reason = str(operating_point["failure_reason"])
                    if reason not in {"timeout", "oom"}:
                        raise RuntimeError("invalid discovery resource-limit reason")
                    resource_stops[algorithm].set()
                    resource_limited[algorithm] = reason
                current_failures = {
                    str(row["failure_reason"]) for row in existing
                    if row["algorithm"] == algorithm and row["d"] == d
                    and row.get("failure_reason") in {"timeout", "oom"}
                }
                if current_failures:
                    resource_stops[algorithm].set()
                    resource_limited[algorithm] = (
                        "oom" if "oom" in current_failures else "timeout"
                    )
            fatal_stop = Event()

            def evaluate(engine: Figure2Engines, trials: Sequence[int]) -> None:
                with tempfile.TemporaryDirectory(prefix="figure2-confirmation-") as temporary:
                    dataset_path = Path(temporary) / "dataset.bin"
                    for trial in trials:
                        if fatal_stop.is_set():
                            break
                        missing = []
                        for algorithm in const.ALGORITHMS:
                            if algorithm in limited_before_d or resource_stops[algorithm].is_set():
                                continue
                            point = operating[(algorithm, d)]
                            candidate_id = str(point.get("candidate_id", point["status"]))
                            if not self.checkpoints.load(
                                "sealed_confirmation", algorithm, d, candidate_id, trial
                            ):
                                missing.append((algorithm, point, candidate_id))
                        if not missing:
                            continue
                        dataset, seeds = self._dataset(
                            engine, dataset_path, "sealed_confirmation", d, trial, full=True
                        )
                        for algorithm, point, candidate_id in missing:
                            if fatal_stop.is_set():
                                break
                            if resource_stops[algorithm].is_set():
                                continue
                            if point["status"] != "selected":
                                terminal = point["status"]
                                result = None
                            else:
                                result, terminal = self._safe_engine(
                                    engine, algorithm, dataset_path,
                                    self._arguments(
                                        algorithm, d, trial, "sealed_confirmation", point["resource"]
                                    ),
                                )
                            self.checkpoints.save(self._result_row(
                                stage="sealed_confirmation", domain="sealed_confirmation",
                                algorithm=algorithm, d=d, trial=trial, candidate_id=candidate_id,
                                resource=point.get("resource"), dataset=dataset, seeds=seeds,
                                result=result, terminal_status=terminal,
                                cpu_affinity=engine.cpu_affinity,
                            ))
                            if terminal == "process_error":
                                fatal_stop.set()
                            elif terminal in {"timeout", "oom"}:
                                resource_stops[algorithm].set()

            self._parallel_batches(
                "sealed_confirmation", range(const.CONFIRMATION_TRIALS), evaluate
            )
            completed_d = self.checkpoints.rows("sealed_confirmation")
            self._raise_on_process_error(completed_d, "sealed_confirmation")
            for algorithm in const.ALGORITHMS:
                failures = {
                    str(row["failure_reason"]) for row in completed_d
                    if row["algorithm"] == algorithm and row["d"] == d
                    and row.get("failure_reason") in {"timeout", "oom"}
                }
                if failures:
                    resource_limited[algorithm] = "oom" if "oom" in failures else "timeout"
        confirmation = self.checkpoints.rows("sealed_confirmation")
        summary = []
        for d in const.DIFFERENCES:
            for algorithm in const.ALGORITHMS:
                rows = [row for row in confirmation if row["algorithm"] == algorithm and row["d"] == d]
                point = self._confirmation_point_summary(rows, algorithm, d)
                if point["status"] == "missing":
                    operating_point = operating[(algorithm, d)]
                    if operating_point["status"] == "resource_limit":
                        point["status"] = str(operating_point["failure_reason"])
                    elif operating_point["status"] != "selected":
                        point["status"] = str(operating_point["status"])
                    elif algorithm in resource_limited:
                        point["status"] = "not_run_after_resource_limit"
                summary.append(point)
        atomic_jsonl(self.path / "confirmation.jsonl", confirmation)
        atomic_json(self.path / "confirmation_summary.json", {"points": summary})
        self._transition("confirmation_running", "confirmation_complete")
        return self.path

    def run_timing(self) -> Path:
        state = _read(self.path / "run_state.json")["status"]
        if state == "confirmation_complete": self._transition("confirmation_complete", "timing_running")
        elif state != "timing_running": raise RuntimeError("timing state is not active")
        self._raise_on_process_error(self.checkpoints.rows("timing"), "timing")
        operating = self._operating_map()
        confirmation_points = _read(self.path / "confirmation_summary.json")["points"]
        confirmation_status = {
            (row["algorithm"], row["d"]): str(row["status"])
            for row in confirmation_points
        }
        confirmed = {key: status == "confirmed" for key, status in confirmation_status.items()}
        resource_limited: Dict[str, str] = {}
        point_status: Dict[Tuple[str, int], str] = {}
        with tempfile.TemporaryDirectory(prefix="figure2-timing-") as temporary:
            dataset_path = Path(temporary) / "dataset.bin"
            for d in const.DIFFERENCES:
                for algorithm in const.ALGORITHMS:
                    key = (algorithm, d)
                    status = confirmation_status[key]
                    if status in {"timeout", "oom"}:
                        resource_limited[algorithm] = status
                        point_status[key] = status
                    elif algorithm in resource_limited \
                            or status == "not_run_after_resource_limit":
                        point_status[key] = "not_run_after_resource_limit"
                existing_timing = self.checkpoints.rows("timing")
                for algorithm in const.ALGORITHMS:
                    current_resource_failures = [
                        str(row["failure_reason"])
                        for row in existing_timing
                        if row["algorithm"] == algorithm and row["d"] == d
                        and row.get("failure_reason") in {"timeout", "oom"}
                    ]
                    if current_resource_failures:
                        reason = "oom" if "oom" in current_resource_failures else "timeout"
                        resource_limited[algorithm] = reason
                        point_status[(algorithm, d)] = reason
                    elif algorithm in resource_limited and (algorithm, d) not in point_status:
                        point_status[(algorithm, d)] = "not_run_after_resource_limit"

                # A crash immediately after a timeout row may leave the attempt partial.
                # Complete it from its checkpointed dataset without running the engine again.
                for algorithm in const.ALGORITHMS:
                    if point_status.get((algorithm, d)) not in {"timeout", "oom"}:
                        continue
                    point = operating[(algorithm, d)]
                    algorithm_rows = [
                        row for row in self.checkpoints.rows("timing")
                        if row["algorithm"] == algorithm and row["d"] == d
                    ]
                    incomplete = [
                        row for row in timing_attempt_records(algorithm_rows)
                        if row["status"] == "incomplete"
                    ]
                    for attempt in incomplete:
                        trial = int(attempt["trial_index"])
                        attempt_rows = [
                            row for row in algorithm_rows if row["trial_index"] == trial
                        ]
                        sample = attempt_rows[0]
                        for repetition in range(const.TIMING_REPETITIONS):
                            identity = "%s-rep%d" % (point["candidate_id"], repetition)
                            if self.checkpoints.load("timing", algorithm, d, identity, trial):
                                continue
                            self.checkpoints.save(self._result_row(
                                stage="timing", domain="timing", algorithm=algorithm, d=d,
                                trial=trial, candidate_id=identity, resource=point["resource"],
                                dataset=sample["dataset"], seeds=sample["dataset_seeds"],
                                result=None, terminal_status="not_run_after_resource_limit",
                                repetition=repetition, cpu_affinity=self.engines.cpu_affinity,
                            ))

                while True:
                    timing = self.checkpoints.rows("timing")
                    attempts = timing_attempt_records(timing)
                    point_attempts = {
                        algorithm: [
                            row for row in attempts
                            if row["algorithm"] == algorithm and row["d"] == d
                        ]
                        for algorithm in const.ALGORITHMS
                    }
                    pending = [
                        algorithm for algorithm in const.ALGORITHMS
                        if confirmed[(algorithm, d)]
                        and algorithm not in resource_limited
                        and sum(row["status"] == "successful" for row in point_attempts[algorithm])
                        < const.TIMING_DATASETS
                    ]
                    if not pending:
                        break
                    next_trials = {
                        algorithm: next_timing_trial(point_attempts[algorithm])
                        for algorithm in pending
                    }
                    trial = min(next_trials.values())
                    trial_algorithms = [
                        algorithm for algorithm in pending if next_trials[algorithm] == trial
                    ]
                    dataset, seeds = self._dataset(
                        self.engines, dataset_path, "timing", d, trial, full=True
                    )
                    fatal_error: Optional[str] = None
                    for algorithm in trial_algorithms:
                        point = operating[(algorithm, d)]
                        arguments = self._arguments(
                            algorithm, d, trial, "timing", point["resource"]
                        )
                        measured_stop_reason: Optional[str] = None
                        for repetition in range(const.TIMING_REPETITIONS):
                            identity = "%s-rep%d" % (point["candidate_id"], repetition)
                            if self.checkpoints.load("timing", algorithm, d, identity, trial):
                                continue
                            if measured_stop_reason is not None:
                                result, terminal = None, (
                                    "not_run_after_resource_limit"
                                    if measured_stop_reason in {"timeout", "oom"}
                                    else "not_run_after_process_error"
                                )
                            elif algorithm in resource_limited:
                                result, terminal = None, "not_run_after_resource_limit"
                            else:
                                result, terminal = self._safe_engine(
                                    self.engines, algorithm, dataset_path, arguments
                                )
                                if result is not None and not result.success \
                                        and result.failure_reason not in TIMING_STATISTICAL_FAILURES:
                                    terminal = "process_error"
                            if terminal in {"timeout", "oom"}:
                                resource_limited[algorithm] = str(terminal)
                                point_status[(algorithm, d)] = str(terminal)
                                measured_stop_reason = str(terminal)
                            elif terminal in {
                                "not_run_after_resource_limit", "not_run_after_process_error"
                            }:
                                pass
                            elif terminal is not None:
                                fatal_error = "%s measured repetition failed with %s" % (
                                    algorithm, terminal
                                )
                                measured_stop_reason = str(terminal)
                            self.checkpoints.save(self._result_row(
                                stage="timing", domain="timing", algorithm=algorithm, d=d,
                                trial=trial, candidate_id=identity, resource=point["resource"],
                                dataset=dataset, seeds=seeds, result=result,
                                terminal_status=terminal, repetition=repetition,
                                cpu_affinity=self.engines.cpu_affinity,
                            ))
                        if fatal_error is not None:
                            self._raise_on_process_error(self.checkpoints.rows("timing"), "timing")
                            raise AssertionError("timing fatal error was not persisted")
        timing = self.checkpoints.rows("timing")
        atomic_jsonl(self.path / "timing.jsonl", timing)
        attempts = timing_attempt_records(timing)
        atomic_jsonl(self.path / "timing_attempts.jsonl", attempts)
        summaries = []
        for d in const.DIFFERENCES:
            for algorithm in const.ALGORITHMS:
                point_attempts = [
                    row for row in attempts
                    if row["algorithm"] == algorithm and row["d"] == d
                    and row["status"] != "incomplete"
                ]
                successful = [row for row in point_attempts if row["status"] == "successful"]
                status = point_status.get(
                    (algorithm, d),
                    "complete" if confirmed[(algorithm, d)] else "not_run_not_confirmed",
                )
                if status == "complete" and len(successful) != const.TIMING_DATASETS:
                    raise RuntimeError("timing point did not collect the required successes")
                plottable = status == "complete" and len(successful) == const.TIMING_DATASETS
                updates = [float(row["update_ns_per_input"]) for row in successful] if plottable else []
                decodes = [float(row["decode_ns_per_difference"]) for row in successful] if plottable else []
                update_ci = percentile_bootstrap(
                    updates,
                    seed_material="figure2_timing_bootstrap|%s|%d|update" % (algorithm, d),
                    estimator="mean",
                ) if updates else (None, None)
                decode_ci = percentile_bootstrap(
                    decodes,
                    seed_material="figure2_timing_bootstrap|%s|%d|decode" % (algorithm, d),
                    estimator="mean",
                ) if decodes else (None, None)
                summaries.append({
                    "algorithm": algorithm, "d": d,
                    "timing_status": status,
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
        atomic_json(self.path / "timing_summary.json", {
            "estimand": "E[runtime | decode success]",
            "successful_datasets_target_per_point": const.TIMING_DATASETS,
            "points": summaries,
        })
        aggregate = self._aggregate_points(
            confirmation_points, self.checkpoints.rows("sealed_confirmation"), summaries
        )
        atomic_json(self.path / "aggregate.json", aggregate)
        self._transition("timing_running", "complete")
        return self.path

    def run_all(self) -> Path:
        state = _read(self.path / "run_state.json")["status"]
        if state in {"created", "discovery_running"}: self.run_discovery()
        state = _read(self.path / "run_state.json")["status"]
        if state in {"discovery_complete", "confirmation_running"}: self.run_confirmation()
        state = _read(self.path / "run_state.json")["status"]
        if state in {"confirmation_complete", "timing_running"}: self.run_timing()
        return self.path


def finalize_timing_run(path: Path) -> Path:
    path = path.resolve()
    state_path = path / "run_state.json"
    state = _read(state_path)
    if state.get("status") != "timing_running":
        raise ValueError("finalization requires a timing_running run")
    config = _read(path / "run_config.json")
    expected = {
        "protocol_version": const.PROTOCOL_VERSION,
        "timing_successful_datasets_target": const.TIMING_DATASETS,
        "timing_repetitions": const.TIMING_REPETITIONS,
        "timing_warmups": 0,
    }
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("run configuration does not match the finalizer protocol")

    confirmation_points = _read(path / "confirmation_summary.json")["points"]
    timing_summary_path = path / "timing_summary.json"
    timing_summaries = _read(timing_summary_path)["points"]
    complete = [
        row for row in timing_summaries if row.get("timing_status") == "complete"
    ]
    if any(row.get("successful_datasets") != const.TIMING_DATASETS for row in complete):
        raise ValueError("complete timing point has the wrong successful dataset count")
    aggregate = FormalRunner._aggregate_points(
        confirmation_points, Checkpoints(path).rows("sealed_confirmation"), timing_summaries
    )
    aggregate_path = path / "aggregate.json"
    atomic_json(aggregate_path, aggregate)
    atomic_json(path / "finalization_manifest.json", {
        "status": "complete",
        "protocol_version": const.PROTOCOL_VERSION,
        "operation": "deterministic_postprocessing_only",
        "engine_trials_executed": False,
        "payload_aggregation": aggregate["payload_aggregation"],
        "confirmation_summary_sha256": sha256_file(path / "confirmation_summary.json"),
        "timing_summary_sha256": sha256_file(timing_summary_path),
        "aggregate_sha256": sha256_file(aggregate_path),
        "finalizer_source_tree_sha256": source_tree_sha256(const.EXPERIMENT_DIR),
    })
    atomic_json(state_path, {
        "sequence": int(state["sequence"]) + 1,
        "status": "complete",
        "completion_operation": "deterministic_postprocessing_only",
    })
    return path
