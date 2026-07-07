# Paper Figure TODO List

This document reorganizes the remaining work around the three main figure tasks proposed by the organizer.

It focuses on what is already implemented, what is partially available, and what still needs to be built or run at paper scale.

## Global Experimental Setup

Target setup:

- Randomly generate sets `A, B subset U`.
- Make `A` and `B` share a large common part.
- Fix symmetric difference size `diff = d`.
- Random shuffle order. Since the sketches are canonical, order should not affect correctness.
- Fix universe word size:

```text
w = log2 V = 30
```

- Use amortized communication:

```text
R = sketch_length_bits / (d * w)
```

- Unless stated otherwise:

```text
confidence interval = 95%
target_success_rate = 0.9
```

## Current Setup Status

### Already Implemented

- Synthetic set generation with large overlap and fixed difference `d` exists in `tests/dataset_generator.py`.
- Shared paired datasets are used by `tests/test_compare_basic.py` and `tests/test_iblt_spatial.py`.
- `tests/test_spatial.py` and `tests/test_circular_a.py` now support `--shared-datasets`.
- Most benchmark rows already report:

```text
bits
bits_per_difference
bit_C_over_d = bits / (32*d)
success_rate
encode_avg_s
decode_avg_s
ci_low / ci_high in threshold-style scripts
```

- Wilson 95% confidence intervals are available in several threshold scripts.
- `target_success_rate` is configurable in threshold scripts.

### Needs Standardization

- The paper metric should be `R = bits / (30*d)`, while the current common field `bit_C_over_d` is `bits / (32*d)`.
- Add a derived field or plotting transform:

```text
R_w30 = bits / (30*d)
```

- Main paper runs should use `target_success_rate = 0.9`. Several existing docs and defaults still use `0.95`.
- For paper-facing paired comparisons, prefer `--shared-datasets` whenever the script supports it.
- `tests/test_xyz_sharp_threshold.py`, `tests/test_z.py`, and `tests/test_find_best_m.py` still need shared-dataset migration if their results enter paper figures.

## Figure 1: XYZ-Sketch Theoretical Claims

Goal: demonstrate that XYZ-Sketch empirically matches the theoretical claims.

Representative tuples:

```text
(k,l) in {(2,3), (2,6), (3,4)}
a = 0
```

Placement variants:

```text
iid / uniform
SC / spatial coupling
```

In current code, the closest mode names are:

```text
iid      -> mode=random
SC       -> mode=naive or circular/spatial depending on k and experiment definition
```

For this organizer setup, `a = 0` should be made explicit for circular-style SC runs.

## Figure 1(a): Sharp Threshold

Target plot:

- Fix one sufficiently large `d`.
- Fix `z`.
- x-axis: `R = bits / (30*d)`.
- y-axis: success rate.
- Curves: `{(k,l)-pair} * {iid, SC}`.
- Show 95% confidence intervals.

Expected result:

- All variants show a sharp threshold.
- SC should have a smaller threshold than iid.

### Current Support

Mostly supported by:

```text
tests/test_xyz_sharp_threshold.py
tests/test_spatial.py
```

`tests/test_xyz_sharp_threshold.py` already scans `M` around a center and records success-rate curves with confidence intervals.

`tests/test_spatial.py` can search thresholds for different modes and supports shared datasets.

### Gaps

- `test_xyz_sharp_threshold.py` does not yet support shared paired datasets.
- It currently summarizes `M@50`, `M@95`, and CI-low `M@95`; the paper needs target `0.9`.
- It reports `bit_C_over_d = bits/(32*d)`, not `R = bits/(30*d)`.
- Need to lock the organizer tuple set and use `a=0` for SC where applicable.
- Need a plotting script for Figure 1(a).

### Required Work

1. Add or use a plot transform `R_w30 = bits / (30*d)`.
2. Run `test_xyz_sharp_threshold.py` on:

```text
d = one large representative value
(k,l) in {(2,3), (2,6), (3,4)}
modes in {random, SC}
fixed z
target_success_rate = 0.9 for summaries
```

3. If paper rigor requires it, migrate `test_xyz_sharp_threshold.py` to shared datasets.
4. Generate Figure 1(a) from `raw.jsonl`.

Status:

```text
partial: scan infrastructure exists
open: paper-scale run, R_w30 metric, shared datasets, plotting
```

## Figure 1(b): Communication Frontier

Target plot:

- x-axis: `d`.
- y-axis: `R = bits / (30*d)` at 90% success probability.
- `z` should be optimal, or selected by the heuristic if justified.
- Curves: `{(k,l,a)-tuple} * {iid, SC}`.
- Show confidence intervals.
- It may be visually cleaner to start from `d >= 100`.

Expected result:

- Each curve should converge toward a value.
- The values should be close to theoretical predictions.
- SC should improve the frontier relative to iid.

### Current Support

Partially supported by:

```text
tests/test_spatial.py
tests/test_find_best_m.py
tests/test_circular_a.py
tests/test_z.py
```

`test_spatial.py` searches best `M` for different placement modes.

`test_find_best_m.py` searches best `M` for one configuration.

`test_z.py` scans `z`, but currently behaves more like a sensitivity scan than a full frontier search.

### Gaps

- No single script currently performs the complete frontier search over:

```text
d values
(k,l,a) tuples
placement variant iid/SC
z optimization
target_success_rate = 0.9
```

- Existing threshold scripts often default to `0.95`, not `0.9`.
- Existing outputs need conversion from `bit_C_over_d` to `R_w30`.
- Need a clear policy for `z`:

```text
heuristic z(d)
or empirical z*(d)
```

- Need confidence intervals on the inferred frontier, not only on individual probe success rates.
- Need a plotting script for Figure 1(b).

### Required Work

1. Define the exact `d` grid, likely:

```text
d in {100, 300, 1000, 3000, 10000}
```

2. Define the exact tuple grid, starting with:

```text
(k,l,a) in {(2,3,0), (2,6,0), (3,4,0)}
```

3. Implement or adapt a frontier script, tentatively:

```text
tests/test_frontier_xyz.py
```

or extend `tests/test_spatial.py` to scan:

```text
target_success_rate = 0.9
d grid
tuple grid
mode in {random, SC}
z policy
```

4. Add output fields or plotting transform:

```text
R_w30
z_policy
z_selected
frontier_target_success_rate = 0.9
```

5. Generate Figure 1(b).

Status:

```text
partial: threshold-search pieces exist
open: unified frontier script/run, z policy, plotting
```

## Figure 2: Effect of `(a,z)`

Goal: analyze how circular parameter `a` and coupling parameter `z` affect performance.

## Figure 2(a): Heatmap Over `(a,z)`

Target plot:

- Fix one representative `d`.
- Heatmap:

```text
x-axis = a
y-axis = z
color = R at 90% success probability
```

Expected result:

- Tuning `a` and `z` should improve communication.

### Current Support

Partially supported by:

```text
tests/test_circular_a.py
tests/test_z.py
```

`test_circular_a.py` scans `a`, supports threshold mode, supports shared datasets, and records confidence intervals.

`test_z.py` scans `z`.

### Gaps

- No current script scans the full 2D grid `(a,z)` and searches `M` for each cell.
- `test_circular_a.py` chooses `z` from a heuristic based on `M`; it does not expose a full `z` grid for each `a`.
- `test_z.py` does not scan `a`.
- Need heatmap-ready output.
- Need `target_success_rate = 0.9`.
- Need `R_w30 = bits/(30*d)`.

### Required Work

1. Create or extend a script:

```text
tests/test_az_grid.py
```

or extend `tests/test_circular_a.py` with:

```text
--z-values
--target-success-rate 0.9
--mode threshold
```

2. For each `(a,z)`:

```text
find minimum M reaching 90% success
record best_M, R_w30, success_rate, ci_low, ci_high
```

3. Use shared datasets across `(a,z)` cells for the same `d` and trial index.
4. Generate Figure 2(a) heatmap.

Status:

```text
partial: separate a and z scans exist
open: joint (a,z) threshold grid and heatmap
```

## Figure 2(b): `z_theory(d)` vs `z*(d)`

Target plot:

- x-axis: `d`.
- y-axis: `z`.
- Two curves:

```text
z_theory(d)
z*(d) from experiments
```

This figure may be optional, but the second curve should be generated first.

### Current Support

Partially supported by:

```text
tests/test_z.py
```

It can scan `z` for representative `(d,l,k,M)` configurations.

### Gaps

- It does not currently search `M` threshold for each `z`.
- It does not output a clean `z*(d)` frontier.
- It does not compare against an explicit `z_theory(d)` field.
- It still uses internal generator rather than shared paired datasets.

### Required Work

1. Define `z_theory(d)` explicitly in code or a config file.
2. Extend the frontier or `(a,z)` grid script to output:

```text
d
z_theory
z_star
R_w30_at_z_star
```

3. Generate Figure 2(b) if it remains in the paper.

Status:

```text
partial: z scan exists
open: z*(d) extraction and theory comparison
```

## Figure 3: Comparison Against Other Algorithms

Goal: compare tuned XYZ against practical set reconciliation baselines.

Default XYZ setting:

```text
(k,l) = (2,6)
choose tuned (a,z)
target_success_rate = 0.9
```

Algorithms:

```text
XYZ
IBLT
minisketch
possibly other external baselines
```

## Figure 3(a): Communication

Target plot:

- x-axis: `d`.
- y-axis: `R = bits / (30*d)`.
- All probabilistic algorithms should be measured at 90% success.

### Current Support

Partially supported by:

```text
tests/test_compare_basic.py
tests/test_iblt_spatial.py
```

`test_compare_basic.py` compares multiple algorithms on shared datasets.

Implemented or scaffolded baselines include:

```text
xyz_v1
xyz_v2
iblt
iblt_cpp
minisketch
cpisync
riblt
negentropy
```

Current environment status:

```text
minisketch and iblt_cpp are real and usable
riblt requires Go
negentropy requires OpenSSL headers/libs
cpisync is optional/platform-sensitive
```

### Gaps

- `test_compare_basic.py` currently compares fixed parameter grids; it does not automatically search each algorithm's minimum communication at 90% success.
- Need tuned XYZ `(a,z)` from Figure 2 or a documented heuristic.
- Need comparable threshold search for IBLT and minisketch.
- Need `R_w30`.
- Need confidence intervals on each plotted point.

### Required Work

1. First determine tuned XYZ `(a,z)` for `(k,l)=(2,6)`.
2. Implement a threshold/frontier comparison script, tentatively:

```text
tests/test_compare_frontier.py
```

or extend `test_compare_basic.py` with a threshold-search mode.

3. For each algorithm and each `d`, find the minimum communication reaching `0.9` success.
4. Use shared datasets for all algorithms.
5. Generate Figure 3(a).

Status:

```text
partial: shared compare infrastructure exists
open: per-algorithm 90% frontier search and plotting
```

## Figure 3(b): Update Cost

Target plot:

- x-axis: `d`.
- y-axis: average update time per element.

### Current Support

Partially supported:

- Benchmarks report `encode_avg_s`.
- For sketch-building algorithms, update cost can be approximated as:

```text
encode_avg_s / number_of_inserted_elements
```

### Gaps

- Current JSON does not consistently report:

```text
update_avg_s_per_element
update_total_elements
```

- Some baselines do not naturally separate update time from other encoding or protocol setup work.
- Need a consistent denominator:

```text
|A| for Alice sketch build
or |A| + |B| if both sides are encoded in the benchmark
```

### Required Work

1. Decide the update-time definition.
2. Add derived fields in Python summaries:

```text
update_avg_s_per_element
update_denominator
```

3. If necessary, add finer timers inside benchmark wrappers.
4. Generate Figure 3(b).

Status:

```text
partial: encode timing exists
open: standardized update-cost metric
```

## Figure 3(c): Decode Cost

Target plot:

- x-axis: `d`.
- y-axis: amortized decode time per element.

### Current Support

Partially supported:

- Benchmarks report `decode_avg_s`.
- Compare outputs preserve decode timing fields.

### Gaps

- Need a consistent denominator:

```text
d
or number of recovered differences
```

The organizer says "per elements"; for set reconciliation, using `d` is likely the cleanest denominator.

- Some interactive baselines use `reconcile_avg_s`; mapping to decode cost must be documented.

### Required Work

1. Define:

```text
decode_avg_s_per_difference = decode_avg_s / d
```

or another agreed denominator.

2. Add derived fields to summaries or plotting code.
3. Generate Figure 3(c).

Status:

```text
partial: decode timing exists
open: standardized amortized decode metric and plotting
```

## Recommended Execution Order

1. Standardize paper metrics:

```text
R_w30 = bits / (30*d)
target_success_rate = 0.9
95% CI
shared datasets for paired comparisons
```

2. Produce Figure 1(a) from a representative sharp-threshold run.
3. Run the `(a,z)` tuning needed before Figure 3.
4. Produce Figure 1(b) communication frontier for XYZ only.
5. Produce Figure 2(a), and optionally Figure 2(b).
6. Implement per-algorithm 90% frontier search for Figure 3(a).
7. Add/update per-element timing metrics for Figure 3(b,c).
8. Generate plotting scripts and final figure tables.

## New Scripts Likely Needed

```text
tests/test_frontier_xyz.py       # Figure 1(b), possibly reusing test_spatial logic
tests/test_az_grid.py            # Figure 2(a), maybe extends test_circular_a
tests/test_compare_frontier.py   # Figure 3(a), per-algorithm 90% frontier
tests/plot_paper_figures.py      # Figures 1-3 from JSON/CSV outputs
```

Some of these can be implemented as extensions of existing scripts instead of new files, but the figure tasks should have stable commands and output directories.

## Paper Result Directories

Suggested directories:

```text
tests/results/paper_fig1_sharp_threshold/
tests/results/paper_fig1_frontier/
tests/results/paper_fig2_az_grid/
tests/results/paper_fig2_z_star/
tests/results/paper_fig3_compare_frontier/
tests/results/paper_fig3_timing/
tests/results/paper_figures/
```

## Summary

Current repository status:

```text
Figure 1(a): partially supported by existing sharp-threshold script
Figure 1(b): threshold pieces exist, but unified frontier run is open
Figure 2(a): a and z scans exist separately, joint heatmap is open
Figure 2(b): z scan exists, z*(d) extraction is open
Figure 3(a): shared compare exists, 90% frontier search is open
Figure 3(b): encode timing exists, update-cost metric is open
Figure 3(c): decode timing exists, amortized decode metric is open
```

