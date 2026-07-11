# Figure 2 Generated Workflow

This document records how Figure 2 was generated on this server.

## 1. Old Figure 2 Threshold Grid

The old Figure 2 experiment searched for the minimum `M` needed by each `(a,z)` pair.

Result directory:

```text
tests/results/paper_fig2_az_grid
```

Important files:

```text
tests/results/paper_fig2_az_grid/summary.jsonl
tests/results/paper_fig2_az_grid/summary.csv
tests/results/paper_fig2_az_grid/probes.jsonl
tests/results/paper_fig2_az_grid/run_config.json
```

Current size:

```text
summary.jsonl: 495 rows
```

The old result is no longer used as the final Figure 2 conclusion. It is used only to provide fixed `M` candidates for the new experiment.

## 2. Extract Fixed-M Candidates

Script:

```text
tests/extract_fig2_m_candidates.py
```

Command:

```bash
python3 tests/extract_fig2_m_candidates.py \
  --input tests/results/paper_fig2_az_grid/summary.jsonl \
  --output-dir tests/results/paper_fig2_m_candidates \
  --include-unresolved-with-m
```

The script:

1. Reads non-empty `best_M` values from the old Figure 2 summary.
2. Keeps unresolved rows if they still contain `best_M`.
3. Merges close budgets by binning on `M*l/d`.
4. Uses the median `M` in each bin as the representative candidate.

Current candidate extraction config:

```json
{
  "c_over_d_bin_width": 0.1,
  "include_unresolved_with_m": true,
  "input_rows": 495,
  "full_candidate_rows": 240,
  "candidate_rows": 43
}
```

Output files:

```text
tests/results/paper_fig2_m_candidates/m_candidates.csv
tests/results/paper_fig2_m_candidates/m_candidates.jsonl
tests/results/paper_fig2_m_candidates/m_candidates.md
tests/results/paper_fig2_m_candidates/run_config.json
```

## 3. New Figure 2(a): Fixed-M Peeling Simulation

Runner:

```text
tests/test_fig2_fixed_m_sim.py
```

C++ simulator:

```text
tests/benchmarks/fig2_peeling_sim.cpp
```

Experiment logic:

```text
fix d,k,l,M
scan circular a and z
run hypergraph peeling simulation
record peeling_success_rate
```

This is not full XYZ decoding. It does not run `XYZSketch::Decode()`, polynomial reconstruction, root finding, or algebraic verification. It measures structural peeling success.

The simulator follows the circular hash geometry from `XYZ-v2/hash.cpp`:

```text
RangeLength = M / (z + 1)
base_range = M - floor(a * RangeLength) + 1
bucket = (base + offset) % M
```

Default behavior:

```text
dedup_hashes = false
trials = 100
```

Command used:

```bash
python3 tests/test_fig2_fixed_m_sim.py \
  --m-candidates tests/results/paper_fig2_m_candidates/m_candidates.csv \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --z-values 0,1,2,3,4,5,6,8,10,12,16 \
  --output-dir tests/results/paper_fig2_fixed_m_sim
```

Resume command:

```bash
python3 tests/test_fig2_fixed_m_sim.py \
  --m-candidates tests/results/paper_fig2_m_candidates/m_candidates.csv \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --z-values 0,1,2,3,4,5,6,8,10,12,16 \
  --resume \
  --skip-build \
  --output-dir tests/results/paper_fig2_fixed_m_sim
```

Output directory:

```text
tests/results/paper_fig2_fixed_m_sim
```

Output files:

```text
raw.jsonl
summary.jsonl
summary.csv
summary.md
run_config.json
```

Current size:

```text
summary.jsonl: 4257 rows
summary.csv: 4258 lines including header
```

Validation:

```bash
python3 tests/json_verifier.py tests/results/paper_fig2_fixed_m_sim/summary.jsonl --strict
```

Result:

```text
checked=4257 failures=0
```

## 4. Backup

The new Figure 2(a) fixed-M simulation result was backed up to:

```text
tests/results/backups/figure2a_fixed_m_sim_20260710_074929
```

Backup files:

```text
raw.jsonl
summary.jsonl
summary.csv
summary.md
run_config.json
```

## 5. Plot Figure 2(a)

Plot script:

```text
tests/plot_figure2_fixed_m.py
```

Command:

```bash
python3 tests/plot_figure2_fixed_m.py \
  --input tests/results/paper_fig2_fixed_m_sim/summary.csv \
  --output-dir tests/results/paper_figures/figure2a_fixed_m \
  --only all \
  --target-success-rate 0.9
```

Figure 2(a) definition:

```text
one SVG per d
one panel per fixed M
x-axis = circular a
y-axis = z
color = peeling_success_rate
yellow box = tested grid cell nearest to the data-fitted heuristic
```

The marker retains the implementation formula, but `C` and `D` are empirical
constants fitted on the current Figure 2 data:

```text
c_orient/c_peel = 1.2081
C = (1/3) / 1.2081 = 0.27591535
a_marker = C * c_orient/c_peel = 1/3
D = 0.5
delta = 0.1
z_marker = D * (1-a_marker)^(2/3) * (M/log(1/delta))^(1/3)
```

The fit first maximizes the number of marked panels reaching `0.9`, then the
mean marked-cell success rate. The grid identifies the tested `a=1/3` column,
not a precise continuous `C`. With that column fixed, the best-scoring `D`
plateau is approximately `[0.3085,0.6235]`; `D=0.5` is an interior representative.

Across the 43 panels, target coverage changes from 37 to 41, mean marked-cell
success from 0.93465 to 0.98837, and mean regret from 0.06140 to 0.00767.

`z_marker` remains continuous. The yellow box selects the tested `(a,z)` cell
nearest to `(a_marker,z_marker)`. These constants are a formula-shaped empirical
fit, not a theory prediction independent of the plotted data.

These values can be overridden with:

```text
--marker-c
--marker-c-orient-over-c-peel
--marker-d
--marker-delta
```

Outputs:

```text
tests/results/paper_figures/figure2a_fixed_m/figure2a_fixed_m_d100.svg
tests/results/paper_figures/figure2a_fixed_m/figure2a_fixed_m_d300.svg
tests/results/paper_figures/figure2a_fixed_m/figure2a_fixed_m_d1000.svg
tests/results/paper_figures/figure2a_fixed_m/figure2a_fixed_m_d3000.svg
tests/results/paper_figures/figure2a_fixed_m/figure2a_fixed_m_d10000.svg
tests/results/paper_figures/figure2a_fixed_m/figure2a_fixed_m_index.md
```

## 6. Plot Figure 2(b)

Figure 2(b) is generated by the same plotting script.

Definition:

```text
For each fixed (d,M), choose the largest z such that peeling_success_rate >= 0.9.
This value is z_star.
If no point reaches 0.9, choose the highest-success point and mark it as below_target.
```

Outputs:

```text
tests/results/paper_figures/figure2a_fixed_m/figure2b_fixed_m_z_star.svg
tests/results/paper_figures/figure2a_fixed_m/figure2b_fixed_m_z_star_source.csv
```

Current Figure 2(b) source table:

```text
43 rows
42 target_met
1 below_target
```

## 7. d=100000 Extension (Legacy Pilot)

This section preserves the original `+100,+200,+300` pilot for provenance.
The current large-d workflow is `tests/run_figure2_large_d.py`; its replacement
`d=100000` candidates are `18440,18940,19940`.

`tests/select_fig2_d100000_m.py` evaluates the fitted heuristic point with 20
shared trials and performs an empirical binary search for the first `M` reaching
`0.9`. The command is:

```bash
python3 tests/select_fig2_d100000_m.py \
  --output-dir tests/results/paper_fig2_d100000_m_search
```

With `a=1/3`, `D=0.5`, and `delta=0.1`, the search produced:

```text
M = 17954: 16/20 = 0.80
M = 17955: 19/20 = 0.95
empirical threshold M = 17955
candidate M values = 18055,18155,18255
```

The fixed-M grid command is:

```bash
python3 tests/test_fig2_fixed_m_sim.py \
  --m-candidates tests/results/paper_fig2_d100000_m_search/m_candidates.csv \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --z-values 0,1,2,3,4,5,6,8,10,12,16 \
  --trials 20 \
  --shared-trial-seeds \
  --skip-build \
  --output-dir tests/results/paper_fig2_d100000_fixed_m_sim
```

`--shared-trial-seeds` applies the same 20 trial seeds to all three `M` values
and every `(a,z)` cell, enabling common-random-number comparisons.

All 297 rows pass strict JSON verification. The marked `(a,z)=(1/3,8)` cells
have success rates `0.95`, `1.00`, and `1.00` for the three increasing `M`
values. Plots are written under `tests/results/paper_figures/figure2_d100000`.

Twenty trials make this a coarse empirical threshold: reaching `0.9` means at
least 18 successes, and the 95% Wilson interval remains wide. `M=17955` must not
be presented as a precise 90% success boundary.

## 8. Main Caveat

The new Figure 2 measures:

```text
peeling_success_rate
```

It does not measure full XYZ end-to-end decode success. The result should be described as structural hypergraph peeling simulation, not complete protocol decoding.
