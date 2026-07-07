# Experimental TODO List

This document collects the next experimental and engineering tasks for the XYZ-Sketch project. It is a planning checklist only; each item should later be expanded into a concrete script or benchmark design before implementation.

## Priority Review

The original list put statistical threshold search first. After reviewing the current codebase, that should be adjusted. The real dependency order is:

```text
Priority 1: Unified JSON schema and standalone dataset generator
Priority 2: Statistical threshold search with confidence intervals
Priority 3: Sharp-threshold experiments
Priority 4: Algorithm-family comparison, including IBLT-uniform/SC and XYZ-uniform/SC
Priority 5: Complete external baseline integrations
Priority 6: Per-item hash-location deduplication
Priority 7: Circular trick parameter a
```

Reason: confidence intervals, sharp-threshold plots, and cross-algorithm comparisons all depend on consistent trial records and shared datasets. Therefore the infrastructure work should happen first, even though the statistical experiments are the most important scientific deliverable.

The detailed sections below preserve much of the previous layout. Treat this review section and the final execution order as the canonical priority order.

## Current Status Snapshot

Use these status labels while reading the older task list:

```text
[done]     implemented and smoke-tested
[partial]  implemented for some scripts/baselines, but not complete
[open]     still needs implementation or full experiment runs
```

Current snapshot:

```text
[done]     benchmark.v1 normalization helper and lightweight strict verifier
[done]     standalone dataset_generator.py
[done]     failed_decode aggregation fix in test_compare_basic.py
[done]     XYZ-v2 first-stage --dedup-hashes support
[partial]  shared dataset migration: done for test_spatial.py and test_circular_a.py
[partial]  external baselines: minisketch and iblt_cpp real; riblt/negentropy/cpisync environment-dependent
[partial]  confidence intervals and threshold rollups exist in several scripts
[open]     paper-ready plotting/table generation
[open]     application-side workload experiments
[open]     complete canonical schema semantics beyond the lightweight verifier
[open]     optional IBLT-SC hash-location deduplication
```

## Priority 2: Statistical Threshold Search

### Confidence Intervals for Target Success Rates

Goal: report the smallest communication/capacity parameter that reaches a target success rate, together with uncertainty.

Tasks:

- Add confidence intervals to threshold-search results.
- For a target success rate such as `0.99`, report the smallest `M` whose estimated success rate meets the target.
- Report the confidence interval of the success rate at that `M`.
- Also report uncertainty for the inferred threshold, for example:
  - the smallest `M` whose lower confidence bound is at least `0.99`;
  - the smallest `M` whose point estimate is at least `0.99`;
  - the range of `M` values whose confidence intervals overlap the target.

Suggested method:

- Use binomial confidence intervals for success/failure trials.
- Prefer Wilson or Clopper-Pearson intervals over a plain normal approximation.
- Store `trials`, `successes`, `success_rate`, `ci_low`, `ci_high`, `target_success_rate`, and `threshold_policy`.

Candidate scripts:

```text
tests/test_find_best_m.py
tests/test_spatial.py
tests/test_threshold.py
```

Target output from the original plan. Current scripts may instead use `probes.jsonl`, `raw.jsonl`, and `summary.jsonl`; see `docs/results_layout.md` for current conventions:

```text
tests/results/<experiment>/raw.jsonl
tests/results/<experiment>/thresholds.csv
tests/results/<experiment>/summary.md
```

## Priority 3: Sharp Threshold Experiment

Goal: experimentally demonstrate the sharp threshold phenomenon: near the critical `M`, a small increase in `M` should cause a rapid transition from mostly failing to mostly succeeding.

Tasks:

- For representative `(d, l, k)` settings, scan `M` densely around the empirical threshold.
- Use enough trials per `M` to make the transition visible.
- Plot or tabulate success rate versus `M` and `C/d`.
- Record confidence intervals for each success-rate point.
- Compare the sharpness across:
  - uniform placement;
  - spatial coupling;
  - different `k`;
  - different `d`.

Suggested parameter choices:

```text
d in {1000, 3000, 10000}
l = 6
k in {2, 3}
trials >= 100 near the threshold
M grid: dense around the estimated threshold
```

Expected result:

- A curve showing a phase-transition-like jump in success rate.
- A table identifying approximate threshold `M` and `C/d`.
- A short interpretation explaining that this is empirical evidence, not a proof of the theoretical threshold.

## Priority 1A: Unified JSON Benchmark Architecture

Goal: make every algorithm and experiment emit the same machine-readable JSON format so results can be managed, compared, and plotted consistently.

Tasks:

- Define one canonical JSON schema for per-trial rows and aggregated rows.
- Make all benchmark wrappers emit that schema or a compatible subset.
- Separate these concepts clearly:
  - workload metadata;
  - algorithm parameters;
  - dataset generation parameters;
  - per-trial result;
  - aggregated statistics;
  - build/runtime status.
- Ensure unavailable baselines use `status = "unavailable"` rather than crashing the whole run.

Recommended common fields:

```text
schema_version
experiment
algorithm
variant
implementation
d
ca
cb
seed
trial
trials
dataset_id
dataset_path
dataset_mode
success
successes
success_rate
ci_low
ci_high
bits
bytes
bits_per_difference
bit_C_over_d
encode_s
decode_s
reconcile_s
status
unavailable_reason
error
```

Target output layout. Current scripts may instead use `raw.jsonl`, `probes.jsonl`, `summary.jsonl`, `raw.csv`, `summary.csv`, and `summary.md`; see `docs/results_layout.md` for current conventions:

```text
tests/results/<experiment>/raw_trials.jsonl
tests/results/<experiment>/raw_aggregated.jsonl
tests/results/<experiment>/summary.md
tests/results/<experiment>/run_config.json
tests/results/<experiment>/errors.log
```

## Priority 4: Algorithm Family Comparison

Goal: compare uniform placement and spatial coupling variants within IBLT-like and XYZ-like families.

Algorithms to include:

```text
IBLT-uniform
IBLT-SC
XYZ-uniform
XYZ-SC
```

Additional baselines:

```text
local IBLT
external IBLT_Cplusplus
minisketch
CPISync
RIBLT
Negentropy
XYZ-v1
XYZ-v2
```

Tasks:

- Define exactly what `uniform` and `SC` mean for each algorithm family.
- Ensure all variants read the same generated dataset.
- Use comparable capacity parameters where possible.
- For fixed-parameter runs, report success/time/communication.
- For threshold runs, report the minimum communication needed to reach a target success rate.

Important caveat:

- Some baselines have different interaction models. RIBLT is rateless, CPISync and Negentropy are interactive, and Minisketch is a fixed sketch. The summary should group them carefully and document the communication accounting.

## Priority 1B: Standalone Dataset Generator

Goal: move dataset generation into a reusable module so all experiments use exactly the same workload definitions.

Tasks:

- Create a standalone dataset generator module.
- Reuse it from:
  - `test_compare_basic.py`;
  - threshold experiments;
  - spatial-coupling experiments;
  - future plotting or reproducibility scripts.
- Make dataset generation configurable.

Candidate file:

```text
tests/dataset_generator.py
```

Suggested parameters:

```text
d
ca
cb
seed
trial
set_size_scale
max_set_size
value_modulus
value_bits
overlap_policy
difference_policy
shuffle_policy
timestamp_policy
duplicate_policy
```

Suggested APIs:

```python
def choose_set_sizes(d: int, scale: int, max_set_size: int) -> tuple[int, int]:
    ...

def make_dataset(config: DatasetConfig, trial: int) -> Dataset:
    ...

def write_dataset(path: Path, dataset: Dataset) -> None:
    ...

def load_dataset(path: Path) -> Dataset:
    ...

def dataset_id(config: DatasetConfig, trial: int) -> str:
    ...
```

Expected benefit:

- All algorithms are compared on the same input sets.
- Dataset provenance is easier to audit.
- Future experiments can vary workload structure without duplicating generator logic.

## Priority 5: Complete External Baseline Integrations

Goal: turn scaffolded baseline adapters into real measured baselines where feasible.

Current status:

```text
xyz_v1      real wrapper exists
xyz_v2      real wrapper exists
iblt        real wrapper exists
iblt_cpp    real wrapper exists
cpisync     scaffolded/unavailable on current Windows setup
minisketch  real wrapper; builds and runs on the current environment
riblt       real wrapper path exists; unavailable here until Go is installed
negentropy  real code path exists; unavailable here until OpenSSL headers/libs are installed
```

Tasks:

- Keep `minisketch` in the real baseline set and use it for failed-decode aggregation smoke tests.
- Run `riblt` through the local Go wrapper/module without modifying `external/riblt` on machines with Go installed.
- Run `negentropy` through the C++ implementation on machines with OpenSSL headers/libs installed.
- Keep `cpisync` optional because it depends on POSIX-style process/communication support and external libraries.
- Preserve `status = "unavailable"` fallback for unsupported platforms.

Why this is Priority 5 rather than Priority 1:

- Baselines are important for the final comparison, but the core XYZ/IBLT threshold experiments can proceed before every external baseline is fully enabled.
- The unified JSON and dataset generator work will make baseline integration cleaner.

## Priority 6: Deduplicate Hash Locations Before Update

Idea: before updating a sketch, manually deduplicate the locations

```text
h_1(x), ..., h_k(x)
```

for the same item `x`.

Motivation:

- In theory, this may not change the model significantly when collisions among the `k` choices are rare.
- In proofs or explanations, deduplicating per-item update locations may make the update rule cleaner because each item updates a set of distinct cells.

Tasks:

- Add an optional implementation flag:

```text
--dedup-hashes true|false
```

- Compare success rate and communication with and without deduplication.
- Measure whether deduplication changes behavior for small `M` or large `k`.
- Keep the default behavior unchanged until results confirm it is safe.

Suggested experiment:

```text
d in {1000, 3000, 10000}
k in {2, 3, 4}
modes in {uniform, spatial}
dedup_hashes in {false, true}
```

Expected result:

- If the curves are indistinguishable, use deduplication only where it simplifies explanation.
- If the curves differ near threshold, document the difference and keep both modes explicit.

## Priority 7: Circular Trick Parameter `a`

Goal: study when the circularized placement parameter `a` is optimal.

Background:

The circular trick uses a placement rule where the coupled range can wrap from the last cell to the first. The paper describes functions equivalent to:

```text
g0: U -> [0, 2 + a)
g_i: U -> [0, 1)
a in [0, 1)
```

and maps each item using a circularized expression of the form:

```text
h_i(x) = 1 + (g0(x) + g_i(x)) mod M
```

with the exact scaling depending on the implementation's `M`, `z`, and coupled-window definition.

Tasks:

- Expose `a` as an explicit benchmark parameter.
- Scan `a` values in `[0, 1)`.
- Compare success rate and required `M`.
- Focus first on the case where circular coupling is expected to help, especially `k = 2`.
- Treat `k >= 3` circular results as diagnostic unless the data show otherwise.

Suggested grid:

```text
a in {0.0, 0.1, 0.2, ..., 0.9}
d in {1000, 3000, 10000}
l = 6
k in {2, 3}
target_success_rate in {0.95, 0.99}
```

Expected output:

```text
tests/results/circular_a/raw.jsonl
tests/results/circular_a/thresholds.csv
tests/results/circular_a/summary.md
```

Interpretation questions:

- Which `a` minimizes the required `M`?
- Does the optimal `a` depend on `d`?
- Does the optimal `a` depend on `k`?
- Is `a = 0` or a near-boundary value enough in practice?

## Suggested Execution Order

1. Define the unified JSON schema.
2. Split out `tests/dataset_generator.py`.
3. Add confidence intervals to existing threshold-search scripts.
4. Run sharp-threshold experiments for XYZ-uniform and XYZ-SC.
5. Add IBLT-uniform and IBLT-SC comparison.
6. Complete external baseline integrations as needed for the paper.
7. Test per-item hash-location deduplication.
8. Study circular parameter `a` if time remains or if the proof narrative needs it.

