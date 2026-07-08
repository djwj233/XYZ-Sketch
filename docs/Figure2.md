# Figure 2 Plan

This document plans the paper-facing Figure 2 experiments.

Figure 2 studies how the circular parameter `a` and the coupling parameter `z` affect XYZ-Sketch performance. Its output should also provide the tuned `(a,z)` values needed before running the final baseline comparison in Figure 3.

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

For Figure 2, the main metric is:

```text
R_w30 = bits / (30*d)
```

The primary XYZ setting should be:

```text
k = 2
l = 6
mode = circular
```

because `a` only has a direct interpretation for circular spatial coupling. If needed, `(k,l)=(2,3)` can be added as a diagnostic tuple, but the first paper-facing version should keep the grid small enough to run reliably.

## Current Support

Relevant existing scripts:

```text
tests/test_circular_a.py
tests/test_z.py
tests/test_spatial.py
tests/test_frontier_xyz.py
tests/benchmarks/xyz_v2_bench.cpp
```

Current capabilities:

- `xyz_v2_bench` accepts `--circular-a`.
- `test_circular_a.py` can scan `a`, including threshold mode.
- `test_z.py` can sweep fixed-`M` `z` values.
- `test_spatial.py` has threshold-search logic, shared-dataset support, Wilson CI, and `R_w30`-ready summary fields.

Resolved in this implementation:

- `tests/test_az_grid.py` scans a full `(a,z)` grid and searches the minimum `M` for every cell.
- `tests/extract_fig2_z_star.py` extracts `z_star(d)` and the associated `a_star(d)` from the grid summary.

Remaining gap:

- `test_z.py` is fixed-`M`, so it cannot directly produce `R_w30 at 90% success`.
- `test_circular_a.py` currently chooses `z` by heuristic; it does not expose a full `z` grid per `a`.
- No plotting script exists for Figure 2 heatmaps or `z_theory(d)` comparison.

## Figure 2(a): `(a,z)` Heatmap

### Goal

For one representative `d`, show how the 90%-success communication threshold changes across a two-dimensional `(a,z)` grid.

Plot:

```text
x-axis = a
y-axis = z
color = R_w30 at target_success_rate = 0.9
```

Expected result:

- Changing `a` and `z` should visibly change the required communication.
- The best region should identify practical tuned parameters for Figure 3.
- The heatmap may contain invalid or unresolved cells; these should be shown distinctly from high-cost cells.

### Recommended Parameters

Smoke grid:

```text
d = 300
k = 2
l = 6
mode = circular
a in {0.0, 0.3333333333, 0.6}
z in {0, 1, 2, 3}
probe_trials = 5
final_trials = 10
target_success_rate = 0.9
```

Paper grid:

```text
d = 3000 or 10000
k = 2
l = 6
mode = circular
a in {0.0, 0.1, 0.2, 0.3333333333, 0.4, 0.5, 0.6, 0.75, 0.9}
z in {0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16}
probe_trials >= 30
final_trials >= 100
target_success_rate = 0.9
threshold_policy = point
```

If runtime is high, reduce the heatmap to:

```text
a in {0.0, 0.2, 0.3333333333, 0.5, 0.75}
z in {0, 1, 2, 3, 4, 6, 8, 12}
```

### Implementation Plan

Implemented paper-facing script:

```text
tests/test_az_grid.py
```

Responsibilities:

1. Build or locate `build/xyz_v2_bench`.
2. Expand `d`, `k`, `l`, `a`, and `z` grids.
3. For every `(d,k,l,a,z)` cell, search the smallest `M` reaching `target_success_rate`.
4. Final-validate the selected `M` with `final_trials`.
5. Use shared paired datasets across all cells with the same `(d, ca, cb, seed)` where practical.
6. Record `R_w30`, Wilson confidence intervals, timing, selected `M`, and status.
7. Write heatmap-ready JSONL/CSV summaries.

The threshold search should reuse the same conceptual policy as `test_spatial.py`:

```text
initial upper bound -> doubling until success -> binary search -> final validation
```

Unlike `test_spatial.py`, `z` must be fixed by the grid and must not be chosen by `choose_z(M)`.

### Output Layout

Recommended output directory:

```text
tests/results/paper_fig2_az_grid/
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
experiment = paper_fig2_az_grid
record_type = threshold
algorithm = xyz_v2
variant = circular
d
l
k
mode = circular
circular_a
z
best_M
best_R_w30
best_C_over_d
final_success_rate
final_ci_low
final_ci_high
target_success_rate
threshold_policy
dataset_mode
status
```

Status policy:

```text
ok          cell reached target and final validation passed
unresolved  no M reached target within max_C_over_d
invalid     z makes RangeLength too small, or parameters are rejected
```

## Figure 2(b): `z_theory(d)` vs `z*(d)`

### Goal

Compare the theoretically or heuristically selected `z` with the empirically best `z`.

Plot:

```text
x-axis = d
y-axis = z
curves = z_theory(d), z_star(d)
```

This figure is optional in the final paper, but producing the experimental `z_star(d)` curve is useful because it informs Figure 3 tuning.

### Definition of `z_star(d)`

For each `d`, define:

```text
z_star(d) = z value in the scanned grid with the lowest best_R_w30
```

Tie-breaking:

1. Prefer smaller `best_R_w30`.
2. If tied within a small tolerance, prefer the higher `final_ci_low`.
3. If still tied, prefer smaller `z`.
4. If still tied, prefer `a` closest to the chosen Figure 3 default.

The summary should also report the associated best `a`:

```text
a_star(d)
z_star(d)
R_w30_at_star
```

### `z_theory(d)` Policy

The current implementation uses the heuristic:

```text
z_heuristic(M) = max(0, round(M^(1/3) / 3))
```

For Figure 2(b), the cleanest first version is:

```text
z_theory(d) = max(0, round(best_M_at_star(d)^(1/3) / 3))
```

If the proof later gives a different formula, replace this field with the proof-derived value but keep the output column name stable:

```text
z_theory
z_theory_policy
```

### Recommended Parameters

Smoke:

```text
d in {300, 1000}
k = 2
l = 6
a in {0.0, 0.3333333333, 0.6}
z in {0, 1, 2, 3, 4}
probe_trials = 5
final_trials = 10
```

Paper:

```text
d in {100, 300, 1000, 3000, 10000}
k = 2
l = 6
a grid = same as Figure 2(a)
z grid = same as Figure 2(a), possibly extended for large d
probe_trials >= 30
final_trials >= 100
```

### Implementation Plan

Use the same `tests/test_az_grid.py` output. The extractor script is implemented as:

```text
tests/extract_fig2_z_star.py
```

Responsibilities:

1. Read `tests/results/paper_fig2_az_grid/summary.jsonl`.
2. Filter `status = ok`.
3. Group by `d,k,l`.
4. Pick `(a_star,z_star)` using the tie-breaking policy.
5. Compute `z_theory`.
6. Write:

```text
tests/results/paper_fig2_z_star/summary.jsonl
tests/results/paper_fig2_z_star/summary.csv
tests/results/paper_fig2_z_star/summary.md
```

Important fields:

```text
experiment = paper_fig2_z_star
record_type = aggregate
d
l
k
a_star
z_star
R_w30_at_star
best_M_at_star
z_theory
z_theory_policy
delta_z = z_star - z_theory
source_summary
```

## Plotting Plan

Create or extend:

```text
tests/plot_paper_figures.py
```

or first create a narrower script:

```text
tests/plot_figure2.py
```

Figure 2(a):

- Read `paper_fig2_az_grid/summary.csv`.
- Pivot rows into an `a x z` matrix.
- Use `best_R_w30` as color.
- Mark `unresolved`/`invalid` cells with a separate hatch or neutral color.
- Annotate the best cell if the plot remains readable.

Figure 2(b):

- Read `paper_fig2_z_star/summary.csv`.
- Plot `z_star` and `z_theory` over `d`.
- Use log-scale x-axis if the `d` grid spans several orders of magnitude.

Output:

```text
tests/results/paper_figures/figure2a_az_heatmap.pdf
tests/results/paper_figures/figure2a_az_heatmap.png
tests/results/paper_figures/figure2b_z_star.pdf
tests/results/paper_figures/figure2b_z_star.png
```

## Verification

Before using the results:

```powershell
python tests\json_verifier.py tests\results\paper_fig2_az_grid\probes.jsonl --strict
python tests\json_verifier.py tests\results\paper_fig2_az_grid\summary.jsonl --strict
python tests\json_verifier.py tests\results\paper_fig2_z_star\summary.jsonl --strict
```

Manual checks:

- Every paper row uses `target_success_rate = 0.9`.
- Every paper row uses `ci_confidence = 0.95`.
- `dataset_mode` is `shared_file` for the paper run.
- `RangeLength = M // (z + 1)` is not too small for accepted cells.
- The best cell is not an artifact of a very low `final_trials` count.

## Suggested Commands

Smoke heatmap:

```powershell
python tests\test_az_grid.py `
  --d-values 300 `
  --k-values 2 `
  --l-values 6 `
  --a-values 0,0.3333333333,0.6 `
  --z-values 0,1,2,3 `
  --probe-trials 5 `
  --final-trials 10 `
  --target-success-rate 0.9 `
  --shared-datasets `
  --output-dir tests\results\paper_fig2_az_grid_smoke
```

Paper heatmap:

```powershell
python tests\test_az_grid.py `
  --d-values 3000 `
  --k-values 2 `
  --l-values 6 `
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 `
  --z-values 0,1,2,3,4,5,6,8,10,12,16 `
  --probe-trials 30 `
  --final-trials 100 `
  --target-success-rate 0.9 `
  --shared-datasets `
  --output-dir tests\results\paper_fig2_az_grid
```

`z_star(d)` extraction:

```powershell
python tests\extract_fig2_z_star.py `
  --input tests\results\paper_fig2_az_grid\summary.jsonl `
  --output-dir tests\results\paper_fig2_z_star
```

## Current Status

```text
Figure 2(a): data generation implemented
  tests/test_az_grid.py runs the combined (a,z) threshold grid.
  Heatmap plotting is still open.

Figure 2(b): data extraction implemented
  tests/extract_fig2_z_star.py extracts z_star(d), a_star(d), and z_theory.
  Plotting is still open.

Figure 3 dependency: open
  Figure 2 should output tuned (a,z), especially for (k,l)=(2,6).
```
