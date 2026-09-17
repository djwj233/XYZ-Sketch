"""Post-freeze 12-panel Appendix Figure 3 experiment."""

import json
import math
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
from .holdout import load_selected_frozen
from .model import PlacementSpec, frozen_holdout_spec
from .threshold import load_threshold


FIGURE3_PROTOCOL_VERSION = "appendix-figure3-centered-v1"
FIGURE3_TRIALS = 100
A_OFFSETS = (-3, -2, -1, 0, 1, 2, 3)
A_STEP = 0.075
Z_OFFSETS = (-2, -1, 0, 1, 2)
CENTER_COLUMN = 3
CENTER_ROW_ASCENDING = 2

# The engine seed includes (domain,d,M).  The two points already present in the
# sealed holdout use the opposite engine domain here, so every Figure 3 panel
# has a post-freeze word stream distinct from calibration and holdout data.
FIGURE3_PANELS: Tuple[Tuple[str, int, int, str], ...] = (
    ("a", 300, 67, "holdout_figure1b"),
    ("b", 300, 72, "holdout_figure1b"),
    ("c", 1_000, 211, "holdout_figure1b"),
    ("d", 1_000, 224, "holdout_figure1b"),
    ("e", 3_000, 596, "holdout_figure1c"),
    ("f", 3_000, 621, "holdout_figure1b"),
    ("g", 10_000, 1_948, "holdout_figure1b"),
    ("h", 10_000, 2_036, "holdout_figure1b"),
    ("i", 100_000, 18_155, "holdout_figure1b"),
    ("j", 100_000, 18_940, "holdout_figure1b"),
    ("k", 1_000_000, 178_767, "holdout_figure1b"),
    ("l", 1_000_000, 183_767, "holdout_figure1b"),
)


def _z_step(selected_z: int) -> int:
    return max(1, int(math.floor(selected_z / 5.0 + 0.5)))


def centered_axes(selected_a: float, selected_z: int) -> Tuple[Tuple[float, ...], Tuple[int, ...]]:
    a_values = tuple(selected_a + offset * A_STEP for offset in A_OFFSETS)
    step = _z_step(selected_z)
    z_values = tuple(selected_z + offset * step for offset in Z_OFFSETS)
    if not (0.0 <= a_values[0] < a_values[-1] < 1.0):
        raise ValueError("centered Figure 3 a axis is outside [0,1)")
    if z_values[0] < 0:
        raise ValueError("centered Figure 3 z axis contains a negative value")
    if a_values[CENTER_COLUMN] != selected_a:
        raise AssertionError("selected a is not the center column")
    if z_values[CENTER_ROW_ASCENDING] != selected_z:
        raise AssertionError("selected z is not the center row")
    return a_values, z_values


def panel_specs(
    panel: str,
    frozen: Mapping[str, Any],
    M: int,
) -> Tuple[Tuple[PlacementSpec, ...], Tuple[float, ...], Tuple[int, ...]]:
    prediction = frozen_holdout_spec(
        float(frozen["C_cal"]),
        float(frozen["gamma_cal"]),
        float(frozen["a_cal"]),
        M,
    )
    if not prediction.valid:
        raise ValueError("frozen Figure 3 prediction is invalid")
    a_values, z_values = centered_axes(prediction.a, prediction.z)
    specs: List[PlacementSpec] = []
    for z_index, z in enumerate(z_values):
        for a_index, a in enumerate(a_values):
            is_center = a_index == CENTER_COLUMN and z_index == CENTER_ROW_ASCENDING
            if is_center:
                specs.append(prediction)
            else:
                specs.append(
                    PlacementSpec(
                        candidate_id="figure3%s-r%02d-c%02d" % (panel, z_index, a_index),
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
    if len(specs) != len(a_values) * len(z_values):
        raise AssertionError("Figure 3 grid construction is incomplete")
    if sum(spec.is_frozen_prediction for spec in specs) != 1:
        raise AssertionError("Figure 3 must contain exactly one selected center")
    return tuple(specs), a_values, z_values


def figure3_config(
    frozen: Mapping[str, Any],
    frozen_sha256: str,
    engine_sha256: str,
    reference_holdout_sha256: str,
) -> Dict[str, Any]:
    panels = []
    for panel, d, M, domain in FIGURE3_PANELS:
        prediction = frozen_holdout_spec(
            float(frozen["C_cal"]), float(frozen["gamma_cal"]), float(frozen["a_cal"]), M
        )
        a_values, z_values = centered_axes(prediction.a, prediction.z)
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
                "center_column_zero_based": CENTER_COLUMN,
                "center_row_ascending_zero_based": CENTER_ROW_ASCENDING,
            }
        )
    return {
        "protocol_version": FIGURE3_PROTOCOL_VERSION,
        "kind": "post_freeze_appendix_figure3",
        "base_seed": const.BASE_SEED,
        "k": const.K,
        "ell": const.ELL,
        "trials_per_cell": FIGURE3_TRIALS,
        "grid_shape": [len(Z_OFFSETS), len(A_OFFSETS)],
        "a_step": A_STEP,
        "z_step_rule": "max(1,floor(selected_z/5+0.5))",
        "selected_cell": [CENTER_ROW_ASCENDING, CENTER_COLUMN],
        "layout": {"columns": 3, "rows": 4},
        "panels": panels,
        "frozen_parameters_sha256": frozen_sha256,
        "engine_sha256": engine_sha256,
        "reference_holdout_build_manifest_sha256": reference_holdout_sha256,
        "calibration_feedback": False,
    }


class Figure3Runner:
    def __init__(
        self,
        *,
        repo: Path,
        results_root: Path,
        frozen_parameters: Path,
        reference_holdout: Path,
        engine_executable: Path,
        resume: Optional[Path] = None,
    ) -> None:
        self.repo = repo.resolve()
        self.results_root = results_root.resolve()
        self.frozen_path = frozen_parameters.resolve()
        self.reference_holdout = reference_holdout.resolve()
        self.frozen, self.frozen_sha256 = load_selected_frozen(self.frozen_path)
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
            raise ValueError("Figure 3 engine differs from the completed holdout engine")
        holdout_summary = json.loads(
            (self.reference_holdout / "holdout_summary.json").read_text(encoding="utf-8")
        )
        if holdout_summary.get("frozen_parameters_sha256") != self.frozen_sha256:
            raise ValueError("reference holdout used different frozen parameters")
        self.repo_manifest = repository_manifest(self.repo)
        self.config = figure3_config(
            self.frozen,
            self.frozen_sha256,
            self.engine_sha256,
            sha256_file(reference_build_path),
        )
        self.config_sha256 = canonical_sha256(self.config)

        if resume is None:
            run_id = make_run_id("figure3", self.config_sha256, self.repo)
            path = self.results_root / "figure3" / run_id
            self.run = RunDirectory.create(
                path,
                "created",
                {
                    "run_id": run_id,
                    "kind": "post_freeze_appendix_figure3",
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
                """# Appendix Figure 3 source manifest

- Figure 3 protocol: `{protocol}`
- Git commit: `{commit}`
- Experiment source tree SHA-256: `{source}`
- Frozen parameters SHA-256: `{frozen}`
- Threshold SHA-256: `{threshold}`
- Simulator engine SHA-256: `{engine}`
- Reference holdout build manifest SHA-256: `{holdout_build}`

The selected cell is fixed before this run. Figure 3 data never feeds back into calibration.
The simulator executable is byte-identical to the completed sealed holdout executable.
""".format(
                    protocol=FIGURE3_PROTOCOL_VERSION,
                    commit=self.repo_manifest["git_commit"],
                    source=self.repo_manifest["source_tree_sha256"],
                    frozen=self.frozen_sha256,
                    threshold=self.threshold.sha256,
                    engine=self.engine_sha256,
                    holdout_build=sha256_file(reference_build_path),
                ),
                exclusive=True,
            )
            self.run_id = run_id
        else:
            self.run = RunDirectory.open_for_resume(resume.resolve())
            existing = json.loads((self.run.path / "run_config.json").read_text(encoding="utf-8"))
            if existing != self.config:
                raise ValueError("resume Figure 3 configuration differs from current configuration")
            identity = json.loads((self.run.path / "run_identity.json").read_text(encoding="utf-8"))
            self.run_id = str(identity["run_id"])
        self.checkpoints = PointCheckpointStore(self.run.path)

    def run_formal(self) -> Path:
        state = self.run.read_state()["status"]
        if state == "created":
            self.run.transition("created", "figure3_running")
        elif state != "figure3_running":
            raise RuntimeError("Figure 3 run is not resumable from state %s" % state)
        checkpoint_paths: List[Path] = []
        try:
            for panel, d, M, domain in FIGURE3_PANELS:
                specs, _a_values, _z_values = panel_specs(panel, self.frozen, M)
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
                    m_grid_phase="post_freeze_centered_grid",
                    rho=M / d,
                    engine=self.engine,
                )
                checkpoint_paths.append(self.checkpoints.path(stage, d, M))

            _concatenate_files(
                self.run.path / "trials.jsonl",
                (path / "trials.jsonl" for path in checkpoint_paths),
            )
            _concatenate_files(
                self.run.path / "placement_groups.jsonl",
                (path / "placement_groups.jsonl" for path in checkpoint_paths),
            )
            checkpoint_aggregate = list(_point_aggregate_rows(checkpoint_paths))
            aggregate = [
                {field: row.get(field) for field in const.AGGREGATE_FIELDS}
                for row in checkpoint_aggregate
            ]
            atomic_write_csv(self.run.path / "aggregate.csv", aggregate, const.AGGREGATE_FIELDS)
            selected = [row for row in aggregate if row["is_frozen_prediction"]]
            if len(selected) != len(FIGURE3_PANELS):
                raise RuntimeError("Figure 3 must contain one selected center per panel")
            summary_rows = []
            for row in selected:
                summary_rows.append(
                    {
                        "panel": str(row["stage"])[-1],
                        "d": row["d"],
                        "M": row["M"],
                        "a": row["a"],
                        "z_raw": row["z_raw"],
                        "z": row["z"],
                        "successes": row["successes"],
                        "trials": row["trials"],
                        "success_rate": row["success_rate"],
                        "ci_low": row["ci_low"],
                        "ci_high": row["ci_high"],
                    }
                )
            summary_rows.sort(key=lambda row: row["panel"])
            summary = {
                "status": "complete",
                "run_id": self.run_id,
                "protocol_version": FIGURE3_PROTOCOL_VERSION,
                "grid_shape": [len(Z_OFFSETS), len(A_OFFSETS)],
                "selected_cell": [CENTER_ROW_ASCENDING, CENTER_COLUMN],
                "frozen_parameters_sha256": self.frozen_sha256,
                "engine_sha256": self.engine_sha256,
                "calibration_feedback": False,
                "panels": summary_rows,
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
            atomic_write_json(self.run.path / "figure3_summary.json", summary, exclusive=True)
            self.run.transition("figure3_running", "complete", {"panel_count": len(summary_rows)})
            return self.run.path
        except Exception as error:
            self.run.record_error("%s: %s" % (type(error).__name__, error))
            current = self.run.read_state()["status"]
            if current == "figure3_running":
                self.run.transition(current, "failed", {"error_type": type(error).__name__})
            raise
