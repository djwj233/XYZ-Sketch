"""Formal fixed-point relative C/D selection and freezing.

This module implements the versioned state machine.  Every costly
``(stage,d,M)`` point is first committed as an atomic checkpoint directory so
an interrupted nonterminal run can later be resumed without rerunning a
completed point.
"""

import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

from . import constants as const
from .artifacts import (
    RunDirectory,
    atomic_write_bytes,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_text,
    build_manifest,
    canonical_json_bytes,
    canonical_sha256,
    make_run_id,
    environment_manifest,
    repository_manifest,
    sha256_file,
)
from .config import (
    CalibrationConfig,
    broad_fine_candidate_grid,
    coarse_candidate_grid,
    dense_rho_grid,
    next_upper_band,
    round_ratio_times_d,
)
from .evaluation import PointEvaluation, evaluate_point
from .engine import CppEngine
from .model import CalibrationCandidate
from .relative import RelativeScore, relative_score_candidates, relative_score_point_rows
from .threshold import Threshold, load_threshold


@dataclass
class MPoint:
    d: int
    M: int
    requested_rho_units: Set[int] = field(default_factory=set)
    phases: Set[str] = field(default_factory=set)
    classification: Optional[str] = None

    @property
    def phase_label(self) -> str:
        return "+".join(sorted(self.phases))

    @property
    def rho(self) -> float:
        return self.M / self.d


@dataclass(frozen=True)
class Bracket:
    d: int
    zero_M: int
    one_M: int
    rho_zero_units: int
    rho_one_units: int


def add_rho_points(points: Dict[int, MPoint], d: int, rho_units: Iterable[int], phase: str) -> List[MPoint]:
    added: List[MPoint] = []
    for rho in rho_units:
        M = round_ratio_times_d(rho, d)
        point = points.get(M)
        if point is None:
            point = MPoint(d=d, M=M)
            points[M] = point
            added.append(point)
        point.requested_rho_units.add(rho)
        point.phases.add(phase)
    return sorted(added, key=lambda point: point.M)


def identify_bracket(points: Mapping[int, MPoint]) -> Optional[Bracket]:
    ordered = [points[M] for M in sorted(points)]
    if not ordered or any(point.classification is None for point in ordered):
        return None
    if ordered[0].classification != "global_zero":
        return None
    zero = ordered[0]
    for point in ordered[1:]:
        if point.classification != "global_zero":
            break
        zero = point
    if ordered[-1].classification != "global_one":
        return None
    one = ordered[-1]
    for point in reversed(ordered[:-1]):
        if point.classification != "global_one":
            break
        one = point
    rho_zero = max(zero.requested_rho_units)
    rho_one = min(one.requested_rho_units)
    if zero.M >= one.M or rho_zero >= rho_one:
        return None
    return Bracket(zero.d, zero.M, one.M, rho_zero, rho_one)


class PointCheckpointStore:
    def __init__(self, run_path: Path) -> None:
        self.root = run_path / "_checkpoints"

    def path(self, stage: str, d: int, M: int) -> Path:
        return self.root / stage / ("d-%06d" % d) / ("M-%08d" % M)

    def load(self, stage: str, d: int, M: int) -> Optional[PointEvaluation]:
        path = self.path(stage, d, M)
        marker = path / "complete.json"
        if not marker.exists():
            return None
        marker_value = json.loads(marker.read_text(encoding="utf-8"))
        if marker_value != {"status": "complete"}:
            raise RuntimeError("checkpoint completion marker is invalid at %s" % path)
        aggregate = json.loads((path / "aggregate.json").read_text(encoding="utf-8"))
        groups = [
            json.loads(line)
            for line in (path / "placement_groups.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        trials = [
            json.loads(line)
            for line in (path / "trials.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        classifications = {row["global_classification"] for row in aggregate}
        if len(classifications) != 1:
            raise RuntimeError("checkpoint has inconsistent classifications")
        return PointEvaluation(
            tuple(trials), tuple(groups), tuple(aggregate), classifications.pop()
        )

    def save(self, stage: str, d: int, M: int, evaluation: PointEvaluation) -> Path:
        final_path = self.path(stage, d, M)
        if final_path.exists():
            raise FileExistsError(str(final_path))
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = Path(tempfile.mkdtemp(prefix=".point-", dir=str(final_path.parent)))
        try:
            atomic_write_bytes(
                temporary_path / "trials.jsonl",
                b"".join(canonical_json_bytes(row) for row in evaluation.trial_rows),
            )
            atomic_write_json(temporary_path / "aggregate.json", list(evaluation.aggregate_rows))
            atomic_write_bytes(
                temporary_path / "placement_groups.jsonl",
                b"".join(canonical_json_bytes(row) for row in evaluation.group_rows),
            )
            atomic_write_json(
                temporary_path / "complete.json",
                {"status": "complete"},
            )
            os.replace(str(temporary_path), str(final_path))
        finally:
            if temporary_path.exists():
                shutil.rmtree(str(temporary_path))
        return final_path

    def evaluate_or_load(self, stage: str, d: int, M: int, **kwargs: Any) -> PointEvaluation:
        cached = self.load(stage, d, M)
        if cached is not None:
            return cached
        evaluation = evaluate_point(stage=stage, d=d, M=M, **kwargs)
        self.save(stage, d, M, evaluation)
        return evaluation

    def iter_paths(self, stages: Sequence[str]) -> Iterator[Path]:
        for stage in stages:
            stage_root = self.root / stage
            if not stage_root.exists():
                continue
            paths = list(stage_root.glob("d-*/M-*"))
            paths.sort(
                key=lambda path: (
                    int(path.parent.name.split("-")[1]),
                    int(path.name.split("-")[1]),
                )
            )
            yield from paths


def _concatenate_files(output: Path, inputs: Iterable[Path]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".%s." % output.name, dir=str(output.parent))
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as target:
            for source in inputs:
                with source.open("rb") as stream:
                    shutil.copyfileobj(stream, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        os.replace(str(temporary_path), str(output))
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _point_aggregate_rows(paths: Iterable[Path]) -> Iterator[Dict[str, Any]]:
    for path in paths:
        rows = json.loads((path / "aggregate.json").read_text(encoding="utf-8"))
        for row in rows:
            yield row


def _source_manifest_text(repo_manifest: Mapping[str, str], threshold: Threshold) -> str:
    return """# Figure 1(b)(c) source manifest

- Protocol version: `{protocol_version}`
- Git commit: `{git_commit}`
- Git short SHA: `{git_short_sha}`
- Tracked diff SHA-256: `{tracked_diff_sha256}`
- Experiment source tree SHA-256: `{source_tree_sha256}`
- Threshold SHA-256: `{threshold_sha256}`
- Threshold entries: `{threshold_entries}`
- Seed rule: `{seed_rule}`
- Placement word stream: `{stream_rule}`

The simulator is independent and does not import or link the XYZ-Sketch core.
""".format(
        protocol_version=const.PROTOCOL_VERSION,
        git_commit=repo_manifest["git_commit"],
        git_short_sha=repo_manifest["git_short_sha"],
        tracked_diff_sha256=repo_manifest["tracked_diff_sha256"],
        source_tree_sha256=repo_manifest["source_tree_sha256"],
        threshold_sha256=threshold.sha256,
        threshold_entries=const.EXPECTED_THRESHOLD_ENTRIES,
        seed_rule=const.SEED_RULE_VERSION,
        stream_rule=const.PLACEMENT_WORD_STREAM_VERSION,
    )


class CalibrationRunner:
    def __init__(
        self,
        *,
        repo: Path,
        results_root: Path,
        engine_executable: Path,
        resume: Optional[Path] = None,
    ) -> None:
        self.repo = repo.resolve()
        self.results_root = results_root.resolve()
        self.config = CalibrationConfig()
        self.config.validate_formal()
        self.threshold = load_threshold()
        self.config_value = self.config.to_dict()
        self.config_sha256 = canonical_sha256(self.config_value)
        self.repo_manifest = repository_manifest(self.repo)
        self.engine = CppEngine(engine_executable)

        if resume is None:
            run_id = make_run_id("figure1bc-calibration", self.config_sha256, self.repo)
            path = self.results_root / "calibration" / run_id
            identity = {
                "run_id": run_id,
                "kind": "formal_calibration",
                "config_sha256": self.config_sha256,
                "source_tree_sha256": self.repo_manifest["source_tree_sha256"],
                "threshold_sha256": self.threshold.sha256,
                "engine_sha256": sha256_file(self.engine.executable),
            }
            self.run = RunDirectory.create(path, "created", identity)
            atomic_write_json(path / "calibration_config.json", self.config_value, exclusive=True)
            atomic_write_text(
                path / "source_manifest.md",
                _source_manifest_text(self.repo_manifest, self.threshold),
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
        else:
            self.run = RunDirectory.open_for_resume(resume.resolve())
            identity = json.loads((self.run.path / "run_identity.json").read_text(encoding="utf-8"))
            if identity.get("config_sha256") != self.config_sha256:
                raise ValueError("resume config hash differs from the audited formal config")
            if identity.get("source_tree_sha256") != self.repo_manifest["source_tree_sha256"]:
                raise ValueError("resume source tree hash differs from the original run")
        self.run_id = json.loads(
            (self.run.path / "run_identity.json").read_text(encoding="utf-8")
        )["run_id"]
        self.checkpoints = PointCheckpointStore(self.run.path)

    def _candidate_specs(self, candidates: Sequence[CalibrationCandidate], M: int) -> List[Any]:
        return [candidate.placement(M, self.threshold) for candidate in candidates]

    def _evaluate_m_point(
        self,
        *,
        stage: str,
        domain: str,
        point: MPoint,
        candidates: Sequence[CalibrationCandidate],
        trials: int,
    ) -> PointEvaluation:
        evaluation = self.checkpoints.evaluate_or_load(
            stage,
            point.d,
            point.M,
            run_id=self.run_id,
            domain=domain,
            specs=self._candidate_specs(candidates, point.M),
            trials=trials,
            threshold_sha256=self.threshold.sha256,
            m_grid_phase=point.phase_label,
            rho=point.rho,
            engine=self.engine,
        )
        point.classification = evaluation.classification
        return evaluation

    def _discover_bracket_for_d(
        self, d: int, candidates: Sequence[CalibrationCandidate]
    ) -> Tuple[Dict[int, MPoint], Optional[Bracket]]:
        points: Dict[int, MPoint] = {}
        initial = add_rho_points(points, d, const.INITIAL_RHO_UNITS, "initial")
        for point in initial:
            self._evaluate_m_point(
                stage="coarse",
                domain="calibration_coarse",
                point=point,
                candidates=candidates,
                trials=const.CALIBRATION_TRIALS,
            )

        bracket = identify_bracket(points)
        if bracket is None and points[min(points)].classification != "global_zero":
            for rho in const.LOWER_EXPANSION_RHO_UNITS:
                added = add_rho_points(points, d, (rho,), "lower_expansion")
                for point in added:
                    self._evaluate_m_point(
                        stage="coarse",
                        domain="calibration_coarse",
                        point=point,
                        candidates=candidates,
                        trials=const.CALIBRATION_TRIALS,
                    )
                if points[min(points)].classification == "global_zero":
                    break

        while points[max(points)].classification != "global_one":
            previous_max = max(max(point.requested_rho_units) for point in points.values())
            band = next_upper_band(previous_max)
            if not band:
                break
            added = add_rho_points(points, d, band, "upper_expansion")
            for point in added:
                self._evaluate_m_point(
                    stage="coarse",
                    domain="calibration_coarse",
                    point=point,
                    candidates=candidates,
                    trials=const.CALIBRATION_TRIALS,
                )
        return points, identify_bracket(points)

    def _write_bracket_artifact(
        self,
        all_points: Mapping[int, Mapping[int, MPoint]],
        brackets: Mapping[int, Bracket],
    ) -> None:
        rows = []
        for d in sorted(all_points):
            bracket = brackets.get(d)
            for M in sorted(all_points[d]):
                point = all_points[d][M]
                rows.append(
                    {
                        "d": d,
                        "M": M,
                        "rho": point.rho,
                        "requested_rho_units": ";".join(
                            str(value) for value in sorted(point.requested_rho_units)
                        ),
                        "m_grid_phase": point.phase_label,
                        "global_classification": point.classification,
                        "is_zero_prefix_endpoint": bool(bracket and M == bracket.zero_M),
                        "is_one_suffix_endpoint": bool(bracket and M == bracket.one_M),
                        "rho_zero_units": bracket.rho_zero_units if bracket else "",
                        "rho_one_units": bracket.rho_one_units if bracket else "",
                    }
                )
        fields = (
            "d",
            "M",
            "rho",
            "requested_rho_units",
            "m_grid_phase",
            "global_classification",
            "is_zero_prefix_endpoint",
            "is_one_suffix_endpoint",
            "rho_zero_units",
            "rho_one_units",
        )
        atomic_write_csv(self.run.path / "m_bracket.csv", rows, fields)

    def _fine_points(
        self,
        all_points: Mapping[int, Mapping[int, MPoint]],
        brackets: Mapping[int, Bracket],
    ) -> Dict[int, Dict[int, MPoint]]:
        result: Dict[int, Dict[int, MPoint]] = {}
        for d in const.TRAINING_D:
            copied: Dict[int, MPoint] = {}
            for M, source in all_points[d].items():
                copied[M] = MPoint(
                    d=d,
                    M=M,
                    requested_rho_units=set(source.requested_rho_units),
                    phases=set(source.phases),
                )
            bracket = brackets[d]
            dense = dense_rho_grid(bracket.rho_zero_units, bracket.rho_one_units)
            add_rho_points(copied, d, dense, "dense")
            result[d] = copied
        return result

    def _aggregate_for_stages(self, stages: Sequence[str]) -> List[Dict[str, Any]]:
        return list(_point_aggregate_rows(self.checkpoints.iter_paths(stages)))

    def _relative_score_stage(
        self, stage: str
    ) -> Tuple[RelativeScore, List[Dict[str, Any]]]:
        paths = self.checkpoints.iter_paths((stage,))
        batches = (
            json.loads((path / "aggregate.json").read_text(encoding="utf-8"))
            for path in paths
        )
        return relative_score_point_rows(batches)

    def _compile_discovery_artifacts(
        self,
        final_fine_stage: str,
        coarse_scores: List[Dict[str, Any]],
        final_scores: List[Dict[str, Any]],
        expansion_history: Sequence[Mapping[str, Any]],
    ) -> None:
        discovery_paths = list(self.checkpoints.iter_paths(("coarse", final_fine_stage)))
        _concatenate_files(
            self.run.path / "trials.jsonl", (path / "trials.jsonl" for path in discovery_paths)
        )
        _concatenate_files(
            self.run.path / "placement_groups.jsonl",
            (path / "placement_groups.jsonl" for path in discovery_paths),
        )
        atomic_write_csv(
            self.run.path / "aggregate.csv",
            _point_aggregate_rows(discovery_paths),
            const.AGGREGATE_FIELDS,
        )
        relative_rows = []
        for stage, rows in (("coarse", coarse_scores), ("fine_final", final_scores)):
            for row in rows:
                relative_rows.append({"stage": stage, **row})
        atomic_write_csv(
            self.run.path / "relative_scores.csv",
            relative_rows,
            const.RELATIVE_SCORE_FIELDS,
        )
        atomic_write_json(
            self.run.path / "relative_selection.json",
            {
                "selection_rule": self.config_value["selection_rule"],
                "expansion_history": list(expansion_history),
                "coarse_scores": coarse_scores,
                "final_scores": final_scores,
            },
        )

    def _freeze(
        self,
        winner: RelativeScore,
    ) -> Dict[str, Any]:
        candidate = CalibrationCandidate(winner.c_units, winner.gamma_units)
        reference = candidate.placement(1, self.threshold)
        gamma = float(candidate.gamma)
        frozen = {
            "status": "selected",
            "protocol_version": const.PROTOCOL_VERSION,
            "run_id": self.run_id,
            "C_cal": float(candidate.C),
            "gamma_cal": gamma,
            "D_cal": gamma * math.pow(math.log(1.0 / const.DELTA), 1.0 / 3.0),
            "delta": const.DELTA,
            "a_cal": reference.a,
            "c_peel": float(self.threshold.c_peel),
            "c_orient": float(self.threshold.c_orient),
            "selection_basis": "fixed_point_relative_success",
            "selection_score": winner.to_dict(),
            "config_sha256": self.config_sha256,
            "source_tree_sha256": self.repo_manifest["source_tree_sha256"],
            "git_commit": self.repo_manifest["git_commit"],
            "threshold_sha256": self.threshold.sha256,
            "input_artifact_sha256": {
                name: sha256_file(self.run.path / name)
                for name in (
                    "calibration_config.json",
                    "m_bracket.csv",
                    "trials.jsonl",
                    "placement_groups.jsonl",
                    "aggregate.csv",
                    "relative_scores.csv",
                    "relative_selection.json",
                    "source_manifest.md",
                    "build_manifest.json",
                    "environment_manifest.json",
                )
            },
        }
        frozen["frozen_payload_sha256"] = canonical_sha256(frozen)
        atomic_write_json(
            self.run.path / "frozen_parameters.json", frozen, exclusive=True
        )
        return frozen

    def run_formal(self) -> Path:
        state = self.run.read_state()["status"]
        try:
            if state == "created":
                self.run.transition("created", "coarse_running")
                state = "coarse_running"
            resumable = {
                "coarse_running",
                "coarse_complete",
                "fine_running",
                "discovery_complete",
            }
            if state not in resumable:
                raise RuntimeError("unsupported nonterminal calibration state: %s" % state)
            if state == "discovery_complete" and (
                self.run.path / "frozen_parameters.json"
            ).exists():
                frozen = json.loads(
                    (self.run.path / "frozen_parameters.json").read_text(encoding="utf-8")
                )
                if frozen.get("status") != "selected":
                    raise RuntimeError("existing frozen parameter artifact is not selected")
                self.run.transition(
                    "discovery_complete",
                    "selected",
                    {
                        "frozen_parameters_sha256": sha256_file(
                            self.run.path / "frozen_parameters.json"
                        )
                    },
                )
                return self.run.path

            coarse_candidates = tuple(
                CalibrationCandidate(c, gamma) for c, gamma in coarse_candidate_grid()
            )
            points_by_d: Dict[int, Dict[int, MPoint]] = {}
            brackets: Dict[int, Bracket] = {}
            for d in const.TRAINING_D:
                points, bracket = self._discover_bracket_for_d(d, coarse_candidates)
                points_by_d[d] = points
                if bracket is not None:
                    brackets[d] = bracket
            self._write_bracket_artifact(points_by_d, brackets)
            if len(brackets) != len(const.TRAINING_D):
                if state != "coarse_running":
                    raise RuntimeError("completed coarse stage cannot be reconstructed as bracketed")
                self.run.transition(
                    state,
                    "calibration_unbracketed",
                    {"unbracketed_d": sorted(set(const.TRAINING_D) - set(brackets))},
                )
                return self.run.path

            coarse_rows = self._aggregate_for_stages(("coarse",))
            try:
                coarse_winner, coarse_scores = relative_score_candidates(coarse_rows)
            except RuntimeError:
                if state != "coarse_running":
                    raise RuntimeError("completed coarse stage has no eligible candidate")
                self.run.transition(state, "no_eligible_candidate")
                return self.run.path
            if state == "coarse_running":
                self.run.transition(
                    "coarse_running",
                    "coarse_complete",
                    {"coarse_winner": coarse_winner.candidate_id},
                )
                state = "coarse_complete"
            if state == "coarse_complete":
                self.run.transition("coarse_complete", "fine_running")
                state = "fine_running"

            fine_candidates = tuple(
                CalibrationCandidate(c, gamma)
                for c, gamma in broad_fine_candidate_grid()
            )
            fine_points = self._fine_points(points_by_d, brackets)
            final_fine_stage = "fine_broad_g_%04d_%04d" % (
                min(const.BROAD_FINE_GAMMA_UNITS),
                max(const.BROAD_FINE_GAMMA_UNITS),
            )
            for d in const.TRAINING_D:
                for M in sorted(fine_points[d]):
                    self._evaluate_m_point(
                        stage=final_fine_stage,
                        domain="calibration_fine",
                        point=fine_points[d][M],
                        candidates=fine_candidates,
                        trials=const.CALIBRATION_TRIALS,
                    )
            cumulative_candidates = list(fine_candidates)
            current_max_gamma = max(candidate.gamma_units for candidate in fine_candidates)
            fine_winner, fine_scores = self._relative_score_stage(final_fine_stage)
            expansion_history: List[Dict[str, Any]] = [
                {
                    "stage": final_fine_stage,
                    "c_min_units": min(candidate.c_units for candidate in fine_candidates),
                    "c_max_units": max(candidate.c_units for candidate in fine_candidates),
                    "gamma_min_units": min(candidate.gamma_units for candidate in fine_candidates),
                    "gamma_max_units": current_max_gamma,
                    "winner": fine_winner.to_dict(),
                }
            ]

            max_legal_c = max(
                c_units
                for c_units in range(const.FINE_STEP_UNITS, 2001, const.FINE_STEP_UNITS)
                if (c_units / 1000.0) * self.threshold.ratio < 1.0
            )
            if max_legal_c != const.MAX_LEGAL_C_UNITS:
                raise RuntimeError("threshold artifact changes the audited maximum legal C grid point")
            while (
                fine_winner.gamma_units
                > current_max_gamma - const.GAMMA_INTERIOR_MARGIN_UNITS
            ):
                start = current_max_gamma + const.FINE_STEP_UNITS
                stop = min(
                    current_max_gamma + const.GAMMA_EXPANSION_BAND_UNITS,
                    const.MAX_GAMMA_UNITS,
                )
                if start > stop:
                    self._compile_discovery_artifacts(
                        final_fine_stage,
                        coarse_scores,
                        fine_scores,
                        expansion_history,
                    )
                    self.run.transition(
                        "fine_running",
                        "relative_search_boundary",
                        {
                            "winner": fine_winner.candidate_id,
                            "maximum_gamma_units": const.MAX_GAMMA_UNITS,
                        },
                    )
                    return self.run.path
                stage = "fine_broad_g_%04d_%04d" % (start, stop)
                band_candidates = tuple(
                    CalibrationCandidate(c_units, gamma_units)
                    for c_units in const.BROAD_FINE_C_UNITS
                    for gamma_units in range(start, stop + 1, const.FINE_STEP_UNITS)
                )
                cumulative_candidates.extend(band_candidates)
                for d in const.TRAINING_D:
                    for M in sorted(fine_points[d]):
                        self._evaluate_m_point(
                            stage=stage,
                            domain="calibration_fine",
                            point=fine_points[d][M],
                            candidates=cumulative_candidates,
                            trials=const.CALIBRATION_TRIALS,
                        )
                final_fine_stage = stage
                current_max_gamma = stop
                fine_winner, fine_scores = self._relative_score_stage(final_fine_stage)
                expansion_history.append(
                    {
                        "stage": stage,
                        "c_min_units": min(const.BROAD_FINE_C_UNITS),
                        "c_max_units": max(const.BROAD_FINE_C_UNITS),
                        "gamma_min_units": min(const.BROAD_FINE_GAMMA_UNITS),
                        "gamma_max_units": stop,
                        "winner": fine_winner.to_dict(),
                    }
                )

            self._compile_discovery_artifacts(
                final_fine_stage,
                coarse_scores,
                fine_scores,
                expansion_history,
            )
            if state == "fine_running":
                self.run.transition(
                    "fine_running",
                    "discovery_complete",
                    {"fine_winner": fine_winner.candidate_id},
                )
                state = "discovery_complete"
            if state != "discovery_complete":
                raise RuntimeError("calibration did not reach discovery_complete")
            self._freeze(fine_winner)
            self.run.transition(
                "discovery_complete",
                "selected",
                {"frozen_parameters_sha256": sha256_file(self.run.path / "frozen_parameters.json")},
            )
            return self.run.path
        except Exception as error:
            self.run.record_error("%s: %s" % (type(error).__name__, error))
            current = self.run.read_state()["status"]
            if current not in {
                "calibration_unbracketed",
                "no_eligible_candidate",
                "relative_search_boundary",
                "confirmation_failed",
                "confirmed",
                "selected",
                "complete",
                "failed",
            }:
                self.run.transition(current, "failed", {"error_type": type(error).__name__})
            raise
