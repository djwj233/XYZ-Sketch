# IBLT Uniform vs Spatial-Coupling Comparison Plan

This document plans how to add an IBLT-uniform vs IBLT-SC comparison. No code is implemented here.

The goal is to compare the effect of spatial coupling inside the IBLT family, in the same spirit as the existing XYZ-uniform vs XYZ-SC experiments.

## Current State

The repository currently has:

```text
IBLT/iblt.cpp
tests/benchmarks/iblt_bench.cpp
tests/test_compare_basic.py
```

The local IBLT implementation is a standard uniform-placement IBLT:

```text
each item updates hash_count cells chosen uniformly from [0, cell_count)
```

`tests/benchmarks/iblt_bench.cpp` exposes:

```text
--d
--trials
--seed
--ca
--cb
--capacity-factor
--dataset
--format jsonl
```

It does not currently expose a placement mode. Therefore, the existing local IBLT rows should be interpreted as:

```text
IBLT-uniform
```

## Goal

Add a controlled comparison between:

```text
IBLT-uniform
IBLT-SC
```

where both variants use:

```text
same cell structure
same peeling decoder
same input datasets
same hash count when possible
same communication accounting
```

Only the item-to-cell placement rule should differ.

## Important Constraint

Do not modify algorithm subproject files:

```text
IBLT/
external/
XYZ-v1/
XYZ-v2/
```

Any new benchmark or experimental implementation should live under:

```text
tests/
tests/benchmarks/
```

This keeps submodules and reference implementations clean.

## Definitions

### IBLT-uniform

The current local IBLT behavior:

```text
h_i(x) = uniform hash into [0, N)
```

where:

```text
N = ceil(capacity_factor * d)
```

and each item updates `hash_count` cells.

### IBLT-SC

A spatially coupled IBLT placement rule.

Use:

```text
g0(x): base position
g_i(x): offset inside a coupling window
h_i(x): g0(x) + g_i(x)
```

Recommended first implementation:

```text
non-circular spatial coupling
```

where:

```text
g0(x) in [0, N - W]
offset_i(x) in [0, W)
h_i(x) = g0(x) + offset_i(x)
```

Here:

```text
N = total cell count
W = coupling window size
```

The window can be parameterized by `z`:

```text
W = max(hash_count, floor(N / (z + 1)))
```

This mirrors the existing XYZ scripts where larger `z` means smaller coupled range.

The benchmark can later also support circular SC:

```text
h_i(x) = (g0(x) + offset_i(x)) mod N
```

but the first IBLT-SC comparison should use one primary SC rule to avoid mixing interpretations.

## Implementation Strategy

Create a new benchmark wrapper under `tests/benchmarks/`, for example:

```text
tests/benchmarks/iblt_sc_bench.cpp
```

This file should contain a test-side IBLT implementation or a small wrapper class that mirrors the local IBLT cell operations:

```text
count
key_sum
key_check
```

The reason to make a new wrapper instead of editing `IBLT/iblt.cpp` is that the current IBLT class hides its hash function and cell update locations. Spatial coupling changes exactly that part.

The new wrapper should expose:

```text
--mode uniform|spatial
--capacity-factor F
--hash-count K
--z Z
--dataset PATH
```

For `--mode uniform`, it should reproduce the current `iblt_bench.cpp` behavior closely enough to serve as a consistency check.

For `--mode spatial`, it should use the SC placement rule.

## Communication Accounting

Keep the same cell layout as the local IBLT benchmark:

```text
cell = tuple<int, uint32_t, uint32_t>
cell_bits = sizeof(cell) * 8
bits = cell_count * cell_bits
bit_C_over_d = bits / (32 * d)
```

Report:

```text
cells
cell_bits
hash_count
capacity_factor
bits
bits_per_difference
bit_C_over_d
```

This makes IBLT-uniform and IBLT-SC directly comparable.

## Script Design

Recommended script:

```text
tests/test_iblt_spatial.py
```

This should be a threshold-search style script, analogous to `tests/test_spatial.py`, but for IBLT.

For each configuration:

```text
d, mode, hash_count, target_success_rate
```

search for the smallest `capacity_factor` or `cell_count` that reaches the target success rate.

Recommended search variable:

```text
cell_count
```

because `capacity_factor` is a derived value:

```text
capacity_factor = cell_count / d
```

However, the CLI can expose user-friendly factor bounds:

```text
--min-capacity-factor
--max-capacity-factor
```

Internally:

```text
lo = ceil(min_capacity_factor * d)
hi = ceil(max_capacity_factor * d)
```

## Why Search Cell Count Instead of Fixed Factors?

A fixed factor grid is useful for smoke testing:

```text
capacity_factor in {1.0, 1.2, 1.5, 2.0, 2.5}
```

But a fair SC comparison should report the minimum communication needed to hit the same target success rate.

Therefore:

```text
fixed-grid mode = diagnostic
threshold-search mode = main result
```

## Parameter Grid

Start small:

```text
d in {100, 300, 1000}
modes = {uniform, spatial}
hash_count = auto
target_success_rate = 0.95
probe_trials = 20
final_trials = 100
```

Then expand:

```text
d in {1000, 3000, 10000, 30000}
modes = {uniform, spatial}
hash_count in {3, 4}
target_success_rate in {0.95, 0.99}
```

Use shared datasets whenever possible:

```text
dataset_mode = shared_file
```

This is especially important because IBLT-uniform and IBLT-SC should be evaluated on identical Alice/Bob sets.

## Hash Count Policy

The current local IBLT uses:

```text
d < 200 -> hash_count = 4
d >= 200 -> hash_count = 3
```

The new benchmark should support:

```text
--hash-count auto
--hash-count 3
--hash-count 4
```

Recommended first comparison:

```text
hash_count = auto
```

Then add explicit `3` and `4` as diagnostic runs.

## z / Window Policy

For uniform mode:

```text
z = 0
```

For spatial mode:

```text
z = max(0, round(cell_count^(1/3) / 3))
```

The script should also allow:

```text
--fixed-z Z
```

The raw output must record:

```text
z
window_size
```

so results can be interpreted later.

## JSON Output

Use `benchmark.v1`.

Recommended experiment name:

```text
iblt_spatial_threshold
```

Probe rows:

```text
record_type = "probe"
algorithm = "iblt"
variant = "uniform" or "spatial"
implementation = "tests/benchmarks/iblt_sc_bench"
```

Summary rows:

```text
record_type = "threshold"
```

Required fields:

```text
d
ca
cb
seed
dataset_mode
mode
capacity_factor
cells
hash_count
cell_bits
z
window_size
trials
successes
success_rate
ci_low
ci_high
bits
bits_per_difference
bit_C_over_d
encode_avg_s
decode_avg_s
status
```

## Output Files

Recommended output directory:

```text
tests/results/iblt_spatial/
```

Files:

```text
probes.jsonl
summary.jsonl
summary.csv
summary.md
run_config.json
errors.log
```

The summary should compare uniform and spatial side by side:

```text
d
hash_count
uniform_cell_count
spatial_cell_count
uniform_bit_C_over_d
spatial_bit_C_over_d
relative_improvement
uniform_ci_low
spatial_ci_low
```

## Smoke Tests

### Benchmark Wrapper Smoke

After implementing the wrapper:

```powershell
build\iblt_sc_bench.exe --d 100 --trials 5 --seed 114514 --ca 1000 --cb 1000 --mode uniform --capacity-factor 2.0 --hash-count auto --format jsonl
build\iblt_sc_bench.exe --d 100 --trials 5 --seed 114514 --ca 1000 --cb 1000 --mode spatial --capacity-factor 2.0 --hash-count auto --z 1 --format jsonl
```

Expected:

```text
both output valid JSON
uniform output is close to existing iblt_bench behavior
spatial output records z and window_size
```

### Script Smoke

```powershell
python tests\test_iblt_spatial.py ^
  --d-values 100 ^
  --modes uniform,spatial ^
  --probe-trials 5 ^
  --final-trials 10 ^
  --target-success-rate 0.95 ^
  --output-dir tests\results\iblt_spatial_smoke
```

Then verify:

```powershell
python tests\json_verifier.py tests\results\iblt_spatial_smoke\probes.jsonl tests\results\iblt_spatial_smoke\summary.jsonl --strict
```

## Correctness Checks

The implementation should check:

```text
decoded Alice-only set equals expected Alice-only set
decoded Bob-only set equals expected Bob-only set
cell_count is identical for uniform and spatial when capacity_factor matches
bits are computed from cell_count * cell_bits
shared datasets are reused across modes
```

For `uniform` mode, compare a few runs with existing `tests/benchmarks/iblt_bench.cpp`. Exact runtime will differ, but success rates and communication accounting should be close or identical when the same hash count and cell count are used.

## Interpretation

Possible outcomes:

1. IBLT-SC needs fewer cells than IBLT-uniform.
   - This supports the idea that spatial coupling helps beyond XYZ.
2. IBLT-SC performs similarly to uniform.
   - This suggests the spatial-coupling gain may depend on XYZ's algebraic/cell structure.
3. IBLT-SC performs worse.
   - This is still valuable; the result should be reported as evidence that the SC rule is not automatically beneficial for every peeling-based sketch.

Do not assume the XYZ-SC improvement will transfer to IBLT. The experiment should answer that empirically.

## Risks

1. The SC placement rule may create boundary effects.
   - Record whether the mode is circular or non-circular.
2. Peeling may behave differently from XYZ under local coupling.
   - Report full success curves or threshold summaries rather than only one point.
3. Hash-function changes can accidentally change the baseline.
   - Keep a uniform-mode consistency check against the existing IBLT benchmark.
4. Communication accounting can become inconsistent.
   - Keep cell layout fixed and report `cell_bits`.

## Completion Criteria

This task is complete when:

```text
tests/benchmarks/iblt_sc_bench.cpp exists
tests/test_iblt_spatial.py exists
uniform and spatial modes run on the same datasets
probe and summary outputs use benchmark.v1
CI fields are recorded
strict JSON verification passes
summary reports relative improvement from uniform to spatial
existing IBLT-uniform behavior is preserved as a comparison point
```
