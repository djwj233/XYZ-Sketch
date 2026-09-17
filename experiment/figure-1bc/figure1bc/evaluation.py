"""Paired evaluation of candidate placements at one (domain,d,M) point."""

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, DefaultDict, Dict, List, Mapping, Optional, Sequence, Tuple

from . import constants as const
from .engine import CppEngine
from .model import PlacementSpec
from .simulator import PlacementGeometry, generate_trial_words, simulate_words
from .statistics import wilson_interval


@dataclass(frozen=True)
class PointEvaluation:
    trial_rows: Tuple[Dict[str, Any], ...]
    group_rows: Tuple[Dict[str, Any], ...]
    aggregate_rows: Tuple[Dict[str, Any], ...]
    classification: str


def dataset_seed_prefix(base_seed: int, domain: str, d: int, M: int) -> str:
    return "figure1bc|%d|%s|%d|%d" % (base_seed, domain, d, M)


def classify_point(specs: Sequence[PlacementSpec], successes: Mapping[str, int], trials: int) -> str:
    if all(successes[spec.candidate_id] == 0 for spec in specs):
        return "global_zero"
    legal_specs = [spec for spec in specs if spec.valid]
    if legal_specs and all(successes[spec.candidate_id] == trials for spec in legal_specs):
        return "global_one"
    return "transition"


def evaluate_point(
    *,
    run_id: str,
    stage: str,
    domain: str,
    d: int,
    M: int,
    specs: Sequence[PlacementSpec],
    trials: int,
    threshold_sha256: str,
    m_grid_phase: str,
    base_seed: int = const.BASE_SEED,
    rho: Optional[float] = None,
    engine: Optional[CppEngine] = None,
) -> PointEvaluation:
    if domain not in const.SEED_DOMAINS:
        raise ValueError("unknown evaluation domain")
    if d <= 0 or M <= 0 or trials <= 0 or not specs:
        raise ValueError("evaluation point dimensions, trials, and specs must be nonempty")
    ids = [spec.candidate_id for spec in specs]
    if len(set(ids)) != len(ids):
        raise ValueError("candidate ids must be unique within a point")

    legal_groups: DefaultDict[Tuple[int, int], List[PlacementSpec]] = defaultdict(list)
    invalid_specs: List[PlacementSpec] = []
    geometry_by_key: Dict[Tuple[int, int], PlacementGeometry] = {}
    for spec in specs:
        if not spec.valid:
            invalid_specs.append(spec)
            continue
        geometry = spec.geometry(M)
        legal_groups[geometry.discrete_key].append(spec)
        geometry_by_key[geometry.discrete_key] = geometry

    successes: Dict[str, int] = {spec.candidate_id: 0 for spec in specs}
    residual_totals: Dict[str, int] = {spec.candidate_id: 0 for spec in specs}
    trial_rows: List[Dict[str, Any]] = []
    stream_digest = hashlib.sha256()
    seed_prefix = dataset_seed_prefix(base_seed, domain, d, M)
    group_rows: List[Dict[str, Any]] = []
    group_id_by_placement: Dict[str, str] = {}

    def register_group(placement_id: str, grouped_specs: Sequence[PlacementSpec], status: str) -> str:
        candidate_ids = sorted(spec.candidate_id for spec in grouped_specs)
        digest = hashlib.sha256()
        for candidate_id in candidate_ids:
            encoded = candidate_id.encode("ascii")
            digest.update(len(encoded).to_bytes(2, "big"))
            digest.update(encoded)
        group_id = digest.hexdigest()
        group_id_by_placement[placement_id] = group_id
        group_rows.append(
            {
                "run_id": run_id,
                "stage": stage,
                "domain": domain,
                "d": d,
                "M": M,
                "candidate_group_id": group_id,
                "placement_id": placement_id,
                "candidate_count": len(candidate_ids),
                "candidate_ids": candidate_ids,
                "status": status,
            }
        )
        return group_id

    for key in sorted(legal_groups):
        placement_id = "CBR%d-Z%d" % key
        register_group(placement_id, legal_groups[key], "ok")
    if invalid_specs:
        register_group("invalid-placement", invalid_specs, "invalid_placement")

    engine_groups = {
        "CBR%d-Z%d" % key: geometry_by_key[key] for key in sorted(legal_groups)
    }
    if engine is not None:
        engine_trials = engine.evaluate(
            base_seed=base_seed,
            domain=domain,
            d=d,
            M=M,
            trials=trials,
            geometries=engine_groups,
        )
        trial_inputs = [
            (
                row.trial_index,
                row.stream_sha256,
                row.residual_by_group,
            )
            for row in engine_trials
        ]
    else:
        trial_inputs = []
        for trial_index in range(trials):
            trial_words = generate_trial_words(base_seed, domain, d, M, trial_index)
            residual_by_group = {}
            for key in sorted(legal_groups):
                group_id = "CBR%d-Z%d" % key
                result = simulate_words(trial_words.words, geometry_by_key[key])
                residual_by_group[group_id] = result.residual_edges
            trial_inputs.append(
                (trial_index, trial_words.stream_sha256, residual_by_group)
            )

    for trial_index, stream_sha256, residual_by_group in trial_inputs:
        stream_digest.update(bytes.fromhex(stream_sha256))
        for key in sorted(legal_groups):
            group = legal_groups[key]
            geometry = geometry_by_key[key]
            group_id = "CBR%d-Z%d" % key
            residual_edges = residual_by_group[group_id]
            success = residual_edges == 0
            for spec in group:
                successes[spec.candidate_id] += int(success)
                residual_totals[spec.candidate_id] += residual_edges
            trial_rows.append(
                {
                    "run_id": run_id,
                    "stage": stage,
                    "domain": domain,
                    "base_seed": base_seed,
                    "d": d,
                    "M": M,
                    "trial_index": trial_index,
                    "placement_id": group_id,
                    "candidate_group_id": group_id_by_placement[group_id],
                    "candidate_count": len(group),
                    "dataset_seed": seed_prefix,
                    "placement_words_sha256": stream_sha256,
                    "initial_edge_count": d,
                    "residual_edge_count": residual_edges,
                    "success": success,
                    "status": "ok",
                }
            )
        if invalid_specs:
            for spec in invalid_specs:
                residual_totals[spec.candidate_id] += d
            trial_rows.append(
                {
                    "run_id": run_id,
                    "stage": stage,
                    "domain": domain,
                    "base_seed": base_seed,
                    "d": d,
                    "M": M,
                    "trial_index": trial_index,
                    "placement_id": "invalid-placement",
                    "candidate_group_id": group_id_by_placement["invalid-placement"],
                    "candidate_count": len(invalid_specs),
                    "dataset_seed": seed_prefix,
                    "placement_words_sha256": stream_sha256,
                    "initial_edge_count": d,
                    "residual_edge_count": d,
                    "success": False,
                    "status": "invalid_placement",
                }
            )

    classification = classify_point(specs, successes, trials)
    aggregate_stream_sha = stream_digest.hexdigest()
    aggregate_rows: List[Dict[str, Any]] = []
    for spec in sorted(specs, key=lambda item: item.candidate_id):
        geometry = spec.geometry(M) if spec.valid else None
        count = successes[spec.candidate_id]
        ci_low, ci_high = wilson_interval(count, trials)
        aggregate_rows.append(
            {
                "run_id": run_id,
                "stage": stage,
                "domain": domain,
                "d": d,
                "M": M,
                "k": const.K,
                "ell": const.ELL,
                "candidate_id": spec.candidate_id,
                "C": spec.C,
                "gamma": spec.gamma,
                "a": spec.a,
                "z_raw": spec.z_raw,
                "z": spec.z,
                "CircularBaseRange": geometry.circular_base_range if geometry else None,
                "trials": trials,
                "successes": count,
                "success_rate": count / trials,
                "ci_low": ci_low,
                "ci_high": ci_high,
                "rho": rho if rho is not None else M / d,
                "m_grid_phase": m_grid_phase,
                "global_classification": classification,
                "is_informative": classification == "transition",
                "dataset_seed": seed_prefix,
                "placement_words_sha256": aggregate_stream_sha,
                "config_sha256": spec.config_sha256(M),
                "threshold_sha256": threshold_sha256,
                "is_frozen_prediction": spec.is_frozen_prediction,
                "status": spec.status,
                "residual_edge_total": residual_totals[spec.candidate_id],
            }
        )
    return PointEvaluation(
        tuple(trial_rows), tuple(group_rows), tuple(aggregate_rows), classification
    )
