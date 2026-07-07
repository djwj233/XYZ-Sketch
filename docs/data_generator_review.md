# Shared Dataset Generator Review

This document reviews which experiment scripts should move from benchmark-internal deterministic data generation to shared paired datasets from `tests/dataset_generator.py`.

It started as a planning document. The first migration patch has now implemented shared-dataset support for `tests/test_spatial.py` and `tests/test_circular_a.py`; the remaining scripts are still tracked below.

## Problem

Several XYZ threshold-style experiments still call `tests/benchmarks/xyz_v2_bench.cpp` without `--dataset`.

In that mode, `xyz_v2_bench` generates data internally from:

```text
d, ca, cb, seed, trial index
```

This is deterministic and good enough for smoke tests or single-algorithm exploratory scans. However, it is not ideal for strict paper-facing comparisons where different parameters or algorithms should be evaluated on exactly the same Alice/Bob sets.

The stricter policy should be:

```text
one workload/trial -> one shared dataset file -> all compared configurations read that exact file
```

This reduces noise and makes paired comparisons cleaner.

## Current Shared-Dataset Infrastructure

The reusable dataset module already exists:

```text
tests/dataset_generator.py
```

It provides:

```python
DatasetConfig
choose_set_sizes(...)
make_dataset(...)
write_dataset(...)
load_dataset(...)
prepare_datasets(...)
```

The benchmark file format is:

```text
# compare-dataset-v1 ca=<...> cb=<...> d=<...> seed=<...> trial=<...>
A <count>
...
B <count>
...
```

Most benchmark adapters already accept `--dataset`, including:

```text
tests/benchmarks/xyz_v2_bench.cpp
tests/benchmarks/iblt_bench.cpp
tests/benchmarks/iblt_sc_bench.cpp
tests/benchmarks/xyz_v1_bench.cpp
tests/benchmarks/iblt_cpp_bench.cpp
tests/benchmarks/minisketch_bench.cpp
tests/benchmarks/cpisync_bench.cpp
tests/benchmarks/negentropy_bench.cpp
tests/benchmarks/riblt_bench.go
```

So this is mostly a Python orchestration issue, not a C++ benchmark capability issue.

## Current Script Status

### Already Uses Shared Datasets

```text
tests/test_compare_basic.py
tests/test_iblt_spatial.py
tests/test_spatial.py with --shared-datasets
tests/test_circular_a.py with --shared-datasets
```

These scripts are the best references for migration.

`test_compare_basic.py`:

- generates one dataset per workload/trial;
- sends the same dataset to every selected algorithm;
- aggregates per-dataset trial rows.

`test_iblt_spatial.py`:

- uses `DatasetConfig` and `prepare_datasets`;
- passes `--dataset` to `iblt_sc_bench`;
- compares IBLT variants on paired datasets.

`test_spatial.py`:

- keeps the old internal generator as the default fast path;
- adds `--shared-datasets`, `--dataset-dir`, and `--keep-datasets`;
- reuses one dataset cache across spatial modes, candidate `M` probes, and final validation for the same `(d, ca, cb, seed)`;
- records `dataset_mode = "shared_file"` and `dataset_dir` in raw probes and summaries.

`test_circular_a.py`:

- keeps the old internal generator as the default fast path;
- adds `--shared-datasets`, `--dataset-dir`, and `--keep-datasets`;
- reuses one dataset cache across `a` values, fixed-`M` rows, threshold probes, and final validation for the same `(d, ca, cb, seed)`;
- avoids varying the paired-comparison seed by `a` when `--shared-datasets` is enabled;
- records `dataset_mode = "shared_file"` and `dataset_dir` in raw rows and summaries.

### Still Mainly Uses Internal Generator

```text
tests/test_find_best_m.py
tests/test_z.py
tests/test_xyz_sharp_threshold.py
tests/test_dlk.py
```

These scripts import `choose_set_sizes`, but they do not generate dataset files for the benchmark probes. They rely on the benchmark's internal generation and emit `dataset_mode = "internal_generator"`.

`test_spatial.py` and `test_circular_a.py` are no longer in this bucket when `--shared-datasets` is enabled, but they intentionally keep the old default for fast smoke runs.

## Which Tests Should Be Migrated First?

### Priority 1: `tests/test_spatial.py`

Status: implemented behind `--shared-datasets`.

Reason:

- It compares different modes: `random`, `circular`, `naive`, and `spatial`.
- This is exactly where paired datasets matter.
- Without shared datasets, a mode can look slightly better or worse because it saw a different random workload.

Migration goal:

```text
For each d/l/k/seed/trial, generate one shared dataset.
Run every mode and every candidate M against that same trial list.
```

Recommended mode:

```text
default: keep internal generator for compatibility
new option: --shared-datasets
```

This avoids breaking existing quick runs.

### Priority 2: `tests/test_circular_a.py`

Status: implemented behind `--shared-datasets`.

Reason:

- It compares many `a` values.
- The expected differences between nearby `a` values may be small.
- Paired datasets reduce variance and make the "best a" claim more credible.

Migration goal:

```text
For each d/l/k and each trial, reuse the same dataset across all a-values.
```

This should apply to both:

```text
--mode fixed-m
--mode threshold
```

For threshold mode, every candidate `M` for every `a` should use the same probe dataset set for a given `(d,l,k,seed)`.

### Priority 3: `tests/test_xyz_sharp_threshold.py`

Reason:

- Sharp-threshold curves compare adjacent `M` values.
- Paired datasets make the transition curve cleaner.
- A curve should not be noisy simply because each `M` saw a different workload sample.

Migration goal:

```text
For each d/l/k/mode and each trial, reuse the same datasets across all M points.
```

This makes the success-rate jump near the threshold easier to interpret.

### Priority 4: `tests/test_z.py`

Reason:

- This script compares different `z` values at fixed `d/l/k/M`.
- Paired datasets are useful because `z` effects may be subtle.

Migration goal:

```text
For each d/l/k/M and trial, reuse one dataset across all z-values.
```

This should be a modest migration because `xyz_v2_bench` already supports `--dataset`.

### Priority 5: `tests/test_find_best_m.py`

Reason:

- It searches a threshold for one configuration.
- It is less of a cross-configuration comparison than `test_spatial.py` or `test_circular_a.py`.
- Internal deterministic generation is acceptable for quick threshold estimates.

However, if the best-`M` result is used as a paper threshold, it should support shared datasets.

Migration goal:

```text
Add --shared-datasets for final runs.
Keep internal generation as default for speed.
```

### Priority 6: `tests/test_dlk.py`

Reason:

- It is mostly a broad parameter sweep, not a strict paired comparison.
- Internal generation is acceptable for exploratory trends.

Migration is optional unless `test_dlk.py` results are directly used in paper tables.

If migrated, use shared datasets across different `l/k` values only when `d/ca/cb` are the same.

## Recommended Shared-Dataset Policy

Do not remove internal generation. Add a switch:

```text
--shared-datasets
```

When disabled:

```text
dataset_mode = "internal_generator"
```

When enabled:

```text
dataset_mode = "shared_file"
dataset_dir = <path>
dataset_id = <id if available>
```

Recommended additional arguments:

```text
--dataset-dir
--keep-datasets
```

Default dataset directory:

```text
tests/tmp/<experiment>/
```

Output rows should record:

```text
dataset_mode
dataset_dir
dataset_id
```

If adding `dataset_id` everywhere is too much for the first patch, `dataset_dir` plus the existing seed/trial metadata is acceptable.

## Dataset Reuse Rules

The key design choice is what should share the same dataset.

### Across Algorithm or Mode Variants

Always share.

Examples:

```text
random vs circular vs naive
IBLT-uniform vs IBLT-SC
XYZ-v2 vs minisketch vs IBLT
```

### Across Internal Parameter Values

Usually share.

Examples:

```text
different a values
different z values
different M values on a sharp-threshold curve
different capacity factors for the same baseline
```

This gives paired comparisons.

### Across Different d Values

Do not share.

Different `d` means a different workload.

### Across Different ca/cb Values

Do not share unless the dataset generator explicitly defines a nested workload relation. The current generator does not.

## Implementation Pattern

Each migrated script should follow this shape.

### 1. Add CLI Flags

```python
parser.add_argument("--shared-datasets", action="store_true")
parser.add_argument("--dataset-dir", type=Path, default=None)
parser.add_argument("--keep-datasets", action="store_true")
```

### 2. Create Dataset Cache

Use a cache keyed by workload identity:

```python
dataset_cache_key = (d, ca, cb, seed, trials)
```

Then:

```python
DatasetConfig(d=d, ca=ca, cb=cb, seed=seed)
prepare_datasets(config, trials, dataset_dir)
```

### 3. Run One Dataset per Trial

Instead of one benchmark call with:

```text
--trials N
```

call the benchmark once per dataset with:

```text
--trials 1 --dataset <path>
```

Then aggregate the trial rows in Python.

This is more subprocess-heavy, but it is clearer and fairer.

### 4. Preserve Old Fast Path

If `--shared-datasets` is not set, keep the old behavior:

```text
one benchmark call with --trials N and no --dataset
```

This is useful for quick smoke tests.

## Aggregation Rules

Use the fixed rule from `test_compare_basic.py`:

```text
valid trial statuses = {"ok", "failed_decode"}
successes = sum(successes)
trials = number of valid rows
status = "ok" for a valid aggregate even if success_rate = 0
```

For infrastructure failures:

```text
unavailable -> record_type = "unavailable"
benchmark_error / parse_error -> record_type = "error"
```

This avoids incorrectly treating low-capacity decode failure as benchmark failure.

## Per-Script Migration Notes

### `tests/test_spatial.py`

Add a dataset cache per:

```text
d, ca, cb, seed
```

Share those datasets across:

```text
mode
candidate M
final validation
```

Recommended first patch:

- add `--shared-datasets`;
- keep existing threshold search;
- change `run_probe()` to either run old one-shot mode or per-dataset mode.

### `tests/test_circular_a.py`

Share datasets across:

```text
a-values
candidate M values
fixed-M rows
threshold final validation
```

Use one workload seed per `(d,l,k)` instead of changing the seed per `a`. Currently the script adds `a_index` into the seed, which is fine for internal generation but not ideal for paired comparison.

When `--shared-datasets` is enabled:

```text
seed should not vary with a
```

### `tests/test_xyz_sharp_threshold.py`

Share datasets across:

```text
M grid points
mode values if comparing random vs spatial
```

This is important because sharp-threshold plots should show the effect of `M`, not trial-sample noise.

### `tests/test_z.py`

Share datasets across:

```text
z values for the same d/l/k/M
```

This should be relatively easy.

### `tests/test_find_best_m.py`

Add shared datasets as an optional final-run mode.

For binary search:

- probe trials can use shared dataset files;
- final validation should definitely use shared dataset files if the result is paper-facing.

### `tests/test_dlk.py`

Optional migration.

If migrated, share datasets across `l/k` only when:

```text
d, ca, cb, seed
```

are identical.

For now, lower priority than the threshold/comparison scripts.

## Output Compatibility

Do not rename existing output files yet. The docs mention names such as:

```text
raw_trials.jsonl
raw_aggregated.jsonl
thresholds.csv
```

but existing scripts use:

```text
raw.jsonl
probes.jsonl
summary.jsonl
summary.csv
summary.md
```

The shared-dataset migration should not also rename outputs. Keep file names stable and only update `dataset_mode` fields.

Renaming output layouts can be a separate cleanup task.

## Acceptance Tests

For each migrated script:

1. Run a dry run.
2. Run a tiny internal-generator smoke and verify output.
3. Run a tiny shared-dataset smoke and verify output.
4. Check that rows include:

   ```text
   dataset_mode = "shared_file"
   dataset_dir
   ```

5. Run strict JSON verification:

   ```bash
   python tests/json_verifier.py <raw-or-summary-jsonl> --strict
   ```

6. For paired comparison scripts, manually inspect that different variants used the same `dataset_dir`.

## Recommended Implementation Order

```text
1. tests/test_spatial.py
2. tests/test_circular_a.py
3. tests/test_xyz_sharp_threshold.py
4. tests/test_z.py
5. tests/test_find_best_m.py
6. tests/test_dlk.py, only if needed
```

This order fixes the experiments where paired comparison matters most.

## Non-Goals for the First Migration

Do not add new workload policies yet:

```text
difference_policy
timestamp_policy
duplicate_policy variants
ordered workloads
Git snapshot workloads
```

Those are separate dataset-generator improvements. The immediate problem is not lack of workload diversity; it is that comparable configurations should read the same generated workload.

## Final Recommendation

The issue is important and should be fixed before running large paper-facing grids.

The first concrete patch should migrate `tests/test_spatial.py` because it compares hash modes directly. The second should migrate `tests/test_circular_a.py` because nearby `a` values need paired datasets to make small differences believable.
