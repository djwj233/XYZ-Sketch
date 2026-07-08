# Figure 1 Plan

This document plans how to produce Figure 1 for the paper-facing experiment set.

Figure 1 should support the claim that XYZ-Sketch has sharp threshold behavior and that spatial coupling improves the communication frontier.

## Shared Setup

Use the global paper setup:

```text
A, B subset U
large common part
|A △ B| = d
w = log2(V) = 30
R = sketch_length_bits / (d * w)
target_success_rate = 0.9
confidence_interval = 95%
```

Current benchmark rows already report:

```text
bits
bit_C_over_d = bits / (32*d)
success_rate
ci_low
ci_high
encode_avg_s
decode_avg_s
```

For paper figures, add or derive:

```text
R_w30 = bits / (30*d)
```

The current Figure 1 data-generation scripts now store this as `R_w30` in the relevant rows/summaries.

## Tuples and Modes

Use representative tuples:

```text
(k,l) in {(2,3), (2,6), (3,4)}
```

Use:

```text
a = 0
```

Compare:

```text
iid / uniform -> mode=random
SC            -> mode=naive or circular/spatial, depending on final definition
```

Recommended first policy:

- Use `mode=random` for iid.
- Use `mode=naive` for non-circular spatial coupling.
- Use `mode=circular --circular-a 0` only when explicitly studying circularized SC.

For Figure 1, because the organizer specifies `a=0`, record `circular_a = 0` for any circular-style SC rows.

## Figure 1(a): Sharp Threshold

### Goal

Show success rate as a function of communication `R`.

Plot:

```text
x-axis = R_w30
y-axis = success_rate
curves = {(k,l)} x {iid, SC}
error bars/bands = 95% CI
```

Expected result:

- Each curve should have a sharp threshold.
- SC should shift the threshold left compared with iid.

### Existing Support

Closest script:

```text
tests/test_xyz_sharp_threshold.py
```

It already:

- scans `M` around an estimated threshold;
- runs multiple trials per `M`;
- records `success_rate`;
- adds Wilson confidence intervals;
- supports `mode=random`, `mode=spatial`, `mode=circular`, and `mode=naive`;
- supports `--dedup-hashes`.

Supporting script:

```text
tests/test_spatial.py
```

It can find approximate threshold centers and supports `--shared-datasets`.

### Gaps

`tests/test_xyz_sharp_threshold.py` now supports:

- paper target `0.9` summary fields;
- `R_w30` per raw row;
- `point_M_90`, `point_R_w30_90`, `ci_low_M_90`, and `ci_low_R_w30_90`;
- `--circular-a` pass-through.

Remaining gap:

- optional shared paired dataset support if this figure is used as a strict paired comparison.

### Recommended Parameters

First smoke-level figure:

```text
d = 1000
(k,l) in {(2,3), (2,6), (3,4)}
modes = random,naive
trials = 30
points = 31
confidence = 0.95
```

Paper-scale run:

```text
d = 10000 or larger if runtime allows
(k,l) in {(2,3), (2,6), (3,4)}
modes = random,naive
trials >= 100
points >= 41
confidence = 0.95
```

If paired datasets are added:

```text
--shared-datasets
```

### Implementation Plan

1. Extend `tests/test_xyz_sharp_threshold.py` with paper-specific summary thresholds:

```text
point_M_90
point_R_w30_90
ci_low_M_90
ci_low_R_w30_90
```

2. Add optional `--shared-datasets` support, reusing the pattern from `tests/test_spatial.py`.

3. `--circular-a` pass-through is implemented.

4. Run sharp-threshold data into:

```text
tests/results/paper_fig1_sharp_threshold/
```

5. Add plotting support in:

```text
tests/plot_paper_figures.py
```

or a narrower first script:

```text
tests/plot_figure1.py
```

### Expected Output

Data:

```text
tests/results/paper_fig1_sharp_threshold/raw.jsonl
tests/results/paper_fig1_sharp_threshold/summary.jsonl
tests/results/paper_fig1_sharp_threshold/summary.csv
tests/results/paper_fig1_sharp_threshold/run_config.json
```

Figure:

```text
tests/results/paper_figures/figure1a_sharp_threshold.pdf
tests/results/paper_figures/figure1a_sharp_threshold.png
```

## Figure 1(b): Communication Frontier

### Goal

Show the minimum communication `R` needed to reach 90% success as `d` grows.

Plot:

```text
x-axis = d
y-axis = R_w30 at target_success_rate = 0.9
curves = {(k,l,a)} x {iid, SC}
error bars/bands = threshold uncertainty / success-rate CI
```

Expected result:

- Curves should approach limiting values.
- SC should be lower than iid.
- Values should be close to theoretical expectations.

### Existing Support

Useful scripts:

```text
tests/test_spatial.py
tests/test_find_best_m.py
tests/test_z.py
tests/test_circular_a.py
```

`tests/test_spatial.py` is the best starting point because it:

- compares placement modes;
- performs threshold search over `M`;
- records confidence intervals;
- supports shared datasets;
- supports `--dedup-hashes`.

### Gaps

Current paper-facing script:

```text
tests/test_frontier_xyz.py
```

It wraps `tests/test_spatial.py` over an explicit tuple grid and merges shard outputs into one Figure 1(b) result directory.
It uses shared paired datasets by default for fair mode comparison. Add `--no-shared-datasets` only for fast debugging.

The current script performs:

```text
d grid
(k,l,a) tuple grid
iid vs SC
target_success_rate = 0.9
R_w30 output
```

The current `z` policy is the existing heuristic:

```text
heuristic z(d, M)
```

Later, Figure 2 can replace this with empirical best `z*(d)` or a theory-driven policy.

### Recommended Parameters

First smoke frontier:

```text
d in {100, 300, 1000}
(k,l,a) in {(2,6,0)}
modes = random,naive
target_success_rate = 0.9
probe_trials = 20
final_trials = 50
```

Paper-scale frontier:

```text
d in {100, 300, 1000, 3000, 10000}
(k,l,a) in {(2,3,0), (2,6,0), (3,4,0)}
modes = random,naive
target_success_rate = 0.9
probe_trials >= 50
final_trials >= 100
```

### Implementation Plan

Two possible approaches:

#### Option A: Extend `test_spatial.py`

Add:

```text
R_w30 fields in summary
tuple labels
paper-friendly output directory
optional fixed circular_a when mode=circular
```

Pros:

- Fastest path.
- Reuses existing binary search and shared datasets.

Cons:

- `test_spatial.py` may become overloaded.

#### Option B: Create `tests/test_frontier_xyz.py`

Build a paper-specific wrapper around existing concepts:

```text
for d
  for (k,l,a)
    for mode in {random, SC}
      search minimum M reaching 0.9 success
```

Pros:

- Clean paper-facing command.
- Easier output schema for Figure 1(b).

Cons:

- Some logic duplicates `test_spatial.py`.

Current choice:

```text
Option B is implemented as tests/test_frontier_xyz.py.
```

### Expected Output

Data:

```text
tests/results/paper_fig1_frontier/probes.jsonl
tests/results/paper_fig1_frontier/summary.jsonl
tests/results/paper_fig1_frontier/summary.csv
tests/results/paper_fig1_frontier/run_config.json
```

Figure:

```text
tests/results/paper_figures/figure1b_frontier.pdf
tests/results/paper_figures/figure1b_frontier.png
```

## Plotting Requirements

The plotting script should:

- read JSONL/CSV outputs;
- compute `R_w30 = bits / (30*d)` if missing;
- group by `(k,l,mode)` or `(k,l,a,mode)`;
- draw 95% CI bands or error bars;
- save both `.pdf` and `.png`;
- write a small `figure1_source_summary.md` with the exact input files and commands.

## Verification

Before using Figure 1 data:

1. Run strict JSON verification:

```powershell
python tests\json_verifier.py tests\results\paper_fig1_sharp_threshold\raw.jsonl --strict
python tests\json_verifier.py tests\results\paper_fig1_frontier\summary.jsonl --strict
```

2. Check all rows use:

```text
target_success_rate = 0.9
ci_confidence = 0.95
w = 30 in plotting/derived metrics
```

3. Check mode mapping is documented:

```text
random = iid
naive/circular/spatial = SC definition used in the figure
```

4. Check every plotted curve has enough successful and failed points to show the threshold.

## Current Status

```text
Figure 1(a): data generation implemented
  Existing sharp-threshold scan now emits R_w30, target 0.9 summaries, and circular_a.
  Still needs paper-scale run and plotting.

Figure 1(b): data generation implemented
  tests/test_frontier_xyz.py runs a unified frontier over d and tuple grid.
  Still needs paper-scale run, possibly improved z policy, and plotting.
```
