# `tests/test_dlk.py` Design Plan

This document plans the first experiment script: a detailed sweep over `d`, `l`, and `k` for XYZ-v2. It does not implement the script yet. The goal is to define the interfaces and structure clearly before writing code.

## Experiment Goal

The script should measure how XYZ-v2 behaves under different values of:

- `d`: symmetric difference size
- `l`: per-cell decoding capacity
- `k`: number of hash locations per element

For each configuration, the script should run multiple trials and record success rate, timing, communication cost, and normalized communication cost.

## Preferred Architecture

Use Python as the experiment driver and C++ as the benchmark executor.

Python should:

- Generate the `d/l/k` parameter grid.
- Decide `M`, `z`, number of trials, and seeds.
- Build or locate the C++ benchmark binary.
- Invoke the binary repeatedly.
- Parse structured output.
- Write raw CSV or JSONL results.
- Optionally print a compact progress summary.

C++ should:

- Run the actual XYZ-v2 encode/decode workload.
- Measure encode and decode time.
- Verify correctness.
- Print one structured record per configuration or per trial.

The Python script should not reimplement XYZ-v2 logic.

## Required C++ Benchmark Interface

The current `XYZ-v2/speedtest.cpp` is useful as a reference, but it is not ideal for automated sweeps because parameters are hardcoded. The Python script should eventually call a small benchmark binary with a command-line interface like this:

```bash
xyz_v2_bench \
  --d 10000 \
  --l 6 \
  --k 2 \
  --m-factor 1.15 \
  --z 5 \
  --trials 30 \
  --seed 114514 \
  --mode spatial \
  --ca 10000000 \
  --cb 10000000 \
  --format jsonl
```

Suggested binary name:

```text
build/xyz_v2_bench.exe
```

The benchmark binary may be implemented later by adapting `XYZ-v2/speedtest.cpp`.

## Command-Line Arguments

The C++ binary should support these arguments:

| Argument | Required | Meaning |
| --- | --- | --- |
| `--d` | yes | Target symmetric difference size. |
| `--l` | yes | Cell capacity parameter. |
| `--k` | yes | Number of hashes per element. |
| `--m` | no | Exact number of cells. If present, overrides `--m-factor`. |
| `--m-factor` | no | Compute `M = ceil(m_factor * d / l)` or equivalent. |
| `--z` | yes | Spatial coupling parameter. |
| `--trials` | yes | Number of repeated trials for this configuration. |
| `--seed` | yes | Base random seed. |
| `--mode` | yes | `spatial` or `random`; this experiment initially uses `spatial`. |
| `--ca` | no | Alice set size; default can be `10000000` for large experiments. |
| `--cb` | no | Bob set size; default can equal `ca`. |
| `--format` | no | `jsonl` preferred, `csv` acceptable. |

For the first `d/l/k` sweep, `--mode spatial` is enough. The non-spatial mode can be reused by the later spatial-coupling comparison experiment.

## Expected C++ Output

Prefer JSONL because it is easy to extend without breaking parsers. The binary should print one JSON object per configuration, after aggregating all trials.

Example:

```json
{"algorithm":"xyz_v2","mode":"spatial","d":10000,"l":6,"k":2,"M":1917,"z":5,"trials":30,"successes":30,"success_rate":1.0,"encode_avg_s":2.31,"decode_avg_s":0.67,"encode_median_s":2.29,"decode_median_s":0.66,"bits":375732,"C_over_d":1.174,"seed":114514}
```

The record should include:

- `algorithm`
- `mode`
- `d`
- `l`
- `k`
- `M`
- `z`
- `trials`
- `successes`
- `success_rate`
- `encode_avg_s`
- `decode_avg_s`
- `encode_median_s`
- `decode_median_s`
- `bits`
- `C_over_d`
- `seed`

The Python script should save these records without modifying their meaning.

## Python Script Responsibilities

`tests/test_dlk.py` should contain the experiment orchestration logic.

Recommended functions:

```python
def repo_root() -> Path:
    """Return the repository root."""

def ensure_dirs(root: Path) -> dict[str, Path]:
    """Create and return output directories."""

def build_benchmark(root: Path) -> Path:
    """Build or locate the xyz_v2 benchmark binary."""

def default_grid() -> list[dict]:
    """Return the default d/l/k experiment configurations."""

def choose_trials(d: int) -> int:
    """Choose trial count based on problem size."""

def choose_z(d: int, l: int, k: int, m: int) -> int:
    """Choose z for the first sweep."""

def choose_m_factor(d: int, l: int, k: int) -> float:
    """Choose the communication budget for this configuration."""

def run_one(binary: Path, config: dict) -> dict:
    """Invoke the C++ benchmark for one configuration and parse JSONL output."""

def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write raw result records."""

def write_csv(path: Path, rows: list[dict]) -> None:
    """Write a tabular copy for quick inspection."""

def main() -> None:
    """Run the d/l/k sweep."""
```

The script should use `subprocess.run` with explicit argument lists, not shell strings.

## Initial Parameter Grid

The first version should keep the grid moderate, so the workflow can be validated quickly.

Suggested quick grid:

```python
D_VALUES = [100, 300, 1000, 3000, 10000]
L_VALUES = [2, 3, 4, 6, 8, 10]
K_VALUES = [2, 3, 4]
```

Suggested extended grid after the script is stable:

```python
D_VALUES = [10, 30, 100, 300, 1000, 3000, 10000, 30000, 100000, 300000, 1000000]
L_VALUES = [2, 3, 4, 6, 8, 10, 16, 20]
K_VALUES = [2, 3, 4]
```

For very small `d`, some `l` values may be too large or not meaningful. The script should skip configurations where `l > d` or where computed `M` is too small.

## Choosing `M` and `z`

For this first experiment, the main variable is `d/l/k`, not communication-threshold searching. Therefore use a simple deterministic policy for `M` and `z`.

The current script uses the original heuristic for `k = 2`, and uses empirically measured `C/d` values for larger `k`.

For `k = 3` and `k = 4`, the values come from `tests/test_find_best_m.py` on the representative setting `d = 1000, l = 6, target_success_rate = 0.9`:

```text
k = 3: C/d = 1.668
k = 4: C/d = 1.782
```

The script scales those values as:

```text
M = ceil((C/d target) * d / l)
```

For `k = 2`, the script keeps the previous size-dependent policy:

```text
d <= 100      -> C/d = 1.60
d <= 1000     -> C/d = 1.30
d <= 10000    -> C/d = 1.20
d <= 100000   -> C/d = 1.12
otherwise     -> C/d = 1.10
```

Then:

```text
z = max(0, round(M^(1/3) / 3))
```

The Python script should make this policy explicit, so future readers know how each result was produced.

## Output Files

Recommended output location:

```text
tests/results/dlk/
```

Recommended files:

```text
tests/results/dlk/raw.jsonl
tests/results/dlk/raw.csv
tests/results/dlk/summary.md
```

`raw.jsonl` should be the source of truth. `raw.csv` is for quick inspection. `summary.md` can contain a short human-readable summary of the run.

## Failure Handling

The Python script should treat benchmark failures carefully:

- If the C++ process exits non-zero, store the command, stderr, and configuration in an error log.
- If JSON output cannot be parsed, store the raw stdout and stderr.
- If decoding fails for a trial, the C++ benchmark should count it as an unsuccessful trial, not crash.
- The script should continue with the next configuration unless a build step fails.

Recommended error file:

```text
tests/results/dlk/errors.log
```

## Reproducibility

Each configuration should have a deterministic base seed. A simple scheme is:

```text
seed = base_seed + 1000000 * d_index + 10000 * l_index + 100 * k_index
```

Inside the C++ benchmark, trial `t` can use:

```text
trial_seed = seed + t
```

The seed must be included in the output record.

## Implementation Sequence

When implementation starts, use this order:

1. Create or adapt a C++ benchmark binary that accepts one configuration and prints JSONL.
2. Implement `tests/test_dlk.py` with a very small grid.
3. Verify that one record is produced and parsed correctly.
4. Add CSV/JSONL writing.
5. Expand to the quick grid.
6. Add failure logging and summary output.
7. Run the extended grid only after the quick grid is stable.

## Non-Goals for This Script

This script should not:

- Compare spatial vs non-spatial coupling in detail.
- Sweep `z` sensitivity.
- Add external baselines.
- Generate final paper plots.
- Reimplement XYZ-v2 in Python.

Those are later tasks. This script should stay focused on the detailed `d/l/k` sweep.

## Build and Usage Guide

The experiment now consists of two files:

- `tests/benchmarks/xyz_v2_bench.cpp`: the C++ benchmark executable source.
- `tests/test_dlk.py`: the Python experiment driver.

### Build the Benchmark Manually

From the repository root:

```bash
mkdir -p build
g++ -std=c++17 -O2 tests/benchmarks/xyz_v2_bench.cpp -o build/xyz_v2_bench
```

On Windows, the output path can be:

```powershell
New-Item -ItemType Directory -Force build
g++ -std=c++17 -O2 tests\benchmarks\xyz_v2_bench.cpp -o build\xyz_v2_bench.exe
```

### Run One Benchmark Configuration

Example:

```bash
./build/xyz_v2_bench \
  --d 1000 \
  --l 6 \
  --k 2 \
  --m 217 \
  --z 2 \
  --trials 5 \
  --seed 114514 \
  --mode spatial \
  --ca 10000 \
  --cb 10000 \
  --format jsonl
```

The benchmark prints one JSON object to stdout.

### Run the Python Sweep

From the repository root:

```bash
python tests/test_dlk.py
```

By default, the script:

1. Builds `build/xyz_v2_bench` or `build/xyz_v2_bench.exe`.
2. Runs the quick `d/l/k` grid.
3. Writes results to `tests/results/dlk/`.

Expected outputs:

```text
tests/results/dlk/raw.jsonl
tests/results/dlk/raw.csv
tests/results/dlk/summary.md
tests/results/dlk/errors.log   # only when failures occur
```

### Useful Script Options

Print commands without running them:

```bash
python tests/test_dlk.py --dry-run
```

Run only the first few configurations for a smoke test:

```bash
python tests/test_dlk.py --limit 2
```

Reuse an already-built benchmark:

```bash
python tests/test_dlk.py --skip-build
```

Run the larger grid:

```bash
python tests/test_dlk.py --extended
```

Use a different output directory:

```bash
python tests/test_dlk.py --output-dir tests/results/dlk_run_001
```

Increase or decrease generated set sizes:

```bash
python tests/test_dlk.py --max-set-size 1000000 --set-size-scale 20
```

### Current Limitation

`xyz_v2_bench.cpp` currently supports only `--mode spatial`, because the existing `XYZ-v2/XYZSketch.cpp` selects `SpatialCoupling` at compile time. The later spatial-coupling comparison experiment should refactor or duplicate the hash selection path so that `--mode random` can be benchmarked cleanly.

