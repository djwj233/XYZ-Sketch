# Figure 1(b): Fixed-M Communication Frontier Plan

## 1. Goal

Figure 1(b) measures the communication ratio obtained by the fitted circular
heuristic as the difference size `d` grows:

```text
x-axis = d
y-axis = R_w30 for a fixed M whose measured success rate is at least 0.9
```

This revision does not search or binary-search `M`. Each `d` reuses one `M`
already identified by the existing experiments, evaluates exactly one
heuristic `(a,z)` configuration for 100 trials, and reports whether that fixed
configuration reaches the 90% target.

## 2. Experiment Scope

Use:

```text
d in {100, 300, 1000, 3000, 10000, 100000, 1000000}
k = 2
l = 6
trials = 100
target_success_rate = 0.9
confidence_interval = 95% Wilson
dedup_hashes = false
base_seed = 114514
```

The fixed configurations are:

| d | M | a | z | M*l/d | expected R_w30 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 26 | 1/3 | 1 | 1.560000 | 1.698667 |
| 300 | 67 | 1/3 | 1 | 1.340000 | 1.459111 |
| 1,000 | 211 | 1/3 | 2 | 1.266000 | 1.378533 |
| 3,000 | 596 | 1/3 | 2 | 1.192000 | 1.297956 |
| 10,000 | 1,948 | 1/3 | 4 | 1.168800 | 1.272693 |
| 100,000 | 18,155 | 1/3 | 8 | 1.089300 | 1.186127 |
| 1,000,000 | 178,767 | 1/3 | 16 | 1.072602 | 1.167944 |

`M=26` is used for `d=100`: the smaller existing values do not reach the
target at the heuristic point (`M=23` gives 72/100 and `M=24` gives 89/100).

The first five configurations have previous 100-trial Figure 2 simulation
results at the heuristic point. The `d=100000` and `d=1000000` values were
previously checked with only 20 trials, so this run provides their required
100-trial validation.

These values are currently sourced from Figure 2 results because this checkout
does not contain completed paper-scale Figure 1 or Figure 3 output. The final
source manifest must record that provenance instead of claiming that the M
values came from completed Figure 1/3 runs.

## 3. Heuristic Parameters

Use the fitted formula already used to annotate the new Figure 2:

```text
C_orient / C_peel = 1.2081
C = (1/3) / 1.2081
a = C * (C_orient / C_peel) = 1/3
D = 0.5
delta = 0.1

z_continuous = D * (1-a)^(2/3) * (M / log(1/delta))^(1/3)
z = round(z_continuous)
```

The runner must calculate `a` and `z` from this formula, then verify that the
result matches the table. The table is a reproducibility assertion, not a
second independent source of heuristic values.

## 4. Simulation Model

The primary run uses the same structural peeling simulator as the new Figure 2:

```text
tests/benchmarks/fig2_peeling_sim.cpp
```

For each trial it generates the circularly coupled random hypergraph defined
by `(d,k,l,M,a,z)` and records whether peeling removes every edge. It does not
construct full sets and does not execute `XYZSketch::Decode()`, polynomial
reconstruction, root finding, fingerprint verification, or final set-difference
comparison.

This choice keeps the model consistent with the experiments that supplied the
fixed M values and makes 100 trials at `d=1000000` practical. Therefore the
paper text must describe this curve as a **peeling-simulation communication
frontier**, not as an end-to-end decoder benchmark. A separate end-to-end spot
check at smaller `d` can be added later without changing this fixed-M run.

## 5. Communication Metric

The simulator currently reports structural success and may leave `bits=0`.
Figure 1(b) must derive communication from the XYZ-v2 sketch layout:

```text
cell_bits = (floor(log2(2*l + 1)) + 1) + 32*l
bits = M * cell_bits
R_w30 = bits / (30*d)
```

For `l=6`:

```text
cell_bits = 196
R_w30 = 196*M / (30*d)
```

The output must retain both:

```text
field_C_over_d = M*l/d
R_w30 = M*cell_bits/(30*d)
```

These quantities are related but are not interchangeable.

## 6. Runner Design

Implement a dedicated runner:

```text
tests/test_figure1b_fixed_m.py
```

The checked-in fixed-M configuration is:

```text
tests/figure1b_fixed_m_config.csv
```

Do not use `tests/test_frontier_xyz.py` for this run because that wrapper always
performs an M threshold search. The new runner should:

1. Read a checked-in `(d,M)` configuration table or use the seven defaults above.
2. Calculate the heuristic `a` and `z` using the shared formula helpers.
3. Build or reuse `build/fig2_peeling_sim`.
4. Run exactly one simulator process per `(d,M)` with `--trials 100`.
5. Add a 95% Wilson interval and the derived communication fields.
6. Mark `target_met = success_rate >= 0.9`.
7. Write each completed row immediately so interruption-safe `--resume` is possible.
8. Support `--jobs`, while keeping each configuration's seed deterministic.

The planned command is:

```bash
python3 tests/test_figure1b_fixed_m.py \
  --trials 100 \
  --target-success-rate 0.9 \
  --jobs 2 \
  --output-dir tests/results/paper_fig1b_fixed_m
```

Resume command:

```bash
python3 tests/test_figure1b_fixed_m.py \
  --trials 100 \
  --target-success-rate 0.9 \
  --jobs 2 \
  --resume \
  --skip-build \
  --output-dir tests/results/paper_fig1b_fixed_m
```

The runner and both commands are implemented.

## 7. Output Contract

Write:

```text
tests/results/paper_fig1b_fixed_m/raw.jsonl
tests/results/paper_fig1b_fixed_m/summary.jsonl
tests/results/paper_fig1b_fixed_m/summary.csv
tests/results/paper_fig1b_fixed_m/summary.md
tests/results/paper_fig1b_fixed_m/run_config.json
tests/results/paper_fig1b_fixed_m/errors.log
```

Required summary fields:

```text
d, k, l, M
circular_a, z, z_continuous
trials, successes, success_rate
ci_low, ci_high, ci_method, ci_confidence
target_success_rate, target_met, status
cell_bits, bits, field_C_over_d, R_w30
seed, dedup_hashes, simulation_model
M_source_file, M_source_description
```

Expected row count is exactly seven.

## 8. Plot Design

Implement:

```text
tests/plot_figure1b.py
```

Plot command:

```bash
python3 tests/plot_figure1b.py \
  --input tests/results/paper_fig1b_fixed_m/summary.csv \
  --output-dir tests/results/paper_figures/figure1b_fixed_m
```

The main figure uses a logarithmic x-axis because `d` spans four orders of
magnitude:

```text
x-axis = d (log scale)
y-axis = R_w30
line/points = rows with target_met=true
failed marker = rows with target_met=false
```

Do not silently draw a failed point as a 90%-success frontier value. If a fixed
M produces fewer than 90 successes, retain it in the source data and show it as
a distinct failed marker, but do not connect it to the accepted frontier line.
No automatic M increase or hidden binary search is allowed.

Planned outputs:

```text
tests/results/paper_figures/figure1b_fixed_m.svg
tests/results/paper_figures/figure1b_fixed_m_source.csv
tests/results/paper_figures/figure1b_fixed_m_source.md
```

## 9. Validation Checklist

Before accepting the figure:

1. Confirm there are exactly seven unique `d` values and seven rows.
2. Confirm every row uses `k=2`, `l=6`, `trials=100`, and `a=1/3`.
3. Recompute `z` from the formula and compare it with the recorded integer.
4. Recompute `bits`, `field_C_over_d`, and `R_w30` independently.
5. Verify `successes/trials == success_rate` and the Wilson interval.
6. Run the strict JSON verifier on `summary.jsonl`.
7. Record any `target_met=false` row without changing M automatically.
8. State clearly in the caption that success is measured by peeling simulation.

## 10. Implementation Order

1. The fixed-M configuration, runner, and plotter are implemented.
2. Run a two-point smoke test at `d=100,300` with 5 trials.
3. Run all seven configurations with 100 trials and resume support enabled.
4. Validate the output and inspect any point below 0.9.
5. Produce the SVG and source manifest with `plot_figure1b.py`.
6. Only after the simulation figure is stable, consider end-to-end decoder spot checks.
