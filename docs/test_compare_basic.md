# `tests/test_compare_basic.py` Design Plan

This document plans a basic cross-algorithm comparison experiment. It describes how `tests/test_compare_basic.py` should compare the algorithms already available in this repository and the newly added external baseline subprojects.

No code is implemented here.

## Experiment Goal

The goal is to compare practical set reconciliation algorithms under the same synthetic workloads.

The main question:

```text
For the same set sizes and symmetric difference d, how do algorithms compare in communication cost, encoding time, decoding time, and success rate?
```

This experiment is different from the earlier XYZ-only scripts:

- `test_dlk.py` studies XYZ-v2 parameters.
- `test_spatial.py` isolates spatial coupling inside XYZ-v2.
- `test_z.py` studies the sensitivity to `z`.
- `test_compare_basic.py` should compare different reconciliation algorithms on shared datasets.

## Algorithms to Compare

The repository currently has these candidate implementations:

```text
XYZ-v2                local implementation
XYZ-v1                local implementation
IBLT                  local implementation
external/minisketch   external baseline
external/cpisync      external baseline
external/riblt        external baseline
external/negentropy   external baseline
external/IBLT_Cplusplus external baseline
```

The first version should be incremental. It should not try to fully integrate every external codebase at once.

Recommended phases:

```text
Phase 1: XYZ-v2 + local IBLT
Phase 2: cpisync
Phase 3: XYZ-v1 + external IBLT_Cplusplus
Phase 4: minisketch
Phase 5: riblt
Phase 6: negentropy, with ordered-workload caveats
```

This keeps the first script useful even if an external dependency has build issues.

## Fairness Policy

All algorithms should receive the same generated input sets for a given trial.

For each trial, generate two sets:

```text
A, B
|A| = ca
|B| = cb
|A symmetric_difference B| = d
```

Use the same dataset generator policy as the existing benchmark scripts:

```text
ca = max(1000, d * set_size_scale), capped by max_set_size
cb = ca - (d % 2)
```

The script should pass the same workload to each algorithm benchmark. The current first implementation uses the same `d`, `ca`, and `cb`, but each benchmark still generates its own data internally. That is not strong enough for a paired comparison.

The next implementation should generate datasets once in Python and pass the same dataset file to every selected algorithm.

For a given workload:

```text
workload_seed = base_seed + 1000000 * workload_index
trial_seed = workload_seed + trial_index
```

The Python script should use `trial_seed` to generate exactly one pair of sets for that trial. All algorithms should read that pair.

If the algorithm benchmark is in another language, the adapter should either:

1. Use the same generated dataset file, or
2. Reimplement the same deterministic generator exactly.

After this change, `seed` in output rows should mean the shared `workload_seed`, not an algorithm-specific seed. Each row should also record:

```text
dataset_mode = "shared_file"
dataset_dir
```

This makes it clear that algorithms were compared on identical inputs.

## Dataset Format

Use a simple line-based format so C++, Go, and shell adapters can read it easily.

Recommended per-trial dataset file:

```text
# compare-dataset-v1 ca=<number> cb=<number> d=<number> seed=<number> trial=<number>
A <ca>
123
456
...
B <cb>
789
...
```

The first non-comment line names the Alice section and its length. The second section names Bob and its length. Lines after each header contain one unsigned integer per line.

The parser should ignore blank lines and comment lines starting with `#`.

The script should create one dataset file per trial. That is slower than internal generation, but the basic comparison is small enough that fairness is worth the cost. Later, if file I/O becomes a bottleneck, a binary format or batched dataset format can be added.

Recommended layout:

```text
tests/tmp/compare_basic/d1000_seed114514_trial0.sets
tests/tmp/compare_basic/d1000_seed114514_trial1.sets
```

These temporary files should not be committed.

## Dataset Generation Algorithm

The Python generator should mirror the current benchmark logic:

1. Create `max(ca, cb)` distinct base values.
2. Alice receives the first `ca` base values.
3. Bob receives the first `cb` base values.
4. Let:

   ```text
   imbalance = abs(ca - cb)
   replacements = (d - imbalance) / 2
   ```

5. Pick `replacements` distinct positions in the common prefix.
6. Replace Bob's values at those positions with new distinct values.
7. Shuffle Alice and Bob independently using the same RNG stream.

The generated values should be positive integers inside the XYZ-v2 field so all current local benchmarks can handle them:

```text
1 <= x < 998244353
```

The generator should validate:

```text
d >= abs(ca - cb)
(d - abs(ca - cb)) is even
replacements <= min(ca, cb)
```

## Required Benchmark Changes for Shared Datasets

Both local C++ benchmark binaries should accept an optional dataset file:

```text
--dataset tests/tmp/compare_basic/d1000_seed114514_trial0.sets
```

When `--dataset` is present:

- Ignore internal random generation.
- Read Alice and Bob sets from the file.
- Infer `ca`, `cb`, and actual symmetric difference from the file, or validate that CLI values match.
- Run exactly one trial for that dataset.

The Python script should then aggregate multiple per-trial benchmark calls into one result row per algorithm/variant/workload.

This is slightly more subprocess-heavy, but it makes the comparison clean and easy to audit.

### `tests/benchmarks/xyz_v2_bench.cpp`

Add:

```text
--dataset PATH
```

Implementation plan:

1. Add `dataset_path` to `Options`.
2. Add a `load_dataset(path)` function returning `TrialData`.
3. If `dataset_path` is set, call `run_trial_on_data(opt, data)` instead of `generate_data`.
4. Keep the old random-generation path for `test_dlk.py`, `test_spatial.py`, and `test_z.py`.

### `tests/benchmarks/iblt_bench.cpp`

Add the same:

```text
--dataset PATH
```

Implementation plan:

1. Add `dataset_path` to `Options`.
2. Add a `load_dataset(path)` function returning `TrialData`.
3. Compute expected `a_diff` and `b_diff` from the loaded sets.
4. Keep the old random-generation path for standalone smoke tests.

## Fixing IBLT Variants

The current raw output loses the IBLT capacity-factor variant because `tests/benchmarks/iblt_bench.cpp` prints:

```text
variant = "local"
```

The comparison script should preserve the job variant in normalized output:

```text
variant = "capacity_factor=1.5"
variant = "capacity_factor=2"
...
```

Recommended policy:

- Benchmark binaries may output implementation-level variants such as `local`.
- `tests/test_compare_basic.py` should override or extend this with the job variant.

For IBLT rows, use:

```text
implementation = "local"
variant = "capacity_factor=<value>"
```

Add `implementation` to the optional output fields if useful.

## Parameter Grid

Start with a small grid that is large enough to show trends but not so large that external builds dominate the work.

Recommended smoke grid:

```text
d in {1000}
set_size_scale = 10
trials = 10
algorithms = xyz_v2, iblt
```

Recommended basic grid:

```text
d in {100, 300, 1000, 3000, 10000}
set_size_scale = 10
trials = 30
algorithms = xyz_v2, iblt, minisketch
```

Recommended extended grid:

```text
d in {100, 300, 1000, 3000, 10000, 30000, 100000}
set_size_scale in {10, 100}
trials = 100 for small d
trials = 30 for large d
```

For XYZ-v2, use representative parameters from previous experiments:

```text
l = 6
k = 2
mode = spatial
M chosen by the current best-M policy
z = round(M^(1/3) / 3)
```

For local IBLT, the script should expose an equivalent capacity factor, such as:

```text
iblt_cell_factor = 1.5, 2.0, 2.5, 3.0
```

For algorithms that require the difference size as a capacity parameter, use:

```text
capacity = ceil(capacity_factor * d)
```

## Normalized Metrics

Each algorithm adapter should produce the same logical fields:

```text
algorithm
variant
d
ca
cb
trials
successes
success_rate
encode_avg_s
decode_avg_s
encode_median_s
decode_median_s
bits
bits_per_difference
bit_C_over_d
seed
status
```

Where:

```text
bits_per_difference = bits / d
bit_C_over_d = bits / (32 * d)
```

For XYZ-v2, also record:

```text
l
k
M
z
mode
field_C_over_d = M * l / d
```

For IBLT-like methods, also record:

```text
cells
hash_count
cell_bits
capacity_factor
```

For minisketch-like methods, also record:

```text
field_bits
capacity
```

## Benchmark Adapter Design

`test_compare_basic.py` should treat every algorithm as an adapter with a common interface.

Recommended Python structure:

```python
class BenchmarkAdapter:
    name: str

    def build(self, root: Path, build_dir: Path, skip_build: bool) -> None:
        """Build this adapter if needed."""

    def make_jobs(self, config: dict) -> list[dict]:
        """Return benchmark jobs for this algorithm and config."""

    def run(self, job: dict, dataset: Path | None) -> dict:
        """Run one benchmark job and return one normalized result row."""
```

Recommended first adapters:

```text
XYZV2Adapter
LocalIBLTAdapter
MinisketchAdapter
```

Adapters for `cpisync`, `riblt`, and `negentropy` can be added after their build and input/output formats are understood.

## C++ Benchmark Binaries

The existing XYZ-v2 benchmark should be reused:

```text
tests/benchmarks/xyz_v2_bench.cpp -> build/xyz_v2_bench.exe
```

The local IBLT code currently has `speedtest.cpp` and `iblttest.cpp`, but it does not yet expose the same JSONL interface. The clean approach is to add a small benchmark binary later:

```text
tests/benchmarks/iblt_bench.cpp -> build/iblt_bench.exe
```

It should accept:

```bash
build/iblt_bench.exe \
  --d 1000 \
  --trials 30 \
  --seed 114514 \
  --ca 10000 \
  --cb 10000 \
  --capacity-factor 2.0 \
  --format jsonl
```

For external baselines, prefer thin wrapper binaries or scripts that output the same JSONL row format.

All benchmark wrappers must live in this repository, not inside algorithm subprojects:

```text
tests/benchmarks/<algorithm>_bench.cpp
tests/benchmarks/<algorithm>_bench.go
tests/test_compare_basic.py
build/<algorithm>_bench(.exe)
build/<external-project>/
```

The external and versioned algorithm directories should be treated as read-only source inputs:

```text
Do not modify or add files under XYZ-v1, XYZ-v2, IBLT, or external/*.
```

If an adapter needs generated code, temporary files, CMake build files, Go command modules, logs, or helper binaries, place them under `tests/`, `build/`, or `tests/tmp/`.

## External Baseline Integration Plan

### Overall Adapter Policy

The remaining adapters should follow the same shape as the existing shared-dataset flow:

1. `tests/test_compare_basic.py` generates one dataset file per workload/trial.
2. Every selected algorithm receives that exact dataset through `--dataset PATH`.
3. Each wrapper prints exactly one JSONL row for one dataset.
4. The Python script aggregates per-trial rows into one row per algorithm/variant/workload.
5. If an adapter cannot build or run on the current platform, it returns `status = "unavailable"` with an `unavailable_reason`.

Recommended new wrapper locations:

```text
tests/benchmarks/xyz_v1_bench.cpp
tests/benchmarks/iblt_cpp_bench.cpp
tests/benchmarks/minisketch_bench.cpp
tests/benchmarks/riblt_bench.go
tests/benchmarks/negentropy_bench.cpp
```

Recommended algorithm names in `--algorithms`:

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

Do not make every algorithm part of the default run. Keep the default small, such as `xyz_v2,iblt`, and let users request external baselines explicitly.

### `XYZ-v1`

XYZ-v1 is valuable because it measures the improvement from the original XYZ sketch to XYZ-v2.

Integration plan:

1. Add `tests/benchmarks/xyz_v1_bench.cpp`.
2. Include or link against `XYZ-v1/XYZ-v1.cpp` as a read-only source dependency.
3. Support the same shared dataset format with `--dataset PATH`.
4. Expose `--d`, `--trials`, `--seed`, `--ca`, `--cb`, and `--format jsonl`.
5. Set the global `D` used by XYZ-v1 before encoding each dataset.
6. Compute expected Alice-only and Bob-only differences from the dataset, then compare them to `Decode`.
7. Report communication as `to_bitstring(Alice).size()`, matching the existing XYZ-v1 sketch serialization.

Recommended output fields:

```text
algorithm = "xyz_v1"
implementation = "local"
variant = "basic"
d
ca
cb
success_rate
encode_avg_s
decode_avg_s
bits
bits_per_difference
bit_C_over_d
dataset_mode
status
```

Important caveat: XYZ-v1 has a different parameter surface from XYZ-v2. It should first be compared as "the original algorithm at capacity D", not as an optimized version with a tuned spatial-coupling policy.

### `external/minisketch`

Minisketch is a mature PinSketch implementation and should be the primary near-optimal fixed-sketch external baseline.

Integration plan:

1. Build `external/minisketch` out-of-tree under `build/minisketch/`.
2. Add `tests/benchmarks/minisketch_bench.cpp`.
3. Link the wrapper against the out-of-tree `libminisketch` build, or compile against the C API if that is simpler on the current platform.
4. Use `field_bits = 30`, because shared dataset values are less than `998244353`.
5. Use `capacity = ceil(capacity_factor * d)`.
6. Build one sketch for Alice and one sketch for Bob, merge them, decode the symmetric difference, and verify it against the dataset-derived symmetric difference.
7. Communication should initially count Alice's serialized sketch only: `minisketch_serialized_size(sketch) * 8`.
8. Optionally add a second accounting field for full two-party repair traffic, because PinSketch recovers the symmetric difference but does not inherently label direction.

Recommended CLI:

```bash
build/minisketch_bench.exe \
  --dataset tests/tmp/compare_basic/d1000_seed114514_trial0.sets \
  --d 1000 \
  --capacity-factor 1.0 \
  --field-bits 30 \
  --format jsonl
```

Recommended output fields:

```text
algorithm = "minisketch"
implementation = "external/minisketch"
variant = "capacity_factor=<value>"
field_bits
capacity
capacity_factor
bits
decode_count
```

Expected behavior: when `capacity >= d`, Minisketch should decode successfully. If `capacity < d`, it should fail cleanly or decode fewer than the expected differences.

### `external/IBLT_Cplusplus`

This is a useful cross-check against the local IBLT implementation.

Integration plan:

1. Add `tests/benchmarks/iblt_cpp_bench.cpp`.
2. Compile the wrapper with read-only source files from `external/IBLT_Cplusplus`: `iblt.cpp`, `murmurhash3.cpp`, and `utilstrencodings.cpp`.
3. Use the public `IBLT(size_t expectedNumEntries, size_t valueSize)` API.
4. Insert Alice's values into one IBLT and Bob's values into another.
5. Subtract the two IBLTs and call `listEntries`.
6. Compare positive/negative entries against dataset-derived Alice-only and Bob-only differences.
7. Sweep `capacity_factor` using `expectedNumEntries = ceil(capacity_factor * d)`.
8. Choose a fixed `valueSize`, likely 0 or 4 bytes depending on whether the implementation permits key-only entries. If values are required, store the key as the value as well.

Recommended CLI:

```bash
build/iblt_cpp_bench.exe \
  --dataset tests/tmp/compare_basic/d1000_seed114514_trial0.sets \
  --d 1000 \
  --capacity-factor 1.3 \
  --value-size 4 \
  --format jsonl
```

Recommended output fields:

```text
algorithm = "iblt_cpp"
implementation = "external/IBLT_Cplusplus"
variant = "capacity_factor=<value>"
capacity_factor
expected_entries
value_size
cells
cell_bits
hash_count
bits
```

This adapter is mainly a diagnostic check. If its memory layout or cell count differs from the local IBLT implementation, report that clearly instead of forcing the same communication formula.

### `external/cpisync`

CPISync is the next external baseline to try. It is a classic characteristic-polynomial set reconciliation implementation, and the upstream project already contains a `GenSync`/`CPISync` path that reports success, total communication bytes, and total elapsed time through `forkHandle`.

Important repository rule:

```text
Do not modify or add files under external/cpisync.
```

All integration code should live in this repository, for example:

```text
tests/benchmarks/cpisync_bench.cpp
tests/test_compare_basic.py
build/cpisync/
build/cpisync_bench.exe
```

Integration plan:

1. Treat CPISync as an optional adapter. If dependencies are unavailable, record `status = "unavailable"` instead of stopping the whole comparison.
2. Build `external/cpisync` out-of-tree, for example with `cmake -S external/cpisync -B build/cpisync`, or compile a wrapper in `tests/benchmarks` that links against the external project sources/library. Do not write generated files into `external/cpisync`.
3. Start with the higher-level route used by `external/cpisync/tests/unit/CPITest.cpp`: construct two `GenSync` instances with protocol `CPISync`, insert `DataObject` values, and run `forkHandle(Alice, Bob, false)`.
4. Use the existing shared dataset file format through `--dataset PATH`, so CPISync receives exactly the same Alice/Bob sets as XYZ-v2 and IBLT.
5. Sweep `mbar_factor`, where `m_bar = ceil(mbar_factor * d)`. CPISync needs an upper bound on the number of differences, so this is the analogue of a capacity factor.
6. Use `bits = 30` for the current shared datasets, because generated values are less than `998244353`. A later version may infer `bits = ceil(log2(max_value + 1))` from each dataset.
7. Start with `epsilon = 64`, `redundant = 0`, and `hashes = false`. Since the generated values already fit the configured bit range, disabling CPISync's internal hashing keeps the result easier to interpret.
8. Prefer CPISync's measured communication accounting: `bytesRTot + bytesXTot` from `forkHandleReport`. Convert this to bits for normalized output.
9. Record that CPISync is an interactive two-party protocol. Its communication metric is protocol bytes, not just a fixed sketch size.

Recommended benchmark CLI:

```bash
build/cpisync_bench.exe \
  --dataset tests/tmp/compare_basic/d1000_seed114514_trial0.sets \
  --d 1000 \
  --mbar-factor 1.2 \
  --bits 30 \
  --epsilon 64 \
  --redundant 0 \
  --hashes false \
  --format jsonl
```

The Python comparison script should still aggregate trials externally. Therefore `cpisync_bench` should normally process one dataset file per invocation, just like the current shared-dataset mode for XYZ-v2 and IBLT.

Recommended normalized output fields:

```text
algorithm = "cpisync"
implementation = "external/cpisync"
variant = "mbar_factor=<value>"
d
ca
cb
trials
successes
success_rate
reconcile_avg_s
bits
bytes
bits_per_difference
bit_C_over_d
mbar
mbar_factor
bits_param
epsilon
redundant
hashes
dataset_mode
dataset_dir
status
```

If CPISync does not expose a meaningful encode/decode split, report the measured synchronization time as `reconcile_avg_s`. For compatibility with the summary table, `test_compare_basic.py` can either leave `encode_avg_s`/`decode_avg_s` empty or map `decode_avg_s = reconcile_avg_s` and `encode_avg_s = 0`.

Python adapter plan:

1. Add `CPISyncAdapter` to `tests/test_compare_basic.py`.
2. `build()` checks whether CPISync dependencies are available: NTL, GMP, CppUnit, CMake, and any allocator/profiler library required by the upstream CMake configuration.
3. If the build fails, return an unavailable row for each requested CPISync job instead of failing the full run.
4. `make_jobs()` expands `--mbar-factors`, similar to how IBLT expands `--capacity-factors`.
5. `run()` invokes `build/cpisync_bench.exe` once per shared dataset file and aggregates the per-trial JSON rows.

Initial smoke command after implementation:

```bash
python tests/test_compare_basic.py \
  --algorithms cpisync \
  --d-values 100 \
  --trials 3 \
  --mbar-factors 1.0,1.2,1.5 \
  --keep-datasets \
  --output-dir tests/results/compare_cpisync_smoke
```

Expected smoke outcomes:

- If dependencies are missing, `raw.jsonl` should contain `status = "unavailable"` rows and the script should exit normally.
- If dependencies are present, each row should contain measured success rate, protocol bytes, and reconciliation time.
- Start with small `d` because characteristic-polynomial reconciliation can be much slower than sketch-based methods when parameters grow.

### `external/riblt`

RIBLT is valuable because it is rateless and practical when `d` is unknown.

Integration plan:

1. Add a Go wrapper under `tests/benchmarks/riblt_bench.go`.
2. Do not add files under `external/riblt`. If Go module wiring is needed, keep it in this repository, for example under `tests/benchmarks/go/` or `build/riblt/`.
3. Use the package in `external/riblt` through a local module replace or by running `go test`/`go run` from a wrapper module outside the subproject.
4. Implement a `uint64` item type with `XOR` and `Hash`, following `external/riblt/example_test.go`.
5. Add Alice values to a `riblt.Encoder` and Bob values to a `riblt.Decoder`.
6. Produce coded symbols until `dec.Decoded()` returns true or a configured ceiling is reached.
7. Sweep `symbol_factor`, where `max_symbols = ceil(symbol_factor * d)`.
8. Communication is `symbols_sent * symbol_bits`. For 30-bit dataset values stored in a `uint64` symbol, report both `symbol_bits = 64` and, if useful, a normalized lower-bound field using `field_bits = 30`.

Recommended CLI:

```bash
go run tests/benchmarks/riblt_bench.go \
  --dataset tests/tmp/compare_basic/d1000_seed114514_trial0.sets \
  --d 1000 \
  --symbol-factor 1.6 \
  --symbol-bits 64 \
  --format jsonl
```

Recommended output fields:

```text
algorithm = "riblt"
implementation = "external/riblt"
variant = "symbol_factor=<value>"
symbol_factor
symbols_sent
max_symbols
symbol_bits
field_bits
bits
```

Important caveat: RIBLT is rateless. A fixed-parameter comparison should cap transmitted symbols, while a target-success comparison should measure how many symbols were actually needed.

### `external/negentropy`

Negentropy is range-based and assumes ordered keys. It is useful, but not always directly comparable to random unordered sets.

Integration plan:

1. Add `tests/benchmarks/negentropy_bench.cpp`.
2. Use the header-only C++ implementation under `external/negentropy/cpp` as a read-only include path.
3. Use `negentropy::storage::Vector` for the first implementation.
4. Convert each dataset value into a 32-byte ID. A deterministic mapping is enough for synthetic tests, for example zero-padding or hashing the 30-bit integer into 32 bytes.
5. Choose a timestamp policy explicitly:
   - `timestamp_mode=value`: timestamp equals the integer value. This gives ordered structure.
   - `timestamp_mode=constant`: all timestamps are equal, leaving lexical ID order only.
   - `timestamp_mode=random`: deterministic pseudo-random timestamps derived from the dataset seed.
6. Run an in-process client/server message loop using `Negentropy::initiate()` and `reconcile()`.
7. Count total bytes over all client-to-server and server-to-client messages.
8. Verify that the final `have`/`need` IDs match Alice-only and Bob-only differences.
9. Sweep `frame_size_limit`, including `0` for unlimited frames.

Recommended CLI:

```bash
build/negentropy_bench.exe \
  --dataset tests/tmp/compare_basic/d1000_seed114514_trial0.sets \
  --d 1000 \
  --frame-size-limit 0 \
  --timestamp-mode value \
  --format jsonl
```

Recommended output fields:

```text
algorithm = "negentropy"
implementation = "external/negentropy"
variant = "frame_size=<value>,timestamp=<mode>"
frame_size_limit
timestamp_mode
rounds
client_bytes
server_bytes
bits
ordered_workload = true
```

Important caveat: Negentropy is not a generic unordered-set sketch. Its performance depends heavily on the timestamp/order distribution. Its results should be grouped separately or marked with an explicit ordered-workload caveat in `summary.md`.

## Search Policy

There are two useful modes for `test_compare_basic.py`.

### Fixed-Parameter Mode

Use fixed algorithm parameters and measure success/time/communication.

This is the simplest first version.

Example:

```bash
python tests/test_compare_basic.py \
  --algorithms xyz_v2,iblt \
  --d-values 1000,3000 \
  --trials 10
```

### Target-Success Mode

Search for the smallest communication cost that reaches a target success rate.

This is fairer when comparing algorithms with different capacity parameters.

Example:

```bash
python tests/test_compare_basic.py \
  --algorithms xyz_v2,iblt,minisketch \
  --d-values 1000,3000,10000 \
  --target-success-rate 0.95 \
  --search-capacity
```

The first implementation can start with fixed-parameter mode. Target-success mode can reuse ideas from `test_spatial.py`.

## Recommended Script Functions

```python
def repo_root() -> Path:
    """Return repository root."""

def ensure_dirs(root: Path, output_dir: Path | None) -> dict[str, Path]:
    """Create output and build directories."""

def parse_list_args(args) -> dict:
    """Parse comma-separated d values, algorithms, and capacity factors."""

def choose_set_sizes(d: int, max_set_size: int, scale: int) -> tuple[int, int]:
    """Choose ca and cb consistently with earlier scripts."""

def make_dataset(seed: int, ca: int, cb: int, d: int) -> tuple[list[int], list[int]]:
    """Generate one deterministic pair of sets."""

def write_dataset(path: Path, alice: list[int], bob: list[int], metadata: dict) -> None:
    """Write one dataset file for external adapters."""

def prepare_datasets(config: dict, trials: int, dataset_dir: Path) -> list[Path]:
    """Generate shared dataset files for one workload."""

def build_adapters(adapters: list[BenchmarkAdapter], root: Path, skip_build: bool) -> None:
    """Build all selected algorithm adapters."""

def make_jobs(args, adapters: list[BenchmarkAdapter]) -> list[dict]:
    """Expand the parameter grid into algorithm-specific jobs."""

def run_one_dataset(job: dict, dataset: Path) -> dict:
    """Run one algorithm on one dataset file and return one trial row."""

def aggregate_trials(job: dict, trial_rows: list[dict]) -> dict:
    """Aggregate per-dataset rows into one normalized summary row."""

def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write raw results."""

def write_csv(path: Path, rows: list[dict]) -> None:
    """Write CSV results."""

def write_summary(path: Path, rows: list[dict]) -> None:
    """Write a human-readable comparison summary."""
```

## Output Directory

Recommended output directory:

```text
tests/results/compare_basic/
```

Recommended files:

```text
tests/results/compare_basic/raw.jsonl
tests/results/compare_basic/raw.csv
tests/results/compare_basic/summary.md
tests/results/compare_basic/errors.log
tests/results/compare_basic/run_config.json
```

## Summary Format

The summary should group rows by workload:

```text
d, ca, cb
```

Within each group, list:

```text
algorithm
variant
success_rate
bits_per_difference
bit_C_over_d
encode_avg_s
decode_avg_s
status
```

For target-success mode, highlight the smallest communication cost among successful algorithms.

## CLI Design

Suggested arguments:

```text
--algorithms
    Comma-separated algorithm list. Example: xyz_v2,iblt,minisketch.

--d-values
    Comma-separated symmetric difference sizes.

--trials
    Trial count per configuration.

--capacity-factors
    Comma-separated factors for capacity-based algorithms.

--target-success-rate
    Target for search mode.

--search-capacity
    Enable best-capacity search instead of fixed-parameter runs.

--skip-build
    Use existing benchmark binaries.

--dry-run
    Print planned jobs without running them.

--limit
    Run only the first N jobs.

--output-dir
    Override output directory.

--base-seed
    Reproducibility seed.

--dataset-dir
    Directory for generated shared dataset files.

--keep-datasets
    Keep generated dataset files after the run.

--max-set-size
    Cap generated set sizes.

--set-size-scale
    ca/cb scale relative to d.
```

## Testing Plan

## Current Implementation Status

The compare script now recognizes all planned baseline names:

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

Current wrapper status:

```text
xyz_v1      implemented, real local wrapper
xyz_v2      implemented, real local wrapper
iblt        implemented, real local wrapper
iblt_cpp    implemented, real external/IBLT_Cplusplus wrapper
cpisync     scaffolded; reports unavailable on Windows/non-POSIX builds
minisketch  scaffolded; reports unavailable until linked with libminisketch
riblt       scaffolded; reports unavailable if Go/module wiring is absent
negentropy  scaffolded; reports unavailable until linked with the C++ implementation
```

All wrappers still receive the same shared dataset files. Rows with `status = "unavailable"` are expected for adapters whose external dependency path has not been enabled on the current machine.

Smoke command for the full algorithm list:

```bash
python tests/test_compare_basic.py \
  --algorithms xyz_v1,xyz_v2,iblt,iblt_cpp,minisketch,cpisync,riblt,negentropy \
  --d-values 100 \
  --trials 1 \
  --capacity-factors 1.3 \
  --mbar-factors 1.0 \
  --symbol-factors 1.5 \
  --frame-size-limits 0 \
  --timestamp-modes value \
  --output-dir tests/results/compare_all_smoke \
  --keep-datasets
```

### 1. Dry Run

```bash
python tests/test_compare_basic.py --dry-run --algorithms xyz_v2,iblt --d-values 1000 --trials 3
```

Expected:

- The script prints the planned workload and selected algorithms.
- No benchmark binary is executed.

### 2. XYZ-v2 Only Smoke Test

```bash
python tests/test_compare_basic.py \
  --algorithms xyz_v2 \
  --d-values 1000 \
  --trials 5 \
  --output-dir tests/results/compare_smoke_xyz
```

Expected:

- Output contains one row for XYZ-v2.
- The row is consistent with `xyz_v2_bench.cpp`.

### 3. XYZ-v2 vs Local IBLT Smoke Test

```bash
python tests/test_compare_basic.py \
  --algorithms xyz_v2,iblt \
  --d-values 1000 \
  --trials 5 \
  --capacity-factors 2.0 \
  --output-dir tests/results/compare_smoke_iblt
```

Expected:

- Output contains one row per algorithm/variant.
- Both algorithms use the same dataset files.
- `raw.jsonl` should include `dataset_mode = "shared_file"`.
- IBLT rows should show distinct variants such as `capacity_factor=2`.

### 4. Minisketch Smoke Test

After the minisketch adapter is implemented:

```bash
python tests/test_compare_basic.py \
  --algorithms minisketch \
  --d-values 1000 \
  --trials 5 \
  --capacity-factors 1.0,1.2,1.5 \
  --output-dir tests/results/compare_smoke_minisketch
```

Expected:

- Communication cost should scale with configured capacity.
- Success should be high when capacity is at least the true difference size.

### 5. Failure Handling Test

Run with an intentionally tiny capacity:

```bash
python tests/test_compare_basic.py \
  --algorithms iblt,minisketch \
  --d-values 1000 \
  --trials 5 \
  --capacity-factors 0.5
```

Expected:

- Some rows should show low success or `status = failed_decode`.
- The script should continue to other algorithms.

### 6. CPISync Smoke Test

After the CPISync adapter is implemented:

```bash
python tests/test_compare_basic.py \
  --algorithms cpisync \
  --d-values 100 \
  --trials 3 \
  --mbar-factors 1.0,1.2,1.5 \
  --keep-datasets \
  --output-dir tests/results/compare_cpisync_smoke
```

Expected:

- All CPISync rows use the same shared dataset format as XYZ-v2 and IBLT.
- On Windows or on machines without CPISync dependencies, rows may show `status = unavailable`.
- On POSIX-like systems with NTL/GMP and CPISync build support, rows should report protocol bytes and reconciliation time.

### 7. Basic Three-Algorithm Run

Once CPISync is available, run the paired comparison with:

```bash
python tests/test_compare_basic.py \
  --algorithms xyz_v2,iblt,cpisync \
  --d-values 100,300,1000 \
  --trials 10 \
  --capacity-factors 1.5,2.0 \
  --mbar-factors 1.0,1.2,1.5 \
  --output-dir tests/results/compare_basic_cpisync
```

This still generates one dataset per workload/trial and sends that exact dataset to every selected algorithm.

## Interpretation Caveats

Important caveats:

- Algorithms do not always have the same interaction model. RIBLT is rateless, while XYZ-v2 and minisketch are fixed-size sketches.
- Negentropy is range-based and should not be treated as a generic unordered-set baseline without qualification.
- Some algorithms may need to know or estimate `d`; report whether the experiment gives them the true `d`.
- Communication accounting must be documented carefully. Count transmitted sketch bytes, not only internal cells.
- Build failures for external baselines should be recorded as `status = unavailable`, not allowed to stop the whole comparison.

## Recommended First Implementation

The current first implementation already does this:

```text
1. Build/reuse xyz_v2_bench.
2. Add or build a JSONL benchmark for local IBLT.
3. Run fixed-parameter comparison for xyz_v2 and iblt.
4. Write raw.jsonl, raw.csv, and summary.md.
```

The next implementation should fix the known comparison issues before adding more baselines:

```text
1. Generate shared dataset files in tests/test_compare_basic.py.
2. Add --dataset support to tests/benchmarks/xyz_v2_bench.cpp.
3. Add --dataset support to tests/benchmarks/iblt_bench.cpp.
4. Preserve IBLT capacity-factor variants in raw and summary output.
5. Add a low-capacity IBLT factor scan, such as 0.7..1.5.
```

Only after this should minisketch be added as the first external baseline.
