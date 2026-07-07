# External Baseline Integration Plan

This document plans how to turn the scaffolded external baseline adapters into real measured baselines for the paper comparison. It is a planning document only; no implementation is included here.

## Goal

The goal is to make external set reconciliation baselines runnable under the same benchmark architecture as XYZ-v2, XYZ-v1, local IBLT, and IBLT-SC:

```text
shared dataset -> thin adapter -> benchmark.v1 JSON row -> common summary
```

The final comparison should answer:

```text
For the same generated Alice/Bob sets and the same target difference size d, how much communication and time does each practical reconciliation method need to succeed?
```

## Repository Rule

External projects are source inputs. Do not modify or add files under:

```text
external/*
XYZ-v1/
XYZ-v2/
IBLT/
```

All glue code, benchmark wrappers, temporary build files, and generated helper files should live under:

```text
tests/benchmarks/
tests/
tests/tmp/
build/
tests/results/
```

If an external project needs a CMake build directory, a Go module wrapper, logs, or generated configuration, keep those artifacts outside the external subproject.

## Current Status

The comparison script already recognizes these algorithms:

```text
xyz_v1
xyz_v2
iblt
iblt_cpp
minisketch
cpisync
riblt
negentropy
```

Current integration status:

```text
xyz_v1      real local wrapper
xyz_v2      real local wrapper
iblt        real local wrapper
iblt_cpp    real external/IBLT_Cplusplus wrapper
minisketch  real wrapper; builds and runs on the current environment
cpisync     scaffolded/optional; platform/dependency sensitive
riblt       real wrapper path exists; unavailable here until Go is installed
negentropy  real code path exists; unavailable here until OpenSSL headers/libs are installed
```

The next work should focus on enabling the environment-dependent rows where feasible while preserving `status = "unavailable"` for unsupported platforms.

## Priority Order

Recommended implementation order:

```text
1. minisketch
2. riblt
3. negentropy
4. cpisync
5. polish iblt_cpp reporting if needed
```

Reasoning:

- `minisketch` is the cleanest fixed-sketch baseline and is directly relevant to set reconciliation.
- `riblt` is practically important because it is rateless and works well when `d` is not known exactly.
- `negentropy` is valuable but has ordered/range-based assumptions, so it should be reported with caveats.
- `cpisync` is a classic baseline, but the current dependency and process model is more platform-sensitive, especially on Windows.
- `iblt_cpp` is already real and mainly serves as a cross-check against the local IBLT implementation.

## Shared Benchmark Contract

Every external adapter should accept the same dataset format:

```text
--dataset PATH
--d D
--format jsonl
```

The adapter should run one trial for one dataset and print one `benchmark.v1` JSON object to stdout.

The Python comparison script should aggregate rows across trials. External adapters should not generate their own random datasets during compare runs.

Required behavior:

- Read Alice and Bob sets from the shared dataset file.
- Compute the true Alice-only and Bob-only differences from the loaded data.
- Run the external algorithm on exactly those sets.
- Verify decoded output against the true differences whenever the algorithm exposes enough information.
- Report communication in bits and bytes using a documented accounting rule.
- Emit `status = "ok"` for real successful benchmark rows.
- Emit `status = "unavailable"` with `unavailable_reason` when the adapter cannot be built or used on the current machine.
- Keep the row valid under `tests/json_verifier.py --strict`.

## Common Output Fields

All adapters should fill the common schema fields:

```text
schema_version = "benchmark.v1"
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
dataset_mode = "shared_file"
success
successes
success_rate
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

If an algorithm does not have a natural encode/decode split, put the total protocol time in `reconcile_s` and leave encode/decode as zero or absent according to the existing schema policy.

## Communication Accounting Policy

Because the baselines have different interaction models, the summary must not hide what is being counted.

Recommended accounting:

```text
XYZ / IBLT / minisketch:
  count the transmitted fixed sketch size.

RIBLT:
  count the coded symbols actually sent until decode succeeds, or the configured cap if it fails.

CPISync:
  count measured protocol bytes across all messages.

Negentropy:
  count client-to-server plus server-to-client message bytes across all rounds.
```

Rows should include method-specific fields so plots can be interpreted correctly:

```text
communication_model = "fixed_sketch" | "rateless" | "interactive"
rounds
messages
symbols_sent
capacity
capacity_factor
mbar
mbar_factor
```

## `external/minisketch`

### Purpose

Minisketch should be the primary near-optimal fixed-sketch baseline.

### Build Plan

Build the external project out-of-tree:

```text
build/minisketch/
```

Then build:

```text
tests/benchmarks/minisketch_bench.cpp -> build/minisketch_bench(.exe)
```

The wrapper should link against the out-of-tree `libminisketch` build and enable the real adapter path, for example with an `ENABLE_REAL_MINISKETCH` compile definition.

### Benchmark Plan

Use the C API:

```text
minisketch_create(...)
minisketch_add_uint64(...)
minisketch_merge(...)
minisketch_decode(...)
minisketch_serialized_size(...)
```

Recommended parameters:

```text
field_bits = 30
capacity = ceil(capacity_factor * d)
```

The dataset generator currently keeps values below `998244353`, so 30-bit fields are enough.

Success condition:

- The decoded symmetric difference exactly matches the true dataset symmetric difference.
- Direction is not inherent to PinSketch, so direction-specific verification should be treated carefully.

Communication:

```text
bits = minisketch_serialized_size(sketch) * 8
```

### Smoke Test

```bash
python tests/test_compare_basic.py \
  --algorithms minisketch \
  --d-values 1000 \
  --trials 5 \
  --capacity-factors 1.0,1.1,1.2 \
  --output-dir tests/results/compare_minisketch_smoke
```

Expected:

- `capacity_factor >= 1.0` should usually succeed.
- Communication should scale linearly with `capacity`.
- JSON rows should pass strict verification.

## `external/riblt`

### Purpose

RIBLT should represent the rateless reconciliation family. It is useful when the difference size is not known exactly.

### Build Plan

Do not add module files under `external/riblt`.

Use one of these project-side approaches:

```text
tests/benchmarks/riblt_bench.go
tests/benchmarks/go/riblt_adapter/
build/riblt/
```

If a Go module is needed, create it outside `external/riblt` and use a local `replace` directive pointing to the read-only external checkout.

### Benchmark Plan

Follow the item type pattern in `external/riblt/example_test.go`.

Implement a `uint64` item type with:

```text
XOR
Hash
```

Flow:

1. Add Alice values to a RIBLT encoder.
2. Add Bob values to a RIBLT decoder.
3. Generate coded symbols until decoding succeeds or a symbol cap is reached.
4. Verify decoded Alice-only and Bob-only values against the dataset.

Recommended parameter:

```text
max_symbols = ceil(symbol_factor * d)
```

Communication:

```text
bits = symbols_sent * symbol_bits
```

Also report `field_bits = 30` so we can distinguish actual implementation cost from a lower-bound normalized cost.

### Smoke Test

```bash
python tests/test_compare_basic.py \
  --algorithms riblt \
  --d-values 1000 \
  --trials 5 \
  --symbol-factors 1.2,1.5,2.0 \
  --output-dir tests/results/compare_riblt_smoke
```

Expected:

- Success should increase as `symbol_factor` grows.
- The row should report `symbols_sent`.
- Failed decodes should be normal low-capacity outcomes, not benchmark crashes.

## `external/negentropy`

### Purpose

Negentropy is an ordered/range-based synchronization baseline. It is useful, but it should not be presented as a direct unordered fixed-sketch competitor without caveats.

### Build Plan

Use the header-only C++ implementation under:

```text
external/negentropy/cpp
```

Build:

```text
tests/benchmarks/negentropy_bench.cpp -> build/negentropy_bench(.exe)
```

No generated files should be written into `external/negentropy`.

### Benchmark Plan

Use `negentropy::storage::Vector` first.

Convert each integer dataset value into the ID format required by Negentropy. Use a deterministic mapping, for example:

```text
uint64 value -> 32-byte zero-padded or hashed ID
```

Expose timestamp modes:

```text
timestamp_mode = value
timestamp_mode = constant
timestamp_mode = random
```

The initial paper-facing result should use `timestamp_mode = random` or clearly label `timestamp_mode = value` as an ordered workload.

Run an in-process client/server message loop:

```text
client initiate
server reconcile
client reconcile
...
```

Stop when the protocol finishes or a maximum round count is reached.

Communication:

```text
bits = 8 * (client_bytes + server_bytes)
```

Output must include:

```text
communication_model = "interactive"
ordered_workload = true
timestamp_mode
rounds
client_bytes
server_bytes
```

### Smoke Test

```bash
python tests/test_compare_basic.py \
  --algorithms negentropy \
  --d-values 1000 \
  --trials 5 \
  --frame-size-limits 0 \
  --timestamp-modes random,value \
  --output-dir tests/results/compare_negentropy_smoke
```

Expected:

- Results may differ greatly by timestamp mode.
- Summary should group or label Negentropy separately.
- If the adapter cannot verify direction exactly, report that limitation explicitly.

## `external/cpisync`

### Purpose

CPISync is a classic characteristic-polynomial set reconciliation baseline. It is valuable historically and scientifically, but it may be slower and harder to build.

### Build Plan

Keep CPISync optional.

Preferred path:

```text
cmake -S external/cpisync -B build/cpisync
cmake --build build/cpisync
```

Alternative path:

```text
compile tests/benchmarks/cpisync_bench.cpp with selected read-only sources from external/cpisync/src
```

On Windows, the real adapter may remain unavailable if the upstream process/IPC or dependency assumptions do not fit the environment.

### Benchmark Plan

Use the high-level path already exercised by the upstream tests:

```text
GenSync
CPISync
DataObject
forkHandle(...)
```

Recommended parameters:

```text
mbar = ceil(mbar_factor * d)
bits_param = 30
epsilon = 64
redundant = 0
hashes = false
```

Communication:

```text
bits = 8 * measured_protocol_bytes
```

If upstream exposes separate round-trip bytes and excess bytes, report both in method-specific fields.

### Smoke Test

```bash
python tests/test_compare_basic.py \
  --algorithms cpisync \
  --d-values 100 \
  --trials 3 \
  --mbar-factors 1.0,1.2,1.5 \
  --output-dir tests/results/compare_cpisync_smoke
```

Expected:

- On unsupported machines, output valid unavailable rows.
- On supported machines, report measured protocol bytes and total reconciliation time.
- Start with small `d`; do not use CPISync as the first large-scale baseline.

## `external/IBLT_Cplusplus`

This adapter is already real. The remaining work is mostly reporting polish:

- Confirm that `bits`, `cells`, `cell_bits`, and `hash_count` reflect the external implementation's actual layout.
- Keep it in the comparison as `implementation = "external/IBLT_Cplusplus"`.
- Use it as a diagnostic cross-check against local IBLT-uniform and IBLT-SC.

## Updates Needed in `tests/test_compare_basic.py`

The script should keep the existing shared-dataset workflow and add real build/run paths per external baseline.

Recommended changes:

1. Keep default algorithms small, such as `xyz_v2,iblt`.
2. Add auto-detection for external dependencies where possible.
3. Add explicit switches if needed:

   ```text
   --enable-real-minisketch
   --enable-real-riblt
   --enable-real-negentropy
   --enable-real-cpisync
   ```

   Auto-detection can be the default, and these switches can force a real build attempt.

4. Preserve unavailable fallback rows when a build fails.
5. Write build errors to `errors.log`.
6. Do not let one failed external adapter abort other selected algorithms.
7. Validate all final rows with `tests/json_verifier.py`.

## Testing Strategy

For each external baseline:

1. Run a single-algorithm dry run.
2. Build only that adapter.
3. Run a small smoke test with `d = 100` or `d = 1000`.
4. Verify JSON strictly.
5. Run paired comparison with `xyz_v2` and `iblt` on the same datasets.
6. Inspect whether success rate changes monotonically with the capacity-like parameter.
7. Only then add the adapter to broader comparison runs.

Recommended verifier command:

```bash
python tests/json_verifier.py \
  --input tests/results/<experiment>/raw.jsonl \
  --strict
```

## Paper-Facing Result Groups

The final paper summary should avoid mixing incomparable communication models in one undifferentiated table.

Recommended grouping:

```text
Fixed sketches:
  XYZ-v2, XYZ-v1, IBLT, IBLT_Cplusplus, minisketch

Spatial-coupled variants:
  XYZ-SC, IBLT-SC

Rateless:
  RIBLT

Interactive protocols:
  CPISync, Negentropy
```

If one combined table is needed, include `communication_model` and caveat columns.

## Completion Criteria

This task is complete when:

- `minisketch`, `riblt`, and `negentropy` produce real rows on at least one supported development environment, or documented unavailable rows with clear dependency reasons.
- `cpisync` is either real on a POSIX-like environment or explicitly documented as unsupported in the current Windows setup.
- No wrapper writes into `external/*`.
- All rows use shared datasets.
- All rows pass the strict JSON verifier.
- `summary.md` separates fixed-sketch, rateless, and interactive baselines clearly.
