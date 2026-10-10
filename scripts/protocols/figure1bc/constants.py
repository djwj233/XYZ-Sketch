"""Protocol constants copied from the audited Figure 1(b)(c) README.

Numeric grids are represented as integers throughout grid construction.  A
``C`` or ``gamma`` unit is one thousandth; a rho unit is one millionth.  This
prevents accumulated floating-point steps from changing a candidate or M grid.
"""

from pathlib import Path


PROTOCOL_VERSION = "figure1bc-v4"
SEED_RULE_VERSION = "sha256-first-u32be-v1"
PLACEMENT_WORD_STREAM_VERSION = "u32be-anchor-offset1-offset2-v1"

BASE_SEED = 114514
K = 2
ELL = 6
DELTA = 0.1
TARGET_SUCCESS_NUMERATOR = 9
TARGET_SUCCESS_DENOMINATOR = 10

TRAINING_D = (100, 200, 400, 600, 800, 1000, 1500, 2000, 2500)
HOLDOUT_SCALES = (
    ("figure1b", "holdout_figure1b", 3000, 596, "sealed holdout, scale 1"),
    ("figure1c", "holdout_figure1c", 10000, 1948, "sealed holdout, scale 2"),
)

CALIBRATION_TRIALS = 100
HOLDOUT_TRIALS = 100

COARSE_C_UNITS = tuple(range(100, 601, 25))
COARSE_GAMMA_UNITS = tuple(range(150, 651, 25))
FINE_RADIUS_UNITS = 50
FINE_STEP_UNITS = 5
C_EXPANSION_BAND_UNITS = 50
C_INTERIOR_MARGIN_UNITS = 50
MAX_LEGAL_C_UNITS = 1205
BROAD_FINE_C_UNITS = tuple(range(5, MAX_LEGAL_C_UNITS + 1, FINE_STEP_UNITS))
BROAD_FINE_GAMMA_UNITS = tuple(range(5, 1001, FINE_STEP_UNITS))
GAMMA_EXPANSION_BAND_UNITS = 250
GAMMA_INTERIOR_MARGIN_UNITS = 50
MAX_GAMMA_UNITS = 4000

RHO_SCALE = 1_000_000
INITIAL_RHO_UNITS = tuple(range(80_000, 450_001, 10_000))
LOWER_EXPANSION_RHO_UNITS = (60_000, 40_000, 20_000, 10_000)
UPPER_BAND_WIDTH_UNITS = 100_000
RHO_STEP_UNITS = 10_000
MAX_RHO_UNITS = 1_450_000
DENSE_RHO_STEP_UNITS = 2_500

HOLDOUT_A_UNITS = (0, 100, 200, 300, 400, 500)
HOLDOUT_Z = (0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16)

SEED_DOMAINS = frozenset(
    {
        "calibration_coarse",
        "calibration_fine",
        "holdout_figure1b",
        "holdout_figure1c",
    }
)

EXPECTED_THRESHOLD_SHA256 = (
    "ef3f0c89d96ab326ed5c33340210b37033e47b033e9f124811cce7c80ef83b87"
)
EXPECTED_THRESHOLD_ENTRIES = 48

PACKAGE_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = PACKAGE_DIR.parent
THRESHOLD_PATH = EXPERIMENT_DIR.parent / "threshold" / "validated_thresholds.json"

AGGREGATE_FIELDS = (
    "run_id",
    "stage",
    "domain",
    "d",
    "M",
    "k",
    "ell",
    "candidate_id",
    "C",
    "gamma",
    "a",
    "z_raw",
    "z",
    "CircularBaseRange",
    "trials",
    "successes",
    "success_rate",
    "ci_low",
    "ci_high",
    "rho",
    "m_grid_phase",
    "global_classification",
    "is_informative",
    "dataset_seed",
    "placement_words_sha256",
    "config_sha256",
    "threshold_sha256",
    "is_frozen_prediction",
    "status",
)

RELATIVE_SCORE_FIELDS = (
    "rank",
    "stage",
    "candidate_id",
    "C",
    "gamma",
    "D",
    "informative_points",
    "equal_d_mean_success_rate",
    "minimum_d_mean_success_rate",
    "mean_pointwise_regret",
    "pointwise_best_tie_fraction",
    "mean_pointwise_rank",
    "is_selected",
)
