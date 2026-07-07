# Review 001: Experiment System Status and Next Fixes

This document records an assessment of the recent project review. The review is mostly accurate: the repository now has a real experimental framework with many smoke-tested components, but several items are still incomplete or only partially implemented.

## Verdict

The review's main conclusion is correct.

## Status Update

Several items from the original review have since been fixed or partially implemented:

```text
fixed     failed_decode aggregation in tests/test_compare_basic.py
fixed     SetCircularA no longer clamps; CLI remains responsible for validation
done      XYZ-v2 first-stage per-item hash-location deduplication
partial   shared-dataset migration for XYZ threshold-style scripts
partial   external baselines: minisketch and iblt_cpp are real; riblt/negentropy/cpisync remain environment-dependent
open      plotting/table generation
open      application-side experiments
open      complete schema semantics beyond the lightweight verifier
open      optional IBLT-SC hash deduplication
```

For shared datasets, `tests/test_spatial.py` and `tests/test_circular_a.py` now support `--shared-datasets`. Remaining paper-facing candidates include `tests/test_xyz_sharp_threshold.py`, `tests/test_z.py`, `tests/test_find_best_m.py`, and `tests/test_dlk.py` if its results are used in final tables.

The project is not an empty scaffold anymore. It already has:

- unified benchmark row normalization and verification helpers;
- a standalone dataset generator;
- XYZ-v2 `d/l/k`, best-`M`, spatial, `z`, sharp-threshold, and circular-`a` scripts;
- IBLT uniform-vs-spatial experiments;
- shared-dataset comparison infrastructure;
- real `minisketch` and `IBLT_Cplusplus` baselines;
- scaffolded or environment-dependent `riblt`, `negentropy`, and `cpisync` baselines.

However, it is not yet at the full paper-ready state described in the planning documents. The biggest gaps are:

- compare aggregation previously mishandled normal decode failures; this has been fixed;
- external baselines are unevenly available;
- some XYZ threshold-style scripts still use internal generation instead of shared paired datasets;
- per-item hash-location deduplication is implemented for XYZ-v2; IBLT-SC dedup remains optional/open;
- application-side and plotting/figure pipelines are not implemented;
- some planning documents describe richer output layouts or workload parameters than the code currently provides.

## Points That Are Correct

### Unified JSON

Correct. `tests/json_schema.py` and `tests/json_verifier.py` exist and smoke outputs pass strict verification.

Important nuance: this is a practical normalization/verifier layer, not a complete canonical schema system. It validates common fields and metric consistency, but it does not yet fully enforce every algorithm-specific semantic requirement.

### Dataset Generator

Correct. `tests/dataset_generator.py` exists and is used by shared-dataset comparisons.

Important nuance: it currently implements one main workload policy. The more general policies mentioned in docs, such as `difference_policy`, `timestamp_policy`, and multiple workload families, are not fully parameterized yet.

### Core XYZ and IBLT Experiments

Correct. These scripts exist and have working smoke paths:

```text
tests/test_dlk.py
tests/test_find_best_m.py
tests/test_spatial.py
tests/test_z.py
tests/test_xyz_sharp_threshold.py
tests/test_iblt_spatial.py
tests/test_circular_a.py
```

The important caveat is that some XYZ threshold-style experiments still use `xyz_v2_bench`'s internal deterministic generator. That is acceptable for smoke testing and single-algorithm scans, but it is weaker than a strict paired shared-dataset comparison. `test_spatial.py` and `test_circular_a.py` now support shared paired datasets.

### Circular `a`

Correct. `circular_a` is now exposed in:

```text
XYZ-v2/hash.cpp
XYZ-v2/hash.h
tests/benchmarks/xyz_v2_bench.cpp
tests/test_circular_a.py
```

The current implementation keeps the default behavior equivalent to the old hard-coded `RangeLength / 3` rule by using:

```text
floor(circular_a * RangeLength)
```

with default:

```text
circular_a = 1/3
```

The review is also correct that only smoke-level results exist so far. The main grid over representative `d` values has not been run.

### External Baselines

Correct.

Current status:

```text
minisketch       real on the current environment
iblt_cpp         real
riblt            real wrapper exists, but unavailable here because Go is missing
negentropy       real code path exists, but unavailable here because OpenSSL headers/libs are missing
cpisync          optional; currently mostly unavailable on Windows
```

This should be reflected in docs. Older text that still says `minisketch` is merely scaffolded is now stale.

### Hash Deduplication

The original review was correct when written, but this is now partially fixed. XYZ-v2 now supports:

```text
--dedup-hashes true|false
```

and uses a shared per-item location helper in `Update()`, `Extract()`, and `PureCellVerify()`. This is still open for IBLT-SC if that ablation becomes necessary.

### Plotting and Application-Side Experiments

Correct. Outputs are mostly JSON/CSV/Markdown summaries. There is no paper-ready plotting/table-generation pipeline yet.

The Git repository snapshot reconciliation idea is also not implemented.

## Fixed Bug: Compare Aggregation

The review correctly identified a real aggregation bug in `tests/test_compare_basic.py`. This has since been fixed.

Current behavior:

```python
ok_rows = [row for row in trial_rows if row.get("status") == "ok"]
```

Then aggregation uses only `ok_rows`.

Problem:

- A low-capacity decode failure is a valid trial outcome.
- Wrappers such as `minisketch`, `riblt`, or `negentropy` may emit `status = "failed_decode"` while still producing a valid benchmark row.
- Excluding those rows biases success rates upward.
- If every trial fails decode, the aggregate can become `benchmark_error`, which is semantically wrong.

Expected behavior:

- Trial-level `failed_decode` should count as a completed trial with `successes = 0`.
- Aggregate rows should usually remain `status = "ok"` if the benchmark process ran normally.
- `status = "benchmark_error"`, `parse_error`, and `unavailable` should remain infrastructure/build/runtime statuses.

Recommended fix:

```text
valid_trial_statuses = {"ok", "failed_decode"}
valid_rows = rows whose status is in valid_trial_statuses
successes = sum(row.successes for valid_rows)
trials = len(valid_rows)
success_rate = successes / trials
aggregate status = "ok"
```

If all rows are `unavailable`, keep `record_type = "unavailable"`.

If rows are process errors only, keep `record_type = "error"`.

If there is a mix of valid trials and process errors, aggregate valid trials but record:

```text
attempted_trials
completed_trials
error_trials
```

as optional diagnostic fields.

Current status: implemented. `tests/test_compare_basic.py` now treats `{"ok", "failed_decode"}` as valid completed trial statuses, aggregates successes over valid rows, and records attempted/completed/error trial counts.

## Minor Correction: Circular `a` Rejection vs Clamp

The review is right that the CLI and library-level behavior differ:

- `xyz_v2_bench` rejects invalid `--circular-a` values.
- `SpatialCoupling::SetCircularA()` clamps values into `[0, 1)`.

Current status: fixed. `SpatialCoupling::SetCircularA()` now assigns the provided value directly, while `xyz_v2_bench` continues to reject invalid user input.

Previous recommended change:

- Keep CLI validation as-is.
- Prefer making the library setter deterministic and explicit. Since this is plain C++ without exceptions elsewhere, a reasonable option is:

```cpp
void SetCircularA(double value) {
    CircularA = value;
}
```

and require callers to validate.

Alternatively, keep clamping but document it clearly. The cleaner experiment semantics are to reject invalid values at every public boundary that accepts user input.

This is no longer an open issue unless another public entry point starts accepting unvalidated `circular_a` values.

## Minor Correction: Chinese Document Encoding

The review reports that `docs/test_circular_a.zh-CN.md` appears garbled. In the current workspace, reading it as UTF-8 works correctly.

Likely explanation:

- the file was viewed with a non-UTF-8 default encoding;
- or the reviewer saw an older version before the latest write.

Recommended action:

- keep all docs as UTF-8 without relying on terminal default code pages;
- if garbling reappears, rewrite the file as UTF-8 without BOM.

No code change is currently required unless the issue is reproduced.

## Recommended Priority Order

### Priority 1: Keep Compare Aggregation Covered

The aggregation fix is implemented. Keep a smoke command or regression test that ensures normal `failed_decode` trial rows are included in aggregation.

Acceptance test:

- Run a deliberately low-capacity baseline, for example `minisketch` or `iblt` with capacity below the difference size.
- The output should be an aggregate row with:

```text
status = "ok"
success_rate < 1
trials = requested trial count
```

not `benchmark_error`.

### Priority 2: Update Baseline Status Docs

Update external-baseline docs and todo-list status:

```text
minisketch: real on current environment
iblt_cpp: real
riblt: wrapper implemented, needs Go toolchain
negentropy: real code path implemented, needs OpenSSL
cpisync: optional / platform-sensitive
```

This prevents future confusion about what is scaffolded versus implemented-but-unavailable.

### Priority 3: Decide Shared-Dataset Policy for XYZ Threshold Scripts

For paper-facing results, decide whether to retrofit shared datasets into:

```text
tests/test_find_best_m.py
tests/test_spatial.py
tests/test_z.py
tests/test_xyz_sharp_threshold.py
tests/test_circular_a.py
```

Recommended policy:

- keep internal generator for quick smoke and exploratory runs;
- add `--shared-datasets` or similar for final paired comparisons.

### Priority 4: Run Missing Main Grids

Run or schedule non-smoke grids:

```text
circular_a main threshold grid
XYZ sharp-threshold representative grid
IBLT uniform/SC representative grid
external baseline compare where dependencies are available
```

### Priority 5: Add Plot/Table Pipeline

Add plotting scripts for:

```text
success_rate vs M
success_rate vs circular_a
best_C_over_d by algorithm
threshold confidence intervals
```

Output should go under:

```text
tests/results/<experiment>/figures/
```

### Priority 6: Extend Hash Deduplication Experiments

XYZ-v2 now has:

```text
--dedup-hashes true|false
```

The remaining work is to run the planned comparison and optionally add the same idea to IBLT-SC.

### Priority 7: Application-Side Experiment

Only after the core paper figures are stable, add a Git snapshot or similar application workload.

## Suggested Immediate Patch List

1. Keep or add a smoke command that intentionally produces `failed_decode` rows and verifies aggregation.
2. Update external baseline status in docs.
3. Add or maintain notes that circular-a and dedup currently have smoke-level results, while main grids still need to be run.
4. Continue shared-dataset migration for remaining paper-facing XYZ scripts.

## Final Assessment

The review is useful and mostly accurate. The best next move is not to start another new experiment, but to harden the comparison pipeline:

```text
keep aggregation regression coverage -> update docs -> run main grids -> add plotting
```

That order improves correctness before spending compute time on larger experiments.
