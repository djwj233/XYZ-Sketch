# Per-Item Hash Update Deduplication Plan

This document plans how to add and test per-item hash-location deduplication for XYZ-style sketch updates.

Implementation status: the first XYZ-v2 stage is implemented. `XYZ-v2` now has a dedup switch, `tests/benchmarks/xyz_v2_bench.cpp` accepts `--dedup-hashes true|false`, and the first Python experiment scripts can scan `--dedup-hashes false,true`.

## Problem

For each item `x`, the sketch computes `k` hash locations:

```text
h_1(x), h_2(x), ..., h_k(x)
```

The current update path treats these as a sequence. If two hash functions map `x` to the same cell, that cell is updated more than once for the same item.

Example:

```text
h_1(x) = 17
h_2(x) = 17
h_3(x) = 42
```

Current behavior:

```text
update cell 17
update cell 17 again
update cell 42
```

Deduplicated behavior:

```text
update cell 17 once
update cell 42 once
```

The deduplicated version treats the item's incident locations as a set instead of a multiset.

## Why This Matters

The expected difference is usually small when `M` is large and hash collisions among the `k` locations are rare. However, collisions can become more visible when:

- `M` is small;
- the spatial-coupling range is short;
- `k` is large;
- circular placement wraps many locations into a tight region.

Deduplication may also make the theoretical explanation cleaner, because each item contributes to a set of distinct cells.

## Scope

### First Stage: XYZ-v2

Start with `XYZ-v2`, because the main threshold, spatial, `z`, and circular-`a` experiments all use it.

Status: implemented for the core XYZ-v2 update/decode path and for these experiment scripts:

```text
tests/test_spatial.py
tests/test_circular_a.py
tests/test_xyz_sharp_threshold.py
```

Relevant files:

```text
XYZ-v2/hash.cpp
XYZ-v2/hash.h
XYZ-v2/XYZSketch.cpp
tests/benchmarks/xyz_v2_bench.cpp
tests/test_spatial.py
tests/test_circular_a.py
tests/test_xyz_sharp_threshold.py
tests/test_z.py
tests/test_find_best_m.py
```

The primary code path is in `XYZ-v2/XYZSketch.cpp`:

```cpp
inline void Update(int x) {
    fo(i, 1, k) InsertToCell_Fast(h(i, x), x);
}
```

`Extract()` must use the same deduplication rule as `Update()`, because decoding removes an item from the cells where it was inserted.

`PureCellVerify()` should also use the same location set when checking whether a recovered item belongs to a cell.

### Second Stage: IBLT-SC

After XYZ-v2 is stable, apply the same idea to `tests/benchmarks/iblt_sc_bench.cpp` if the paper needs an IBLT-uniform vs IBLT-SC dedup ablation.

Do not start with every external baseline. Most external projects should remain untouched, and many do not expose the same hash-location update semantics.

## Proposed C++ Interface

Add a global switch in the XYZ hash/update layer:

```cpp
namespace SpatialCoupling {
    void SetDedupHashes(bool enabled);
    bool GetDedupHashes();
}
```

Default:

```text
false
```

Keeping the default as `false` preserves existing experiment behavior and makes old results reproducible.

## Location Helper

Add a helper that returns the per-item update locations:

```cpp
inline vector<int> HashLocations(int x) {
    vector<int> positions;
    positions.reserve(k);
    for(int i = 1; i <= k; i++) positions.push_back(h(i, x));
    if(GetDedupHashes()) {
        sort(positions.begin(), positions.end());
        positions.erase(unique(positions.begin(), positions.end()), positions.end());
    }
    return positions;
}
```

Then use it consistently:

```cpp
for(int pos : HashLocations(x)) InsertToCell_Fast(pos, x);
```

and:

```cpp
for(int pos : HashLocations(x)) Extract from pos;
```

and membership checking:

```cpp
for(int pos : HashLocations(x)) {
    if(pos == cell_id) ...
}
```

The helper can live in `XYZSketch.cpp` if it only needs sketch globals, or in `hash.cpp`/`hash.h` if other benchmarks should reuse it. The first implementation can keep it local to `XYZSketch.cpp` for minimal blast radius.

## Benchmark CLI

Add a benchmark option to `tests/benchmarks/xyz_v2_bench.cpp`:

```text
--dedup-hashes true|false
```

Parsing should accept:

```text
true, false, 1, 0, yes, no
```

The benchmark output should include:

```json
"dedup_hashes": true
```

The normalized JSON rows should keep this field as an algorithm parameter.

## Python Experiment Support

Add `--dedup-hashes` to the relevant Python scripts that call `xyz_v2_bench`.

Recommended first scripts:

```text
tests/test_spatial.py
tests/test_circular_a.py
tests/test_xyz_sharp_threshold.py
```

Later scripts:

```text
tests/test_z.py
tests/test_find_best_m.py
tests/test_dlk.py
```

Use a CLI style that allows scanning both values:

```text
--dedup-hashes false,true
```

For scripts that only need one value, allow:

```text
--dedup-hashes false
```

The experiment variant should include the setting:

```text
variant = spatial,dedup=false
variant = spatial,dedup=true
```

## Experiment Design

The goal is not to replace the main experiments immediately. The first goal is an ablation study.

### Smoke Test

Run a tiny fixed-parameter test:

```text
d = 20
l = 6
k = 2
mode = circular
dedup_hashes in {false, true}
trials = 2
shared_datasets = true
```

Expected outcome:

- both modes run without crashing;
- strict JSON verifier passes;
- both rows point to the same `dataset_dir`;
- `dedup_hashes` is present in the raw and summary rows.

### Collision-Stress Test

Use settings where duplicate hash locations are more likely:

```text
d in {100, 300}
l = 6
k in {3, 4, 5}
mode in {random, circular, naive}
M near the failure/success threshold
trials >= 50
shared_datasets = true
dedup_hashes in {false, true}
```

This test answers whether deduplication changes success rate in the region where decoding is sensitive.

### Threshold Test

For representative paper settings:

```text
d in {1000, 3000}
l = 6
k in {2, 3, 4}
mode in {random, spatial/circular-or-naive}
target_success_rate = 0.95 or 0.99
dedup_hashes in {false, true}
shared_datasets = true
```

Compare:

```text
best_M
best_C_over_d
success_rate
ci_low / ci_high
encode/decode time
```

## Output Layout

Use a dedicated result directory:

```text
tests/results/hash_update_dedup/
```

Suggested files:

```text
raw.jsonl
raw.csv
summary.jsonl
summary.csv
summary.md
run_config.json
errors.log
```

## Interpretation Rules

If `dedup=true` and `dedup=false` produce nearly identical thresholds:

- keep the main experiment default unchanged for comparability;
- mention dedup as an implementation robustness check;
- use the cleaner deduplicated semantics in proof discussion only if the proof needs it.

If dedup noticeably improves or hurts performance:

- report it as a real ablation result;
- decide explicitly which behavior the paper's main algorithm definition should use;
- rerun the main XYZ-v2 experiments with the chosen setting.

## Risks

The main correctness risk is inconsistent update and decode semantics.

These functions must agree:

```text
Update(x)
Extract(x, type)
PureCellVerify(cell)
```

If `Update()` deduplicates but `Extract()` does not, decoding can corrupt the residual sketch.

If `PureCellVerify()` does not use the same location set, it may reject valid pure cells or accept invalid ones.

## Verification Checklist

Before trusting results:

1. Compile `xyz_v2_bench`.
2. Run one internal-generator smoke test with `--dedup-hashes false`.
3. Run one internal-generator smoke test with `--dedup-hashes true`.
4. Run one shared-dataset smoke test comparing both settings.
5. Run `tests/json_verifier.py --strict` on the output.
6. Confirm `dataset_dir` is identical across dedup variants in paired tests.
7. Confirm `dedup_hashes` appears in raw and summary rows.
8. For a tiny debug run, optionally count how often an item has fewer than `k` distinct locations.

## Recommended Implementation Order

1. Add the C++ dedup switch and location helper.
2. Update `Update()`, `Extract()`, and `PureCellVerify()` to use the helper.
3. Add `--dedup-hashes` to `xyz_v2_bench`.
4. Add `dedup_hashes` to benchmark JSON output.
5. Add Python pass-through support to `test_spatial.py` and `test_circular_a.py`.
6. Run smoke tests.
7. Add a small dedicated ablation script only if existing scripts become awkward for scanning both values.

Items 1-6 are complete for `test_spatial.py`, `test_circular_a.py`, and `test_xyz_sharp_threshold.py`. A dedicated ablation script is not necessary yet because those scripts can already scan both settings.

## Smoke Commands Used

```powershell
g++ -std=c++17 -O2 tests\benchmarks\xyz_v2_bench.cpp -o build\xyz_v2_bench.exe

python tests\test_spatial.py --d-values 20 --l-values 6 --k-values 2 --modes circular --probe-trials 2 --final-trials 2 --target-success-rate 0.5 --max-C-over-d 3 --limit 2 --shared-datasets --dedup-hashes false,true --output-dir tests\results\hash_update_dedup_spatial_smoke --skip-build

python tests\test_circular_a.py --mode fixed-m --d-values 20 --l-values 6 --k-values 2 --a-values 1/3 --trials 2 --limit 2 --shared-datasets --dedup-hashes false,true --output-dir tests\results\hash_update_dedup_circular_a_smoke --skip-build

python tests\test_xyz_sharp_threshold.py --d-values 20 --l-values 6 --k-values 2 --modes circular --trials 2 --center-trials 1 --points 3 --min-window 1 --window-fraction 0 --dedup-hashes false,true --limit 2 --output-dir tests\results\hash_update_dedup_sharp_smoke --skip-build
```
