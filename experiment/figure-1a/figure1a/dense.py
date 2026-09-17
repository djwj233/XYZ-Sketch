"""Formal 100-trial dense scan and Figure 1(a) rendering."""

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

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
from .config import ConfigSpec, PanelParameters, load_frozen, load_thresholds, make_spec
from .engine import CppEngine
from .runner import (
    PointCheckpointStore,
    _read_json,
    _trial_row,
    aggregate_point,
    validate_formal_inputs,
)


BOUNDARY_STRATEGIES = ("transition", "literal_extrema", "plateau_platforms")


def dense_grid(
    coarse_curve: Mapping[str, Any],
    strategy: str,
) -> Tuple[Tuple[int, ...], Dict[str, Any]]:
    if strategy not in BOUNDARY_STRATEGIES:
        raise ValueError("unknown dense boundary strategy")
    ell = int(coarse_curve["ell"])
    step = const.DENSE_STEP[ell]
    if strategy in {"transition", "plateau_platforms"}:
        low = int(coarse_curve["maximum_M_p_le_005"])
        high = int(coarse_curve["minimum_M_p_ge_095"])
    else:
        low = int(coarse_curve["minimum_M_p_le_005"])
        high = int(coarse_curve["maximum_M_p_ge_095"])
    if high <= low:
        raise ValueError("dense success boundary does not follow the failure boundary")
    padding_steps = (
        const.PLATEAU_PADDING_STEPS if strategy == "plateau_platforms" else 5
    )
    start = low - padding_steps * step
    target_end = high + padding_steps * step
    if start <= 1:
        raise ValueError("dense lower plateau would produce an invalid M")
    intervals = int(math.ceil((target_end - start) / step))
    values = tuple(start + index * step for index in range(intervals + 1))
    return values, {
        "strategy": strategy,
        "coarse_low_M": low,
        "coarse_high_M": high,
        "dense_step": step,
        "padding_steps_each_side": padding_steps,
        "start_M": values[0],
        "target_end_M": target_end,
        "actual_end_M": values[-1],
        "end_alignment_overshoot": values[-1] - target_end,
        "point_count": len(values),
    }


def build_dense_config(
    coarse_artifact: Path,
    frozen: Mapping[str, Any],
    frozen_sha256: str,
    engine_sha256: str,
    strategy: str,
) -> Dict[str, Any]:
    state = _read_json(coarse_artifact / "run_state.json")
    summary = _read_json(coarse_artifact / "coarse_summary.json")
    candidates = _read_json(coarse_artifact / "dense_boundary_candidates.json")
    if state.get("status") != "coarse_complete" or summary.get("status") != "coarse_complete":
        raise ValueError("dense scan requires a completed coarse artifact")
    if not summary.get("all_nine_curves_bracketed") or len(candidates.get("curves", [])) != 9:
        raise ValueError("coarse artifact does not contain nine bracketed curves")
    if summary.get("formal_trials_reexecuted") is not False:
        raise ValueError("recovery provenance is missing")
    for name, expected in summary.get("artifact_sha256", {}).items():
        if sha256_file(coarse_artifact / name) != expected:
            raise ValueError("coarse recovery artifact hash mismatch: %s" % name)
    curves = []
    for coarse_curve in candidates["curves"]:
        values, boundary = dense_grid(coarse_curve, strategy)
        curves.append({
            "k": int(coarse_curve["k"]),
            "ell": int(coarse_curve["ell"]),
            "mode": str(coarse_curve["mode"]),
            "M_values": list(values),
            "boundary": boundary,
        })
    curves.sort(key=lambda row: (
        const.PANELS.index((row["k"], row["ell"])), const.MODES.index(row["mode"])
    ))
    return {
        "protocol_version": const.PROTOCOL_VERSION,
        "kind": "formal_dense_scan",
        "workload_label": "reduced-cardinality revision",
        "d": const.D,
        "set_size_A": const.SET_SIZE,
        "set_size_B": const.SET_SIZE,
        "common_size": const.COMMON_SIZE,
        "difference_A": const.ONE_DIRECTION,
        "difference_B": const.ONE_DIRECTION,
        "base_seed": const.BASE_SEED,
        "seed_phase": "dense",
        "trials_per_point": const.DENSE_TRIALS,
        "workers": const.WORKERS,
        "boundary_strategy": strategy,
        "boundary_semantics": (
            "minimum coarse M with p<=0.05 to maximum coarse M with p>=0.95"
            if strategy == "literal_extrema" else
            "largest coarse M with p<=0.05 to smallest later coarse M with p>=0.95"
        ),
        "dense_grid_alignment": (
            "anchor at lower boundary minus %d dense steps; ceil upper endpoint" %
            (const.PLATEAU_PADDING_STEPS if strategy == "plateau_platforms" else 5)
        ),
        "platform_requirement": {
            "leading_success_rate": 0.0,
            "trailing_success_rate": 1.0,
            "minimum_consecutive_points": const.PLATEAU_REQUIRED_CONSECUTIVE,
        },
        "curves": curves,
        "point_count": sum(len(curve["M_values"]) for curve in curves),
        "logical_point_trials": sum(len(curve["M_values"]) for curve in curves) * const.DENSE_TRIALS,
        "frozen_parameters_sha256": frozen_sha256,
        "coarse_artifact_path": str(coarse_artifact.resolve()),
        "coarse_summary_sha256": sha256_file(coarse_artifact / "coarse_summary.json"),
        "coarse_boundary_candidates_sha256": sha256_file(
            coarse_artifact / "dense_boundary_candidates.json"
        ),
        "engine_sha256": engine_sha256,
        "C_cal": float(frozen["C_cal"]),
        "gamma_cal": float(frozen["gamma_cal"]),
        "D_cal": float(frozen["D_cal"]),
        "delta": float(frozen["delta"]),
    }


def build_platform_completion_config(source_run: Path) -> Dict[str, Any]:
    source_run = source_run.resolve()
    state = _read_json(source_run / "run_state.json")
    summary = _read_json(source_run / "dense_summary.json")
    source = _read_json(source_run / "run_config.json")
    if state.get("status") != "complete" or summary.get("status") != "complete" \
            or not summary.get("all_points_have_100_trials"):
        raise ValueError("platform completion requires a completed dense run")
    summary_curves = {
        (int(row["k"]), int(row["ell"]), str(row["mode"])): row
        for row in summary.get("curves", [])
    }
    curves = []
    added_points = 0
    for source_curve in source.get("curves", []):
        curve = json.loads(json.dumps(source_curve))
        key = (int(curve["k"]), int(curve["ell"]), str(curve["mode"]))
        if key not in summary_curves:
            raise ValueError("platform completion source lacks a curve summary")
        row = summary_curves[key]
        values = [int(value) for value in curve["M_values"]]
        step = const.DENSE_STEP[key[1]]
        lower_count = 0
        upper_count = 0
        if int(row.get("leading_zero_points", 0)) < const.PLATEAU_REQUIRED_CONSECUTIVE:
            lower_count = const.PLATEAU_COMPLETION_BATCH_STEPS
            values = [values[0] - step * offset for offset in range(lower_count, 0, -1)] + values
        if int(row.get("trailing_one_points", 0)) < const.PLATEAU_REQUIRED_CONSECUTIVE:
            upper_count = const.PLATEAU_COMPLETION_BATCH_STEPS
            values += [values[-1] + step * offset for offset in range(1, upper_count + 1)]
        if values[0] <= 1:
            raise ValueError("platform completion would produce an invalid M")
        curve["M_values"] = values
        boundary = dict(curve.get("boundary", {}))
        boundary.update({
            "strategy": "platform_completion",
            "start_M": values[0],
            "actual_end_M": values[-1],
            "point_count": len(values),
            "completion_lower_points_added": lower_count,
            "completion_upper_points_added": upper_count,
        })
        curve["boundary"] = boundary
        added_points += lower_count + upper_count
        curves.append(curve)
    if added_points == 0:
        raise ValueError("all curves already satisfy the platform requirement")
    target = json.loads(json.dumps(source))
    target.pop("imported_dense", None)
    target.update({
        "kind": "formal_dense_platform_completion",
        "boundary_strategy": "platform_completion",
        "boundary_semantics": "extend only curve edges that fail the frozen 0/1 platform requirement",
        "dense_grid_alignment": "append ten dense steps per failing edge per completion round",
        "curves": curves,
        "point_count": sum(len(curve["M_values"]) for curve in curves),
        "logical_point_trials": sum(len(curve["M_values"]) for curve in curves) * const.DENSE_TRIALS,
        "completion_policy": {
            "source_run": str(source_run),
            "source_dense_summary_sha256": sha256_file(source_run / "dense_summary.json"),
            "batch_steps_per_failing_edge": const.PLATEAU_COMPLETION_BATCH_STEPS,
            "added_point_count": added_points,
        },
    })
    return target


class DenseRunner:
    def __init__(
        self,
        *,
        repo: Path,
        results_root: Path,
        frozen_path: Path,
        holdout_path: Path,
        coarse_artifact: Path,
        engine_path: Path,
        boundary_strategy: str,
        import_dense_run: Optional[Path] = None,
        resume: Optional[Path] = None,
    ) -> None:
        self.repo = repo.resolve()
        self.results_root = results_root.resolve()
        self.frozen_path = frozen_path.resolve()
        self.holdout_path = holdout_path.resolve()
        self.coarse_artifact = coarse_artifact.resolve()
        self.import_dense_run = import_dense_run.resolve() if import_dense_run else None
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
        self.config = (
            build_platform_completion_config(self.import_dense_run)
            if boundary_strategy == "platform_completion" and self.import_dense_run else
            build_dense_config(
                self.coarse_artifact, self.frozen, self.frozen_sha256,
                sha256_file(self.engine.executable), boundary_strategy,
            )
        )
        self.import_info = self._validate_import() if self.import_dense_run else None
        if self.import_info:
            self.config["imported_dense"] = self.import_info
        self.config_sha256 = canonical_sha256(self.config)
        if resume is None:
            run_id = make_run_id(self.config_sha256, self.repo).replace("figure1a-", "figure1a-dense-", 1)
            path = self.results_root / "dense" / run_id
            self.run = RunDirectory.create(path, {
                "run_id": run_id,
                "kind": "formal_dense_scan",
                "config_sha256": self.config_sha256,
                "frozen_parameters_sha256": self.frozen_sha256,
                "coarse_summary_sha256": self.config["coarse_summary_sha256"],
                "engine_sha256": self.config["engine_sha256"],
            })
            self.run_id = run_id
            atomic_write_json(path / "run_config.json", self.config, exclusive=True)
            atomic_write_json(path / "startup_gates.json", self.gates, exclusive=True)
            atomic_write_json(path / "build_manifest.json", build_manifest(self.engine.executable), exclusive=True)
            atomic_write_json(path / "environment_manifest.json", environment_manifest(), exclusive=True)
            atomic_write_json(path / "repository_manifest.json", self.repo_manifest, exclusive=True)
            atomic_write_text(path / "source_manifest.md", self._source_manifest(), exclusive=True)
        else:
            self.run = RunDirectory.resume(resume.resolve())
            identity = _read_json(self.run.path / "run_identity.json")
            if _read_json(self.run.path / "run_config.json") != self.config \
                    or identity.get("config_sha256") != self.config_sha256:
                raise ValueError("resume dense configuration differs")
            self.run_id = str(identity["run_id"])
        self.checkpoints = PointCheckpointStore(
            self.run.path, phase="dense", expected_trials=const.DENSE_TRIALS
        )
        if self.import_dense_run:
            self._import_completed_trials()

    def _validate_import(self) -> Dict[str, Any]:
        assert self.import_dense_run is not None
        source = self.import_dense_run
        state = _read_json(source / "run_state.json")
        summary = _read_json(source / "dense_summary.json")
        config = _read_json(source / "run_config.json")
        if state.get("status") != "complete" or summary.get("status") != "complete" \
                or not summary.get("all_points_have_100_trials"):
            raise ValueError("dense import source is not complete")
        for name, expected in summary.get("artifact_sha256", {}).items():
            if sha256_file(source / name) != expected:
                raise ValueError("dense import artifact hash mismatch: %s" % name)
        for field in (
            "protocol_version", "d", "set_size_A", "set_size_B", "common_size",
            "difference_A", "difference_B", "trials_per_point", "seed_phase",
            "frozen_parameters_sha256", "engine_sha256",
        ):
            if config.get(field) != self.config.get(field):
                raise ValueError("dense import configuration differs: %s" % field)
        target = {
            (int(curve["k"]), int(curve["ell"]), str(curve["mode"])):
            {int(value) for value in curve["M_values"]}
            for curve in self.config["curves"]
        }
        imported_points = 0
        for curve in config.get("curves", []):
            key = (int(curve["k"]), int(curve["ell"]), str(curve["mode"]))
            values = {int(value) for value in curve["M_values"]}
            if key not in target or not values <= target[key]:
                raise ValueError("dense import grid is not a subset of the target grid")
            imported_points += len(values)
        if imported_points != int(summary["point_count"]):
            raise ValueError("dense import point count mismatch")
        return {
            "source_run": str(source),
            "source_run_id": str(summary["run_id"]),
            "source_run_config_sha256": sha256_file(source / "run_config.json"),
            "source_dense_summary_sha256": sha256_file(source / "dense_summary.json"),
            "source_trials_sha256": sha256_file(source / "trials.jsonl"),
            "imported_point_count": imported_points,
            "imported_trial_count": imported_points * const.DENSE_TRIALS,
            "metadata_normalization": "run_id rewritten to target run id; all statistical fields unchanged",
        }

    def _import_completed_trials(self) -> None:
        assert self.import_dense_run is not None and self.import_info is not None
        specs = {(spec.k, spec.ell, spec.mode, spec.M): spec for spec in self._all_specs()}
        grouped: Dict[Tuple[int, int, str, int], List[Dict[str, Any]]] = {}
        with (self.import_dense_run / "trials.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                key = (int(row["k"]), int(row["ell"]), str(row["mode"]), int(row["M"]))
                if key not in specs:
                    raise ValueError("dense import contains a point outside the target grid")
                row["run_id"] = self.run_id
                grouped.setdefault(key, []).append(row)
        if len(grouped) != int(self.import_info["imported_point_count"]):
            raise ValueError("dense import grouped point count mismatch")
        for key, rows in grouped.items():
            self.checkpoints.import_complete(specs[key], rows)

    def _source_manifest(self) -> str:
        return """# Figure 1(a) dense source manifest

- Protocol: `{protocol}`
- Workload: reduced-cardinality revision, `d=10000`, `|A|=|B|=20000`
- Boundary strategy: `{strategy}`
- Imported dense run: `{imported}`
- Coarse summary SHA-256: `{coarse}`
- Frozen parameters SHA-256: `{frozen}`
- Threshold SHA-256: `{threshold}`
- Engine SHA-256: `{engine}`
- Source SHA-256: `{source}`

All plotted points use 100 dense-domain trials through the complete real XYZ-Sketch path.
No coarse trial is combined with the formal dense statistics. A completed dense point may be
imported only after its bound trials artifact is verified; only its run-id metadata is normalized.
""".format(
            protocol=const.PROTOCOL_VERSION,
            strategy=self.config["boundary_strategy"],
            imported=self.import_dense_run if self.import_dense_run else "none",
            coarse=self.config["coarse_summary_sha256"],
            frozen=self.frozen_sha256,
            threshold=const.EXPECTED_THRESHOLD_SHA256,
            engine=self.config["engine_sha256"],
            source=self.repo_manifest["figure1a_and_core_source_sha256"],
        )

    def _all_specs(self) -> List[ConfigSpec]:
        specs = []
        for curve in self.config["curves"]:
            parameters = self.parameters[(curve["k"], curve["ell"])]
            specs.extend(make_spec(parameters, curve["mode"], M) for M in curve["M_values"])
        return sorted(specs, key=lambda spec: (
            const.PANELS.index((spec.k, spec.ell)), const.MODES.index(spec.mode), spec.M
        ))

    def _evaluate(self) -> None:
        specs = self._all_specs()
        for k, ell in const.PANELS:
            panel_specs = [spec for spec in specs if (spec.k, spec.ell) == (k, ell)]
            for trial_index in range(const.DENSE_TRIALS):
                missing = [spec for spec in panel_specs if self.checkpoints.missing(spec, trial_index)]
                if not missing:
                    continue
                evaluated = self.engine.evaluate(
                    phase="dense", k=k, ell=ell, trial_index=trial_index,
                    specs=missing, workers=const.WORKERS,
                )
                for spec in missing:
                    self.checkpoints.add(spec, _trial_row(
                        run_id=self.run_id,
                        git_commit=self.repo_manifest["git_commit"],
                        spec=spec,
                        dataset=evaluated.dataset,
                        result=evaluated.results[spec.config_id],
                        phase="dense",
                    ))

    def _aggregates(self) -> List[Dict[str, Any]]:
        return [aggregate_point(
            spec, self.checkpoints.trials(spec),
            phase="dense", expected_trials=const.DENSE_TRIALS,
        ) for spec in self._all_specs()]

    @staticmethod
    def _first(rows: Sequence[Mapping[str, Any]], field: str, threshold: float) -> Optional[Dict[str, Any]]:
        for row in rows:
            if float(row[field]) >= threshold:
                return {"M": int(row["M"]), "R_w30": float(row["R_w30"]), field: float(row[field])}
        return None

    def _summary_curves(self, aggregates: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        curves = []
        for k, ell in const.PANELS:
            for mode in const.MODES:
                rows = sorted(
                    (row for row in aggregates if (
                        int(row["k"]), int(row["ell"]), str(row["mode"])
                    ) == (k, ell, mode)),
                    key=lambda row: int(row["M"]),
                )
                first_01 = self._first(rows, "success_rate", 0.1)
                first_09 = self._first(rows, "success_rate", 0.9)
                decreases = []
                for left, right in zip(rows, rows[1:]):
                    drop = float(left["success_rate"]) - float(right["success_rate"])
                    if drop > 0:
                        decreases.append({
                            "left_M": int(left["M"]), "right_M": int(right["M"]), "drop": drop,
                        })
                leading_zero = 0
                for row in rows:
                    if float(row["success_rate"]) != 0.0:
                        break
                    leading_zero += 1
                trailing_one = 0
                for row in reversed(rows):
                    if float(row["success_rate"]) != 1.0:
                        break
                    trailing_one += 1
                curves.append({
                    "k": k,
                    "ell": ell,
                    "mode": mode,
                    "points": len(rows),
                    "leading_zero_points": leading_zero,
                    "trailing_one_points": trailing_one,
                    "platform_requirement_passed": (
                        leading_zero >= const.PLATEAU_REQUIRED_CONSECUTIVE and
                        trailing_one >= const.PLATEAU_REQUIRED_CONSECUTIVE
                    ),
                    "first_p_ge_05": self._first(rows, "success_rate", 0.5),
                    "first_p_ge_09": first_09,
                    "first_wilson_low_ge_09": self._first(rows, "ci_low", 0.9),
                    "transition_width_R_01_to_09": (
                        first_09["R_w30"] - first_01["R_w30"]
                        if first_01 is not None and first_09 is not None else None
                    ),
                    "adjacent_empirical_decreases": decreases,
                })
        return curves

    def _write_outputs(self, aggregates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        trials = []
        for spec in self._all_specs():
            trials.extend(self.checkpoints.trials(spec))
        trials.sort(key=lambda row: (
            const.PANELS.index((int(row["k"]), int(row["ell"]))),
            const.MODES.index(str(row["mode"])), int(row["M"]), int(row["trial_index"]),
        ))
        rows = [dict(row) for row in aggregates]
        atomic_write_jsonl(self.run.path / "trials.jsonl", trials)
        atomic_write_jsonl(self.run.path / "aggregate.jsonl", rows)
        atomic_write_csv(self.run.path / "aggregate.csv", rows, const.AGGREGATE_FIELDS)
        curve_summaries = self._summary_curves(rows)
        summary = {
            "status": "complete",
            "run_id": self.run_id,
            "protocol_version": const.PROTOCOL_VERSION,
            "workload_label": "reduced-cardinality revision",
            "boundary_strategy": self.config["boundary_strategy"],
            "point_count": len(rows),
            "trial_row_count": len(trials),
            "all_points_have_100_trials": len(trials) == len(rows) * const.DENSE_TRIALS,
            "imported_point_count": (
                int(self.import_info["imported_point_count"]) if self.import_info else 0
            ),
            "new_point_count": len(rows) - (
                int(self.import_info["imported_point_count"]) if self.import_info else 0
            ),
            "platform_requirement": self.config["platform_requirement"],
            "all_curves_have_required_platforms": all(
                curve["platform_requirement_passed"] for curve in curve_summaries
            ),
            "curves": curve_summaries,
            "artifact_sha256": {
                name: sha256_file(self.run.path / name)
                for name in (
                    "run_config.json", "trials.jsonl", "aggregate.jsonl", "aggregate.csv",
                    "startup_gates.json", "source_manifest.md", "build_manifest.json",
                    "environment_manifest.json", "repository_manifest.json",
                )
            },
        }
        atomic_write_json(self.run.path / "dense_summary.json", summary)
        return summary

    def run_formal(self) -> Path:
        state = self.run.read_state()["status"]
        if state == "created":
            self.run.transition("created", "dense_running")
        elif state != "dense_running":
            raise RuntimeError("dense run is not active")
        try:
            self._evaluate()
            summary = self._write_outputs(self._aggregates())
            self.run.transition("dense_running", "complete", {
                "point_count": summary["point_count"],
                "trial_row_count": summary["trial_row_count"],
            })
            return self.run.path
        except Exception as error:
            self.run.record_error("%s: %s" % (type(error).__name__, error))
            if self.run.read_state()["status"] == "dense_running":
                self.run.transition("dense_running", "failed", {"error_type": type(error).__name__})
            raise
