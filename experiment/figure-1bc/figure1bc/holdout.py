"""Sealed Figure 1(b)(c) holdout runner (data only; plotting is separate)."""

import json
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
    make_run_id,
    environment_manifest,
    repository_manifest,
    sha256_file,
)
from .calibration import PointCheckpointStore, _concatenate_files, _point_aggregate_rows
from .engine import CppEngine
from .evaluation import PointEvaluation, evaluate_point
from .model import PlacementSpec, direct_holdout_spec, frozen_holdout_spec
from .threshold import load_threshold


def load_selected_frozen(path: Path) -> Tuple[Dict[str, Any], str]:
    frozen = json.loads(path.read_text(encoding="utf-8"))
    if frozen.get("status") != "selected":
        raise ValueError("holdout requires frozen_parameters.json with status=selected")
    if frozen.get("protocol_version") != const.PROTOCOL_VERSION:
        raise ValueError("frozen parameters use a different protocol version")
    required = {
        "C_cal",
        "gamma_cal",
        "D_cal",
        "delta",
        "a_cal",
        "config_sha256",
        "source_tree_sha256",
        "threshold_sha256",
        "selection_score",
    }
    missing = sorted(required - set(frozen))
    if missing:
        raise ValueError("frozen parameters missing fields: %s" % ", ".join(missing))
    if float(frozen["delta"]) != const.DELTA:
        raise ValueError("frozen delta differs from the audited protocol")
    return frozen, sha256_file(path)


def holdout_specs(frozen: Mapping[str, Any], M: int) -> Tuple[PlacementSpec, ...]:
    prediction = frozen_holdout_spec(
        float(frozen["C_cal"]),
        float(frozen["gamma_cal"]),
        float(frozen["a_cal"]),
        M,
    )
    specs: List[PlacementSpec] = []
    prediction_is_base = False
    for a_units in const.HOLDOUT_A_UNITS:
        for z in const.HOLDOUT_Z:
            direct = direct_holdout_spec(a_units, z)
            if direct.a == prediction.a and direct.z == prediction.z:
                direct = PlacementSpec(
                    candidate_id=direct.candidate_id,
                    C=prediction.C,
                    gamma=prediction.gamma,
                    a=direct.a,
                    z_raw=prediction.z_raw,
                    z=direct.z,
                    valid=prediction.valid,
                    status=prediction.status,
                    is_frozen_prediction=True,
                )
                prediction_is_base = True
            specs.append(direct)
    if not prediction_is_base:
        specs.append(prediction)
    return tuple(specs)


class HoldoutRunner:
    def __init__(
        self,
        *,
        repo: Path,
        results_root: Path,
        frozen_parameters: Path,
        engine_executable: Path,
    ) -> None:
        self.repo = repo.resolve()
        self.results_root = results_root.resolve()
        self.frozen_path = frozen_parameters.resolve()
        self.frozen, self.frozen_sha256 = load_selected_frozen(self.frozen_path)
        self.threshold = load_threshold()
        if self.frozen["threshold_sha256"] != self.threshold.sha256:
            raise ValueError("frozen parameters reference a different threshold artifact")
        self.repo_manifest = repository_manifest(self.repo)
        if self.frozen["source_tree_sha256"] != self.repo_manifest["source_tree_sha256"]:
            raise ValueError("holdout source tree differs from the frozen calibration source")
        self.engine = CppEngine(engine_executable)
        self.config = {
            "protocol_version": const.PROTOCOL_VERSION,
            "kind": "sealed_holdout",
            "base_seed": const.BASE_SEED,
            "k": const.K,
            "ell": const.ELL,
            "trials_per_cell": const.HOLDOUT_TRIALS,
            "base_a_units": list(const.HOLDOUT_A_UNITS),
            "base_z": list(const.HOLDOUT_Z),
            "scales": [
                {
                    "figure": figure,
                    "domain": domain,
                    "d": d,
                    "M": M,
                    "label": label,
                }
                for figure, domain, d, M, label in const.HOLDOUT_SCALES
            ],
            "frozen_parameters_sha256": self.frozen_sha256,
            "threshold_sha256": self.threshold.sha256,
        }
        self.config_sha256 = canonical_sha256(self.config)
        run_id = make_run_id("figure1bc-holdout", self.config_sha256, self.repo)
        path = self.results_root / "holdout" / run_id
        self.run = RunDirectory.create(
            path,
            "created",
            {
                "run_id": run_id,
                "kind": "sealed_holdout",
                "config_sha256": self.config_sha256,
                "source_tree_sha256": self.repo_manifest["source_tree_sha256"],
                "frozen_parameters_sha256": self.frozen_sha256,
                "engine_sha256": sha256_file(self.engine.executable),
            },
        )
        self.run_id = run_id
        self.checkpoints = PointCheckpointStore(path)
        atomic_write_json(path / "run_config.json", self.config, exclusive=True)
        atomic_write_text(
            path / "source_manifest.md",
            """# Figure 1(b)(c) sealed holdout source manifest

- Protocol version: `{protocol}`
- Git commit: `{commit}`
- Experiment source tree SHA-256: `{source}`
- Threshold SHA-256: `{threshold}`
- Frozen parameters SHA-256: `{frozen}`
- C++ engine SHA-256: `{engine}`

Both holdout scales share this run identity and use separate audited seed domains.
""".format(
                protocol=const.PROTOCOL_VERSION,
                commit=self.repo_manifest["git_commit"],
                source=self.repo_manifest["source_tree_sha256"],
                threshold=self.threshold.sha256,
                frozen=self.frozen_sha256,
                engine=sha256_file(self.engine.executable),
            ),
            exclusive=True,
        )
        atomic_write_json(
            path / "build_manifest.json",
            build_manifest(self.engine.executable),
            exclusive=True,
        )
        atomic_write_json(
            path / "environment_manifest.json",
            environment_manifest(),
            exclusive=True,
        )

    def run_formal(self) -> Path:
        self.run.transition("created", "holdout_running")
        checkpoint_paths: List[Path] = []
        try:
            for figure, domain, d, M, _label in const.HOLDOUT_SCALES:
                if d < 3000:
                    raise RuntimeError("holdout data must satisfy d>=3000")
                specs = holdout_specs(self.frozen, M)
                evaluation = self.checkpoints.evaluate_or_load(
                    figure,
                    d,
                    M,
                    run_id=self.run_id,
                    domain=domain,
                    specs=specs,
                    trials=const.HOLDOUT_TRIALS,
                    threshold_sha256=self.threshold.sha256,
                    m_grid_phase="holdout_grid+frozen_prediction",
                    rho=M / d,
                    engine=self.engine,
                )
                checkpoint_paths.append(self.checkpoints.path(figure, d, M))

            _concatenate_files(
                self.run.path / "trials.jsonl",
                (path / "trials.jsonl" for path in checkpoint_paths),
            )
            _concatenate_files(
                self.run.path / "placement_groups.jsonl",
                (path / "placement_groups.jsonl" for path in checkpoint_paths),
            )
            aggregate = list(_point_aggregate_rows(checkpoint_paths))
            atomic_write_csv(
                self.run.path / "aggregate.csv", aggregate, const.AGGREGATE_FIELDS
            )
            predictions = [row for row in aggregate if row["is_frozen_prediction"]]
            if len(predictions) != len(const.HOLDOUT_SCALES):
                raise RuntimeError("holdout must contain one frozen prediction per scale")
            prediction_summary = []
            all_passed = True
            for row in predictions:
                passed = (
                    int(row["successes"]) * const.TARGET_SUCCESS_DENOMINATOR
                    >= const.TARGET_SUCCESS_NUMERATOR * int(row["trials"])
                )
                all_passed = all_passed and passed
                prediction_summary.append(
                    {
                        "domain": row["domain"],
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
                        "passed": passed,
                    }
                )
            summary = {
                "status": "complete",
                "run_id": self.run_id,
                "frozen_parameters_sha256": self.frozen_sha256,
                "frozen_predictions_passed": all_passed,
                "downstream_experiments_unlocked": all_passed,
                "predictions": prediction_summary,
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
            atomic_write_json(self.run.path / "holdout_summary.json", summary)
            self.run.transition(
                "holdout_running",
                "complete",
                {
                    "frozen_predictions_passed": all_passed,
                    "downstream_experiments_unlocked": all_passed,
                },
            )
            return self.run.path
        except Exception as error:
            self.run.record_error("%s: %s" % (type(error).__name__, error))
            current = self.run.read_state()["status"]
            if current == "holdout_running":
                self.run.transition(current, "failed", {"error_type": type(error).__name__})
            raise
