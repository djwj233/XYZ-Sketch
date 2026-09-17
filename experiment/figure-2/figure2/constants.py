from pathlib import Path


PROTOCOL_VERSION = "figure2-v4"
ENGINE_PROTOCOL = "figure2-engine-v2"
DATASET_PROTOCOL = "figure2-dataset-v1"
BASE_SEED = 114514
SET_SIZE = 10_000_000
DIFFERENCES = (100, 300, 1_000, 3_000, 10_000, 30_000, 100_000, 300_000, 1_000_000)
ALGORITHMS = (
    "xyz", "minisketch", "external_iblt", "project_iblt", "riblt", "cpisync",
)
DISCOVERY_TRIALS = 100
CONFIRMATION_TRIALS = 100
TIMING_DATASETS = 5
TIMING_REPETITIONS = 3
TIMING_BOOTSTRAPS = 10_000
TARGET_NUMERATOR = 9
TARGET_DENOMINATOR = 10

PACKAGE_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = PACKAGE_DIR.parent
REPO_DIR = EXPERIMENT_DIR.parent.parent
BUILD_DIR = EXPERIMENT_DIR / "build"
DEFAULT_FROZEN = EXPERIMENT_DIR.parent / "figure-1bc" / "results" / "calibration" / \
    "figure1bc-calibration-20260716T095512Z-99bbe7a-b4444f9c40f4" / "frozen_parameters.json"
DEFAULT_HOLDOUT = EXPERIMENT_DIR.parent / "figure-1bc" / "results" / "holdout" / \
    "figure1bc-holdout-20260716T110856Z-99bbe7a-35901f553b9f"
THRESHOLD = EXPERIMENT_DIR.parent / "threshold" / "validated_thresholds.json"
THRESHOLD_SHA256 = "ef3f0c89d96ab326ed5c33340210b37033e47b033e9f124811cce7c80ef83b87"

EXECUTABLES = {
    "dataset": BUILD_DIR / "figure2_dataset_engine",
    "xyz": BUILD_DIR / "figure2_xyz_engine",
    "minisketch": BUILD_DIR / "figure2_minisketch_engine",
    "external_iblt": BUILD_DIR / "figure2_external_iblt_engine",
    "project_iblt": BUILD_DIR / "figure2_project_iblt_engine",
    "riblt": BUILD_DIR / "figure2_riblt_engine",
    "cpisync": BUILD_DIR / "figure2_cpisync_engine",
}

SOURCE_COMMITS = {
    "minisketch": "d1bd01e189e745cd1828707e0a7004b6a6909650",
    "external_iblt": "db28fd0fd213b37714e7dfdea3ca2ca67e9f1c09",
    "riblt": "4afa6bc06cb2237d9ea273a51d97a7e05b3f573b",
    "cpisync": "268c38fb130dd385469291288a3632b8c31e6e70",
}

RATIO_GRIDS = {
    "xyz": {"minimum": 100, "maximum": 400, "coarse_step": 20, "fine_step": 2, "scale": 1000},
    "external_iblt": {"minimum": 500, "maximum": 1500, "coarse_step": 50, "fine_step": 5, "scale": 1000},
    "project_iblt": {"minimum": 800, "maximum": 3000, "coarse_step": 100, "fine_step": 10, "scale": 1000},
}

MAX_CANDIDATES = {"xyz": 25, "external_iblt": 30, "project_iblt": 32}
MAX_DISCOVERY_UPDATE_MULTIPLIER = {"xyz": 2500, "external_iblt": 3000, "project_iblt": 3200}
