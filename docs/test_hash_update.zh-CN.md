# 单元素 Hash 更新位置去重实验规划

本文档规划如何为 XYZ 类 sketch update 加入 per-item hash-location deduplication，并设计对应实验。

实现状态：第一阶段 XYZ-v2 已完成。`XYZ-v2` 现在有 dedup 开关，`tests/benchmarks/xyz_v2_bench.cpp` 支持 `--dedup-hashes true|false`，第一批 Python 实验脚本可以扫描 `--dedup-hashes false,true`。

## 问题

对每个元素 `x`，sketch 会计算 `k` 个 hash 位置：

```text
h_1(x), h_2(x), ..., h_k(x)
```

当前 update 路径把它们当成一个序列处理。如果两个 hash 函数把同一个 `x` 映射到同一个 cell，那么这个 cell 会被同一个元素更新多次。

例子：

```text
h_1(x) = 17
h_2(x) = 17
h_3(x) = 42
```

当前行为：

```text
更新 cell 17
再次更新 cell 17
更新 cell 42
```

去重后的行为：

```text
只更新一次 cell 17
更新一次 cell 42
```

去重版本把一个元素关联的位置看成集合，而不是多重集合。

## 为什么重要

当 `M` 较大、同一个元素的 `k` 个位置互相碰撞概率很低时，预期差别通常很小。但在以下情况下，重复位置可能更明显：

- `M` 较小；
- spatial-coupling range 较短；
- `k` 较大；
- circular placement 把很多位置 wrap 到较紧的区域里。

去重也可能让理论叙事更干净，因为每个元素只贡献到一组互不相同的 cell。

## 范围

### 第一阶段：XYZ-v2

先从 `XYZ-v2` 开始，因为主 threshold、spatial、`z` 和 circular-`a` 实验都依赖它。

状态：XYZ-v2 核心 update/decode 路径已经实现，以下实验脚本已经接入：

```text
tests/test_spatial.py
tests/test_circular_a.py
tests/test_xyz_sharp_threshold.py
```

相关文件：

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

主要代码路径在 `XYZ-v2/XYZSketch.cpp`：

```cpp
inline void Update(int x) {
    fo(i, 1, k) InsertToCell_Fast(h(i, x), x);
}
```

`Extract()` 必须使用和 `Update()` 一致的去重规则，因为 decoding 时要从当初插入过的 cell 中移除元素。

`PureCellVerify()` 在检查恢复出的元素是否属于某个 cell 时，也应该使用同一套位置集合。

### 第二阶段：IBLT-SC

等 XYZ-v2 稳定后，如果论文需要 IBLT-uniform vs IBLT-SC 的 dedup ablation，再把同样思路应用到 `tests/benchmarks/iblt_sc_bench.cpp`。

不建议一开始就改所有 external baseline。大多数 external 项目不应该被修改，而且很多 baseline 并不暴露同样的 hash-location update 语义。

## 建议的 C++ 接口

在 XYZ hash/update 层加入一个全局开关：

```cpp
namespace SpatialCoupling {
    void SetDedupHashes(bool enabled);
    bool GetDedupHashes();
}
```

默认值：

```text
false
```

默认保持 `false` 可以保留已有实验行为，方便复现旧结果。

## 位置辅助函数

增加一个返回单元素 update 位置的 helper：

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

然后统一使用它：

```cpp
for(int pos : HashLocations(x)) InsertToCell_Fast(pos, x);
```

以及：

```cpp
for(int pos : HashLocations(x)) 从 pos 中 Extract;
```

membership checking 也使用：

```cpp
for(int pos : HashLocations(x)) {
    if(pos == cell_id) ...
}
```

这个 helper 可以放在 `XYZSketch.cpp`，如果只服务 sketch 全局变量；也可以放在 `hash.cpp`/`hash.h`，如果后续 benchmark 想复用。第一版建议放在 `XYZSketch.cpp`，减少影响范围。

## Benchmark CLI

给 `tests/benchmarks/xyz_v2_bench.cpp` 增加参数：

```text
--dedup-hashes true|false
```

解析时建议接受：

```text
true, false, 1, 0, yes, no
```

benchmark 输出中应包含：

```json
"dedup_hashes": true
```

规范化后的 JSON row 应保留这个字段作为算法参数。

## Python 实验支持

给调用 `xyz_v2_bench` 的相关 Python 脚本加入 `--dedup-hashes`。

第一批推荐脚本：

```text
tests/test_spatial.py
tests/test_circular_a.py
tests/test_xyz_sharp_threshold.py
```

后续脚本：

```text
tests/test_z.py
tests/test_find_best_m.py
tests/test_dlk.py
```

CLI 风格建议支持同时扫描两个值：

```text
--dedup-hashes false,true
```

如果脚本只需要单个值，也允许：

```text
--dedup-hashes false
```

实验 variant 应包含该设置：

```text
variant = spatial,dedup=false
variant = spatial,dedup=true
```

## 实验设计

目标不是立刻替换主实验，而是先做 ablation study。

### Smoke Test

先跑一个很小的固定参数测试：

```text
d = 20
l = 6
k = 2
mode = circular
dedup_hashes in {false, true}
trials = 2
shared_datasets = true
```

预期结果：

- 两种模式都不崩溃；
- strict JSON verifier 通过；
- 两行结果指向同一个 `dataset_dir`；
- raw 和 summary row 中都包含 `dedup_hashes`。

### Collision-Stress Test

选择更容易出现重复 hash 位置的设置：

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

这个测试回答：在 decoding 敏感区域，去重是否改变成功率。

### Threshold Test

对代表性的论文参数：

```text
d in {1000, 3000}
l = 6
k in {2, 3, 4}
mode in {random, spatial/circular-or-naive}
target_success_rate = 0.95 or 0.99
dedup_hashes in {false, true}
shared_datasets = true
```

比较：

```text
best_M
best_C_over_d
success_rate
ci_low / ci_high
encode/decode time
```

## 输出目录

使用独立结果目录：

```text
tests/results/hash_update_dedup/
```

建议文件：

```text
raw.jsonl
raw.csv
summary.jsonl
summary.csv
summary.md
run_config.json
errors.log
```

## 解释规则

如果 `dedup=true` 和 `dedup=false` 得到几乎相同的 threshold：

- 主实验默认值先保持不变，方便和已有结果对齐；
- 把 dedup 作为实现鲁棒性检查来说明；
- 只有在证明确实需要时，才在证明叙事中使用更干净的去重语义。

如果 dedup 明显提升或降低性能：

- 把它作为真实 ablation 结果报告；
- 明确决定论文主算法定义应该使用哪种行为；
- 用选定设置重跑主要 XYZ-v2 实验。

## 风险

主要正确性风险是 update 和 decode 语义不一致。

这些函数必须一致：

```text
Update(x)
Extract(x, type)
PureCellVerify(cell)
```

如果 `Update()` 去重但 `Extract()` 不去重，decoding 可能破坏 residual sketch。

如果 `PureCellVerify()` 不使用同一套位置集合，它可能拒绝合法 pure cell，或者接受非法 pure cell。

## 验证清单

信任结果前需要：

1. 编译 `xyz_v2_bench`。
2. 用 `--dedup-hashes false` 跑一个 internal-generator smoke test。
3. 用 `--dedup-hashes true` 跑一个 internal-generator smoke test。
4. 跑一个 shared-dataset smoke test，同时比较两个设置。
5. 对输出运行 `tests/json_verifier.py --strict`。
6. 确认 paired test 中不同 dedup variants 使用相同 `dataset_dir`。
7. 确认 raw 和 summary row 中都有 `dedup_hashes`。
8. 对很小的 debug run，可以额外统计有多少元素的 distinct locations 少于 `k`。

## 推荐实现顺序

1. 增加 C++ dedup 开关和位置 helper。
2. 让 `Update()`、`Extract()` 和 `PureCellVerify()` 使用 helper。
3. 给 `xyz_v2_bench` 增加 `--dedup-hashes`。
4. 在 benchmark JSON 输出中加入 `dedup_hashes`。
5. 给 `test_spatial.py` 和 `test_circular_a.py` 增加 Python 透传支持。
6. 跑 smoke tests。
7. 只有当现有脚本不方便同时扫描两个值时，再增加一个独立的小 ablation 脚本。

对 `test_spatial.py`、`test_circular_a.py` 和 `test_xyz_sharp_threshold.py` 来说，1-6 已完成。现在暂时不需要独立 ablation 脚本，因为这些脚本已经可以直接扫描两个设置。

## 已使用的 Smoke 命令

```powershell
g++ -std=c++17 -O2 tests\benchmarks\xyz_v2_bench.cpp -o build\xyz_v2_bench.exe

python tests\test_spatial.py --d-values 20 --l-values 6 --k-values 2 --modes circular --probe-trials 2 --final-trials 2 --target-success-rate 0.5 --max-C-over-d 3 --limit 2 --shared-datasets --dedup-hashes false,true --output-dir tests\results\hash_update_dedup_spatial_smoke --skip-build

python tests\test_circular_a.py --mode fixed-m --d-values 20 --l-values 6 --k-values 2 --a-values 1/3 --trials 2 --limit 2 --shared-datasets --dedup-hashes false,true --output-dir tests\results\hash_update_dedup_circular_a_smoke --skip-build

python tests\test_xyz_sharp_threshold.py --d-values 20 --l-values 6 --k-values 2 --modes circular --trials 2 --center-trials 1 --points 3 --min-window 1 --window-fraction 0 --dedup-hashes false,true --limit 2 --output-dir tests\results\hash_update_dedup_sharp_smoke --skip-build
```
