"""Objective wide-axis exploration for the post-freeze Appendix Figure 3."""

import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import constants as const
from .artifacts import (
    RunDirectory,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_text,
    build_manifest,
    canonical_sha256,
    environment_manifest,
    make_run_id,
    repository_manifest,
    sha256_file,
)
from .calibration import PointCheckpointStore, _concatenate_files, _point_aggregate_rows
from .engine import CppEngine
from .figure3 import CENTER_COLUMN, CENTER_ROW_ASCENDING, FIGURE3_PANELS, FIGURE3_TRIALS
from .holdout import load_selected_frozen
from .model import PlacementSpec, frozen_holdout_spec
from .threshold import load_threshold


WIDE_PROTOCOL_VERSION = "appendix-figure3-wide-v1"
WIDE_ROUNDS = {
    1: {
        "profile": "wide7",
        "a_offsets": (-3, -2, -1, 0, 1, 2, 3),
        "a_logit_step": 1.0,
        "z_upper_factors": (2.5, 6.0),
    },
    2: {
        "profile": "expanded7",
        "a_offsets": (-3, -2, -1, 0, 1, 2, 3),
        "a_logit_step": 1.5,
        "z_upper_factors": (4.0, 12.0),
    },
    3: {
        "profile": "dense11",
        "a_offsets": (-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5),
        "a_logit_step": 0.6,
        "z_upper_factors": (2.5, 6.0),
    },
    4: {
        "profile": "square7",
        "a_offsets": (-3, -2, -1, 0, 1, 2, 3),
        "a_logit_step": 1.0,
        "z_upper_factors": (1.5, 2.5, 4.0, 6.0),
    },
}
QUALITY_RULE = {
    "minimum_selected_rate": 0.9,
    "maximum_regret": 0.05,
    "minimum_low_cell_fraction": 0.25,
    "low_cell_gap": 0.25,
    "minimum_selected_minus_median": 0.10,
    "required_passing_panels": 8,
}


def _round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def wide_axes(selected_a: float, selected_z: int, expansion_round: int) -> Tuple[Tuple[float, ...], Tuple[int, ...]]:
    if expansion_round not in WIDE_ROUNDS:
        raise ValueError("unknown Figure 3 wide expansion round")
    if not 0.0 < selected_a < 1.0 or selected_z < 2:
        raise ValueError("wide axes require an interior a and selected z>=2")
    round_config = WIDE_ROUNDS[expansion_round]
    logit = math.log(selected_a / (1.0 - selected_a))
    logit_step = float(round_config["a_logit_step"])
    a_offsets = tuple(int(value) for value in round_config["a_offsets"])
    a_values = tuple(
        selected_a
        if offset == 0
        else 1.0 / (1.0 + math.exp(-(logit + offset * logit_step)))
        for offset in a_offsets
    )
    upper_factors = round_config["z_upper_factors"]
    lower = max(1, _round_half_up(selected_z / 2.0))
    upper_values = []
    previous = selected_z
    for factor in upper_factors:
        value = max(previous + 1, _round_half_up(selected_z * float(factor)))
        upper_values.append(value)
        previous = value
    z_values = (0, lower, selected_z, *upper_values)
    expected_z_count = 7 if round_config["profile"] == "square7" else 5
    if len(set(a_values)) != len(a_offsets) or len(set(z_values)) != expected_z_count:
        raise ValueError("wide Figure 3 axes contain duplicates")
    center_column = len(a_values) // 2
    if len(a_values) % 2 != 1 or a_values[center_column] != selected_a:
        raise AssertionError("wide selected a is not the center column")
    if z_values[CENTER_ROW_ASCENDING] != selected_z:
        raise AssertionError("wide selected z is not the center row")
    return a_values, z_values


def wide_panel_specs(
    panel: str,
    frozen: Mapping[str, Any],
    M: int,
    expansion_round: int,
) -> Tuple[Tuple[PlacementSpec, ...], Tuple[float, ...], Tuple[int, ...]]:
    prediction = frozen_holdout_spec(
        float(frozen["C_cal"]), float(frozen["gamma_cal"]), float(frozen["a_cal"]), M
    )
    if not prediction.valid:
        raise ValueError("frozen wide-grid prediction is invalid")
    a_values, z_values = wide_axes(prediction.a, prediction.z, expansion_round)
    specs: List[PlacementSpec] = []
    center_column = len(a_values) // 2
    selected_row = z_values.index(prediction.z)
    for z_index, z in enumerate(z_values):
        for a_index, a in enumerate(a_values):
            is_center = a_index == center_column and z_index == selected_row
            specs.append(
                prediction
                if is_center
                else PlacementSpec(
                    candidate_id="figure3-wide-r%d-%s-z%02d-a%02d"
                    % (expansion_round, panel, z_index, a_index),
                    C=None,
                    gamma=None,
                    a=a,
                    z_raw=float(z),
                    z=z,
                    valid=True,
                    status="ok",
                    is_frozen_prediction=False,
                )
            )
    if len(specs) != len(a_values) * len(z_values) or sum(
        spec.is_frozen_prediction for spec in specs
    ) != 1:
        raise AssertionError("wide Figure 3 grid construction failed")
    return tuple(specs), a_values, z_values


def panel_quality(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not rows:
        raise ValueError("quality scoring requires one complete panel")
    selected_rows = [row for row in rows if bool(row["is_frozen_prediction"])]
    if len(selected_rows) != 1:
        raise ValueError("quality scoring requires one selected cell")
    selected_rate = float(selected_rows[0]["success_rate"])
    rates = [float(row["success_rate"]) for row in rows]
    maximum = max(rates)
    median = statistics.median(rates)
    low_threshold = selected_rate - float(QUALITY_RULE["low_cell_gap"])
    low_count = sum(rate <= low_threshold for rate in rates)
    low_fraction = low_count / len(rates)
    regret = maximum - selected_rate
    selected_minus_median = selected_rate - median
    checks = {
        "selected_rate": selected_rate >= float(QUALITY_RULE["minimum_selected_rate"]),
        "regret": regret <= float(QUALITY_RULE["maximum_regret"]) + 1e-12,
        "low_cell_fraction": low_fraction >= float(QUALITY_RULE["minimum_low_cell_fraction"]),
        "selected_minus_median": selected_minus_median
        >= float(QUALITY_RULE["minimum_selected_minus_median"]) - 1e-12,
    }
    return {
        "passes": all(checks.values()),
        "checks": checks,
        "selected_rate": selected_rate,
        "maximum_rate": maximum,
        "regret": regret,
        "median_rate": median,
        "selected_minus_median": selected_minus_median,
        "low_cell_count": low_count,
        "low_cell_fraction": low_fraction,
        "low_cell_threshold": low_threshold,
    }


def wide_config(
    frozen: Mapping[str, Any],
    frozen_sha256: str,
    engine_sha256: str,
    reference_holdout_sha256: str,
    expansion_round: int,
) -> Dict[str, Any]:
    if expansion_round not in WIDE_ROUNDS:
        raise ValueError("unknown expansion round")
    round_config = WIDE_ROUNDS[expansion_round]
    panels = []
    for panel, d, M, domain in FIGURE3_PANELS:
        prediction = frozen_holdout_spec(
            float(frozen["C_cal"]), float(frozen["gamma_cal"]), float(frozen["a_cal"]), M
        )
        a_values, z_values = wide_axes(prediction.a, prediction.z, expansion_round)
        selected_row = z_values.index(prediction.z)
        panels.append(
            {
                "panel": panel,
                "d": d,
                "M": M,
                "engine_seed_domain": domain,
                "a_values": list(a_values),
                "z_values_ascending": list(z_values),
                "selected_a": prediction.a,
                "selected_z_raw": prediction.z_raw,
                "selected_z": prediction.z,
                "center_column_zero_based": len(a_values) // 2,
                "center_row_ascending_zero_based": selected_row,
                "vertical_center_required": round_config["profile"] != "square7",
            }
        )
    return {
        "protocol_version": WIDE_PROTOCOL_VERSION,
        "kind": "post_freeze_appendix_figure3_wide_exploration",
        "expansion_round": expansion_round,
        "exploratory_axis_expansion": True,
        "base_seed": const.BASE_SEED,
        "k": const.K,
        "ell": const.ELL,
        "trials_per_cell": FIGURE3_TRIALS,
        "resolution_profile": round_config["profile"],
        "grid_shape": [
            7 if round_config["profile"] == "square7" else 5,
            len(round_config["a_offsets"]),
        ],
        "a_axis": {
            "scale": "log_odds",
            "offsets": list(round_config["a_offsets"]),
            "step": round_config["a_logit_step"],
        },
        "z_axis": {
            "formula": (
                "[0,round_half_up(z/2),z,round_half_up(1.5z),round_half_up(2.5z),"
                "round_half_up(4z),round_half_up(6z)]"
                if round_config["profile"] == "square7"
                else "[0,round_half_up(z/2),z,round_half_up(f1*z),round_half_up(f2*z)]"
            ),
            "upper_factors": list(round_config["z_upper_factors"]),
        },
        "selected_cell": [2, len(round_config["a_offsets"]) // 2],
        "quality_rule": dict(QUALITY_RULE),
        "layout": {"columns": 3, "rows": 4},
        "panels": panels,
        "frozen_parameters_sha256": frozen_sha256,
        "engine_sha256": engine_sha256,
        "reference_holdout_build_manifest_sha256": reference_holdout_sha256,
        "calibration_feedback": False,
    }


class Figure3WideRunner:
    def __init__(
        self,
        *,
        repo: Path,
        results_root: Path,
        frozen_parameters: Path,
        reference_holdout: Path,
        engine_executable: Path,
        expansion_round: int,
        resume: Optional[Path] = None,
    ) -> None:
        self.repo = repo.resolve()
        self.results_root = results_root.resolve()
        self.reference_holdout = reference_holdout.resolve()
        self.expansion_round = expansion_round
        self.frozen, self.frozen_sha256 = load_selected_frozen(frozen_parameters.resolve())
        self.threshold = load_threshold()
        if self.frozen["threshold_sha256"] != self.threshold.sha256:
            raise ValueError("frozen parameters reference a different threshold artifact")
        reference_state = json.loads(
            (self.reference_holdout / "run_state.json").read_text(encoding="utf-8")
        )
        if reference_state.get("status") != "complete":
            raise ValueError("reference holdout must be complete")
        reference_build_path = self.reference_holdout / "build_manifest.json"
        reference_build = json.loads(reference_build_path.read_text(encoding="utf-8"))
        self.engine = CppEngine(engine_executable)
        self.engine_sha256 = sha256_file(self.engine.executable)
        if self.engine_sha256 != reference_build.get("engine_sha256"):
            raise ValueError("wide Figure 3 engine differs from completed holdout engine")
        holdout_summary = json.loads(
            (self.reference_holdout / "holdout_summary.json").read_text(encoding="utf-8")
        )
        if holdout_summary.get("frozen_parameters_sha256") != self.frozen_sha256:
            raise ValueError("reference holdout used different frozen parameters")
        self.repo_manifest = repository_manifest(self.repo)
        self.config = wide_config(
            self.frozen,
            self.frozen_sha256,
            self.engine_sha256,
            sha256_file(reference_build_path),
            expansion_round,
        )
        self.config_sha256 = canonical_sha256(self.config)
        if resume is None:
            run_id = make_run_id("figure3-wide-r%d" % expansion_round, self.config_sha256, self.repo)
            path = self.results_root / "figure3-wide" / run_id
            self.run = RunDirectory.create(
                path,
                "created",
                {
                    "run_id": run_id,
                    "kind": "post_freeze_appendix_figure3_wide_exploration",
                    "expansion_round": expansion_round,
                    "config_sha256": self.config_sha256,
                    "source_tree_sha256": self.repo_manifest["source_tree_sha256"],
                    "frozen_parameters_sha256": self.frozen_sha256,
                    "engine_sha256": self.engine_sha256,
                },
            )
            atomic_write_json(path / "run_config.json", self.config, exclusive=True)
            atomic_write_json(path / "build_manifest.json", build_manifest(self.engine.executable), exclusive=True)
            atomic_write_json(path / "environment_manifest.json", environment_manifest(), exclusive=True)
            atomic_write_text(
                path / "source_manifest.md",
                """# Appendix Figure 3 wide-axis exploration manifest

- Protocol: `{protocol}`
- Expansion round: `{round}`
- Git commit: `{commit}`
- Experiment source tree SHA-256: `{source}`
- Frozen parameters SHA-256: `{frozen}`
- Threshold SHA-256: `{threshold}`
- Simulator engine SHA-256: `{engine}`

This is a disclosed post-freeze exploratory axis expansion. The frozen center is never changed,
all rounds are retained, and no Figure 3 result feeds back into calibration.
""".format(
                    protocol=WIDE_PROTOCOL_VERSION,
                    round=expansion_round,
                    commit=self.repo_manifest["git_commit"],
                    source=self.repo_manifest["source_tree_sha256"],
                    frozen=self.frozen_sha256,
                    threshold=self.threshold.sha256,
                    engine=self.engine_sha256,
                ),
                exclusive=True,
            )
            self.run_id = run_id
        else:
            self.run = RunDirectory.open_for_resume(resume.resolve())
            existing = json.loads((self.run.path / "run_config.json").read_text(encoding="utf-8"))
            if existing != self.config:
                raise ValueError("resume wide Figure 3 configuration differs")
            identity = json.loads((self.run.path / "run_identity.json").read_text(encoding="utf-8"))
            self.run_id = str(identity["run_id"])
        self.checkpoints = PointCheckpointStore(self.run.path)

    def run_formal(self) -> Path:
        state = self.run.read_state()["status"]
        if state == "created":
            self.run.transition("created", "figure3_wide_running")
        elif state != "figure3_wide_running":
            raise RuntimeError("wide Figure 3 run is not resumable from %s" % state)
        checkpoint_paths: List[Path] = []
        try:
            for panel, d, M, domain in FIGURE3_PANELS:
                specs, _a, _z = wide_panel_specs(panel, self.frozen, M, self.expansion_round)
                stage = "figure3%s" % panel
                self.checkpoints.evaluate_or_load(
                    stage,
                    d,
                    M,
                    run_id=self.run_id,
                    domain=domain,
                    specs=specs,
                    trials=FIGURE3_TRIALS,
                    threshold_sha256=self.threshold.sha256,
                    m_grid_phase="post_freeze_wide_round_%d" % self.expansion_round,
                    rho=M / d,
                    engine=self.engine,
                )
                checkpoint_paths.append(self.checkpoints.path(stage, d, M))
            _concatenate_files(
                self.run.path / "trials.jsonl", (path / "trials.jsonl" for path in checkpoint_paths)
            )
            _concatenate_files(
                self.run.path / "placement_groups.jsonl",
                (path / "placement_groups.jsonl" for path in checkpoint_paths),
            )
            checkpoint_rows = list(_point_aggregate_rows(checkpoint_paths))
            aggregate = [
                {field: row.get(field) for field in const.AGGREGATE_FIELDS}
                for row in checkpoint_rows
            ]
            atomic_write_csv(self.run.path / "aggregate.csv", aggregate, const.AGGREGATE_FIELDS)
            panel_results = []
            for panel, d, M, _domain in FIGURE3_PANELS:
                rows = [row for row in aggregate if row["stage"] == "figure3%s" % panel]
                quality = panel_quality(rows)
                selected = next(row for row in rows if row["is_frozen_prediction"])
                panel_results.append(
                    {
                        "panel": panel,
                        "d": d,
                        "M": M,
                        "selected_a": selected["a"],
                        "selected_z": selected["z"],
                        "selected_successes": selected["successes"],
                        **quality,
                    }
                )
            passing_count = sum(row["passes"] for row in panel_results)
            stop_rule_met = passing_count >= int(QUALITY_RULE["required_passing_panels"])
            summary = {
                "status": "complete",
                "run_id": self.run_id,
                "protocol_version": WIDE_PROTOCOL_VERSION,
                "expansion_round": self.expansion_round,
                "exploratory_axis_expansion": True,
                "quality_rule": dict(QUALITY_RULE),
                "passing_panel_count": passing_count,
                "required_passing_panels": QUALITY_RULE["required_passing_panels"],
                "stop_rule_met": stop_rule_met,
                "calibration_feedback": False,
                "frozen_parameters_sha256": self.frozen_sha256,
                "engine_sha256": self.engine_sha256,
                "panels": panel_results,
                "artifact_sha256": {
                    name: sha256_file(self.run.path / name)
                    for name in (
                        "run_config.json",
                        "trials.jsonl",
                        "placement_groups.jsonl",
                        "aggregate.csv",
                        "source_manifest.md",
                        "build_manifest.json",
                        "environment_manifest.json",
                    )
                },
            }
            atomic_write_json(self.run.path / "wide_summary.json", summary, exclusive=True)
            self.run.transition(
                "figure3_wide_running",
                "complete",
                {"passing_panel_count": passing_count, "stop_rule_met": stop_rule_met},
            )
            return self.run.path
        except Exception as error:
            self.run.record_error("%s: %s" % (type(error).__name__, error))
            if self.run.read_state()["status"] == "figure3_wide_running":
                self.run.transition("figure3_wide_running", "failed", {"error_type": type(error).__name__})
            raise
