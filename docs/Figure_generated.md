# Figure Generation Guide

This file explains how to generate the data and figures for Figure 1, Figure 2,
and Figure 3.

Run all commands from the repository root:

```bash
cd /root/XYZ-Sketch
```

## 0. Prepare External Submodules

Figure 3 uses external baselines such as minisketch. Initialize the submodules
first:

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

If this step fails because GitHub cannot be reached, fix network access or change
the URLs in `.gitmodules` to SSH URLs, then run the same commands again.

## 1. Figure 1

Figure 1 is independent from Figure 2 and Figure 3.

### Figure 1(a): Sharp Threshold

Goal:

- Show success rate as communication `R_w30` increases.
- Compare `random`, `naive`, and `circular` modes.
- Use representative tuples `(k,l) = (2,3), (2,6), (3,4)`.

Run:

```bash
python3 tests/test_xyz_sharp_threshold.py \
  --d-values 10000 \
  --tuple-values 2:3,2:6,3:4 \
  --modes random,naive,circular \
  --trials 100 \
  --center-trials 10 \
  --window-fraction 0.06 \
  --min-window 20 \
  --max-window 120 \
  --step 3 \
  --target-success-rate 0.9 \
  --a-constant 0.3333333333 \
  --z-constant 1.3333333333 \
  --output-dir tests/results/paper_fig1_sharp_threshold
```

This first searches an empirical center `M0` with 10 `center-trials`, then scans
the narrower interval `M0 +/- min(max(0.06*M0, 20), 120)` with `step = 3`.
If the resulting curve does not include clear failure and success points on
both sides, increase `--max-window` or `--window-fraction`.

Important output files:

```text
tests/results/paper_fig1_sharp_threshold/raw.jsonl
tests/results/paper_fig1_sharp_threshold/raw.csv
tests/results/paper_fig1_sharp_threshold/summary.jsonl
tests/results/paper_fig1_sharp_threshold/summary.csv
tests/results/paper_fig1_sharp_threshold/summary.md
tests/results/paper_fig1_sharp_threshold/run_config.json
```

The command above uses `--tuple-values`, so it runs only `(2,3)`, `(2,6)`, and `(3,4)`.

### Figure 1(b): Communication Frontier

Goal:

- For each `d`, find the minimum communication needed to reach 90% success.
- Compare iid hashing and spatial coupling.
- In this codebase, `random = iid`; `naive` and `circular` are two spatial-coupling variants.

Run:

```bash
python3 tests/test_frontier_xyz.py \
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 \
  --tuple-values 2:3,2:6,3:4 \
  --modes random,naive,circular \
  --probe-trials 50 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --a-constant 0.3333333333 \
  --z-constant 1.3333333333 \
  --output-dir tests/results/paper_fig1_frontier
```

Important output files:

```text
tests/results/paper_fig1_frontier/probes.jsonl
tests/results/paper_fig1_frontier/summary.jsonl
tests/results/paper_fig1_frontier/summary.csv
tests/results/paper_fig1_frontier/summary.md
tests/results/paper_fig1_frontier/run_config.json
```

Validate Figure 1 data:

```bash
python3 tests/json_verifier.py tests/results/paper_fig1_sharp_threshold/raw.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_sharp_threshold/summary.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/summary.jsonl --strict
```

Current plotting status:

```text
Figure 1 data generation exists.
Figure 1 SVG plotting is implemented in tests/plot_figure1.py.
PNG/PDF export can be produced from the SVG files with Inkscape, rsvg-convert, or a browser print/export flow.
```

Run:

```bash
python3 tests/plot_figure1.py \
  --sharp-input tests/results/paper_fig1_sharp_threshold/raw.csv \
  --frontier-input tests/results/paper_fig1_frontier/summary.csv \
  --output-dir tests/results/paper_figures
```

Current figure outputs:

```text
tests/results/paper_figures/figure1a_sharp_threshold.svg
tests/results/paper_figures/figure1b_frontier.svg
tests/results/paper_figures/figure1_source_summary.md
```

## 2. Figure 2

Figure 2 can be generated independently. The current Figure 3 main run does not consume tuned `(a,z)` values from Figure 2 by default; it computes `a,z` from the heuristic formulas. `paper_fig2_z_star/summary.jsonl` remains available as an optional tuning input for future runs.

### Figure 2(a): Circular `(a,z)` Heatmap

Goal:

- Scan circular spatial coupling parameters `a` and `z`.
- For each `(a,z)` cell, search the minimum `M` that reaches 90% success.
- Use `best_R_w30` as the heatmap value.

For a single representative heatmap, run:

```bash
python3 tests/test_az_grid.py \
  --d-values 3000 \
  --k-values 2 \
  --l-values 6 \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --z-values 0,1,2,3,4,5,6,8,10,12,16 \
  --probe-trials 30 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --shared-datasets \
  --output-dir tests/results/paper_fig2_az_grid
```

If you also need a meaningful Figure 2(b) curve, use multiple `d` values:

```bash
python3 tests/test_az_grid.py \
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 \
  --k-values 2 \
  --l-values 6 \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --z-values 0,1,2,3,4,5,6,8,10,12,16 \
  --probe-trials 30 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --shared-datasets \
  --output-dir tests/results/paper_fig2_az_grid
```

Important output files:

```text
tests/results/paper_fig2_az_grid/probes.jsonl
tests/results/paper_fig2_az_grid/summary.jsonl
tests/results/paper_fig2_az_grid/summary.csv
tests/results/paper_fig2_az_grid/summary.md
tests/results/paper_fig2_az_grid/run_config.json
tests/results/paper_fig2_az_grid/errors.log
```

### Figure 2(b): Extract `z_star(d)`

Goal:

- Select the best `(a,z)` for each `d`.
- Compare experimental `z_star` with heuristic/theory `z_theory`.
- Produce the tuning file used by Figure 3.

Run:

```bash
python3 tests/extract_fig2_z_star.py \
  --input tests/results/paper_fig2_az_grid/summary.jsonl \
  --output-dir tests/results/paper_fig2_z_star
```

Important output files:

```text
tests/results/paper_fig2_z_star/summary.jsonl
tests/results/paper_fig2_z_star/summary.csv
tests/results/paper_fig2_z_star/summary.md
tests/results/paper_fig2_z_star/run_config.json
```

Validate Figure 2 data:

```bash
python3 tests/json_verifier.py tests/results/paper_fig2_az_grid/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig2_az_grid/summary.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig2_z_star/summary.jsonl --strict
```

Current plotting status:

```text
Figure 2 data generation exists.
Figure 2 z_star extraction exists.
Figure 2 plotting script is not implemented yet.
Expected script name: tests/plot_figure2.py
```

The plotting script should read:

```text
tests/results/paper_fig2_az_grid/summary.csv
tests/results/paper_fig2_z_star/summary.csv
```

Expected final figure outputs:

```text
tests/results/paper_figures/figure2a_az_heatmap.png
tests/results/paper_figures/figure2a_az_heatmap.pdf
tests/results/paper_figures/figure2b_z_star.png
tests/results/paper_figures/figure2b_z_star.pdf
```

## 3. Figure 3

Figure 3 compares heuristic-formula XYZ-Sketch with practical baselines.

The default constants are `C=1/3` and `D=4/3`:

```text
a = C * c_orient / c_peel
z = D * (1-a)^(2/3) * (M/log(1/delta))^(1/3)
```

To switch back to tuned `(a,z)` from Figure 2 later, add:

```text
--xyz-tuning tests/results/paper_fig2_z_star/summary.jsonl
```

### Figure 3(a), 3(b), 3(c): Shared Experiment

This one experiment produces the data for all three Figure 3 panels:

- Figure 3(a): communication frontier, using `best_R_w30`
- Figure 3(b): update cost, using `update_avg_s_per_element`
- Figure 3(c): decode cost, using `decode_avg_s_per_difference`

Run:

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 \
  --algorithms xyz_v1,xyz_v2,iblt,minisketch,cpisync,riblt,negentropy \
  --probe-trials 30 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --job-timeout-s 1800 \
  --a-constant 0.3333333333 \
  --z-constant 1.3333333333 \
  --output-dir tests/results/paper_fig3_compare_frontier
```

Important output files:

```text
tests/results/paper_fig3_compare_frontier/probes.jsonl
tests/results/paper_fig3_compare_frontier/summary.jsonl
tests/results/paper_fig3_compare_frontier/summary.csv
tests/results/paper_fig3_compare_frontier/summary.md
tests/results/paper_fig3_compare_frontier/run_config.json
tests/results/paper_fig3_compare_frontier/errors.log
```

Validate Figure 3 data:

```bash
python3 tests/json_verifier.py tests/results/paper_fig3_compare_frontier/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig3_compare_frontier/summary.jsonl --strict
```

Generate Figure 3 SVG images:

```bash
python3 tests/plot_figure3.py \
  --input tests/results/paper_fig3_compare_frontier/summary.csv \
  --output-dir tests/results/paper_figures
```

Generated files:

```text
tests/results/paper_figures/figure3a_communication.svg
tests/results/paper_figures/figure3b_update_cost.svg
tests/results/paper_figures/figure3c_decode_cost.svg
tests/results/paper_figures/figure3_source_summary.md
```

Current plotting status:

```text
Figure 3 SVG plotting exists.
PNG/PDF export is not implemented yet.
test_compare_frontier.py includes xyz_v1, cpisync, riblt, and negentropy; iblt_cpp remains optional/outside frontier search.
Currently supported baselines: xyz_v1, xyz_v2, iblt, minisketch, cpisync, riblt, negentropy. xyz_v1 is included as a fixed-parameter baseline; riblt searches max_symbols.
```

Expected final publication outputs after PNG/PDF export is added:

```text
tests/results/paper_figures/figure3a_communication.png
tests/results/paper_figures/figure3a_communication.pdf
tests/results/paper_figures/figure3b_update_cost.png
tests/results/paper_figures/figure3b_update_cost.pdf
tests/results/paper_figures/figure3c_decode_cost.png
tests/results/paper_figures/figure3c_decode_cost.pdf
```

## 4. Smoke Tests Before Paper Runs

Before launching expensive paper-scale runs, use small smoke runs.

Figure 2 smoke:

```bash
python3 tests/test_az_grid.py \
  --d-values 300 \
  --k-values 2 \
  --l-values 6 \
  --a-values 0,0.3333333333,0.6 \
  --z-values 0,1,2,3 \
  --probe-trials 5 \
  --final-trials 10 \
  --target-success-rate 0.9 \
  --shared-datasets \
  --output-dir tests/results/paper_fig2_az_grid_smoke
```

Figure 3 smoke:

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100,300 \
  --algorithms xyz_v1,xyz_v2,iblt,minisketch,cpisync,riblt,negentropy \
  --probe-trials 5 \
  --final-trials 10 \
  --target-success-rate 0.9 \
  --job-timeout-s 1800 \
  --a-constant 0.3333333333 \
  --z-constant 1.3333333333 \
  --output-dir tests/results/paper_fig3_compare_frontier_smoke
```

## 5. Final Result Directory Layout

After all successful runs, the expected result directories are:

```text
tests/results/
  paper_fig1_sharp_threshold/
  paper_fig1_frontier/
  paper_fig2_az_grid/
  paper_fig2_z_star/
  paper_fig3_compare_frontier/
  paper_figures/
```

The key files used for plotting are:

```text
Figure 1(a): tests/results/paper_fig1_sharp_threshold/raw.csv
Figure 1(b): tests/results/paper_fig1_frontier/summary.csv
Figure 2(a): tests/results/paper_fig2_az_grid/summary.csv
Figure 2(b): tests/results/paper_fig2_z_star/summary.csv
Figure 3:    tests/results/paper_fig3_compare_frontier/summary.csv
```

## 6. Work Still Needed

To fully generate publication-ready Figure 1, Figure 2, and Figure 3 images,
the remaining code work is:

```text
1. Add tests/plot_figure2.py.
2. Add PNG/PDF export for tests/plot_figure1.py and tests/plot_figure3.py if publication requires raster/PDF artifacts.
3. Optional remaining extension: add iblt_cpp to tests/test_compare_frontier.py. xyz_v1 and riblt are already connected.
```
