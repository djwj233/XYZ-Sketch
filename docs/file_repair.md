# Documentation Drift Repair Plan

This document plans how to repair documentation drift in the experiment system.

It does not change implementation behavior. The goal is to make the docs clearly distinguish:

- current implemented behavior;
- planned target behavior;
- optional future cleanup.

## Problem

Some documentation still describes older project states or ideal future layouts as if they were current facts.

Examples:

- `docs/review_001.md` and `docs/review_001.zh-CN.md` still describe the `failed_decode` aggregation bug as a current issue, but the code has already been fixed.
- Some docs mention target output files such as:

```text
raw_trials.jsonl
raw_aggregated.jsonl
thresholds.csv
```

while current scripts often emit:

```text
raw.jsonl
probes.jsonl
summary.jsonl
raw.csv
summary.csv
summary.md
run_config.json
```

- Some docs call the JSON work a unified schema, while the current implementation is more accurately a lightweight normalization and verifier layer.
- Some completed work is still listed as a TODO, such as the first-stage XYZ-v2 hash-location deduplication.

This is not unusual in a fast-moving experiment repo, but it can mislead future work and reviews.

## Repair Principles

### 1. Do Not Rewrite History

Review documents can keep the original review context, but they should add status updates.

Use labels such as:

```text
Status: fixed
Status: partially implemented
Status: still open
Status: planned target, not current output
```

This is better than silently deleting old concerns.

### 2. Separate Current Layout From Target Layout

When a doc proposes an ideal layout, mark it explicitly:

```text
Target layout
```

When a doc describes actual script output, mark it:

```text
Current output
```

Do not mix the two.

### 3. Prefer Small Status Patches

Do not refactor all docs at once. Update the documents that are most likely to mislead current work first.

### 4. Keep English and zh-CN Documents in Sync

Every repaired English doc should have the corresponding zh-CN doc updated in the same patch when a translation exists.

## Documents To Repair First

### `docs/review_001.md` and `docs/review_001.zh-CN.md`

Problem:

- Still describes the `failed_decode` aggregation bug as a current highest-priority fix.
- Still says per-item hash-location deduplication is not implemented.
- Still says many shared-dataset migrations are missing without reflecting that `test_spatial.py` and `test_circular_a.py` now support shared datasets.

Repair:

- Add a short "Status Update" section near the top.
- Mark `failed_decode` aggregation as fixed.
- Mark `SetCircularA` clamp/reject cleanup as fixed if applicable.
- Mark XYZ-v2 hash dedup first stage as implemented.
- Mark shared-dataset migration as partially implemented:

```text
implemented: test_spatial.py, test_circular_a.py
remaining: test_xyz_sharp_threshold.py, test_z.py, test_find_best_m.py, test_dlk.py if paper-facing
```

- Keep open items:

```text
external baseline environment availability
plotting/table generation
application-side experiments
full schema semantics
IBLT-SC hash dedup if needed
```

### `docs/todo-list.md` and `docs/todo-list.zh-CN.md`

Problem:

- Some priorities list tasks that are now partially or fully complete.
- The output layout examples include target names that do not match many current scripts.

Repair:

- Add status markers to priority items:

```text
[done]
[partial]
[open]
```

- Update the priority summary to separate completed infrastructure from remaining scientific experiments.
- For output layout sections, replace ambiguous "Expected output" with either:

```text
Current output
```

or:

```text
Target output layout
```

- Update hash dedup priority:

```text
XYZ-v2 first stage done; IBLT-SC optional/open.
```

### `docs/json_verifier.md` and `docs/json_verifier.zh-CN.md`

Problem:

- The docs describe a more complete canonical schema vision.
- The implementation is currently `json_schema.py` normalization plus `json_verifier.py --strict` common-field checks.

Repair:

- Add a "Current Implementation" section:

```text
json_schema.py normalizes common rows.
json_verifier.py checks common fields, numeric consistency, known record types, and confidence interval sanity.
It does not yet fully enforce algorithm-specific fields, communication-model caveats, or all unavailable semantics.
```

- Add a "Next Verifier Enhancements" section:

```text
status enum
dataset_mode enum
unavailable requires unavailable_reason
failed_decode is a valid trial outcome
algorithm/implementation compatibility checks
optional communication-model fields
```

### `docs/data_generator_review.md` and `docs/data_generator_review.zh-CN.md`

Problem:

- This doc already has some implementation status updates.
- It should remain the canonical source for shared-dataset migration status.

Repair:

- Confirm that `test_spatial.py` and `test_circular_a.py` are marked implemented.
- Keep the remaining migration list explicit.
- Add a reminder that shared-dataset mode is optional and internal generation remains the default fast path.

### `docs/test_compare_basic.md` and `docs/test_compare_basic.zh-CN.md`

Problem:

- Some external baseline status text is stale, especially around `minisketch`.

Repair:

- Mark `minisketch` and `iblt_cpp` as real wrappers.
- Mark `riblt`, `negentropy`, and `cpisync` as implemented/optional but environment-dependent where appropriate.
- Ensure `failed_decode` is described as a valid trial outcome, not an infrastructure error.

## Output Layout Repair

Create a small canonical reference document:

```text
docs/results_layout.md
docs/results_layout.zh-CN.md
```

It should list current output conventions:

### Fixed Parameter Scans

Used by scripts such as:

```text
tests/test_dlk.py
tests/test_z.py
tests/test_circular_a.py --mode fixed-m
```

Current output:

```text
raw.jsonl
raw.csv
summary.md
run_config.json when available
errors.log when available
```

### Threshold / Search Experiments

Used by scripts such as:

```text
tests/test_find_best_m.py
tests/test_spatial.py
tests/test_iblt_spatial.py
tests/test_circular_a.py --mode threshold
```

Current output:

```text
probes.jsonl or raw.jsonl
summary.jsonl
summary.csv when available
summary.md when available
run_config.json when available
errors.log when available
```

### Compare Experiments

Used by:

```text
tests/test_compare_basic.py
```

Current output:

```text
raw.jsonl
raw.csv
summary.md
run_config.json
errors.log when needed
```

### Future Target Layout

If desired, keep this as a future cleanup target:

```text
raw_trials.jsonl
raw_aggregated.jsonl
summary.jsonl
summary.csv
summary.md
run_config.json
errors.log
```

But mark it as target/future, not current behavior.

## JSON Verifier Repair

This planning item should not immediately require a full schema rewrite.

Recommended near-term implementation:

1. Keep `tests/json_schema.py` as the normalization helper.
2. Keep `tests/json_verifier.py --strict` backward-compatible for current smoke outputs.
3. Add semantic checks incrementally:

```text
known status values
known dataset_mode values
unavailable rows should include unavailable_reason
failed_decode is accepted as a valid trial status
success_rate must equal successes/trials when trials > 0
record_type=unavailable should pair with status=unavailable
record_type=error should pair with error-like status
```

4. Add warnings or optional strictness before making new rules hard failures for all historical outputs.

## Suggested Repair Order

1. Update `review_001` English and zh-CN status.
2. Update `todo-list` English and zh-CN status.
3. Add `results_layout.md` and `results_layout.zh-CN.md`.
4. Update JSON verifier docs to describe current lightweight implementation honestly.
5. Update compare/basic docs for external baseline current status.
6. Add optional verifier semantic checks in code.
7. Run a docs consistency scan with `rg`.

## Consistency Scan

After repairs, scan for stale phrases:

```powershell
rg -n "failed_decode aggregation|not implemented|尚未实现|raw_trials.jsonl|raw_aggregated.jsonl|thresholds.csv|scaffolded" docs
```

Not every hit is wrong. For each hit, ensure the text clearly says whether it is:

```text
historical context
current status
future target
open TODO
```

## Acceptance Criteria

The repair is complete when:

- `review_001` no longer presents fixed bugs as current blockers.
- `todo-list` distinguishes done, partial, and open tasks.
- result file names are documented as current output versus future target layout.
- JSON docs accurately describe the current lightweight verifier.
- English and zh-CN documents agree on task status.
- a reader can tell what to implement next without rereading the entire git history.

