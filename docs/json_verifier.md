# JSON Schema and Verifier Plan

This document plans a unified JSON format and verifier for all benchmark and experiment outputs. No code is implemented here.

## Goals

The project currently has multiple JSONL-producing scripts and wrappers:

```text
tests/test_compare_basic.py
tests/test_dlk.py
tests/test_spatial.py
tests/test_z.py
tests/test_find_best_m.py
tests/benchmarks/*_bench.cpp
tests/benchmarks/riblt_bench.go
```

They all emit useful JSON, but the fields are not yet managed by a single schema. Some rows are aggregated summaries, some are probe rows, some are benchmark rows, and some are unavailable-baseline rows.

The goal is to introduce:

```text
schema_version = "benchmark.v1"
one canonical row format
one verifier script
one migration path for every existing script
```

The first implementation should be practical rather than over-engineered. It should normalize the existing flat JSON style, while leaving room for more structured records later.

## Design Principles

1. Every JSONL line must be independently valid.
2. Every row must say what kind of record it is.
3. Every row must contain enough workload and parameter metadata to be interpreted without reading the summary.
4. All failures or unavailable baselines must be represented as rows, not as missing data.
5. Algorithm-specific fields are allowed, but common fields must have stable names and types.
6. The verifier should warn on unknown optional fields but fail on missing required fields.
7. The schema should support both per-trial rows and aggregated rows.

## Row Types

Use `record_type` to distinguish row semantics:

```text
trial
aggregate
probe
threshold
unavailable
error
```

Recommended usage:

- `trial`: one algorithm on one dataset/trial.
- `aggregate`: multiple trials summarized into one row.
- `probe`: a threshold-search probe at a candidate `M` or capacity.
- `threshold`: final threshold-search result.
- `unavailable`: adapter or dependency unavailable.
- `error`: benchmark failed, parse failed, or command failed.

In the current scripts, most output rows are already aggregated. Those should use:

```text
record_type = "aggregate"
```

Rows from `test_find_best_m.py` and `test_spatial.py` probes should use:

```text
record_type = "probe"
```

Final threshold summaries should use:

```text
record_type = "threshold"
```

## Canonical Flat Schema v1

The first schema should stay flat because current C++ wrappers already print flat JSON. This reduces migration cost.

Required fields for every row:

```text
schema_version: string
record_type: string
experiment: string
algorithm: string
variant: string
implementation: string
status: string
```

Required workload fields for benchmark-like rows:

```text
d: integer
ca: integer
cb: integer
seed: integer
dataset_mode: string
```

Required trial/statistical fields:

```text
trials: integer
successes: integer
success_rate: number
```

Required communication fields:

```text
bits: number
bits_per_difference: number
bit_C_over_d: number
```

Required timing fields:

```text
encode_avg_s: number
decode_avg_s: number
encode_median_s: number
decode_median_s: number
```

Optional common fields:

```text
trial
trial_seed
dataset_id
dataset_path
dataset_dir
target_success_rate
ci_method
ci_confidence
ci_low
ci_high
threshold_policy
unavailable_reason
error
command
```

Algorithm-specific fields are allowed. Examples:

```text
l
k
M
z
mode
field_C_over_d
RangeLength
capacity_factor
cells
hash_count
cell_bits
mbar
mbar_factor
field_bits
capacity
symbol_factor
symbols_sent
max_symbols
frame_size_limit
timestamp_mode
rounds
```

## Status Values

Allowed `status` values:

```text
ok
unavailable
benchmark_error
parse_error
failed_decode
unresolved
invalid
```

Rules:

- `ok`: benchmark ran and produced a valid row.
- `unavailable`: dependency, platform, or adapter is unavailable.
- `benchmark_error`: benchmark process failed.
- `parse_error`: benchmark output was not valid JSON.
- `failed_decode`: benchmark ran normally but decode failed for a trial-level row.
- `unresolved`: threshold search could not confirm the target.
- `invalid`: verifier found a schema violation.

For aggregate rows, a low success rate should not automatically change `status` from `ok` to `failed_decode`. The row can be valid even if the algorithm fails often.

## Experiment Names

Use stable experiment names:

```text
compare_basic
dlk_sweep
find_best_m
spatial_threshold
z_sensitivity
sharp_threshold
circular_a
dedup_hashes
```

Each script should set `experiment` explicitly.

## Migration Plan by Script

### `tests/test_compare_basic.py`

Current role: cross-algorithm comparison on shared datasets.

Changes:

1. Add `schema_version = "benchmark.v1"`.
2. Add `experiment = "compare_basic"`.
3. Add `record_type = "aggregate"` to aggregated rows.
4. Add `dataset_id` once the standalone dataset generator exists.
5. Continue to allow algorithm-specific fields.
6. Ensure unavailable baselines produce the same required common fields with zeros where metrics are not meaningful.

Recommended normalization responsibility:

- C++/Go wrappers may keep emitting a smaller flat row.
- `test_compare_basic.py` should normalize wrapper output into full schema rows.

### `tests/test_dlk.py`

Current role: fixed grid sweep over `d`, `l`, and `k`.

Changes:

1. Add `schema_version = "benchmark.v1"`.
2. Add `experiment = "dlk_sweep"`.
3. Add `record_type = "aggregate"`.
4. Add `variant`, probably `variant = "spatial"` or `variant = "mode=<mode>"`.
5. Add `implementation = "XYZ-v2"`.
6. Add `dataset_mode = "internal_generator"` until it uses the shared dataset generator.

### `tests/test_find_best_m.py`

Current role: binary search for suitable `M`.

Changes:

1. Probe rows should use `record_type = "probe"`.
2. Final rows should use `record_type = "threshold"`.
3. Add `experiment = "find_best_m"`.
4. Add confidence interval fields once implemented:

```text
ci_method
ci_confidence
ci_low
ci_high
threshold_policy
```

5. Keep `target_success_rate`, `required_probe_successes`, and `required_final_successes`.

### `tests/test_spatial.py`

Current role: threshold comparison between placement modes.

Changes:

1. Probe rows should use `record_type = "probe"`.
2. Summary rows should use `record_type = "threshold"`.
3. Add `experiment = "spatial_threshold"`.
4. Use `variant = mode`, where `mode` is `random`, `circular`, or `naive`.
5. Add confidence interval fields for final validation.

### `tests/test_z.py`

Current role: sensitivity sweep over `z`.

Changes:

1. Add `schema_version = "benchmark.v1"`.
2. Add `experiment = "z_sensitivity"`.
3. Add `record_type = "aggregate"`.
4. Keep `RangeLength` as an algorithm-specific field.
5. Add `variant = "z=<value>"` or keep `variant = mode` and leave `z` as a parameter. Prefer `variant = mode` and explicit `z`.

### C++ and Go Benchmark Wrappers

Wrappers currently print flat JSON. There are two possible approaches:

1. Minimal wrapper output:
   - wrapper prints only fields it naturally knows;
   - Python scripts add schema fields and normalize.

2. Full wrapper output:
   - every wrapper prints `schema_version`, `record_type`, `experiment`, etc.

Recommended approach:

```text
Use minimal wrapper output now.
Let Python orchestrator scripts normalize into benchmark.v1.
```

Reason: this avoids repeating schema logic in C++, Go, and Python. Later, a shared C++ JSON helper can be added if needed.

## Verifier Plan

Add a verifier script:

```text
tests/json_verifier.py
```

Responsibilities:

1. Read one or more JSONL files.
2. Validate each row against `benchmark.v1`.
3. Check required fields based on `record_type`.
4. Check type constraints.
5. Check numeric sanity:

```text
0 <= successes <= trials
0 <= success_rate <= 1
bits >= 0
bits_per_difference >= 0
bit_C_over_d >= 0
d > 0
ca > 0
cb > 0
```

6. Check consistency:

```text
success_rate == successes / trials  (within tolerance)
bits_per_difference == bits / d      (within tolerance)
bit_C_over_d == bits / (32*d)        (within tolerance)
```

7. Print warnings for unknown fields.
8. Exit nonzero if any row is invalid.

CLI design:

```bash
python tests/json_verifier.py tests/results/compare_basic/raw.jsonl
python tests/json_verifier.py tests/results/**/*.jsonl --recursive
python tests/json_verifier.py tests/results/compare_basic/raw.jsonl --strict
```

Options:

```text
--schema benchmark.v1
--recursive
--strict
--allow-legacy
--max-errors N
```

## Legacy Compatibility

Many existing result files do not have `schema_version`. The verifier should support a transition mode:

```text
--allow-legacy
```

Legacy mode:

- accepts rows without `schema_version`;
- infers missing fields when safe;
- reports warnings instead of hard failures for missing schema-only fields.

Strict mode:

- requires `schema_version = "benchmark.v1"`;
- requires all common fields for the row type;
- should be used for new experiment outputs.

## Migration Order

Recommended order:

1. Implement `tests/json_verifier.py` with legacy and strict modes.
2. Add normalization helpers in `tests/test_compare_basic.py`.
3. Migrate `test_compare_basic.py` output to `benchmark.v1`.
4. Migrate `test_dlk.py` and `test_z.py`.
5. Migrate `test_find_best_m.py` and `test_spatial.py`, including threshold row types.
6. Add confidence interval fields.
7. Update summaries to mention verifier status.

## Example Rows

### Aggregate Row

```json
{
  "schema_version": "benchmark.v1",
  "record_type": "aggregate",
  "experiment": "compare_basic",
  "algorithm": "xyz_v2",
  "variant": "spatial",
  "implementation": "XYZ-v2",
  "status": "ok",
  "d": 1000,
  "ca": 10000,
  "cb": 10000,
  "seed": 114514,
  "dataset_mode": "shared_file",
  "dataset_id": "d1000_ca10000_cb10000_seed114514",
  "trials": 30,
  "successes": 29,
  "success_rate": 0.9666666667,
  "bits": 42532,
  "bits_per_difference": 42.532,
  "bit_C_over_d": 1.329125,
  "encode_avg_s": 0.00078,
  "decode_avg_s": 0.20761,
  "encode_median_s": 0.00075,
  "decode_median_s": 0.20111,
  "l": 6,
  "k": 2,
  "M": 217,
  "z": 2,
  "mode": "spatial"
}
```

### Unavailable Row

```json
{
  "schema_version": "benchmark.v1",
  "record_type": "unavailable",
  "experiment": "compare_basic",
  "algorithm": "cpisync",
  "variant": "mbar_factor=1.2",
  "implementation": "external/cpisync",
  "status": "unavailable",
  "unavailable_reason": "cpisync_bench was built without ENABLE_REAL_CPISYNC",
  "d": 1000,
  "ca": 10000,
  "cb": 10000,
  "seed": 114514,
  "dataset_mode": "shared_file",
  "trials": 30,
  "successes": 0,
  "success_rate": 0.0,
  "bits": 0,
  "bits_per_difference": 0.0,
  "bit_C_over_d": 0.0,
  "encode_avg_s": 0.0,
  "decode_avg_s": 0.0,
  "encode_median_s": 0.0,
  "decode_median_s": 0.0
}
```

### Threshold Row

```json
{
  "schema_version": "benchmark.v1",
  "record_type": "threshold",
  "experiment": "find_best_m",
  "algorithm": "xyz_v2",
  "variant": "spatial",
  "implementation": "XYZ-v2",
  "status": "ok",
  "d": 1000,
  "ca": 10000,
  "cb": 10000,
  "seed": 114514,
  "dataset_mode": "internal_generator",
  "target_success_rate": 0.99,
  "threshold_policy": "lower_ci_meets_target",
  "ci_method": "wilson",
  "ci_confidence": 0.95,
  "trials": 300,
  "successes": 298,
  "success_rate": 0.9933333333,
  "ci_low": 0.9761,
  "ci_high": 0.9982,
  "M": 225,
  "bits": 44100,
  "bits_per_difference": 44.1,
  "bit_C_over_d": 1.378125
}
```

## Open Decisions

1. Should `C_over_d` be removed in favor of `bit_C_over_d`?
   - Recommendation: keep `C_over_d` as legacy alias for now, but standardize on `bit_C_over_d`.

2. Should schema be nested instead of flat?
   - Recommendation: keep v1 flat. Consider nested v2 later.

3. Should wrappers emit full schema?
   - Recommendation: no, not initially. Let Python orchestrators normalize.

4. Should per-trial rows become mandatory?
   - Recommendation: yes for new threshold experiments, but allow aggregate-only legacy output until migration is complete.

