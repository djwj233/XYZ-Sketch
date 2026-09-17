"""Frozen protocol configuration and fixed-point grid construction."""

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Tuple

from . import constants as const


def round_ratio_times_d(rho_units: int, d: int) -> int:
    """Return floor((rho*d)+0.5) using integer arithmetic."""

    if rho_units < 0 or d <= 0:
        raise ValueError("rho must be nonnegative and d must be positive")
    return (rho_units * d + const.RHO_SCALE // 2) // const.RHO_SCALE


def deduplicated_m_grid(rho_units: Iterable[int], d: int) -> Tuple[int, ...]:
    return tuple(sorted({round_ratio_times_d(rho, d) for rho in rho_units}))


def fine_axis(center_units: int) -> Tuple[int, ...]:
    start = max(const.FINE_STEP_UNITS, center_units - const.FINE_RADIUS_UNITS)
    stop = center_units + const.FINE_RADIUS_UNITS
    first = ((start + const.FINE_STEP_UNITS - 1) // const.FINE_STEP_UNITS) * const.FINE_STEP_UNITS
    return tuple(range(first, stop + 1, const.FINE_STEP_UNITS))


def candidate_grid(c_units: Iterable[int], gamma_units: Iterable[int]) -> Tuple[Tuple[int, int], ...]:
    return tuple((c, gamma) for c in c_units for gamma in gamma_units)


def coarse_candidate_grid() -> Tuple[Tuple[int, int], ...]:
    return candidate_grid(const.COARSE_C_UNITS, const.COARSE_GAMMA_UNITS)


def fine_candidate_grid(coarse_c_units: int, coarse_gamma_units: int) -> Tuple[Tuple[int, int], ...]:
    return candidate_grid(fine_axis(coarse_c_units), fine_axis(coarse_gamma_units))


def broad_fine_candidate_grid() -> Tuple[Tuple[int, int], ...]:
    return candidate_grid(const.BROAD_FINE_C_UNITS, const.BROAD_FINE_GAMMA_UNITS)


def next_upper_band(previous_max_rho_units: int) -> Tuple[int, ...]:
    start = previous_max_rho_units + const.RHO_STEP_UNITS
    stop = min(previous_max_rho_units + const.UPPER_BAND_WIDTH_UNITS, const.MAX_RHO_UNITS)
    if start > stop:
        return ()
    return tuple(range(start, stop + 1, const.RHO_STEP_UNITS))


def dense_rho_grid(rho_zero_units: int, rho_one_units: int) -> Tuple[int, ...]:
    if not 0 <= rho_zero_units < rho_one_units:
        raise ValueError("dense grid requires 0 <= rho_zero < rho_one")
    result = list(range(rho_zero_units, rho_one_units + 1, const.DENSE_RHO_STEP_UNITS))
    if result[-1] != rho_one_units:
        result.append(rho_one_units)
    return tuple(result)


@dataclass(frozen=True)
class CalibrationConfig:
    protocol_version: str = const.PROTOCOL_VERSION
    base_seed: int = const.BASE_SEED
    k: int = const.K
    ell: int = const.ELL
    delta: float = const.DELTA
    training_d: Tuple[int, ...] = const.TRAINING_D
    calibration_trials: int = const.CALIBRATION_TRIALS
    coarse_c_units: Tuple[int, ...] = const.COARSE_C_UNITS
    coarse_gamma_units: Tuple[int, ...] = const.COARSE_GAMMA_UNITS
    initial_rho_units: Tuple[int, ...] = const.INITIAL_RHO_UNITS
    lower_expansion_rho_units: Tuple[int, ...] = const.LOWER_EXPANSION_RHO_UNITS
    maximum_rho_units: int = const.MAX_RHO_UNITS
    dense_rho_step_units: int = const.DENSE_RHO_STEP_UNITS
    threshold_sha256: str = const.EXPECTED_THRESHOLD_SHA256

    def validate_formal(self) -> None:
        expected = CalibrationConfig()
        if self != expected:
            raise ValueError("formal calibration configuration differs from the audited protocol")
        if any(d >= 3000 for d in self.training_d):
            raise ValueError("calibration data must satisfy d < 3000")

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["training_d"] = list(self.training_d)
        data["coarse_c_units"] = list(self.coarse_c_units)
        data["coarse_gamma_units"] = list(self.coarse_gamma_units)
        data["initial_rho_units"] = list(self.initial_rho_units)
        data["lower_expansion_rho_units"] = list(self.lower_expansion_rho_units)
        data["seed_domains"] = sorted(const.SEED_DOMAINS)
        data["seed_rule_version"] = const.SEED_RULE_VERSION
        data["placement_word_stream_version"] = const.PLACEMENT_WORD_STREAM_VERSION
        data["selection_rule"] = {
            "primary": "maximize_equal_d_mean_success_rate_on_informative_fixed_points",
            "tie_break": [
                "maximize_minimum_d_mean_success_rate",
                "minimize_mean_pointwise_regret",
                "maximize_pointwise_best_tie_fraction",
                "minimize_mean_pointwise_rank",
                "smaller_C",
                "smaller_gamma",
            ],
            "fine_c_min_units": min(const.BROAD_FINE_C_UNITS),
            "fine_c_max_units": max(const.BROAD_FINE_C_UNITS),
            "fine_gamma_min_units": min(const.BROAD_FINE_GAMMA_UNITS),
            "fine_gamma_initial_max_units": max(const.BROAD_FINE_GAMMA_UNITS),
            "gamma_expansion_step_units": const.FINE_STEP_UNITS,
            "gamma_expansion_band_units": const.GAMMA_EXPANSION_BAND_UNITS,
            "gamma_interior_margin_units": const.GAMMA_INTERIOR_MARGIN_UNITS,
            "gamma_max_units": const.MAX_GAMMA_UNITS,
        }
        return data


@dataclass(frozen=True)
class SmokeConfig:
    base_seed: int = const.BASE_SEED
    domain: str = "calibration_coarse"
    d: int = 12
    M: int = 20
    trials: int = 3

    def validate(self) -> None:
        if self.domain not in const.SEED_DOMAINS:
            raise ValueError("unknown seed domain")
        if not 0 < self.d < 100:
            raise ValueError("smoke d must be outside the formal training grid and in (0,100)")
        if self.M <= 1 or self.trials <= 0:
            raise ValueError("invalid smoke configuration")


def dry_run_budget() -> Dict[str, object]:
    coarse_candidates = len(coarse_candidate_grid())
    fine_candidates_initial = len(const.BROAD_FINE_C_UNITS) * len(const.BROAD_FINE_GAMMA_UNITS)
    fine_candidates_max = len(const.BROAD_FINE_C_UNITS) * (
        const.MAX_GAMMA_UNITS // const.FINE_STEP_UNITS
    )
    initial_points = len(const.INITIAL_RHO_UNITS)
    lower_points = len(const.LOWER_EXPANSION_RHO_UNITS)
    upper_points = (
        const.MAX_RHO_UNITS - max(const.INITIAL_RHO_UNITS)
    ) // const.RHO_STEP_UNITS
    dense_points_max = (
        const.MAX_RHO_UNITS - min(const.LOWER_EXPANSION_RHO_UNITS)
    ) // const.DENSE_RHO_STEP_UNITS + 1
    per_d_scanned_max = initial_points + lower_points + upper_points
    per_d_final_max = per_d_scanned_max + dense_points_max
    return {
        "protocol_version": const.PROTOCOL_VERSION,
        "executes_trials": False,
        "training_scales": len(const.TRAINING_D),
        "coarse_candidates": coarse_candidates,
        "fine_candidates_initial": fine_candidates_initial,
        "fine_candidates_adaptive_upper_bound": fine_candidates_max,
        "initial_m_points_per_d_before_integer_deduplication": initial_points,
        "scanned_m_points_per_d_upper_bound_before_integer_deduplication": per_d_scanned_max,
        "final_m_points_per_d_upper_bound_before_integer_deduplication": per_d_final_max,
        "coarse_candidate_point_trials_upper_bound": (
            len(const.TRAINING_D)
            * per_d_scanned_max
            * coarse_candidates
            * const.CALIBRATION_TRIALS
        ),
        "fine_candidate_point_trials_upper_bound": (
            len(const.TRAINING_D)
            * per_d_final_max
            * fine_candidates_max
            * const.CALIBRATION_TRIALS
        ),
        "holdout_base_cells_per_scale": len(const.HOLDOUT_A_UNITS) * len(const.HOLDOUT_Z),
        "holdout_cells_per_scale_upper_bound": len(const.HOLDOUT_A_UNITS) * len(const.HOLDOUT_Z) + 1,
        "holdout_trials_per_cell": const.HOLDOUT_TRIALS,
    }
