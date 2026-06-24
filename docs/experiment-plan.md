# Experiment Planning Notes

This document turns the current TODO list into an implementation plan for the next experimental phase. It is intentionally a planning document only: it describes what should be measured, how to organize the work, and what artifacts should be produced before rewriting the paper's experiment section.

## Goals

The next phase should make the experimental evidence stronger in four directions:

1. Cover a finer parameter space for `d`, `l`, and `k`.
2. Directly compare XYZ-Sketch with and without spatial coupling.
3. Show how sensitive the results are to the spatial coupling parameter `z`, so that `z` does not look like an unexplained magic parameter.
4. Add more external baselines if feasible, beyond the current comparison with IBLT and minisketch.

An optional final direction is to add one application-oriented experiment that demonstrates practical relevance, such as repository snapshot reconciliation.

## Current Starting Point

The repository already contains:

- `XYZ-v1`: the polynomial/RFR-based version.
- `XYZ-v2`: the multivariate-cell version, currently using spatial coupling by default.
- `IBLT`: an IBLT baseline.
- `finalResult.txt`: existing timing and communication results.

The main missing piece is not the core XYZ-v2 algorithm, but a systematic experiment harness: parameter sweeps, repeated trials, structured output, and plots/tables suitable for the paper.

## Work Package 1: Parameter Sweep for `d`, `l`, and `k`

### Purpose

Measure how communication cost, encoding time, decoding time, and success probability change as the main algorithm parameters vary.

### Suggested Sweep

Use several logarithmic values for `d`, for example:

- `10`, `30`, `100`, `300`, `1,000`, `3,000`
- `10,000`, `30,000`, `100,000`, `300,000`
- `1,000,000` if the machine can handle it

Use a small set of `l` values:

- `2`, `3`, `4`, `6`, `8`, `10`, `16`, `20`

Use a small set of `k` values:

- `2`, `3`, `4`

For each configuration, run multiple trials rather than a single trial. A good starting point is `30` trials for large configurations and `100` trials for small or medium configurations.

### Metrics

Record at least:

- `d`
- `l`
- `k`
- `M`
- `z`
- spatial coupling mode
- number of trials
- number of successful decodes
- success rate
- average encode time
- average decode time
- median encode time
- median decode time
- communication cost in bits
- normalized communication cost, such as `bits / (d * 32)` or `C / d`

### Expected Output

This package should produce a CSV or JSONL file that can later be converted into paper tables and plots.

## Work Package 2: Spatial Coupling vs Non-Spatial Coupling

### Purpose

Isolate the benefit of spatial coupling. Reviewers should be able to see that the improvement is not caused by unrelated parameter choices.

### Design

Run paired experiments:

- XYZ-v2 with `SpatialCoupling`.
- XYZ-v2 with `RandomHash`.

Keep `d`, `l`, `k`, target communication cost, and trial count the same where possible.

For each `d, l, k`, search for the smallest communication cost that reaches a target success rate. Suggested targets:

- `50%` success rate for threshold-style plots.
- `95%` or `99%` success rate for practical-performance plots.

### Metrics

Record:

- smallest `C / d` achieving the target success rate
- encode/decode times at that point
- failure modes, if available

### Expected Output

This package should produce a table or figure comparing `C / d` for spatial coupling and non-spatial coupling. This is likely one of the most important new experiments.

## Work Package 3: Sensitivity to `z`

### Purpose

Explain how `z` affects performance and avoid the impression that it is a hidden magic parameter.

### Design

Fix representative values of `d`, `l`, and `k`, then sweep `z`.

Suggested fixed settings:

- `k = 2`
- `l = 6`
- `d` in `{10,000, 100,000, 1,000,000}` if feasible

Suggested `z` values:

- `0` as the no-coupling or near-no-coupling reference when applicable
- `1`, `2`, `4`, `8`, `16`, `25`, `32`, `64`
- values around the heuristic `M^(1/3) / 3`

### Metrics

Record:

- success rate
- communication cost
- encode/decode time
- `RangeLength = M / (z + 1)`

### Expected Output

Use a plot where the x-axis is `z` and the y-axis is either success rate or minimum `C / d`. The paper text should emphasize the broad range of acceptable `z` values, if the data supports that.

## Work Package 4: Additional Baselines

### Purpose

Strengthen the comparison against related practical set reconciliation methods.

### Candidate Baselines

Possible candidates from the TODO list:

- Parity Bitmap Sketch, from "Space- and Computationally-Efficient Set Reconciliation via Parity Bitmap Sketch".
- Practical Rateless Set Reconciliation.

### Recommended Strategy

Do not reimplement these methods from scratch unless necessary. First check whether public implementations exist and whether their licenses allow experimental use.

For each candidate:

1. Find an implementation or artifact.
2. Identify its expected input format and assumptions.
3. Match the same synthetic dataset generator used for XYZ-v2 where possible.
4. Measure the same metrics: communication, encode time, decode time, and success rate.
5. Clearly document any mismatch in assumptions.

### Risk

This package may be time-consuming because external code often has build issues or incompatible assumptions. Treat it as high value but not blocking for the core XYZ-Sketch experiment refresh.

## Work Package 5: Application-Oriented Experiment

This is optional and should only be started after the core experiments are complete.

### Candidate: Git Repository Snapshot Reconciliation

The goal is to create a realistic-looking workload where two snapshots contain mostly shared object IDs and a small number of differences.

Possible approach:

1. Pick one or more public Git repositories.
2. Extract commit, tree, or blob object IDs from two nearby snapshots.
3. Map object IDs into 32-bit field elements in a deterministic way.
4. Run XYZ-v2, IBLT, and any available baselines on these sets.
5. Report communication and runtime versus the actual symmetric difference size.

### Caveat

This experiment is meant to demonstrate practicality, not to replace the controlled synthetic experiments. It should be presented as a case study.

## Harness and Output Recommendations

Before running large experiments, add a small experiment harness around the existing code.

Recommended output format:

```text
algorithm,d,l,k,M,z,mode,trials,successes,success_rate,encode_avg_s,decode_avg_s,encode_median_s,decode_median_s,bits,C_over_d,seed
```

Use deterministic seeds for reproducibility, but allow the seed to vary across trials.

Recommended artifacts:

- Raw CSV or JSONL results.
- A short README explaining how each experiment was run.
- Scripts for producing tables and plots.
- Final paper-ready tables/figures.

## Suggested Priority Order

1. Build the structured experiment harness.
2. Run the `d/l/k` sweep for XYZ-v2.
3. Run spatial coupling vs non-spatial coupling.
4. Run the `z` sensitivity study.
5. Add external baselines if suitable implementations are available.
6. Add the optional application-oriented experiment.
7. Rewrite the experiment section using the new results.

## Notes for Rewriting the Experiment Section

The rewritten section should answer these questions clearly:

- How close does XYZ-v2 get to the theoretical communication target?
- How much does spatial coupling help?
- How sensitive is the method to `z`?
- What are the runtime costs compared with IBLT, minisketch, and any new baselines?
- Which parameter settings should practitioners use?
- Where does XYZ-Sketch win, and where are the tradeoffs?
