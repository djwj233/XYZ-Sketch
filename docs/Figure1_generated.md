# Figure 1 Server Run Workflow

This document records how Figure 1 has been run on this server, including the
entry scripts, parameters, output files, and current result state.

Run every command from the repository root:

```bash
cd /root/XYZ-Sketch
```

## Scope

Figure 1 is independent from Figure 2 and Figure 3.

- Figure 1(a): sharp-threshold curves for XYZ-v2.
- Figure 1(b): XYZ-only communication frontier.
- Representative tuples: `(k,l) = (2,3), (2,6), (3,4)`.
- Modes: `random`, `naive`, `circular`.
- `random` is the iid hashing baseline in this codebase.
- `naive` and `circular` are spatial-coupling variants.

For Figure 1, `a` and `z` are computed by formulas, not fixed by hand:

```text
a = C * c_orient / c_peel, C = 1/3
z = D * (1-a)^(2/3) * (M/log(1/delta))^(1/3), D = 4/3
```

The constants `c_orient` and `c_peel` are provided by `tests/xyz_tuning.py`.
For the paper tuples, the current `a` values are recorded in each run config.

## Figure 1(a): Sharp Threshold

Entry script:

```text
tests/test_xyz_sharp_threshold.py
```

Server-scale command:

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

Implementation flow:

1. Build or reuse `xyz_v2_bench`.
2. For each `(k,l,mode)` config, run a small center search with
   `--center-trials 10` to estimate the threshold center `M0`.
3. Scan `M` in the window
   `M0 +/- min(max(0.06*M0, 20), 120)`.
4. Use `--step 3`, so candidate `M` values are spaced by 3.
5. Run `--trials 100` at every scanned `M`.
6. Write raw points and threshold summaries.

Important output files:

```text
tests/results/paper_fig1_sharp_threshold/raw.jsonl
tests/results/paper_fig1_sharp_threshold/raw.csv
tests/results/paper_fig1_sharp_threshold/summary.jsonl
tests/results/paper_fig1_sharp_threshold/summary.csv
tests/results/paper_fig1_sharp_threshold/summary.md
tests/results/paper_fig1_sharp_threshold/run_config.json
```

Current server state:

- This run exists on the server.
- The active run config is
  `tests/results/paper_fig1_sharp_threshold/run_config.json`.
- It uses `--tuple-values 2:3,2:6,3:4`, so it does not run the Cartesian
  product from `--k-values` and `--l-values`.
- It has 9 configurations: 3 tuples times 3 modes.
- The latest backup directories are:

```text
tests/results/paper_fig1_sharp_threshold_backup_20260709_065443
tests/results/paper_fig1_sharp_threshold_backup_20260709_222516
```

## Figure 1(b): Communication Frontier

Entry script:

```text
tests/test_frontier_xyz.py
```

Server-scale command:

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

Implementation flow:

1. `tests/test_frontier_xyz.py` is a paper-facing wrapper.
2. It splits the tuple list into shards.
3. For each tuple shard, it calls `tests/test_spatial.py`.
4. Each shard searches the smallest `M` reaching 90% success for each `d`
   and mode.
5. The intended top-level outputs are merged `probes` and `summary` files.

Expected top-level output files:

```text
tests/results/paper_fig1_frontier/probes.jsonl
tests/results/paper_fig1_frontier/summary.jsonl
tests/results/paper_fig1_frontier/summary.csv
tests/results/paper_fig1_frontier/summary.md
tests/results/paper_fig1_frontier/run_config.json
```

Current server state:

- The top-level merged `summary.csv` and `run_config.json` are currently not
  present in `tests/results/paper_fig1_frontier`.
- The shard outputs do exist:

```text
tests/results/paper_fig1_frontier/shards/k2_l3/
tests/results/paper_fig1_frontier/shards/k2_l6/
tests/results/paper_fig1_frontier/shards/k3_l4/
```

- Current shard row counts:

```text
k2_l3: 18 summary rows
k2_l6: 10 summary rows
k3_l4: 10 summary rows
total: 38 summary rows
```

- `tests/plot_figure1.py` can read the shard summaries directly if the
  requested top-level `summary.csv` is absent.

## Validation

Run strict JSON validation before treating the data as paper input:

```bash
python3 tests/json_verifier.py tests/results/paper_fig1_sharp_threshold/raw.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_sharp_threshold/summary.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/shards/k2_l3/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/shards/k2_l3/summary.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/shards/k2_l6/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/shards/k2_l6/summary.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/shards/k3_l4/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/shards/k3_l4/summary.jsonl --strict
```

## Plotting

Entry script:

```text
tests/plot_figure1.py
```

Command used on this server:

```bash
python3 tests/plot_figure1.py \
  --sharp-input tests/results/paper_fig1_sharp_threshold/raw.csv \
  --frontier-input tests/results/paper_fig1_frontier/summary.csv \
  --output-dir tests/results/paper_figures
```

Generated SVG files:

```text
tests/results/paper_figures/figure1a_sharp_threshold.svg
tests/results/paper_figures/figure1b_frontier.svg
tests/results/paper_figures/figure1_source_summary.md
```

The source summary currently reports:

```text
Figure 1(a) raw rows read: 725
Figure 1(a) summary rows read: 9
Figure 1(b) rows read from shards: 38
Figure 1(b) unresolved rows marked, not hidden: 11
```

## Operational Notes

- Run long Figure 1 jobs in `tmux` if the VSCode connection may close.
- `status=unresolved` means the final validation did not reach the target
  success rate. It is not a process crash by itself.
- If Figure 1(b) should be a clean final artifact, rerun or repair the wrapper
  merge so the top-level `summary.csv`, `summary.jsonl`, and `run_config.json`
  are present.
