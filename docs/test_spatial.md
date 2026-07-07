# `tests/test_spatial.py` Design Plan

This document plans the spatial-coupling isolation experiment. It describes how to compare XYZ-v2 with spatial coupling against XYZ-v2 without spatial coupling. No code is implemented here.

## Experiment Goal

The goal is to measure the benefit of spatial coupling by comparing the minimum communication cost needed to reach a target decoding success rate.

The main question:

```text
For the same d, l, k, and target success rate, how much smaller can C/d be when spatial coupling is enabled?
```

The primary metric should be:

```text
best_C_over_d = best_M * l / d
```

where `best_M` is the smallest empirically working number of cells.

## Why This Needs a Separate Script

The existing `tests/test_dlk.py` runs a fixed parameter grid. That is useful for observing trends, but it is not the right way to compare spatial coupling modes.

For a fair comparison, each mode should be allowed to choose its own best `M`. Otherwise one mode may look bad only because the shared `M` is too small for it.

Therefore, this experiment should use threshold search, similar to `tests/test_find_best_m.py`.

## Proposed Script Name

```text
tests/test_spatial.py
```

## Modes to Compare

The experiment should eventually compare three modes:

```text
random
circular
naive
```

### `random`

This is non-spatial coupling. Each hash maps uniformly to `[0, M)`.

This corresponds to the current `RandomHash` namespace in `XYZ-v2/hash.cpp`.

### `circular`

This is the circular spatial coupling variant described in the paper. It wraps the spatial window around the end of the array.

It is expected to work well for `k = 2`, but poorly for larger `k`.

### `naive`

This is non-circular spatial coupling. The spatial window does not wrap around.

It usually needs a larger `M` than circular coupling, but it is the appropriate spatial-coupling baseline for `k >= 3`.

## Required C++ Benchmark Changes

The current `tests/benchmarks/xyz_v2_bench.cpp` accepts:

```bash
--mode spatial
```

but the actual circular-vs-naive choice is currently controlled inside `XYZ-v2/hash.cpp` based on global `k`.

For this experiment, the C++ benchmark should expose explicit hash modes:

```bash
--mode random
--mode circular
--mode naive
```

Recommended implementation approach:

1. Add a global hash-mode enum or integer in `XYZ-v2/hash.cpp`.
2. Add a setter such as:

   ```cpp
   enum class HashMode { Random, Circular, Naive };
   void SetHashMode(HashMode mode);
   ```

3. Change `h(i, x)` so it dispatches based on the selected mode.
4. Make `xyz_v2_bench.cpp` parse `--mode random|circular|naive`.
5. Keep the old behavior available by mapping:

   ```text
   --mode spatial
   ```

   to:

   ```text
   k <= 2 -> circular
   k >= 3 -> naive
   ```

   This preserves compatibility with `test_dlk.py` and `test_find_best_m.py`.

## Fair Comparison Policy

For each configuration:

```text
d, l, k, mode, target_success_rate
```

the script should find the smallest `M` that reaches the target success rate.

This means `random`, `circular`, and `naive` are not forced to share the same `M`. Instead, the output compares their required `C/d`.

## Recommended Configurations

Start with a small but meaningful grid:

```text
d in {1000, 3000, 10000}
l in {4, 6, 8}
k in {2, 3}
modes:
  for k = 2: random, circular, naive
  for k = 3: random, naive
```

For `k = 3`, circular can be added as a diagnostic mode, but it should not be the main spatial-coupling representative because the paper says circular performs poorly when `k` is larger than 2.

After the script is stable, expand to:

```text
d in {100, 300, 1000, 3000, 10000, 30000, 100000}
l in {2, 3, 4, 6, 8, 10}
k in {2, 3, 4}
```

## Target Success Rate

Recommended defaults:

```text
target_success_rate = 0.95
probe_trials = 30
final_trials = 100
```

For smoke tests:

```text
target_success_rate = 0.9
probe_trials = 10
final_trials = 20
```

The success condition should be:

```text
successes >= ceil(target_success_rate * trials)
```

## Search Strategy

Reuse the same core idea as `tests/test_find_best_m.py`:

1. Choose lower bound:

   ```text
   lo = max(k, ceil(d / l))
   ```

2. Choose an initial upper bound depending on mode:

   ```text
   random:   initial_factor = 2.5
   circular: initial_factor = 1.5
   naive:    initial_factor = 2.5
   ```

   These are starting points only.

3. Double `hi` until the mode succeeds or reaches:

   ```text
   max_C_over_d = 8.0
   ```

4. Binary search for the smallest working `M`.
5. Final-validate `best_M` with more trials.

## Choosing `z`

`z` only matters for spatial modes.

For `circular` and `naive`, use:

```text
z = max(0, round(M^(1/3) / 3))
```

For `random`, use:

```text
z = 0
```

The script should still record `z` for every probe.

## Python Script Structure

Recommended functions:

```python
def repo_root() -> Path:
    """Return repository root."""

def ensure_dirs(root: Path) -> dict[str, Path]:
    """Create output directories."""

def build_benchmark(root: Path) -> Path:
    """Build or locate xyz_v2_bench."""

def make_grid(args) -> list[dict]:
    """Create d/l/k/mode configurations."""

def modes_for_k(k: int, include_diagnostic_circular: bool) -> list[str]:
    """Return modes to test for a k value."""

def choose_z(mode: str, m: int) -> int:
    """Return z for this mode and M."""

def initial_factor(mode: str, k: int) -> float:
    """Return initial upper-bound factor."""

def run_probe(binary: Path, config: dict, m: int, trials: int, seed: int) -> dict:
    """Run one benchmark probe."""

def works(row: dict, target: float) -> bool:
    """Check whether a probe reaches the target."""

def find_best_m(binary: Path, config: dict) -> tuple[int | None, list[dict]]:
    """Find smallest M for one config/mode."""

def final_validate(binary: Path, config: dict, best_m: int) -> dict:
    """Validate best M with more trials."""

def write_outputs(probes: list[dict], summaries: list[dict]) -> None:
    """Write JSONL and CSV outputs."""
```

## Output Files

Recommended output directory:

```text
tests/results/spatial/
```

Recommended files:

```text
tests/results/spatial/probes.jsonl
tests/results/spatial/summary.jsonl
tests/results/spatial/summary.csv
tests/results/spatial/errors.log
```

## Output Fields

Each summary row should include:

```text
d
l
k
mode
best_M
best_C_over_d
z_at_best_M
target_success_rate
probe_trials
final_trials
final_successes
final_success_rate
encode_avg_s
decode_avg_s
status
seed
```

`status` should be:

```text
ok
unresolved
benchmark_error
```

## Main Comparisons to Report

For each `d/l/k`, the final table should make it easy to compare:

```text
random C/d
circular C/d
naive C/d
spatial improvement over random
```

For `k = 2`, the key comparison is:

```text
random vs circular
```

For `k >= 3`, the key comparison is:

```text
random vs naive
```

If circular is also measured for `k >= 3`, mark it as diagnostic.

## Testing Plan

### 1. Dry Run

The script should support:

```bash
python tests/test_spatial.py --dry-run
```

It should print planned `d/l/k/mode` configurations and search bounds.

### 2. Benchmark Mode Smoke Test

Before running the full script, manually test the C++ benchmark:

```bash
build/xyz_v2_bench.exe --d 1000 --l 6 --k 2 --m 217 --z 2 --mode circular --trials 5 --seed 114514 --ca 10000 --cb 10000 --format jsonl
build/xyz_v2_bench.exe --d 1000 --l 6 --k 2 --m 217 --z 0 --mode random --trials 5 --seed 114514 --ca 10000 --cb 10000 --format jsonl
build/xyz_v2_bench.exe --d 1000 --l 6 --k 3 --m 300 --z 2 --mode naive --trials 5 --seed 114514 --ca 10000 --cb 10000 --format jsonl
```

Expected:

- All modes should run and output valid JSON.
- `random` may need larger `M` than spatial modes.
- `circular` should remain good for `k = 2`.

### 3. Single-Configuration Script Smoke Test

Run:

```bash
python tests/test_spatial.py \
  --d-values 1000 \
  --l-values 6 \
  --k-values 2 \
  --modes random,circular,naive \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9
```

Expected:

- The script should produce one summary row per mode.
- `circular` should need less or comparable `C/d` than `random`.

### 4. `k = 3` Smoke Test

Run:

```bash
python tests/test_spatial.py \
  --d-values 1000 \
  --l-values 6 \
  --k-values 3 \
  --modes random,naive \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9
```

Expected:

- `naive` should be the spatial representative.
- The result should show whether spatial coupling reduces `C/d` relative to random.

### 5. Failure Handling

Use a very small maximum communication budget:

```bash
python tests/test_spatial.py --max-C-over-d 1.05
```

Expected:

- Some modes should be marked `unresolved`.
- The script should continue to other configurations.

## Interpretation Notes

This experiment should be interpreted as an empirical comparison of required communication cost under the current implementation. It does not prove the theoretical threshold.

Important caveats:

- `best_M` depends on target success rate and trial count.
- Small `d` values can have strong finite-size effects.
- `z` is chosen by a heuristic and should later be studied separately.
- `circular` and `naive` should not be mixed when explaining the result; they are different spatial-coupling variants.

## Relationship to Other Scripts

- `tests/test_dlk.py`: fixed-grid sweep over `d/l/k`.
- `tests/test_find_best_m.py`: generic best-`M` search for one algorithm mode.
- `tests/test_spatial.py`: best-`M` search grouped by spatial mode, designed specifically to isolate the benefit of spatial coupling.

## Build and Usage Guide

The implemented experiment uses:

- `XYZ-v2/hash.cpp` and `XYZ-v2/hash.h` for selectable hash modes.
- `tests/benchmarks/xyz_v2_bench.cpp` for benchmark execution.
- `tests/test_spatial.py` for mode-wise best-`M` search.

### Benchmark Modes

The benchmark now accepts:

```text
--mode random
--mode circular
--mode naive
--mode spatial
```

`spatial` is the compatibility mode:

```text
k <= 2 -> circular
k >= 3 -> naive
```

### Manual Benchmark Smoke Test

From the repository root:

```powershell
g++ -std=c++17 -O2 tests\benchmarks\xyz_v2_bench.cpp -o build\xyz_v2_bench.exe
build\xyz_v2_bench.exe --d 1000 --l 6 --k 2 --m 217 --z 2 --mode circular --trials 5 --seed 114514 --ca 10000 --cb 10000 --format jsonl
build\xyz_v2_bench.exe --d 1000 --l 6 --k 2 --m 217 --z 0 --mode random --trials 5 --seed 114514 --ca 10000 --cb 10000 --format jsonl
build\xyz_v2_bench.exe --d 1000 --l 6 --k 3 --m 300 --z 2 --mode naive --trials 5 --seed 114514 --ca 10000 --cb 10000 --format jsonl
```

### Script Dry Run

```bash
python tests/test_spatial.py --dry-run
```

Single `k = 2` dry run:

```bash
python tests/test_spatial.py --dry-run --d-values 1000 --l-values 6 --k-values 2 --modes random,circular,naive
```

### Script Smoke Tests

For `k = 2`:

```bash
python tests/test_spatial.py \
  --skip-build \
  --d-values 1000 \
  --l-values 6 \
  --k-values 2 \
  --modes random,circular,naive \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9 \
  --output-dir tests/results/spatial_smoke_k2
```

For `k = 3`:

```bash
python tests/test_spatial.py \
  --skip-build \
  --d-values 1000 \
  --l-values 6 \
  --k-values 3 \
  --modes random,naive \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9 \
  --output-dir tests/results/spatial_smoke_k3
```

### Full Default Run

```bash
python tests/test_spatial.py
```

Default output:

```text
tests/results/spatial/probes.jsonl
tests/results/spatial/summary.jsonl
tests/results/spatial/summary.csv
```

### Note on Small Trial Counts

With small values such as `probe_trials = 10` and `final_trials = 20`, binary search may find a boundary `M` that passes probe trials but fails final validation. In that case the summary status is `unresolved`.

For more stable results, use:

```bash
python tests/test_spatial.py --probe-trials 30 --final-trials 100 --target-success-rate 0.95
```

