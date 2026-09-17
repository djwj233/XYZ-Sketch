"""Audited coarse-scan runner for the reduced-cardinality Figure 1(a)."""

import json
import subprocess
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import constants as const
from .artifacts import (
    RunDirectory,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_jsonl,
    atomic_write_text,
    build_manifest,
    canonical_sha256,
    environment_manifest,
    make_run_id,
    repository_manifest,
    sha256_file,
)
from .config import (
    ConfigSpec,
    PanelParameters,
    build_initial_manifest,
    extended_m_values,
    initial_m_values,
    load_frozen,
    load_thresholds,
    make_spec,
)
from .engine import CppEngine
from .statistics import wilson_interval


CurveKey = Tuple[int, int, str]


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_formal_inputs(
    repo: Path,
    frozen_path: Path,
    holdout_path: Path,
    engine: CppEngine,
) -> Dict[str, Any]:
    """Validate all downstream gates without opening a formal seed domain."""
    frozen, frozen_sha256 = load_frozen(frozen_path)
    thresholds = load_thresholds()
    calibration_path = frozen_path.parent
    calibration_state = _read_json(calibration_path / "run_state.json")
    calibration_config = _read_json(calibration_path / "calibration_config.json")
    if calibration_state.get("status") != "selected":
        raise ValueError("calibration run is not selected")
    if calibration_state.get("frozen_parameters_sha256") != frozen_sha256:
        raise ValueError("calibration state does not bind the frozen artifact")
    training_d = [int(value) for value in calibration_config.get("training_d", [])]
    if not training_d or any(value >= 3000 for value in training_d):
        raise ValueError("calibration data are not confined to d<3000")
    if calibration_config.get("threshold_sha256") != const.EXPECTED_THRESHOLD_SHA256:
        raise ValueError("calibration used a different threshold artifact")
    for name in frozen.get("input_artifact_sha256", {}):
        if not (calibration_path / name).is_file():
            raise ValueError("calibration input artifact is missing: %s" % name)

    holdout_state = _read_json(holdout_path / "run_state.json")
    holdout_summary = _read_json(holdout_path / "holdout_summary.json")
    if holdout_state.get("status") != "complete" or holdout_summary.get("status") != "complete":
        raise ValueError("sealed holdout is not complete")
    if not holdout_summary.get("frozen_predictions_passed") \
            or not holdout_summary.get("downstream_experiments_unlocked"):
        raise ValueError("sealed holdout did not unlock downstream experiments")
    if holdout_summary.get("frozen_parameters_sha256") != frozen_sha256:
        raise ValueError("sealed holdout used different frozen parameters")
    predictions = holdout_summary.get("predictions", [])
    if len(predictions) != 2 or any(not row.get("passed") for row in predictions):
        raise ValueError("sealed holdout lacks two passing predictions")
    for name in holdout_summary.get("artifact_sha256", {}):
        if not (holdout_path / name).is_file():
            raise ValueError("holdout artifact is missing: %s" % name)

    core_status = subprocess.run(
        ["git", "status", "--short", "--", "XYZ-Sketch"], cwd=str(repo), check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout.strip()
    if core_status:
        raise ValueError("core XYZ-Sketch tree is modified: %s" % core_status)
    self_test = json.loads(engine.self_test())
    if self_test.get("protocol") != const.ENGINE_PROTOCOL \
            or not self_test.get("residual_equivalence") \
            or not self_test.get("golden_accounting"):
        raise ValueError("engine self-test did not pass all gates")

    return {
        "status": "passed",
        "threshold_entries": len(thresholds),
        "threshold_sha256": const.EXPECTED_THRESHOLD_SHA256,
        "frozen_parameters_sha256": frozen_sha256,
        "calibration_run_id": frozen["run_id"],
        "calibration_training_d": training_d,
        "holdout_run_id": holdout_summary["run_id"],
        "holdout_success_rates": [row["success_rate"] for row in predictions],
        "engine_self_test": self_test,
        "core_tree_clean": True,
    }


def _curve_key(k: int, ell: int, mode: str) -> str:
    return "k%d-l%d-%s" % (k, ell, mode)


def _spec_payload(spec: ConfigSpec) -> Dict[str, Any]:
    value = asdict(spec)
    value["config_id"] = spec.config_id
    value["bits_per_cell"] = spec.bits_per_cell
    value["logical_state_bits"] = spec.logical_state_bits
    value["state_bits"] = spec.state_bits
    value["total_payload_bits"] = spec.total_payload_bits
    value["R_w30"] = spec.R_w30
    return value


class PointCheckpointStore:
    def __init__(
        self,
        root: Path,
        *,
        phase: str = "coarse",
        expected_trials: int = const.COARSE_TRIALS,
    ) -> None:
        self.root = root / "checkpoints" / "points"
        self.root.mkdir(parents=True, exist_ok=True)
        self.phase = phase
        self.expected_trials = expected_trials

    def path(self, spec: ConfigSpec) -> Path:
        return self.root / (spec.config_id + ".json")

    def load(self, spec: ConfigSpec) -> Dict[str, Any]:
        path = self.path(spec)
        if not path.exists():
            return {
                "protocol_version": const.PROTOCOL_VERSION,
                "phase": self.phase,
                "spec": _spec_payload(spec),
                "trials": [],
                "complete": False,
            }
        value = _read_json(path)
        if value.get("protocol_version") != const.PROTOCOL_VERSION \
                or value.get("phase") != self.phase \
                or value.get("spec") != _spec_payload(spec):
            raise ValueError("point checkpoint configuration drift: %s" % spec.config_id)
        indices = [int(row["trial_index"]) for row in value.get("trials", [])]
        if len(indices) != len(set(indices)) \
                or any(index not in range(self.expected_trials) for index in indices):
            raise ValueError("point checkpoint has invalid trial indices: %s" % spec.config_id)
        return value

    def missing(self, spec: ConfigSpec, trial_index: int) -> bool:
        return trial_index not in {
            int(row["trial_index"]) for row in self.load(spec)["trials"]
        }

    def add(self, spec: ConfigSpec, row: Mapping[str, Any]) -> None:
        value = self.load(spec)
        index = int(row["trial_index"])
        if any(int(existing["trial_index"]) == index for existing in value["trials"]):
            raise ValueError("duplicate trial checkpoint")
        value["trials"].append(dict(row))
        value["trials"].sort(key=lambda item: int(item["trial_index"]))
        value["complete"] = len(value["trials"]) == self.expected_trials
        atomic_write_json(self.path(spec), value)

    def import_complete(self, spec: ConfigSpec, rows: Sequence[Mapping[str, Any]]) -> None:
        imported = [dict(row) for row in rows]
        indices = sorted(int(row["trial_index"]) for row in imported)
        if indices != list(range(self.expected_trials)):
            raise ValueError("imported point trial indices are incomplete: %s" % spec.config_id)
        for row in imported:
            if row.get("protocol_version") != const.PROTOCOL_VERSION \
                    or row.get("phase") != self.phase \
                    or (int(row["k"]), int(row["ell"]), str(row["mode"]), int(row["M"])) != \
                    (spec.k, spec.ell, spec.mode, spec.M):
                raise ValueError("imported point configuration drift: %s" % spec.config_id)
        value = {
            "protocol_version": const.PROTOCOL_VERSION,
            "phase": self.phase,
            "spec": _spec_payload(spec),
            "trials": sorted(imported, key=lambda row: int(row["trial_index"])),
            "complete": True,
        }
        path = self.path(spec)
        if path.exists():
            if self.load(spec) != value:
                raise ValueError("imported point checkpoint collision: %s" % spec.config_id)
            return
        atomic_write_json(path, value)

    def trials(self, spec: ConfigSpec, *, require_complete: bool = True) -> List[Dict[str, Any]]:
        value = self.load(spec)
        if require_complete and not value["complete"]:
            raise RuntimeError("incomplete point checkpoint: %s" % spec.config_id)
        return list(value["trials"])


def _trial_row(
    *,
    run_id: str,
    git_commit: str,
    spec: ConfigSpec,
    dataset: Mapping[str, Any],
    result: Mapping[str, Any],
    phase: str = "coarse",
) -> Dict[str, Any]:
    expected = {
        "logical_state_bits": spec.logical_state_bits,
        "state_bits": spec.state_bits,
        "control_bits": const.CONTROL_BITS,
        "total_payload_bits": spec.total_payload_bits,
    }
    for field, value in expected.items():
        if int(result[field]) != value:
            raise RuntimeError("%s accounting mismatch for %s" % (field, spec.config_id))
    if result["failure_reason"] == "process_error":
        raise RuntimeError("core process error for %s" % spec.config_id)
    return {
        "run_id": run_id,
        "protocol_version": const.PROTOCOL_VERSION,
        "git_commit": git_commit,
        "phase": phase,
        "k": spec.k,
        "ell": spec.ell,
        "mode": spec.mode,
        "M": spec.M,
        "trial_index": dataset["trial_index"],
        "set_size_A": const.SET_SIZE,
        "set_size_B": const.SET_SIZE,
        "difference_A": const.ONE_DIRECTION,
        "difference_B": const.ONE_DIRECTION,
        "base_seed": const.BASE_SEED,
        "dataset_seed": dataset["dataset_seed"],
        "alice_order_seed": dataset["alice_order_seed"],
        "bob_order_seed": dataset["bob_order_seed"],
        "decoder_seed": dataset["decoder_seed"],
        "hash_family_seed": dataset["hash_family_seed"],
        "dataset_sha256": dataset["dataset_sha256"],
        "dataset_seconds": dataset["dataset_seconds"],
        "C": spec.C,
        "D": spec.D,
        "delta": spec.delta,
        "a_raw": spec.a,
        "a": spec.a,
        "z_raw": spec.z_raw,
        "z": spec.z,
        "z_rounding": "fixed_zero_iid" if spec.mode == "iid" else "floor(z_raw+0.5)",
        "success": bool(result["success"]),
        "failure_reason": result["failure_reason"],
        "logical_state_bits": result["logical_state_bits"],
        "state_bits": result["state_bits"],
        "control_bits": result["control_bits"],
        "total_payload_bits": result["total_payload_bits"],
        "bits_per_cell": spec.bits_per_cell,
        "R_w30": spec.R_w30,
        "alice_encode_seconds": result["alice_encode_seconds"],
        "serialization_seconds": result["serialization_seconds"],
        "bob_encode_seconds": result["bob_encode_seconds"],
        "decode_seconds": result["decode_seconds"],
        "total_seconds": result["total_seconds"],
        "dedup_hashes": True,
        "fingerprint_enabled": False,
        "status": "valid",
    }


def aggregate_point(
    spec: ConfigSpec,
    trials: Sequence[Mapping[str, Any]],
    *,
    phase: str = "coarse",
    expected_trials: int = const.COARSE_TRIALS,
) -> Dict[str, Any]:
    if len(trials) != expected_trials:
        raise ValueError("point does not have the required trial count")
    indices = sorted(int(row["trial_index"]) for row in trials)
    if indices != list(range(expected_trials)):
        raise ValueError("point trial indices are incomplete")
    successes = sum(bool(row["success"]) for row in trials)
    low, high = wilson_interval(successes, len(trials))
    failures = Counter(
        str(row["failure_reason"]) for row in trials if not bool(row["success"])
    )
    first = trials[0]
    return {
        "run_id": first["run_id"],
        "protocol_version": const.PROTOCOL_VERSION,
        "git_commit": first["git_commit"],
        "phase": phase,
        "k": spec.k,
        "ell": spec.ell,
        "mode": spec.mode,
        "M": spec.M,
        "C": spec.C,
        "D": spec.D,
        "delta": spec.delta,
        "a_raw": spec.a,
        "a": spec.a,
        "z_raw": spec.z_raw,
        "z": spec.z,
        "z_rounding": "fixed_zero_iid" if spec.mode == "iid" else "floor(z_raw+0.5)",
        "set_size_A": const.SET_SIZE,
        "set_size_B": const.SET_SIZE,
        "difference_A": const.ONE_DIRECTION,
        "difference_B": const.ONE_DIRECTION,
        "trials": len(trials),
        "successes": successes,
        "success_rate": successes / len(trials),
        "ci_low": low,
        "ci_high": high,
        "logical_state_bits": spec.logical_state_bits,
        "state_bits": spec.state_bits,
        "control_bits": const.CONTROL_BITS,
        "total_payload_bits": spec.total_payload_bits,
        "bits_per_cell": spec.bits_per_cell,
        "R_w30": spec.R_w30,
        "dedup_hashes": True,
        "fingerprint_enabled": False,
        "base_seed": const.BASE_SEED,
        "failure_counts": dict(sorted(failures.items())),
        "status": "complete",
    }


def coarse_curve_summaries(
    aggregate_rows: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    def plan_curve(k: int, ell: int, mode: str) -> Mapping[str, Any]:
        for curve in plan["curves"]:
            if (curve["k"], curve["ell"], curve["mode"]) == (k, ell, mode):
                return curve
        raise KeyError((k, ell, mode))

    curves = []
    for k, ell in const.PANELS:
        for mode in const.MODES:
            rows = sorted(
                (row for row in aggregate_rows if (
                    int(row["k"]), int(row["ell"]), str(row["mode"])
                ) == (k, ell, mode)),
                key=lambda row: int(row["M"]),
            )
            low = [row for row in rows if float(row["success_rate"]) <= 0.05]
            high = [row for row in rows if float(row["success_rate"]) >= 0.95]
            if not low or not high:
                raise RuntimeError("coarse curve is not bracketed")
            curves.append({
                "k": k,
                "ell": ell,
                "mode": mode,
                "points": len(rows),
                "M_min": int(rows[0]["M"]),
                "M_max": int(rows[-1]["M"]),
                "minimum_M_p_le_005": int(low[0]["M"]),
                "maximum_M_p_le_005": int(low[-1]["M"]),
                "minimum_M_p_ge_095": int(high[0]["M"]),
                "maximum_M_p_ge_095": int(high[-1]["M"]),
                "transition_low_candidate_M": int(low[-1]["M"]),
                "transition_high_candidate_M": int(high[0]["M"]),
                "extension_rounds": dict(plan_curve(k, ell, mode)["extension_rounds"]),
            })
    return curves


def recover_failed_coarse(parent: Path, frozen_path: Path) -> Path:
    """Finalize valid checkpoints without mutating their terminal failed parent."""
    parent = parent.resolve()
    state = _read_json(parent / "run_state.json")
    if state.get("status") != "failed" or state.get("error_type") != "TypeError":
        raise ValueError("recovery only accepts the canonical-JSON TypeError run")
    errors = (parent / "errors.log").read_text(encoding="utf-8").strip()
    if errors != "TypeError: non-string JSON key at $.dense_step":
        raise ValueError("failed run error does not match the reviewed finalization defect")
    config = _read_json(parent / "run_config.json")
    plan = _read_json(parent / "coarse_plan.json")
    if config.get("protocol_version") != const.PROTOCOL_VERSION \
            or plan.get("protocol_version") != const.PROTOCOL_VERSION:
        raise ValueError("failed parent uses a different protocol")
    frozen, frozen_sha256 = load_frozen(frozen_path.resolve())
    if config.get("frozen_parameters_sha256") != frozen_sha256:
        raise ValueError("failed parent used different frozen parameters")
    thresholds = load_thresholds()
    parameters = {
        panel: PanelParameters.create(*panel, thresholds, frozen) for panel in const.PANELS
    }
    specs = []
    for curve in plan["curves"]:
        panel_parameters = parameters[(int(curve["k"]), int(curve["ell"]))]
        specs.extend(
            make_spec(panel_parameters, str(curve["mode"]), int(M))
            for M in curve["M_values"]
        )
    specs.sort(key=lambda spec: (spec.k, spec.ell, const.MODES.index(spec.mode), spec.M))
    checkpoints = PointCheckpointStore(parent)
    trials = []
    aggregates = []
    for spec in specs:
        point_trials = checkpoints.trials(spec)
        trials.extend(point_trials)
        aggregates.append(aggregate_point(spec, point_trials))
    trials.sort(key=lambda row: (
        int(row["k"]), int(row["ell"]), const.MODES.index(str(row["mode"])),
        int(row["M"]), int(row["trial_index"]),
    ))
    if len(specs) != 359 or len(trials) != 7180:
        raise ValueError("failed parent checkpoint cardinality differs from reviewed run")
    curves = coarse_curve_summaries(aggregates, plan)
    boundary_options = {
        "status": "awaiting_dense_boundary_confirmation",
        "reason": "README literal extrema and local transition endpoints are both recorded",
        "dense_step_by_ell": {str(ell): step for ell, step in const.DENSE_STEP.items()},
        "plateau_steps_each_side": 5,
        "curves": curves,
    }

    recovery = parent / "recovery-canonical-json-v1"
    recovery.mkdir(parents=False, exist_ok=False)
    identity = {
        "protocol_version": const.PROTOCOL_VERSION,
        "kind": "coarse_finalization_recovery",
        "parent_failed_run_id": _read_json(parent / "run_identity.json")["run_id"],
        "parent_run_state_sha256": sha256_file(parent / "run_state.json"),
        "parent_checkpoint_count": len(specs),
        "recovery_reason": errors,
        "formal_trials_reexecuted": False,
    }
    atomic_write_json(recovery / "recovery_identity.json", identity, exclusive=True)
    atomic_write_jsonl(recovery / "trials.jsonl", trials)
    atomic_write_jsonl(recovery / "aggregate.jsonl", aggregates)
    atomic_write_csv(recovery / "aggregate.csv", aggregates, const.AGGREGATE_FIELDS)
    atomic_write_json(recovery / "dense_boundary_candidates.json", boundary_options)
    atomic_write_text(recovery / "source_manifest.md", """# Figure 1(a) coarse recovery

This artifact finalizes complete point checkpoints from `{parent}` without rerunning any trial
or modifying the failed parent's terminal state. The parent failed only while serializing the
dense-boundary metadata after all formal coarse trials and aggregates were complete.
""".format(parent=parent), exclusive=True)
    summary = {
        "status": "coarse_complete",
        "protocol_version": const.PROTOCOL_VERSION,
        "workload_label": "reduced-cardinality revision",
        "parent_failed_run_id": identity["parent_failed_run_id"],
        "formal_trials_reexecuted": False,
        "point_count": len(specs),
        "trial_row_count": len(trials),
        "all_nine_curves_bracketed": True,
        "dense_boundary_status": boundary_options["status"],
        "curves": curves,
        "artifact_sha256": {
            name: sha256_file(recovery / name)
            for name in (
                "recovery_identity.json", "trials.jsonl", "aggregate.jsonl", "aggregate.csv",
                "dense_boundary_candidates.json", "source_manifest.md",
            )
        },
    }
    atomic_write_json(recovery / "coarse_summary.json", summary)
    atomic_write_json(recovery / "run_state.json", {
        "sequence": 0,
        "status": "coarse_complete",
        "protocol_version": const.PROTOCOL_VERSION,
        "parent_terminal_state_preserved": True,
        "formal_trials_reexecuted": False,
    })
    return recovery


class CoarseRunner:
    def __init__(
        self,
        *,
        repo: Path,
        results_root: Path,
        frozen_path: Path,
        holdout_path: Path,
        engine_path: Path,
        resume: Optional[Path] = None,
    ) -> None:
        self.repo = repo.resolve()
        self.results_root = results_root.resolve()
        self.frozen_path = frozen_path.resolve()
        self.holdout_path = holdout_path.resolve()
        self.engine = CppEngine(engine_path.resolve())
        self.frozen, self.frozen_sha256 = load_frozen(self.frozen_path)
        self.thresholds = load_thresholds()
        self.parameters = {
            panel: PanelParameters.create(*panel, self.thresholds, self.frozen)
            for panel in const.PANELS
        }
        self.gates = validate_formal_inputs(
            self.repo, self.frozen_path, self.holdout_path, self.engine
        )
        self.repo_manifest = repository_manifest(self.repo)
        initial = build_initial_manifest(self.frozen, self.frozen_sha256)
        self.config = {
            **initial,
            "executes_trials": True,
            "kind": "formal_coarse_scan",
            "engine_sha256": sha256_file(self.engine.executable),
            "holdout_summary_sha256": sha256_file(self.holdout_path / "holdout_summary.json"),
            "coarse_extension_fraction_of_M0": 0.10,
            "coarse_low_gate": 0.05,
            "coarse_high_gate": 0.95,
            "maximum_extension_rounds_per_direction": const.MAX_EXTENSION_ROUNDS,
        }
        self.config_sha256 = canonical_sha256(self.config)
        if resume is None:
            run_id = make_run_id(self.config_sha256, self.repo)
            path = self.results_root / "coarse" / run_id
            self.run = RunDirectory.create(path, {
                "run_id": run_id,
                "kind": "formal_coarse_scan",
                "config_sha256": self.config_sha256,
                "frozen_parameters_sha256": self.frozen_sha256,
                "engine_sha256": sha256_file(self.engine.executable),
                "figure1a_and_core_source_sha256": self.repo_manifest["figure1a_and_core_source_sha256"],
            })
            self.run_id = run_id
            atomic_write_json(path / "run_config.json", self.config, exclusive=True)
            atomic_write_json(path / "startup_gates.json", self.gates, exclusive=True)
            atomic_write_json(path / "build_manifest.json", build_manifest(self.engine.executable), exclusive=True)
            atomic_write_json(path / "environment_manifest.json", environment_manifest(), exclusive=True)
            atomic_write_json(path / "repository_manifest.json", self.repo_manifest, exclusive=True)
            self.plan = self._initial_plan()
            atomic_write_json(path / "coarse_plan.json", self.plan, exclusive=True)
            atomic_write_text(path / "source_manifest.md", self._source_manifest(), exclusive=True)
        else:
            self.run = RunDirectory.resume(resume)
            identity = _read_json(self.run.path / "run_identity.json")
            existing_config = _read_json(self.run.path / "run_config.json")
            if existing_config != self.config or identity.get("config_sha256") != self.config_sha256:
                raise ValueError("resume configuration differs from current formal configuration")
            self.run_id = str(identity["run_id"])
            self.plan = _read_json(self.run.path / "coarse_plan.json")
        self.checkpoints = PointCheckpointStore(self.run.path)

    def _initial_plan(self) -> Dict[str, Any]:
        curves = []
        for k, ell in const.PANELS:
            parameters = self.parameters[(k, ell)]
            for mode in const.MODES:
                curves.append({
                    "k": k,
                    "ell": ell,
                    "mode": mode,
                    "M0": parameters.center(mode),
                    "M_values": list(initial_m_values(parameters, mode)),
                    "extension_rounds": {"lower": 0, "upper": 0},
                })
        return {
            "protocol_version": const.PROTOCOL_VERSION,
            "phase": "coarse",
            "curves": curves,
            "extension_history": [],
        }

    def _source_manifest(self) -> str:
        return """# Figure 1(a) reduced-cardinality coarse source manifest

- Protocol: `{protocol}`
- Workload: `d=10000`, `|A|=|B|=20000` (`reduced-cardinality revision`)
- Git commit: `{commit}`
- Figure 1(a) and core source SHA-256: `{source}`
- Threshold SHA-256: `{threshold}`
- Frozen parameters SHA-256: `{frozen}`
- Sealed holdout summary SHA-256: `{holdout}`
- C++ engine SHA-256: `{engine}`

The run uses the real XYZ-Sketch encode, wire serialization, subtraction, D-RFR,
rehash verification, and peeling path. The core `XYZ-Sketch/` tree is unmodified.
""".format(
            protocol=const.PROTOCOL_VERSION,
            commit=self.repo_manifest["git_commit"],
            source=self.repo_manifest["figure1a_and_core_source_sha256"],
            threshold=const.EXPECTED_THRESHOLD_SHA256,
            frozen=self.frozen_sha256,
            holdout=sha256_file(self.holdout_path / "holdout_summary.json"),
            engine=sha256_file(self.engine.executable),
        )

    def _curve(self, k: int, ell: int, mode: str) -> Dict[str, Any]:
        for curve in self.plan["curves"]:
            if (curve["k"], curve["ell"], curve["mode"]) == (k, ell, mode):
                return curve
        raise KeyError((k, ell, mode))

    def _all_specs(self) -> List[ConfigSpec]:
        specs = []
        for curve in self.plan["curves"]:
            parameters = self.parameters[(curve["k"], curve["ell"])]
            specs.extend(make_spec(parameters, curve["mode"], M) for M in curve["M_values"])
        return sorted(specs, key=lambda spec: (spec.k, spec.ell, const.MODES.index(spec.mode), spec.M))

    def _evaluate(self, specs: Sequence[ConfigSpec]) -> None:
        for k, ell in const.PANELS:
            panel_specs = [spec for spec in specs if (spec.k, spec.ell) == (k, ell)]
            if not panel_specs:
                continue
            for trial_index in range(const.COARSE_TRIALS):
                missing = [spec for spec in panel_specs if self.checkpoints.missing(spec, trial_index)]
                if not missing:
                    continue
                evaluated = self.engine.evaluate(
                    phase="coarse", k=k, ell=ell, trial_index=trial_index,
                    specs=missing, workers=const.WORKERS,
                )
                if int(evaluated.dataset["trial_index"]) != trial_index:
                    raise RuntimeError("engine returned the wrong trial index")
                for spec in missing:
                    row = _trial_row(
                        run_id=self.run_id,
                        git_commit=self.repo_manifest["git_commit"],
                        spec=spec,
                        dataset=evaluated.dataset,
                        result=evaluated.results[spec.config_id],
                    )
                    self.checkpoints.add(spec, row)

    def _aggregates(self) -> List[Dict[str, Any]]:
        return [
            aggregate_point(spec, self.checkpoints.trials(spec))
            for spec in self._all_specs()
        ]

    def _extend_if_needed(self, aggregates: Sequence[Mapping[str, Any]]) -> List[ConfigSpec]:
        rows_by_curve: Dict[CurveKey, List[Mapping[str, Any]]] = {}
        for row in aggregates:
            rows_by_curve.setdefault((int(row["k"]), int(row["ell"]), str(row["mode"])), []).append(row)
        new_specs = []
        for k, ell in const.PANELS:
            parameters = self.parameters[(k, ell)]
            for mode in const.MODES:
                curve = self._curve(k, ell, mode)
                rows = rows_by_curve[(k, ell, mode)]
                requests = []
                if not any(float(row["success_rate"]) <= 0.05 for row in rows):
                    requests.append("lower")
                if not any(float(row["success_rate"]) >= 0.95 for row in rows):
                    requests.append("upper")
                for direction in requests:
                    next_round = int(curve["extension_rounds"][direction]) + 1
                    if next_round > const.MAX_EXTENSION_ROUNDS:
                        raise RuntimeError("coarse %s extension exceeded limit for %s" % (
                            direction, _curve_key(k, ell, mode)
                        ))
                    values = extended_m_values(parameters, mode, next_round, direction)
                    existing = set(int(M) for M in curve["M_values"])
                    added = sorted(set(values) - existing)
                    if not added:
                        raise RuntimeError("coarse extension added no points")
                    curve["M_values"] = sorted(existing | set(added))
                    curve["extension_rounds"][direction] = next_round
                    record = {
                        "curve": _curve_key(k, ell, mode),
                        "direction": direction,
                        "round": next_round,
                        "added_M": added,
                    }
                    self.plan["extension_history"].append(record)
                    new_specs.extend(make_spec(parameters, mode, M) for M in added)
        if new_specs:
            atomic_write_json(self.run.path / "coarse_plan.json", self.plan)
        return new_specs

    def _write_outputs(self, aggregates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        trials = []
        for spec in self._all_specs():
            trials.extend(self.checkpoints.trials(spec))
        trials.sort(key=lambda row: (
            int(row["k"]), int(row["ell"]), const.MODES.index(str(row["mode"])),
            int(row["M"]), int(row["trial_index"]),
        ))
        aggregate_rows = [dict(row) for row in aggregates]
        atomic_write_jsonl(self.run.path / "trials.jsonl", trials)
        atomic_write_jsonl(self.run.path / "aggregate.jsonl", aggregate_rows)
        atomic_write_csv(self.run.path / "aggregate.csv", aggregate_rows, const.AGGREGATE_FIELDS)

        curves = coarse_curve_summaries(aggregate_rows, self.plan)
        boundary_options = {
            "status": "awaiting_dense_boundary_confirmation",
            "reason": "README literal extrema and local transition endpoints are both recorded",
            "dense_step_by_ell": {str(ell): step for ell, step in const.DENSE_STEP.items()},
            "plateau_steps_each_side": 5,
            "curves": curves,
        }
        atomic_write_json(self.run.path / "dense_boundary_candidates.json", boundary_options)
        summary = {
            "status": "coarse_complete",
            "run_id": self.run_id,
            "protocol_version": const.PROTOCOL_VERSION,
            "workload_label": "reduced-cardinality revision",
            "d": const.D,
            "set_size_A": const.SET_SIZE,
            "set_size_B": const.SET_SIZE,
            "point_count": len(aggregate_rows),
            "trial_row_count": len(trials),
            "all_nine_curves_bracketed": True,
            "dense_boundary_status": boundary_options["status"],
            "curves": curves,
            "artifact_sha256": {
                name: sha256_file(self.run.path / name)
                for name in (
                    "run_config.json", "coarse_plan.json", "trials.jsonl", "aggregate.jsonl",
                    "aggregate.csv", "dense_boundary_candidates.json", "startup_gates.json",
                    "source_manifest.md", "build_manifest.json", "environment_manifest.json",
                    "repository_manifest.json",
                )
            },
        }
        atomic_write_json(self.run.path / "coarse_summary.json", summary)
        return summary

    def run_formal(self) -> Path:
        state = self.run.read_state()["status"]
        if state == "created":
            self.run.transition("created", "coarse_running")
        elif state != "coarse_running":
            raise RuntimeError("coarse run is not active")
        try:
            self._evaluate(self._all_specs())
            while True:
                aggregates = self._aggregates()
                new_specs = self._extend_if_needed(aggregates)
                if not new_specs:
                    break
                self._evaluate(new_specs)
            summary = self._write_outputs(self._aggregates())
            self.run.transition("coarse_running", "coarse_complete", {
                "point_count": summary["point_count"],
                "trial_row_count": summary["trial_row_count"],
                "all_nine_curves_bracketed": True,
            })
            return self.run.path
        except Exception as error:
            self.run.record_error("%s: %s" % (type(error).__name__, error))
            if self.run.read_state()["status"] == "coarse_running":
                self.run.transition("coarse_running", "failed", {"error_type": type(error).__name__})
            raise
