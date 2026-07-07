# Find Best `M` Planning Document

This document plans a future script for finding the smallest suitable `M` for each parameter setting, especially for different `k` values. No code is implemented here.

## Motivation

The current `d/l/k` sweep uses a fixed heuristic for `M`. That is enough for a first pass, but it is not a fair way to compare different `k` values.

In particular:

- The existing XYZ-v2 experiments were mainly tuned for `k = 2`.
- Circular spatial coupling works well for `k = 2`.
- Naive/non-circular spatial coupling needs a larger `M`.
- For `k >= 3`, reusing the `k = 2` communication budget can make the result look artificially bad.

Therefore, before comparing `k = 2`, `k = 3`, and `k = 4`, we should search for the smallest `M` that reaches a target decoding success rate.

## Goal

For each configuration:

```text
d, l, k, z policy, hash mode, target success rate
```

find the smallest `M` such that XYZ-v2 reaches the target success rate over repeated trials.

The main output should be:

```text
best_M
C_over_d = best_M * l / d
measured_success_rate
encode/decode timing at best_M
```

## Proposed Script Name

Recommended future script:

```text
tests/test_find_best_m.py
```

This should be separate from `tests/test_dlk.py`, because threshold search is a different experiment from a fixed-grid sweep.

## C++ Benchmark Dependency

The script should reuse:

```text
tests/benchmarks/xyz_v2_bench.cpp
```

The benchmark already supports:

```bash
--d
--l
--k
--m
--z
--trials
--seed
--mode spatial
--ca
--cb
--format jsonl
```

The script should call the benchmark with an exact `--m` value during binary search.

## Search Target

Use one or more target success rates:

```text
0.50 for threshold-style exploration
0.95 for practical settings
0.99 if the trial count is large enough
```

Recommended first target:

```text
target_success_rate = 0.95
```

However, when using a small trial count, `0.95` is not very meaningful. For example, with `20` trials, the nearest practical thresholds are:

```text
19/20 = 0.95
20/20 = 1.00
```

So the script should define success as:

```text
successes >= ceil(target_success_rate * trials)
```

## Binary Search Assumption

The search assumes monotonicity:

```text
If M works, then larger M should usually also work.
```

This is true in the intended probabilistic sense, but measured success can be noisy because every `M` may use different random trials.

To reduce noise, the script should use the same base seed for all `M` values in a single search. That makes comparisons more stable.

## Search Procedure

For each configuration:

1. Choose a lower bound `lo`.
2. Choose an upper bound `hi`.
3. Increase `hi` until it works.
4. Binary search between `lo` and `hi`.
5. Re-test the final `best_M` with more trials.
6. Save both raw probe records and the final summary.

### Lower Bound

A safe lower bound is:

```text
lo = max(k, ceil(d / l))
```

This corresponds to roughly `C/d >= 1`.

For very small `d`, it may be useful to enforce:

```text
lo >= 1
```

### Initial Upper Bound

Use a conservative starting point:

```text
hi = ceil(initial_factor * d / l)
```

Suggested `initial_factor`:

```text
k = 2: initial_factor = 1.5
k = 3: initial_factor = 2.5
k = 4: initial_factor = 3.5
```

These are only starting values. If `hi` fails, double it:

```text
hi = hi * 2
```

until success or until a maximum limit is reached.

### Maximum Limit

To avoid runaway experiments, set:

```text
max_C_over_d = 8.0
max_M = ceil(max_C_over_d * d / l)
```

If no `M` works before this limit, mark the configuration as unresolved.

## Choosing `z`

There are two possible policies.

### Policy A: `z` Depends on `M`

For every candidate `M`, recompute:

```text
z = max(0, round(M^(1/3) / 3))
```

This is simple and adapts to the search range.

### Policy B: Fixed `z`

Fix `z` for all `M` in a search, usually based on the initial or expected `M`.

This isolates the effect of `M`, but can make the result worse if `z` is badly chosen.

Recommended first implementation:

```text
Use Policy A.
```

Later, `z` sensitivity should be handled by a separate experiment.

## Hash Mode Policy

Use:

```text
k = 2: circular spatial coupling
k >= 3: naive/non-circular spatial coupling
```

Currently this is implemented inside `XYZ-v2/hash.cpp` by selecting behavior based on global `k`.

The script can continue passing:

```bash
--mode spatial
```

The exact circular-vs-naive choice is currently made by the C++ code.

## Recommended Parameter Grid

Start small:

```text
d in {1000, 3000, 10000}
l in {4, 6, 8}
k in {2, 3}
trials_per_probe = 20
final_trials = 100
target_success_rate = 0.95
```

Then expand:

```text
d in {100, 300, 1000, 3000, 10000, 30000, 100000}
l in {2, 3, 4, 6, 8, 10}
k in {2, 3, 4}
trials_per_probe = 30
final_trials = 100
```

Large `d` values should be added only after the script is stable.

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
    """Create d/l/k configurations."""

def choose_z(m: int, policy: str) -> int:
    """Choose z for a candidate M."""

def run_probe(binary: Path, config: dict, m: int, trials: int, seed: int) -> dict:
    """Run one benchmark probe and return parsed JSON."""

def works(row: dict, target: float) -> bool:
    """Return whether a benchmark row meets the target success count."""

def find_upper_bound(binary: Path, config: dict) -> tuple[int, list[dict]]:
    """Find a working hi value, collecting raw probes."""

def binary_search_m(binary: Path, config: dict) -> tuple[int | None, list[dict]]:
    """Find the smallest working M."""

def final_validate(binary: Path, config: dict, best_m: int) -> dict:
    """Re-test best M with more trials."""

def write_outputs(raw_probes: list[dict], summaries: list[dict]) -> None:
    """Write raw and summary outputs."""
```

## Output Files

Recommended directory:

```text
tests/results/best_m/
```

Recommended files:

```text
tests/results/best_m/probes.jsonl
tests/results/best_m/summary.jsonl
tests/results/best_m/summary.csv
tests/results/best_m/errors.log
```

### `probes.jsonl`

Contains every benchmark call made during the upper-bound search and binary search.

Add fields such as:

```text
search_id
phase = upper_bound | binary_search | final_validate
candidate_M
target_success_rate
required_successes
```

### `summary.jsonl` / `summary.csv`

One row per searched configuration:

```text
d,l,k,best_M,best_C_over_d,z_policy,target_success_rate,
probe_trials,final_trials,final_successes,final_success_rate,
encode_avg_s,decode_avg_s,status
```

`status` should be one of:

```text
ok
unresolved
benchmark_error
```

## Testing Plan

### 1. Unit-Level Dry Run

The script should support:

```bash
python tests/test_find_best_m.py --dry-run
```

This should print the planned configurations without calling the benchmark.

### 2. Single Configuration Smoke Test

Run:

```bash
python tests/test_find_best_m.py \
  --d-values 1000 \
  --l-values 6 \
  --k-values 3 \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9
```

Expected behavior:

- The script should first try a lower or initial `M`.
- If it fails, it should increase `M`.
- It should eventually find a working `M` around the range where manual tests succeeded.

Based on current manual tests:

```text
d=1000, l=6, k=3
M=217 failed
M=300 succeeded
```

So a reasonable result should find `best_M` somewhere near this interval, depending on trials and seeds.

### 3. Compare with Known `k = 2` Case

Run:

```bash
python tests/test_find_best_m.py \
  --d-values 1000 \
  --l-values 6 \
  --k-values 2 \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9
```

Expected behavior:

- The found `M` should be close to or below the existing tuned value `217`.
- If it is much larger, inspect the search logic and `z` policy.

### 4. Reproducibility Test

Run the same command twice with the same seed. The result should be identical if all candidate probes use deterministic seeds.

### 5. Failure Handling Test

Use an artificially tiny `max_C_over_d`, such as:

```bash
python tests/test_find_best_m.py --max-C-over-d 1.05
```

Expected behavior:

- Some configurations should be marked `unresolved`.
- The script should not crash.

## Interpretation Notes

The result should not be interpreted as an exact mathematical threshold. It is an empirical threshold under:

- the chosen random seed policy,
- the chosen number of trials,
- the chosen `z` policy,
- the current hash implementation,
- and the current dataset generator.

For paper-quality results, the final selected `best_M` values should be validated with more trials and possibly multiple independent seed groups.

## Important Caveat

Binary search can be misleading if measured success is noisy. For example:

```text
M = 280 succeeds by chance
M = 290 fails by chance
M = 300 succeeds
```

To reduce this issue:

- Use enough probe trials.
- Keep seeds deterministic across candidate `M`.
- Re-test the final `best_M` with more trials.
- Optionally also test `best_M - 1` and `best_M + 1` in the final validation phase.

