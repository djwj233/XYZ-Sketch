# XYZ Uniform vs Spatial-Coupling Sharp-Threshold Plan

This document plans a sharp-threshold experiment for:

```text
XYZ-uniform
XYZ-SC
```

No code is implemented here. The goal is to show how decoding success changes when `M` moves through the critical region, and to compare whether spatial coupling shifts or sharpens that transition.

## Motivation

The existing threshold-search scripts answer:

```text
What is the smallest tested M that reaches a target success rate?
```

A sharp-threshold experiment asks a different question:

```text
What does the whole success-rate curve look like around the threshold?
```

If the algorithm has a sharp threshold, then a small increase in `M` near the critical value should move the success rate quickly from mostly failing to mostly succeeding.

This experiment should provide visual and tabular evidence for that transition, separately for uniform placement and spatial coupling.

## Definitions

Use XYZ-v2 as the implementation.

```text
XYZ-uniform = XYZ-v2 with --mode random
XYZ-SC = XYZ-v2 with spatial coupling enabled
```

For `XYZ-SC`, the recommended default is:

```text
--mode spatial
```

This keeps the current implementation's automatic policy:

```text
k = 2     -> circular spatial coupling
k >= 3   -> naive/non-circular spatial coupling
```

For diagnostic runs, the script should also allow explicit modes:

```text
--modes random,spatial
--modes random,circular
--modes random,naive
```

The main paper-facing comparison should use:

```text
random vs spatial
```

unless a section explicitly discusses circular or naive variants.

## Proposed Script

Recommended future script:

```text
tests/test_xyz_sharp_threshold.py
```

It should reuse:

```text
tests/benchmarks/xyz_v2_bench.cpp
tests/statistics.py
tests/json_schema.py
tests/dataset_generator.py
```

It should not modify any algorithm subproject.

## High-Level Experiment Design

For each configuration:

```text
d, l, k, mode
```

the script should:

1. Estimate a threshold center `M0`.
2. Generate a dense grid of `M` values around `M0`.
3. Run the benchmark at every `M`.
4. Record success rate and confidence interval for each `M`.
5. Summarize threshold location and transition width.

The output should support plots like:

```text
x-axis: C/d or M
y-axis: success_rate
bands: ci_low to ci_high
series: random vs spatial
```

## Choosing the Threshold Center

There are two practical options.

### Option A: Use Existing Threshold Results

If `tests/results/spatial/summary.jsonl` or another threshold-search output exists, use it as input:

```text
--threshold-summary tests/results/spatial/summary.jsonl
```

For each `(d, l, k, mode)`, read:

```text
point_best_M
best_M
ci_low_best_M
```

Recommended center priority:

```text
point_best_M if available
best_M otherwise
```

This avoids redoing the rough threshold search.

### Option B: Estimate Internally

If no summary is provided, run a quick search internally. This can reuse the same basic logic as `test_spatial.py`:

```text
find a working upper bound
binary search by point threshold
use that M as M0
```

The first implementation can keep this simple. The dense scan is the main result.

## M Grid Around the Threshold

Given `M0`, scan around it using either a relative or absolute window.

Recommended defaults:

```text
window_fraction = 0.20
min_window = 8
points = 41
```

Compute:

```text
radius = max(min_window, ceil(window_fraction * M0))
M_min = max(k, ceil(d / l), M0 - radius)
M_max = M0 + radius
```

Then choose evenly spaced integer values between `M_min` and `M_max`, de-duplicated and sorted.

For small `d`, the grid can be dense by every integer:

```text
step = 1
```

For larger `d`, use a fixed number of points to avoid runaway cost.

## Parameter Grid

Start with a focused grid:

```text
d in {1000, 3000, 10000}
l = 6
k in {2, 3}
modes = {random, spatial}
```

Then expand if runtime is acceptable:

```text
d in {100, 300, 1000, 3000, 10000, 30000}
l in {4, 6, 8}
k in {2, 3, 4}
modes = {random, spatial}
```

For paper-quality curves, prioritize:

```text
d in {3000, 10000}
l = 6
k in {2, 3}
```

These are large enough to show threshold behavior but still manageable.

## Trial Counts

Sharp-threshold plots need enough trials per point.

Recommended defaults:

```text
trials = 100
ci_confidence = 0.95
ci_method = wilson
```

For quick smoke tests:

```text
trials = 5 or 10
```

For paper-quality curves:

```text
trials >= 200 near the steep transition
```

The script may optionally support adaptive trials later, but the first implementation should use a fixed trial count per point.

## z Policy

For uniform mode:

```text
z = 0
```

For spatial modes:

```text
z = max(0, round(M^(1/3) / 3))
```

This matches the current heuristic used by the other scripts.

The script should also allow:

```text
--fixed-z <int>
```

for diagnostic runs, but the default should remain adaptive.

## Dataset Policy

The current `xyz_v2_bench` supports internal generation and optional dataset files. For this experiment, there are two acceptable modes:

```text
internal_generator
shared_file
```

Recommended first implementation:

```text
dataset_mode = internal_generator
```

Reason: the existing threshold-search scripts use internal generation, and the sharp-threshold script should first match their behavior.

Later, add:

```text
--dataset-mode shared_file
```

to reuse `tests/dataset_generator.py` and make random-vs-spatial curves share exact per-trial datasets.

## Output Files

Recommended output directory:

```text
tests/results/xyz_sharp_threshold/
```

Files:

```text
raw.jsonl
raw.csv
summary.jsonl
summary.csv
summary.md
run_config.json
errors.log
```

`raw.jsonl` should contain one row per `(d, l, k, mode, M)` scan point.

Use:

```text
schema_version = benchmark.v1
experiment = xyz_sharp_threshold
record_type = aggregate
algorithm = xyz_v2
variant = mode
```

## Raw Row Fields

Each raw row should include:

```text
d
l
k
M
z
mode
ca
cb
seed
trials
successes
success_rate
ci_low
ci_high
ci_method
ci_confidence
bits
bits_per_difference
bit_C_over_d
field_C_over_d
encode_avg_s
decode_avg_s
encode_median_s
decode_median_s
dataset_mode
status
```

Additional fields:

```text
scan_id
M0
M_offset
C_over_d_offset
grid_index
grid_size
threshold_source
```

## Summary Metrics

For each `(d, l, k, mode)`, summarize:

```text
point_M_50
point_M_95
ci_low_M_95
transition_M_min
transition_M_max
transition_width_M
transition_C_over_d_min
transition_C_over_d_max
transition_width_C_over_d
max_slope
```

Definitions:

```text
point_M_50 = smallest M with success_rate >= 0.50
point_M_95 = smallest M with success_rate >= 0.95
ci_low_M_95 = smallest M with ci_low >= 0.95
transition_M_min = smallest M with ci_high >= 0.10
transition_M_max = smallest M with ci_low >= 0.90
transition_width_M = transition_M_max - transition_M_min
```

`max_slope` can be estimated from adjacent scan points:

```text
delta success_rate / delta C_over_d
```

These are empirical descriptors, not theoretical proofs.

## Comparing Uniform and SC

For each `(d, l, k)`, compare:

```text
uniform_M_95
sc_M_95
uniform_C_over_d_95
sc_C_over_d_95
relative_improvement = (uniform_C_over_d_95 - sc_C_over_d_95) / uniform_C_over_d_95
transition_width_uniform
transition_width_sc
```

Expected interpretation:

- If SC works as intended, its curve should shift left, needing smaller `C/d`.
- The transition may also become sharper, but this is an empirical question.
- If curves overlap heavily, report that spatial coupling did not clearly improve that configuration.

## CLI Sketch

Recommended CLI:

```powershell
python tests\test_xyz_sharp_threshold.py ^
  --d-values 1000,3000,10000 ^
  --l-values 6 ^
  --k-values 2,3 ^
  --modes random,spatial ^
  --trials 100 ^
  --ci-confidence 0.95 ^
  --threshold-summary tests\results\spatial\summary.jsonl ^
  --output-dir tests\results\xyz_sharp_threshold
```

Smoke test:

```powershell
python tests\test_xyz_sharp_threshold.py ^
  --d-values 100 ^
  --l-values 6 ^
  --k-values 2 ^
  --modes random,spatial ^
  --trials 5 ^
  --points 7 ^
  --output-dir tests\results\xyz_sharp_threshold_smoke ^
  --skip-build
```

## Testing Plan

### Dry Run

```powershell
python tests\test_xyz_sharp_threshold.py --dry-run --d-values 100 --l-values 6 --k-values 2 --modes random,spatial --points 7
```

Expected:

```text
prints planned scan points
shows M0 and M grid for each mode
does not run benchmark
```

### Smoke Run

Run the smoke command above.

Then verify:

```powershell
python tests\json_verifier.py tests\results\xyz_sharp_threshold_smoke\raw.jsonl --strict
```

Expected:

```text
random and spatial both produce rows
success_rate generally increases with M, though noise is allowed
CI fields are present and valid
summary files are written
```

### Consistency Checks

The script should warn, not fail, when measured success is non-monotone. Non-monotonicity can happen because of finite trials.

Useful warnings:

```text
success_rate drops by more than 0.30 between adjacent M values
no point reaches 0.50
no point reaches 0.95
all points have success_rate = 1.0, meaning the grid is too far above threshold
all points have success_rate = 0.0, meaning the grid is too far below threshold
```

## Plotting Plan

The first script does not need to generate plots, but the output should be plot-ready.

Recommended later plot:

```text
one panel per (d, l, k)
x-axis = C/d
y-axis = success_rate
line = mode
ribbon = [ci_low, ci_high]
vertical marker = point_M_95 or ci_low_M_95
```

The summary table should provide paper-ready values even before plotting.

## Risks

1. If `M0` is poor, the dense grid may miss the transition.
   - Mitigation: detect all-zero/all-one curves and recommend expanding the window.
2. Success rates can be noisy.
   - Mitigation: use Wilson intervals and enough trials.
3. `random` may need much larger `M` than `spatial`.
   - Mitigation: estimate separate `M0` per mode, not one shared center.
4. `spatial` is an automatic mode.
   - Mitigation: record both `mode` and explicit `z`; optionally run explicit `circular`/`naive` diagnostics.

## Completion Criteria

This task is complete when:

```text
tests/test_xyz_sharp_threshold.py exists
it can scan random and spatial modes around mode-specific M0 values
raw rows use benchmark.v1 and include CI fields
summary rows identify 50%, 95%, and CI-lower-bound thresholds
strict JSON verification passes
smoke run completes
the output is sufficient for success-rate-vs-C/d plots
```
