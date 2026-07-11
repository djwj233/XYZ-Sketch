# Figure 3 Server Run Workflow

This document records how Figure 3 has been run on this server, including the
entry script, experiment flow, command lines, output files, and current result
state.

Run every command from the repository root:

```bash
cd /root/XYZ-Sketch
```

## Scope

Figure 3 compares XYZ-Sketch against practical set-reconciliation baselines.
One shared experiment produces the data for all three panels:

- Figure 3(a): communication frontier, using `best_R_w30`.
- Figure 3(b): update cost, using `update_avg_s_per_element`.
- Figure 3(c): decode cost, using `decode_avg_s_per_difference`.

Current frontier algorithms:

```text
xyz_v1, xyz_v2, iblt, minisketch, cpisync, riblt, negentropy
```

The main runner is:

```text
tests/test_compare_frontier.py
```

The plotter is:

```text
tests/plot_figure3.py
```

## External Dependencies

Figure 3 uses external baseline implementations. Before a clean run, initialize
submodules:

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

The runner builds or prepares benchmark binaries automatically unless
`--skip-build` is passed.

## XYZ-v2 Parameter Policy

For `xyz_v2`, the default policy is formula-based, not Figure 2 tuning:

```text
a = C * c_orient / c_peel, C = 1/3
z = D * (1-a)^(2/3) * (M/log(1/delta))^(1/3), D = 4/3
```

The implementation is in:

```text
tests/xyz_tuning.py
```

Current Figure 3 default:

```text
(k,l) = (2,6)
a = 0.4026505079327622
z = computed from the formula for each candidate M
```

To switch back to Figure 2 tuned parameters later, pass:

```bash
--xyz-tuning tests/results/paper_fig2_z_star/summary.jsonl
```

## Scientific Rerun Plan

The existing Figure 3 results are diagnostic only. They must not be extended to
larger `d` and used as paper results without fixing the workload, communication,
statistics, and timing definitions below.

### Experimental Invariants

The rerun must hold the following conditions fixed across every `d`:

1. Use one workload family with a constant set-size ratio. The planned main
   profile is `ca = cb = 2d`, which gives `common/d = 1.5`. Remove the current
   minimum-size and `max_set_size` regime changes.
2. Use the exact same trial datasets for all algorithms at a given `d`.
3. Use disjoint search and final-validation datasets. A dataset used to choose a
   parameter must never be reused to validate that parameter.
4. Use the same 30-bit input universe for algorithms that support it. A native
   256-bit protocol such as Negentropy must be labelled separately rather than
   silently treated as a 30-bit sketch.
5. Never give XYZ-only final slack. Either validate the searched parameter
   exactly or apply the same statistically defined upper bracket to every
   fixed-capacity algorithm.

The staged `d` grid is:

```text
smoke:       100, 1000
main:        100, 300, 1000, 3000, 10000, 30000, 100000, 300000, 1000000
large-scale: 3000000, 10000000 only after the main grid passes validation
```

Large-scale datasets must be generated and consumed incrementally. Keeping
hundreds of text datasets containing about `4d` elements each on disk is not
an acceptable execution strategy.

### Current Runner Status

The runner has been updated with the baseline fixes needed before the next
smoke run:

- The default workload is now `--set-size-policy fixed-ratio` with
  `--set-size-ratio 2.0`, so the standard grid uses `ca = cb = 2d` for even
  `d`. The old capped/minimum-size behavior remains available with
  `--set-size-policy legacy` for reproducing historical runs.
- Search and final validation now use disjoint dataset slices. Each
  `(algorithm, d)` prepares `probe_trials + final_trials` shared datasets;
  search sees the first block and final validation sees the second block.
- Trial aggregation no longer inherits communication fields from trial zero.
  The runner records average, median, and 90th percentile values for varying
  fields such as `bits`, `symbols_sent`, `rounds`, `client_bytes`, and
  `server_bytes`. If `bits` varies across trials, the primary plotted budget
  uses the empirical 90th percentile.
- RIBLT accounting now counts one coded symbol as
  `symbol_bits + 64-bit hash + 64-bit count`; with the current default
  `symbol_bits=64`, this is 192 bits per transmitted coded symbol. The
  `field_bits` argument is still metadata for this wrapper, not a compact
  30-bit serialization.
- The runner can now repair near-miss final validations with bounded upward
  retries. Use `--final-retry-algorithms xyz_v2,iblt,riblt`,
  `--final-retry-growth 1.05`, `--final-retry-limit 4`, and
  `--final-retry-min-success-rate 0.75` to retry only candidates that are close
  to the 90% target. Each retry reruns final validation on the same held-out
  final dataset and records `final_retry_count`, `search_parameter`,
  `best_parameter`, and `final_parameter_multiplier`.

These fixes make the next `d <= 10000` smoke meaningful as engineering data.
They still do not replace the final statistical protocol below.

### Planned Algorithm Queue

Minisketch is part of every new correctness smoke and the main comparison queue.

| Queue | Algorithms | Purpose |
| --- | --- | --- |
| Q0: wrapper correctness | `xyz_v2,minisketch,iblt,riblt,negentropy` | Verify decoded differences, accounting, and timing boundaries on `d=100,1000`. |
| Q1: core frontier | `xyz_v2,minisketch,iblt,riblt` | Main one-way/fixed-budget communication comparison. |
| Q2: interactive protocol | `negentropy` | Fixed-frame total-byte and round-count experiment, reported separately. |
| Q3: optional appendix | `cpisync,xyz_v1` | Run only after their accounting and capacity semantics are audited. |

The immediate Minisketch integration smoke, which checks only that the current
wrapper builds and runs, is:

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100,1000 \
  --algorithms minisketch \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9 \
  --output-dir tests/results/paper_fig3_minisketch_smoke
```

This smoke is not paper data because it still uses a small-trial binary search
rather than the final grid/isotonic statistical protocol.

### Required Implementation Fixes

Complete the remaining changes before starting paper-quality Q1:

1. Replace noisy five-trial binary search with a capacity grid followed by an
   isotonic success-rate fit for XYZ, Minisketch, and IBLT.
2. Use at least 50 independent search trials and 200 independent final trials.
   Report a bootstrap confidence interval for the inferred 90% communication
   threshold.
3. Treat bounded final retry as a smoke-run repair, not as the final estimator.
   It is acceptable for current Figure 3 diagnostics because it converts
   near-miss binary-search candidates into validated points with controlled
   overhead, but paper-quality Q1 should still use a grid/isotonic estimate.
4. For RIBLT, run with a sufficiently high cap, measure required coded symbols
   per trial, and use the empirical 90th percentile as the communication budget.
   The current wrapper now fixes the basic 192-bit coded-symbol accounting, but
   the search strategy is still a cap search rather than a dedicated
   required-symbol distribution experiment.
5. For Negentropy, do not search `frame_size_limit` as a capacity. Fix a
   documented frame policy, initially 64 KiB, and report total bytes, rounds,
   and their distributions. A communication frontier requires an explicit
   cumulative-byte budget.
6. Keep historical output directories immutable. Write corrected data under
   `tests/results/paper_fig3_v2_*`.

### Bounded Final Retry

The recommended smoke-run command for searched algorithms is:

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000 \
  --algorithms xyz_v2,iblt,riblt \
  --probe-trials 5 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --final-retry-algorithms xyz_v2,iblt,riblt \
  --final-retry-growth 1.05 \
  --final-retry-limit 4 \
  --final-retry-min-success-rate 0.75 \
  --job-timeout-s 0 \
  --output-dir tests/results/paper_fig3_v2_retry_frontier
```

This mode does not retry candidates that are clearly poor. If the first final
validation is below `--final-retry-min-success-rate`, the point remains
unresolved. This prevents a bad search or broken wrapper from spending many
extra final validations.

### Communication Metrics

The core frontier has this meaning:

```text
x = d
y = minimum serialized communication budget reaching 90% success
normalization = transmitted_bits / (30*d)
```

Metric policy by algorithm:

| Algorithm | Communication value |
| --- | --- |
| XYZ-v2 | Serialized sketch bits at the selected `M`. |
| Minisketch | Serialized capacity times the 30-bit field width, including byte rounding. |
| IBLT | Canonical serialized cell width times the selected cell count. |
| RIBLT | 90th percentile of serialized coded-symbol bytes required to decode. |
| Negentropy | Distribution of total bidirectional bytes at a fixed frame policy; not the fixed-sketch frontier. |

Do not force raw curves to be monotone. Finite-size estimates may fluctuate.
The paper claim is convergence with uncertainty, so plots should show measured
points, bootstrap intervals, and an optional clearly labelled isotonic trend.

### Timing Metrics

Timing must be a separate pass using capacities selected by the communication
experiment. Every wrapper must expose the same boundaries:

```text
sender_update_s_per_element
receiver_update_s_per_element
decode_or_reconcile_s_per_difference
```

Use in-process warmups, repeated measurements, medians, and bootstrap
confidence intervals. Do not compare the current mixed definitions where XYZ
times only Alice, RIBLT times both local structures, and Negentropy includes
storage construction in reconciliation.

### Rerun Gate

The full Q1 run may start only after the following smoke assertions pass:

- every successful row reconstructs the exact symmetric difference;
- increasing a fixed capacity has a nondecreasing isotonic success estimate;
- reported fixed-sketch bits are constant across datasets at one capacity;
- RIBLT wire bytes match the serialized coded-symbol representation;
- search and validation dataset IDs are disjoint;
- `ca/d` and `common/d` stay constant across the complete grid;
- Minisketch appears in Q0 and Q1 outputs.

## Historical Full Algorithm Run

The commands and result counts below describe previous runs. Preserve them for
auditability, but do not resume them as the corrected paper experiment.

Server-scale command for the all-baseline run:

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

Current server state:

- The output directory exists:

```text
tests/results/paper_fig3_compare_frontier
```

- `summary.jsonl` currently has 45 rows.
- A complete all-algorithm run over 7 algorithms and 11 `d` values would have
  77 summary rows.
- This means the current all-algorithm directory is not a complete final run.
- Several large jobs timed out because this command used
  `--job-timeout-s 1800`.

Important output files:

```text
tests/results/paper_fig3_compare_frontier/probes.jsonl
tests/results/paper_fig3_compare_frontier/summary.jsonl
tests/results/paper_fig3_compare_frontier/summary.csv
tests/results/paper_fig3_compare_frontier/summary.md
tests/results/paper_fig3_compare_frontier/run_config.json
tests/results/paper_fig3_compare_frontier/errors.log
```

## Historical Focused Subset Run

The previous focused run used only the following algorithms and did not include
Minisketch:

```text
xyz_v2, iblt, riblt, negentropy
```

Command:

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 \
  --algorithms xyz_v2,iblt,riblt,negentropy \
  --probe-trials 5 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --job-timeout-s 0 \
  --xyz-final-m-offset 4 \
  --output-dir tests/results/paper_fig3_compare_frontier_subset \
  2>&1 | tee tests/results/paper_fig3_compare_frontier_subset/run.log
```

Meaning:

- Search probes use only 5 trials.
- Final validation still uses 100 trials.
- `--job-timeout-s 0` disables the per-job 30 minute timeout.
- For `xyz_v2`, the searched `M` is increased by 4 before final validation.
- Progress is written both to the terminal and to `run.log`.

Current server state:

- The output directory exists:

```text
tests/results/paper_fig3_compare_frontier_subset
```

- `summary.jsonl` currently has 36 rows.
- A complete subset run over 4 algorithms and 11 `d` values would have
  44 summary rows.
- Therefore this subset directory is also not yet a complete final run unless a
  background process is still appending to it.
- Do not append the new Minisketch queue to this directory. The corrected queue
  must use a new `paper_fig3_v2_*` output directory.

Important output files:

```text
tests/results/paper_fig3_compare_frontier_subset/probes.jsonl
tests/results/paper_fig3_compare_frontier_subset/summary.jsonl
tests/results/paper_fig3_compare_frontier_subset/summary.csv
tests/results/paper_fig3_compare_frontier_subset/summary.md
tests/results/paper_fig3_compare_frontier_subset/run_config.json
tests/results/paper_fig3_compare_frontier_subset/run.log
```

## Runner Implementation Flow

For each `(algorithm,d)` job, `tests/test_compare_frontier.py` does the
following:

1. Build or prepare benchmark binaries.
2. Generate shared datasets for the current `(d, ca, cb, seed)`.
3. Reuse the same shared datasets across algorithms for that `d`.
4. Run an upper-bound search for the algorithm's capacity parameter.
5. Binary-search the smallest parameter that passes the probe criterion.
6. Run final validation with `--final-trials`.
7. Write `probes`, `summary`, `run_config`, and `errors` files incrementally
   after every job.

Capacity parameter by algorithm:

```text
xyz_v1:      fixed
xyz_v2:      M
iblt:        cells
minisketch:  capacity
cpisync:     mbar
riblt:       max_symbols
negentropy:  frame_size_limit
```

The success target is point-estimate based by default:

```text
--target-success-rate 0.9
--threshold-policy point
```

So a row is marked `ok` only if the final validation reaches at least 90%
success. If the probe search found a candidate but the final validation misses
90%, the summary status becomes `unresolved`.

## Timing Metrics

The runner derives timing metrics from each benchmark row:

```text
update_avg_s_per_element = encode_avg_s / (ca + cb)
decode_avg_s_per_difference = decode_avg_s / d
```

Important caveat:

- `cpisync` currently reports `encode_avg_s=0`; its `decode_avg_s` is closer to
  full reconciliation time.
- `negentropy` has the same timing caveat.
- Therefore Figure 3(b) should not interpret CPISync or Negentropy update cost
  as genuinely zero.

## Validation

Validate the selected result directory before plotting:

```bash
python3 tests/json_verifier.py tests/results/paper_fig3_compare_frontier_subset/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig3_compare_frontier_subset/summary.jsonl --strict
```

For the all-algorithm directory, use:

```bash
python3 tests/json_verifier.py tests/results/paper_fig3_compare_frontier/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig3_compare_frontier/summary.jsonl --strict
```

## Plotting

Plot the subset result:

```bash
python3 tests/plot_figure3.py \
  --input tests/results/paper_fig3_compare_frontier_subset/summary.jsonl \
  --output-dir tests/results/paper_figures
```

Or plot the all-algorithm result:

```bash
python3 tests/plot_figure3.py \
  --input tests/results/paper_fig3_compare_frontier/summary.jsonl \
  --output-dir tests/results/paper_figures
```

Generated SVG files:

```text
tests/results/paper_figures/figure3a_communication.svg
tests/results/paper_figures/figure3b_update_cost.svg
tests/results/paper_figures/figure3c_decode_cost.svg
tests/results/paper_figures/figure3_source_summary.md
```

`tests/plot_figure3.py` reads either CSV or JSONL. All panels use a logarithmic
x-axis, and communication/time also use logarithmic y-axes so algorithms with
different orders of magnitude remain visible.

- Filled markers and connecting lines passed the 90% final validation.
- Open crossed markers have a measurement but failed final validation; they are
  not connected.
- `encode_avg_s=0` is treated as unavailable update timing, not zero cost.
- `final_ci_low/high` describe success rate, not communication-threshold
  uncertainty, so they are not drawn as Figure 3(a) y-error bars.
- Pass `--hide-unresolved` for a strict plot containing only validated points.

PNG/PDF export is not currently implemented in `tests/plot_figure3.py`; the
existing plotter writes dependency-free SVG.

## Running in the Background

For long Figure 3 runs, use `tmux`:

```bash
cd /root/XYZ-Sketch
tmux new -s fig3
```

Run the experiment inside the tmux session, then detach with:

```text
Ctrl-b d
```

Reattach later:

```bash
tmux attach -t fig3
```

Follow the subset log:

```bash
tail -f /root/XYZ-Sketch/tests/results/paper_fig3_compare_frontier_subset/run.log
```

## Operational Notes

- `status=job_timeout` means the per-job timeout fired.
- `status=unresolved` means the final validation did not reach the 90% target.
- `xyz_v1` is a fixed-parameter baseline in the current wrapper.
- `minisketch` is a strong communication baseline; current data should not be
  used to claim XYZ-v2 is globally best across every metric.
- For communication comparisons against IBLT/RIBLT/CPISync/Negentropy, XYZ-v2
  is competitive in the current partial results, but incomplete rows should be
  handled explicitly.
