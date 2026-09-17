from pathlib import Path


PROTOCOL_VERSION = "figure1a-reduced-v1"
ENGINE_PROTOCOL = "figure1a-engine-v1"
BASE_SEED = 114514
FIELD_MODULUS = 998244353
D = 10_000
SET_SIZE = 2 * D
COMMON_SIZE = SET_SIZE - D // 2
ONE_DIRECTION = D // 2
DELTA = 0.1
CONTROL_BITS = 352
COARSE_TRIALS = 20
DENSE_TRIALS = 100
WORKERS = 32
MAX_EXTENSION_ROUNDS = 20
PLATEAU_PADDING_STEPS = 20
PLATEAU_REQUIRED_CONSECUTIVE = 5
PLATEAU_COMPLETION_BATCH_STEPS = 10

PANELS = ((2, 3), (2, 6), (3, 4))
MODES = ("iid", "naive", "circular")
COARSE_STEP = {3: 30, 6: 16, 4: 24}
DENSE_STEP = {3: 6, 6: 3, 4: 4}
SEED_ROLES = (
    "dataset_identity",
    "alice_insertion_order",
    "bob_insertion_order",
    "decoder_root_finding",
    "hash_family",
)

PACKAGE_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = PACKAGE_DIR.parent
REPO_DIR = EXPERIMENT_DIR.parent.parent
THRESHOLD_PATH = EXPERIMENT_DIR.parent / "threshold" / "validated_thresholds.json"
DEFAULT_FROZEN_PATH = EXPERIMENT_DIR.parent / "figure-1bc" / "results" / "calibration" / \
    "figure1bc-calibration-20260716T095512Z-99bbe7a-b4444f9c40f4" / "frozen_parameters.json"
DEFAULT_HOLDOUT_PATH = EXPERIMENT_DIR.parent / "figure-1bc" / "results" / "holdout" / \
    "figure1bc-holdout-20260716T110856Z-99bbe7a-35901f553b9f"
EXPECTED_THRESHOLD_SHA256 = "ef3f0c89d96ab326ed5c33340210b37033e47b033e9f124811cce7c80ef83b87"

TRIAL_FIELDS = (
    "run_id", "protocol_version", "git_commit", "phase", "k", "ell", "mode", "M", "trial_index",
    "set_size_A", "set_size_B", "difference_A", "difference_B", "base_seed",
    "dataset_seed", "alice_order_seed", "bob_order_seed", "decoder_seed", "hash_family_seed",
    "dataset_sha256", "dataset_seconds", "C", "D", "delta", "a_raw", "a", "z_raw", "z", "z_rounding",
    "success", "failure_reason", "logical_state_bits", "state_bits", "control_bits",
    "total_payload_bits", "bits_per_cell", "R_w30", "alice_encode_seconds",
    "serialization_seconds", "bob_encode_seconds", "decode_seconds", "total_seconds",
    "dedup_hashes", "fingerprint_enabled", "status",
)

AGGREGATE_FIELDS = (
    "run_id", "protocol_version", "git_commit", "phase", "k", "ell", "mode", "M", "C", "D", "delta",
    "a_raw", "a", "z_raw", "z", "z_rounding", "set_size_A", "set_size_B", "difference_A",
    "difference_B", "trials", "successes", "success_rate", "ci_low", "ci_high",
    "logical_state_bits", "state_bits", "control_bits", "total_payload_bits", "bits_per_cell",
    "R_w30", "dedup_hashes", "fingerprint_enabled", "base_seed", "failure_counts", "status",
)
