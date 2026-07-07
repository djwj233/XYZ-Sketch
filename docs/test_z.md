# `tests/test_z.py` Design Plan

This document describes the implemented `z` sensitivity experiment for XYZ-v2. It explains how representative parameters are selected, how `z` is swept, how `tests/test_z.py` works, and how to run or validate the experiment.

## Experiment Goal

The goal is to understand how sensitive XYZ-v2 is to the spatial-coupling parameter `z`.

The main question:

```text
For fixed d, l, k, and M, how does decoding success rate change as z changes?
```

This is different from the best-`M` experiments:

- `test_find_best_m.py` searches for the smallest working `M`.
- `test_spatial.py` compares hash modes by searching each mode's best `M`.
- `test_z.py` should keep `M` fixed and sweep only `z`.

Keeping `M` fixed is important because otherwise the experiment would mix the effect of `z` with the effect of communication cost.

## Parameter Selection from Existing Results

Use `tests/results/dlk_best_m_policy/raw.jsonl` as the starting point.

The existing quick sweep shows:

- `d = 100` and `d = 300` have strong finite-size effects and unstable success rates.
- `d >= 1000` is much more stable.
- `l = 6` is the main setting used in earlier experiments.
- `k = 2` is the paper's main circular spatial-coupling case.
- `k = 3` is useful because it uses naive/non-circular spatial coupling in the current implementation.

Recommended first configurations:

```text
d = 1000,  l = 6, k = 2, M = 217
d = 3000,  l = 6, k = 2, M = 600
d = 10000, l = 6, k = 2, M = 2000

d = 1000,  l = 6, k = 3, M = 278
d = 3000,  l = 6, k = 3, M = 834
d = 10000, l = 6, k = 3, M = 2780
```

These `M` values come from the current `test_dlk.py` policy after using measured `C/d` values for larger `k`.

Optional additional configurations:

```text
d = 1000,  l = 6, k = 4, M = 297
d = 3000,  l = 6, k = 4, M = 891
d = 10000, l = 6, k = 4, M = 2970
```

The first version of the script should focus on `k = 2` and `k = 3`. Add `k = 4` only after the workflow is stable.

## What to Sweep

For each fixed `d/l/k/M`, sweep `z`.

Suggested `z` values:

```text
0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 32
```

For larger `M`, optionally add:

```text
48, 64
```

The script should skip invalid `z` values where:

```text
RangeLength = M / (z + 1)
```

becomes too small. A practical rule is:

```text
RangeLength >= 2
```

or, more conservatively:

```text
RangeLength >= k
```

The script should record `RangeLength` for every run.

## Mode Policy

Use:

```text
--mode spatial
```

This keeps compatibility with current experiments:

```text
k <= 2 -> circular spatial coupling
k >= 3 -> naive/non-circular spatial coupling
```

If later we want to study circular and naive separately, `test_z.py` can accept explicit modes:

```text
--mode circular
--mode naive
```

But the first version should use `spatial`.

## C++ Benchmark Dependency

Reuse:

```text
tests/benchmarks/xyz_v2_bench.cpp
```

The script should call it with exact `--m` and varying `--z`:

```bash
build/xyz_v2_bench.exe \
  --d 1000 \
  --l 6 \
  --k 2 \
  --m 217 \
  --z 2 \
  --mode spatial \
  --trials 30 \
  --seed 114514 \
  --ca 10000 \
  --cb 10000 \
  --format jsonl
```

## Trial Counts

For smoke tests:

```text
trials = 10
```

For exploratory plots:

```text
trials = 30
```

For paper-quality results:

```text
trials = 100
```

The script should support a single `--trials` argument.

## Python Script Responsibilities

Recommended script:

```text
tests/test_z.py
```

Responsibilities:

1. Build or locate `xyz_v2_bench`.
2. Build a list of representative `d/l/k/M` configurations.
3. Expand each configuration across the `z` sweep.
4. Run the C++ benchmark for each candidate.
5. Record success rate, timing, communication cost, and `RangeLength`.
6. Write raw JSONL and CSV outputs.
7. Optionally produce a small Markdown summary.

## Recommended Script Functions

```python
def repo_root() -> Path:
    """Return repository root."""

def ensure_dirs(root: Path) -> dict[str, Path]:
    """Create output directories."""

def build_benchmark(root: Path) -> Path:
    """Build or locate xyz_v2_bench."""

def default_configs() -> list[dict]:
    """Return representative d/l/k/M configurations."""

def parse_configs(path: Path) -> list[dict]:
    """Optionally load configurations from a CSV or JSONL file."""

def z_values(args) -> list[int]:
    """Return z values to sweep."""

def range_length(m: int, z: int) -> int:
    """Return M // (z + 1)."""

def valid_z(config: dict, z: int) -> bool:
    """Return whether z should be tested for this config."""

def run_one(binary: Path, config: dict, z: int, seed: int) -> dict:
    """Run one z candidate and parse JSON output."""

def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write raw results."""

def write_csv(path: Path, rows: list[dict]) -> None:
    """Write tabular results."""

def write_summary(path: Path, rows: list[dict]) -> None:
    """Write human-readable summary."""
```

## Output Directory

Recommended output directory:

```text
tests/results/z_sensitivity/
```

Recommended files:

```text
tests/results/z_sensitivity/raw.jsonl
tests/results/z_sensitivity/raw.csv
tests/results/z_sensitivity/summary.md
tests/results/z_sensitivity/errors.log
```

## Output Fields

Each row should include:

```text
algorithm
d
l
k
M
z
RangeLength
mode
trials
successes
success_rate
encode_avg_s
decode_avg_s
encode_median_s
decode_median_s
bits
bit_C_over_d
field_C_over_d
seed
ca
cb
```

Use two communication fields to avoid ambiguity:

```text
field_C_over_d = M * l / d
bit_C_over_d = bits / (32 * d)
```

Since `M` is fixed within one `d/l/k` group, both communication fields should stay constant while `z` changes.

## Seed Policy

For a fair `z` comparison, all `z` values for the same `d/l/k/M` configuration should use the same base seed.

Example:

```text
seed = base_seed + 1000000 * config_index
```

The C++ benchmark internally uses:

```text
trial_seed = seed + trial_index
```

This makes different `z` values see the same sequence of generated datasets.

## Expected Analysis

For each `d/l/k/M` group, inspect:

```text
z -> success_rate
z -> decode_avg_s
z -> RangeLength
```

Useful summaries:

- Best `z` by success rate.
- Smallest `z` reaching a target success rate.
- Broad plateau of good `z` values, if one exists.
- Whether the heuristic `round(M^(1/3) / 3)` lies inside the good region.

The experiment should help answer:

```text
Is z a fragile magic parameter, or is there a reasonably wide stable range?
```

## Testing Plan

### 1. Dry Run

The script should support:

```bash
python tests/test_z.py --dry-run
```

It should print each planned `d/l/k/M/z` combination and `RangeLength`.

### 2. Single-Configuration Smoke Test

Run:

```bash
python tests/test_z.py \
  --d-values 1000 \
  --l-values 6 \
  --k-values 2 \
  --m-values 217 \
  --z-values 0,1,2,3,4,5,8 \
  --trials 10 \
  --output-dir tests/results/z_smoke_k2
```

Expected:

- Results should contain one row per valid `z`.
- `field_C_over_d` should be constant across all rows.
- `success_rate` should vary with `z`.

### 3. `k = 3` Smoke Test

Run:

```bash
python tests/test_z.py \
  --d-values 1000 \
  --l-values 6 \
  --k-values 3 \
  --m-values 278 \
  --z-values 0,1,2,3,4,5,8 \
  --trials 10 \
  --output-dir tests/results/z_smoke_k3
```

Expected:

- The mode should be `spatial`, which maps to naive for `k = 3`.
- `z = 2` should be near the previously used setting.

### 4. Default Run

Run:

```bash
python tests/test_z.py
```

This should use the representative configurations listed above and write to:

```text
tests/results/z_sensitivity/
```

## Interpretation Caveats

Important caveats:

- This experiment fixes `M`; it does not search for the best `M` for each `z`.
- Small `d` is intentionally avoided in the first version because finite-size effects are strong.
- Low trial counts are only for smoke tests.
- `z = 0` under spatial mode is not exactly the same as random hashing; it is a spatial mode with a very large range.
- Random-hash comparison belongs to `test_spatial.py`, not this experiment.

## Relationship to Other Scripts

- `tests/test_dlk.py`: chooses representative `d/l/k/M` values.
- `tests/test_find_best_m.py`: finds best `M` for a fixed mode.
- `tests/test_spatial.py`: compares spatial vs non-spatial modes.
- `tests/test_z.py`: fixes `M` and sweeps `z` to measure sensitivity.

## Build and Usage Guide

The script can build the C++ benchmark automatically:

```bash
python tests/test_z.py --dry-run
python tests/test_z.py --limit 2 --trials 5
```

If the benchmark has already been built, skip rebuilding:

```bash
python tests/test_z.py --skip-build --limit 2 --trials 5
```

Run a small `k = 2` smoke test:

```bash
python tests/test_z.py \
  --skip-build \
  --d-values 1000 \
  --l-values 6 \
  --k-values 2 \
  --m-values 217 \
  --z-values 0,1,2,3,4,5,8 \
  --trials 10 \
  --output-dir tests/results/z_smoke_k2
```

Run a small `k = 3` smoke test:

```bash
python tests/test_z.py \
  --skip-build \
  --d-values 1000 \
  --l-values 6 \
  --k-values 3 \
  --m-values 278 \
  --z-values 0,1,2,3,4,5,8 \
  --trials 10 \
  --output-dir tests/results/z_smoke_k3
```

Run the default representative sweep:

```bash
python tests/test_z.py --skip-build
```

The default output directory is:

```text
tests/results/z_sensitivity/
```

The important command-line options are:

```text
--d-values, --l-values, --k-values, --m-values
    Comma-separated lists for custom fixed configurations. These four options
    must be provided together and must have the same length.

--z-values
    Comma-separated z values to test. If omitted, the default z sweep is used.

--mode
    spatial, random, circular, or naive. The default is spatial.

--trials
    Number of benchmark trials per z value.

--min-range-length
    Skip z values where M // (z + 1) is below this threshold.

--limit
    Run only the first N planned jobs. Useful for quick checks.

--output-dir
    Override the output directory.
```

The generated files are:

```text
raw.jsonl     Full machine-readable benchmark output.
raw.csv       Same rows in CSV form.
summary.md    Per-configuration best-z summary.
errors.log    Failed subprocess calls, if any.
```

