# `tests/test_circular_a.py` Design Plan

This document plans an experiment for the circular spatial-coupling parameter `a` in XYZ-v2. It is a planning document only; no code is implemented here.

## Goal

The paper describes a circular placement rule with a tunable parameter:

```text
g0: U -> [0, z + a),  a in [0, 1)
gi: U -> [0, 1)
```

The practical question is:

```text
For circular spatial coupling, which value of a gives the lowest communication threshold or the highest success rate?
```

This is not a core experiment unless the proof narrative or paper discussion needs it. It should be treated as a follow-up diagnostic experiment after the main `d/l/k`, spatial-coupling, sharp-threshold, and baseline comparisons.

## Current Implementation Status

The current code already has circular spatial coupling:

```text
XYZ-v2/hash.cpp
tests/benchmarks/xyz_v2_bench.cpp
tests/test_spatial.py
```

The current circular base range is hard-coded:

```cpp
inline int circular_base_h0(int x) {
    return MurmurHash::Hash(x, 114514) % (M - RangeLength / 3 + 1);
}
```

Since:

```text
RangeLength = M / (z + 1)
```

this is approximately equivalent to using:

```text
a = 1/3
```

under the current discretized implementation. Therefore the first implementation should not invent a new rule from scratch. It should generalize the existing hard-coded `1/3` into a parameter.

## Required C++ Changes

### `XYZ-v2/hash.h`

Add a circular-parameter setter/getter:

```cpp
namespace SpatialCoupling {
    void SetCircularA(double value);
    double GetCircularA();
}
```

The default should preserve current behavior:

```text
default circular_a = 1.0 / 3.0
```

### `XYZ-v2/hash.cpp`

Add a global circular parameter:

```cpp
double CircularA = 1.0 / 3.0;
```

Update `circular_base_h0` from:

```cpp
M - RangeLength / 3 + 1
```

to a parameterized base range:

```cpp
base_range = M - floor(CircularA * RangeLength) + 1
```

Then clamp it safely:

```text
base_range >= 1
base_range <= M
```

Rationale:

- `a = 1/3` reproduces the current `RangeLength / 3` integer-division behavior.
- `a = 0` gives a base range close to `M`, meaning the circular window can start almost anywhere.
- Larger `a` reduces the base range and changes how much mass is pushed away from the wrap boundary.

The implementation should reject values outside:

```text
0 <= a < 1
```

### `tests/benchmarks/xyz_v2_bench.cpp`

Add a CLI argument:

```text
--circular-a FLOAT
```

Behavior:

- Only meaningful for `--mode circular` or `--mode spatial` when `k <= 2` and auto mode selects circular.
- Still record the value for all rows so output is easy to filter.
- Default to `1.0 / 3.0`.

The benchmark should call:

```cpp
SpatialCoupling::SetCircularA(opt.circular_a);
```

before `SpatialCoupling::HashingInit(opt.Z)`.

Output fields:

```text
circular_a
```

If possible, also output:

```text
circular_base_range
range_length
```

These are useful for checking integer rounding effects.

## Python Script

Recommended script:

```text
tests/test_circular_a.py
```

This script should scan `a` for circular spatial coupling.

It should be separate from `tests/test_spatial.py` because `test_spatial.py` compares modes, while this script holds the circular mode fixed and varies one internal parameter.

## Experiment Modes

The script should support two modes.

### Fixed-`M` Scan

Hold `M` fixed and measure success rate for different `a`.

Use this to see the shape of the curve cheaply:

```text
d, l, k, M, z fixed
a scanned over a grid
```

Recommended first grid:

```text
a in {0.0, 0.1, 0.2, 1/3, 0.4, 0.5, 0.6, 0.75, 0.9}
```

Expected output:

```text
success_rate vs a
bits unchanged because M is fixed
```

### Threshold Search

For each `a`, search for the smallest `M` that reaches a target success rate.

This is the paper-facing mode:

```text
for each a:
    binary-search best M
    final-validate best M
    report best_C_over_d and confidence interval
```

This should reuse the threshold-search structure from:

```text
tests/test_find_best_m.py
tests/test_spatial.py
```

Expected output:

```text
best_M vs a
best_C_over_d vs a
final_success_rate and CI vs a
```

## Recommended Parameters

Focus on `k = 2` first. The paper says circular performs well for `k = 2` and poorly for larger `k`, so `a` tuning is most relevant for `k = 2`.

Initial smoke grid:

```text
d = 100
l = 6
k = 2
trials = 5
a in {0.0, 1/3, 0.6}
```

Main fixed-`M` grid:

```text
d in {1000, 3000, 10000}
l = 6
k = 2
M from current best-M policy for circular
trials = 50
a in {0.0, 0.1, 0.2, 1/3, 0.4, 0.5, 0.6, 0.75, 0.9}
```

Main threshold grid:

```text
d in {1000, 3000, 10000}
l = 6
k = 2
target_success_rate = 0.95
probe_trials = 30
final_trials = 100
a in {0.0, 0.1, 0.2, 1/3, 0.4, 0.5, 0.6, 0.75, 0.9}
```

Diagnostic grid for `k >= 3`:

```text
d in {1000, 3000}
l = 6
k in {3, 4}
mode = circular
a in {0.0, 1/3, 0.6}
```

This should be clearly marked diagnostic. It should not replace the `naive` spatial-coupling results for `k >= 3`.

## Choosing `z`

Use the same heuristic as other spatial experiments:

```text
z = max(0, round(M^(1/3) / 3))
```

Do not scan `z` and `a` at the same time in the first version. That would make the experiment too large and harder to interpret.

Later, if needed, a small two-dimensional diagnostic scan can test:

```text
z around the heuristic value
a around the best observed value
```

## Dataset Policy

The first version may use the internal deterministic generator in `xyz_v2_bench`, consistent with `test_spatial.py`.

If the result becomes paper-facing, switch to shared datasets from:

```text
tests/dataset_generator.py
```

This makes different `a` values a paired comparison on identical Alice/Bob sets.

Recommended policy:

- Smoke mode: internal generator is acceptable.
- Main fixed-`M` and threshold mode: use shared datasets if practical.

## JSON Output

Use `benchmark.v1` rows.

Probe rows should include:

```text
experiment = "circular_a"
record_type = "probe"
algorithm = "xyz_v2"
variant = "circular_a=<value>"
mode = "circular"
d
l
k
M
z
circular_a
successes
trials
success_rate
ci_low
ci_high
bits
bit_C_over_d
status
```

Threshold summary rows should include:

```text
record_type = "threshold"
best_M
best_C_over_d
final_success_rate
final_ci_low
final_ci_high
target_success_rate
threshold_policy
```

Fixed-`M` summary rows should include:

```text
record_type = "aggregate"
M
C_over_d
circular_a
success_rate
ci_low
ci_high
```

## Output Layout

Recommended output directory:

```text
tests/results/circular_a/
```

Recommended files:

```text
raw.jsonl
raw.csv
summary.jsonl
summary.csv
summary.md
run_config.json
errors.log
```

## CLI Design

Suggested arguments:

```text
--d-values
--l-values
--k-values
--a-values
--mode fixed-m|threshold
--m-values
--target-success-rate
--probe-trials
--final-trials
--trials
--ci-confidence
--threshold-policy
--skip-build
--dry-run
--limit
--output-dir
--base-seed
--max-set-size
--set-size-scale
```

Example smoke command:

```bash
python tests/test_circular_a.py \
  --mode fixed-m \
  --d-values 100 \
  --l-values 6 \
  --k-values 2 \
  --a-values 0,0.3333333333,0.6 \
  --trials 5 \
  --limit 3 \
  --output-dir tests/results/circular_a_smoke
```

Example threshold command:

```bash
python tests/test_circular_a.py \
  --mode threshold \
  --d-values 1000,3000 \
  --l-values 6 \
  --k-values 2 \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --probe-trials 30 \
  --final-trials 100 \
  --target-success-rate 0.95 \
  --output-dir tests/results/circular_a
```

## Interpretation

The expected result is not necessarily a smooth universal optimum. The best `a` may depend on:

- `d`;
- `M`;
- `z`;
- finite-size effects;
- integer rounding in `RangeLength`;
- `k`.

The summary should report:

```text
best observed a for each d/l/k
whether a = 1/3 remains competitive
whether improvements are larger than the confidence intervals
```

If `a = 1/3` is close to optimal, keep the current default and cite the experiment as a sanity check. If another `a` is consistently better, update the default only after confirming that it also behaves well across several `d` values.

## Implementation Order

1. Expose `circular_a` in `XYZ-v2/hash.cpp` and `XYZ-v2/hash.h`.
2. Add `--circular-a` and output fields in `tests/benchmarks/xyz_v2_bench.cpp`.
3. Implement `tests/test_circular_a.py` in fixed-`M` mode.
4. Verify smoke output with `tests/json_verifier.py --strict`.
5. Add threshold-search mode.
6. Run the main `k = 2` threshold grid.
7. Optionally run `k = 3,4` diagnostic circular scans.

## Completion Criteria

This task is complete when:

- the current default `a = 1/3` can be reproduced by the parameterized implementation;
- fixed-`M` scans produce valid JSON and a readable summary;
- threshold scans identify the best observed `a` for representative `d`;
- all output rows pass strict JSON verification;
- the summary clearly states whether changing `a` is worthwhile.

## Current Run Status

The implementation and smoke tests exist. The full paper-facing grid has not been run yet.

Completed smoke coverage:

```text
fixed-M smoke with d = 100, l = 6, k = 2
threshold smoke with tiny d/trial settings
strict JSON verification for smoke outputs
```

Still missing:

```text
d in {1000, 3000, 10000}
k = 2
main threshold grid over a-values
optional k = 3,4 diagnostic circular scans
```
