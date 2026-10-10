"""Relative candidate scoring on fixed paired (d,M) observations."""

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from . import constants as const


@dataclass(frozen=True)
class RelativeScore:
    candidate_id: str
    C: float
    gamma: float
    D: float
    informative_points: int
    equal_d_mean_success_rate: float
    minimum_d_mean_success_rate: float
    mean_pointwise_regret: float
    pointwise_best_tie_fraction: float
    mean_pointwise_rank: float

    @property
    def c_units(self) -> int:
        return int(round(self.C * 1000))

    @property
    def gamma_units(self) -> int:
        return int(round(self.gamma * 1000))

    @property
    def sort_key(self) -> Tuple[Any, ...]:
        return (
            -self.equal_d_mean_success_rate,
            -self.minimum_d_mean_success_rate,
            self.mean_pointwise_regret,
            -self.pointwise_best_tie_fraction,
            self.mean_pointwise_rank,
            self.c_units,
            self.gamma_units,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "C": self.C,
            "gamma": self.gamma,
            "D": self.D,
            "informative_points": self.informative_points,
            "equal_d_mean_success_rate": self.equal_d_mean_success_rate,
            "minimum_d_mean_success_rate": self.minimum_d_mean_success_rate,
            "mean_pointwise_regret": self.mean_pointwise_regret,
            "pointwise_best_tie_fraction": self.pointwise_best_tie_fraction,
            "mean_pointwise_rank": self.mean_pointwise_rank,
        }


def relative_score_candidates(
    aggregate_rows: Iterable[Mapping[str, Any]],
    training_d: Sequence[int] = const.TRAINING_D,
) -> Tuple[RelativeScore, List[Dict[str, Any]]]:
    points: Dict[Tuple[int, int], List[Mapping[str, Any]]] = defaultdict(list)
    for row in aggregate_rows:
        d = int(row["d"])
        M = int(row["M"])
        points[(d, M)].append(row)
    return relative_score_point_rows(points.values(), training_d)


def relative_score_point_rows(
    point_rows: Iterable[Sequence[Mapping[str, Any]]],
    training_d: Sequence[int] = const.TRAINING_D,
) -> Tuple[RelativeScore, List[Dict[str, Any]]]:
    candidate_meta: Dict[str, Tuple[float, float]] = {}
    candidate_ids = None
    points_per_d = Counter()
    success_sum: Dict[str, Counter] = {}
    regret_sum = Counter()
    best_ties = Counter()
    rank_sum = Counter()
    point_count = 0

    for rows in point_rows:
        if not rows:
            raise ValueError("relative-scoring point may not be empty")
        row_candidate_ids = {str(row["candidate_id"]) for row in rows}
        if candidate_ids is None:
            candidate_ids = row_candidate_ids
            success_sum = {candidate_id: Counter() for candidate_id in candidate_ids}
        elif row_candidate_ids != candidate_ids:
            raise ValueError("every relative-scoring point must contain every candidate")
        for row in rows:
            candidate_id = str(row["candidate_id"])
            metadata = (float(row["C"]), float(row["gamma"]))
            if candidate_id in candidate_meta and candidate_meta[candidate_id] != metadata:
                raise ValueError("candidate metadata changes between fixed points")
            candidate_meta[candidate_id] = metadata
        successes = {str(row["candidate_id"]): int(row["successes"]) for row in rows}
        if len(set(successes.values())) == 1:
            continue
        d_values = {int(row["d"]) for row in rows}
        m_values = {int(row["M"]) for row in rows}
        trial_counts = {int(row["trials"]) for row in rows}
        if len(d_values) != 1 or len(m_values) != 1 or len(trial_counts) != 1:
            raise ValueError("one relative-scoring batch must be one paired (d,M) point")
        d = d_values.pop()
        trials = trial_counts.pop()
        points_per_d[d] += 1
        point_count += 1
        best = max(successes.values())
        histogram = Counter(successes.values())
        better = 0
        rank_by_success: Dict[int, int] = {}
        for value in sorted(histogram, reverse=True):
            rank_by_success[value] = better + 1
            better += histogram[value]
        for candidate_id, value in successes.items():
            rate = value / trials
            best_rate = best / trials
            success_sum[candidate_id][d] += rate
            regret_sum[candidate_id] += best_rate - rate
            best_ties[candidate_id] += int(value == best)
            rank_sum[candidate_id] += rank_by_success[value]

    if candidate_ids is None:
        raise RuntimeError("relative scoring received no candidates")
    if point_count == 0:
        raise RuntimeError("relative scoring found no informative fixed (d,M) point")
    missing_d = [d for d in training_d if points_per_d[d] == 0]
    if missing_d:
        raise RuntimeError("no informative point for training d=%s" % missing_d)

    d_count = len(training_d)
    log_factor = math.pow(math.log(1.0 / const.DELTA), 1.0 / 3.0)
    scores: List[RelativeScore] = []
    for candidate_id in sorted(candidate_ids):
        per_d_means = [
            success_sum[candidate_id][d] / points_per_d[d] for d in training_d
        ]
        C, gamma = candidate_meta[candidate_id]
        scores.append(
            RelativeScore(
                candidate_id=candidate_id,
                C=C,
                gamma=gamma,
                D=gamma * log_factor,
                informative_points=point_count,
                equal_d_mean_success_rate=sum(per_d_means) / d_count,
                minimum_d_mean_success_rate=min(per_d_means),
                mean_pointwise_regret=regret_sum[candidate_id] / point_count,
                pointwise_best_tie_fraction=best_ties[candidate_id] / point_count,
                mean_pointwise_rank=rank_sum[candidate_id] / point_count,
            )
        )
    scores.sort(key=lambda score: score.sort_key)
    output = []
    for rank, score in enumerate(scores, 1):
        output.append({"rank": rank, **score.to_dict(), "is_selected": rank == 1})
    return scores[0], output
