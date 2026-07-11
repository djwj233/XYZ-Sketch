# Figure 3 Plan

This document plans the paper-facing Figure 3 experiments.

Figure 3 compares XYZ-Sketch with `(a,z)` computed from heuristic formulas against practical set-reconciliation baselines. It reports communication, update cost, and decode cost under the same shared workloads. The tuned `(a,z)` policy from Figure 2 remains available as an optional `--xyz-tuning` input for future runs.

## Shared Setup

Use the global paper setup:

```text
A, B subset U
large common part
|A symmetric-difference B| = d
w = log2(V) = 30
R = sketch_length_bits / (d * w)
target_success_rate = 0.9
confidence_interval = 95%
```

All algorithms should run on the same shared paired datasets:

```text
dataset_mode = shared_file
```

The default XYZ setting should be:

```text
algorithm = xyz_v2
k = 2
l = 6
mode = circular
a,z = heuristic formulas with C=1/3, D=4/3
```

If Figure 2 has not produced stable tuning yet, use a documented fallback:

```text
a = 0
z = max(0, round(M^(1/3) / 3))
```

or use the best `(a,z)` from the largest completed Figure 2 grid.

## Algorithms

Primary algorithms:

```text
xyz_v2
iblt
minisketch
```

Optional baselines:

```text
xyz_v1
iblt_cpp
cpisync
riblt
negentropy
```

Recommended paper policy:

- Main figure: include only baselines that are real, buildable, and stable in the current environment.
- Appendix or caveat table: include unavailable/optional baselines with explicit `status` and `unavailable_reason`.
- Do not silently replace a real baseline with a stub in paper plots.

## Current Support

Existing useful scripts:

```text
tests/test_compare_basic.py
tests/test_frontier_xyz.py
tests/test_az_grid.py
tests/extract_fig2_z_star.py
tests/dataset_generator.py
```

Existing benchmark wrappers:

```text
tests/benchmarks/xyz_v2_bench.cpp
tests/benchmarks/xyz_v1_bench.cpp
tests/benchmarks/iblt_bench.cpp
tests/benchmarks/iblt_cpp_bench.cpp
tests/benchmarks/minisketch_bench.cpp
tests/benchmarks/cpisync_bench.cpp
tests/benchmarks/riblt_bench.go
tests/benchmarks/negentropy_bench.cpp
```

Current capabilities:

- `test_compare_basic.py` builds and runs multiple algorithms.
- It uses shared paired datasets.
- It writes normalized JSON rows.
- It records `bits`, `success_rate`, `encode_avg_s`, and `decode_avg_s`.
- Several external baselines are integrated as real wrappers or optional/unavailable wrappers.

Resolved in this implementation:

- `tests/test_compare_frontier.py` performs per-algorithm frontier search for the primary algorithms.
- The supported algorithms are `xyz_v1`, `xyz_v2`, `iblt`, `minisketch`, `cpisync`, `riblt`, and `negentropy`.
- The script uses shared paired datasets and writes `benchmark.v1` probes/summaries.
- It derives `best_R_w30`, `update_avg_s_per_element`, and `decode_avg_s_per_difference`.
- By default it computes `a,z` from formulas. It can still consume Figure 2 tuning through `--xyz-tuning` when requested.

Remaining gap:

- `xyz_v1` and `riblt` are implemented in `test_compare_frontier.py`; `xyz_v1` is fixed-parameter because the current wrapper exposes no capacity knob, while `riblt` searches `max_symbols`. `iblt_cpp` can smoke-run through `test_compare_basic.py` but is not yet implemented in `test_compare_frontier.py`.
- Dependency-free SVG plotting is implemented in `tests/plot_figure3.py`. PNG/PDF export still needs a matplotlib backend or an SVG conversion step.

## Figure 3(a): Communication Frontier

### Goal

For each algorithm and each `d`, find the minimum communication `R_w30` that reaches 90% success.

Plot:

```text
x-axis = d
y-axis = R_w30 at target_success_rate = 0.9
curves = algorithms
error bars/bands = threshold uncertainty / confidence intervals
```

Expected result:

- XYZ should offer a strong communication/performance trade-off.
- Minisketch should be a strong baseline for pure set reconciliation.
- IBLT variants should be useful but typically require more communication.

### Implementation Plan

Implemented paper-facing script:

```text
tests/test_compare_frontier.py
```

Responsibilities:

1. Build or locate benchmark binaries for selected algorithms.
2. Generate shared datasets once per `(d, seed, trial)`.
3. For each algorithm and `d`, search the smallest communication parameter reaching `target_success_rate = 0.9`.
4. Final-validate the selected parameter with `final_trials`.
5. Normalize results into `benchmark.v1`.
6. Derive `R_w30 = bits / (30*d)`.
7. Record threshold uncertainty fields.

### Bounded Final Retry

The frontier runner now supports an optional repair step for near-miss final
validations. The idea is to keep the current binary search cheap, but avoid
leaving many points unresolved only because the selected parameter was slightly
too aggressive.

Policy:

```text
1. Run the normal search and obtain search_parameter.
2. Run final validation on held-out final datasets.
3. If final_success_rate >= target_success_rate, accept the point.
4. If final_success_rate is below final_retry_min_success_rate, keep unresolved.
5. Otherwise multiply the searched parameter by final_retry_growth and rerun
   final validation, up to final_retry_limit times.
```

Recommended smoke-run settings:

```bash
--final-retry-algorithms xyz_v2,iblt,riblt
--final-retry-growth 1.05
--final-retry-limit 4
--final-retry-min-success-rate 0.75
```

This gives at most four extra final validations per near-miss point and raises
the final parameter to at most about `1.05^4 = 1.216` times the binary-search
candidate. It should be used for `xyz_v2`, `iblt`, and `riblt`, but not for
fixed-parameter baselines such as `minisketch` and `cpisync`.

The summary records both the original search result and the accepted final
parameter:

```text
search_parameter
best_parameter
final_retry_count
final_parameter_offset
final_parameter_multiplier
```

This is a pragmatic smoke-run repair. The paper-quality estimator should still
be a capacity grid with isotonic success-rate fitting and bootstrap confidence
intervals.

Recommended search parameters:

```text
xyz_v2:
  search M
  fixed k = 2, l = 6
  fixed mode = circular
  use heuristic a,z policy by default

iblt:
  search capacity_factor or cells

minisketch:
  search capacity_factor
  field_bits = 30

iblt_cpp:
  search capacity_factor

cpisync:
  search mbar or mbar_factor

riblt:
  search capacity_factor or symbol count if wrapper supports it

negentropy:
  search implementation-specific capacity/byte budget if supported;
  otherwise report a fixed real run with caveat
```

The first implemented version supports:

```text
xyz_v2, iblt, minisketch
```

Optional baselines should be added incrementally.

### Output Layout

Recommended output directory:

```text
tests/results/paper_fig3_compare_frontier/
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

Important summary fields:

```text
experiment = paper_fig3_compare_frontier
record_type = threshold
algorithm
variant
d
best_parameter
best_parameter_name
search_parameter
final_retry_count
final_parameter_offset
final_parameter_multiplier
best_R_w30
best_bits
target_success_rate
final_success_rate
final_ci_low
final_ci_high
threshold_policy
dataset_mode
status
unavailable_reason
```

## Figure 3(b): Update Cost

### Goal

Compare average update/build cost per input element.

Plot:

```text
x-axis = d
y-axis = update_avg_s_per_element
curves = algorithms
```

Recommended definition:

```text
update_denominator = ca + cb
update_avg_s_per_element = encode_avg_s / update_denominator
```

Rationale:

- Most current benchmark wrappers encode/build sketches for both Alice and Bob inside one run.
- Using `ca + cb` is consistent across algorithms.
- If a future wrapper times only Alice, it must record `update_denominator = ca` explicitly.

Fields to add or derive in `test_compare_frontier.py`:

```text
update_avg_s_per_element
update_denominator
update_metric_policy = encode_avg_s/(ca+cb)
```

If an algorithm does not expose meaningful update time, keep the row but mark:

```text
update_status = unavailable
```

## Figure 3(c): Decode Cost

### Goal

Compare amortized decode/reconciliation cost per difference.

Plot:

```text
x-axis = d
y-axis = decode_avg_s_per_difference
curves = algorithms
```

Recommended definition:

```text
decode_avg_s_per_difference = decode_avg_s / d
decode_denominator = d
```

For interactive protocols such as cpisync/negentropy, the wrapper may report a full reconciliation time as `decode_avg_s`. That is acceptable if documented:

```text
decode_metric_policy = decode_or_reconcile_avg_s/d
```

Fields to add or derive:

```text
decode_avg_s_per_difference
decode_denominator
decode_metric_policy
```

## Parameter Grid

Smoke:

```text
d in {100, 300}
algorithms = xyz_v1, xyz_v2, iblt, minisketch, cpisync, riblt, negentropy
probe_trials = 5
final_trials = 10
target_success_rate = 0.9
```

Paper:

```text
d in {100, 300, 1000, 3000, 10000}
algorithms = xyz_v1, xyz_v2, iblt, minisketch, cpisync, riblt, negentropy
probe_trials >= 30
final_trials >= 100
target_success_rate = 0.9
confidence_interval = 95%
```

If runtime allows:

```text
add iblt_cpp to frontier search
```

## Tuning Input from Figure 2

`test_compare_frontier.py` should accept:

```text
--a-constant 0.3333333333
--z-constant 1.3333333333
```

Policy:

- For each `d`, use the exact `(a_star,z_star)` if present.
- If a `d` is missing, use the nearest smaller `d`; if none exists, use nearest available `d`.
- Record:

```text
xyz_tuning_source
xyz_circular_a
xyz_z
xyz_tuning_d
```

If no tuning file is provided:

```text
xyz_circular_a = 0
xyz_z_policy = round(M^(1/3)/3)
```

## Plotting Plan

Implemented dependency-free first plotting script:

```text
tests/plot_figure3.py
```

It reads the frontier `summary.csv` and writes SVG figures.

Later, create or extend:

```text
tests/plot_paper_figures.py
```

Inputs:

```text
tests/results/paper_fig3_compare_frontier/summary.csv
```

Outputs:

```text
tests/results/paper_figures/figure3a_communication.pdf
tests/results/paper_figures/figure3a_communication.png
tests/results/paper_figures/figure3b_update_cost.pdf
tests/results/paper_figures/figure3b_update_cost.png
tests/results/paper_figures/figure3c_decode_cost.pdf
tests/results/paper_figures/figure3c_decode_cost.png
```

Current implemented SVG outputs:

```text
tests/results/paper_figures/figure3a_communication.svg
tests/results/paper_figures/figure3b_update_cost.svg
tests/results/paper_figures/figure3c_decode_cost.svg
tests/results/paper_figures/figure3_source_summary.md
```

Plotting rules:

- Use `d` on a log-scale x-axis.
- Use `best_R_w30` for Figure 3(a).
- Use `update_avg_s_per_element` for Figure 3(b).
- Use `decode_avg_s_per_difference` for Figure 3(c).
- Exclude `status != ok` from main lines, but report skipped rows in a source summary.
- Save both `.pdf` and `.png`.

## Verification

Before plotting:

```powershell
python tests\json_verifier.py tests\results\paper_fig3_compare_frontier\probes.jsonl --strict
python tests\json_verifier.py tests\results\paper_fig3_compare_frontier\summary.jsonl --strict
```

Manual checks:

- All paper rows use `target_success_rate = 0.9`.
- All paper rows use `ci_confidence = 0.95`.
- All successful paper rows use `dataset_mode = shared_file`.
- `best_R_w30 = best_bits / (30*d)`.
- The selected XYZ `(a,z)` is recorded.
- Unavailable external baselines are not mixed into main curves as zero-cost points.

## Suggested Commands

Smoke:

```powershell
python tests\test_compare_frontier.py `
  --d-values 100,300 `
  --algorithms xyz_v1,xyz_v2,iblt,minisketch,cpisync,riblt,negentropy `
  --probe-trials 5 `
  --final-trials 10 `
  --target-success-rate 0.9 `
  --job-timeout-s 1800 `
  --a-constant 0.3333333333 `
  --z-constant 1.3333333333 `
  --output-dir tests\results\paper_fig3_compare_frontier_smoke
```

Paper:

```powershell
python tests\test_compare_frontier.py `
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 `
  --algorithms xyz_v1,xyz_v2,iblt,minisketch,cpisync,riblt,negentropy `
  --probe-trials 30 `
  --final-trials 100 `
  --target-success-rate 0.9 `
  --job-timeout-s 1800 `
  --a-constant 0.3333333333 `
  --z-constant 1.3333333333 `
  --output-dir tests\results\paper_fig3_compare_frontier
```

Currently supported extended baseline run:

```powershell
python tests\test_compare_frontier.py `
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 `
  --algorithms xyz_v1,xyz_v2,iblt,minisketch,cpisync,riblt,negentropy `
  --probe-trials 30 `
  --final-trials 100 `
  --target-success-rate 0.9 `
  --job-timeout-s 1800 `
  --a-constant 0.3333333333 `
  --z-constant 1.3333333333 `
  --output-dir tests\results\paper_fig3_compare_frontier_extended
```

## Current Status

```text
Figure 3(a): primary data generation implemented
  tests/test_compare_frontier.py runs per-algorithm threshold/frontier search for xyz_v1, xyz_v2, iblt, minisketch, cpisync, riblt, and negentropy.
  xyz_v1, cpisync, riblt, and negentropy are connected; iblt_cpp remains open.

Figure 3(b): primary data generation implemented
  tests/test_compare_frontier.py derives update_avg_s_per_element.

Figure 3(c): primary data generation implemented
  tests/test_compare_frontier.py derives decode_avg_s_per_difference.

Plotting: partial
  tests/plot_figure3.py generates dependency-free SVG figures.
  PNG/PDF export remains open.
```
