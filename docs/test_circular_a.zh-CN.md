# `tests/test_circular_a.py` 设计规划

本文档规划 XYZ-v2 中 circular spatial-coupling 参数 `a` 的实验。这里只做规划，不包含具体实现。

## 目标

论文中描述了一个带参数的 circular placement rule：

```text
g0: U -> [0, z + a),  a in [0, 1)
gi: U -> [0, 1)
```

实际问题是：

```text
对于 circular spatial coupling，哪个 a 能带来最低通信阈值，或者最高成功率？
```

这不是核心实验，除非证明叙事或论文讨论需要它。它应该作为主线 `d/l/k`、spatial-coupling、sharp-threshold 和 baseline 对比之后的 follow-up diagnostic experiment。

## 当前实现状态

当前代码已经有 circular spatial coupling：

```text
XYZ-v2/hash.cpp
tests/benchmarks/xyz_v2_bench.cpp
tests/test_spatial.py
```

当前 circular base range 是硬编码的：

```cpp
inline int circular_base_h0(int x) {
    return MurmurHash::Hash(x, 114514) % (M - RangeLength / 3 + 1);
}
```

由于：

```text
RangeLength = M / (z + 1)
```

这在当前离散实现里大致等价于：

```text
a = 1/3
```

所以第一版实现不应该从零发明新规则，而是把现有硬编码的 `1/3` 泛化成参数。

## 需要的 C++ 修改

### `XYZ-v2/hash.h`

新增 circular 参数 setter/getter：

```cpp
namespace SpatialCoupling {
    void SetCircularA(double value);
    double GetCircularA();
}
```

默认值应保持当前行为：

```text
default circular_a = 1.0 / 3.0
```

### `XYZ-v2/hash.cpp`

新增全局 circular 参数：

```cpp
double CircularA = 1.0 / 3.0;
```

把 `circular_base_h0` 从：

```cpp
M - RangeLength / 3 + 1
```

改为参数化 base range：

```cpp
base_range = M - floor(CircularA * RangeLength) + 1
```

然后安全 clamp：

```text
base_range >= 1
base_range <= M
```

理由：

- `a = 1/3` 会复现当前 `RangeLength / 3` 的整数除法行为。
- `a = 0` 让 base range 接近 `M`，即 circular window 几乎可以从任何位置开始。
- 更大的 `a` 会缩小 base range，改变 wrap boundary 附近的质量分布。

实现应拒绝范围外参数：

```text
0 <= a < 1
```

### `tests/benchmarks/xyz_v2_bench.cpp`

新增 CLI 参数：

```text
--circular-a FLOAT
```

行为：

- 只对 `--mode circular` 有实际意义；或者 `--mode spatial` 且 `k <= 2` 时 auto mode 会选择 circular。
- 仍然在所有 row 中记录该值，方便筛选。
- 默认值为 `1.0 / 3.0`。

benchmark 应在：

```cpp
SpatialCoupling::HashingInit(opt.Z)
```

之前调用：

```cpp
SpatialCoupling::SetCircularA(opt.circular_a);
```

输出字段：

```text
circular_a
```

如果方便，也输出：

```text
circular_base_range
range_length
```

这些字段有助于检查整数 rounding 的影响。

## Python 脚本

推荐脚本名：

```text
tests/test_circular_a.py
```

这个脚本用于扫描 circular spatial coupling 的 `a`。

它应该和 `tests/test_spatial.py` 分开，因为 `test_spatial.py` 比较不同 mode，而这个脚本固定 circular mode，只改变一个内部参数。

## 实验模式

脚本应支持两种模式。

### 固定 `M` 扫描

固定 `M`，测量不同 `a` 的成功率。

这个模式便宜，适合先看曲线形状：

```text
d, l, k, M, z fixed
a scanned over a grid
```

推荐第一组 grid：

```text
a in {0.0, 0.1, 0.2, 1/3, 0.4, 0.5, 0.6, 0.75, 0.9}
```

预期输出：

```text
success_rate vs a
bits unchanged because M is fixed
```

### 阈值搜索

对每个 `a`，搜索达到目标成功率所需的最小 `M`。

这是更适合论文展示的模式：

```text
for each a:
    binary-search best M
    final-validate best M
    report best_C_over_d and confidence interval
```

它应复用这些脚本的 threshold-search 结构：

```text
tests/test_find_best_m.py
tests/test_spatial.py
```

预期输出：

```text
best_M vs a
best_C_over_d vs a
final_success_rate and CI vs a
```

## 推荐参数

先聚焦 `k = 2`。论文中提到 circular 在 `k = 2` 表现好，而较大 `k` 下表现差，所以调 `a` 最相关的是 `k = 2`。

初始 smoke grid：

```text
d = 100
l = 6
k = 2
trials = 5
a in {0.0, 1/3, 0.6}
```

主 fixed-`M` grid：

```text
d in {1000, 3000, 10000}
l = 6
k = 2
M from current best-M policy for circular
trials = 50
a in {0.0, 0.1, 0.2, 1/3, 0.4, 0.5, 0.6, 0.75, 0.9}
```

主 threshold grid：

```text
d in {1000, 3000, 10000}
l = 6
k = 2
target_success_rate = 0.95
probe_trials = 30
final_trials = 100
a in {0.0, 0.1, 0.2, 1/3, 0.4, 0.5, 0.6, 0.75, 0.9}
```

`k >= 3` 的诊断 grid：

```text
d in {1000, 3000}
l = 6
k in {3, 4}
mode = circular
a in {0.0, 1/3, 0.6}
```

这部分要明确标为 diagnostic。它不应该替代 `k >= 3` 的 `naive` spatial-coupling 结果。

## `z` 的选择

沿用其它 spatial 实验中的启发式：

```text
z = max(0, round(M^(1/3) / 3))
```

第一版不要同时扫描 `z` 和 `a`。那会让实验太大，也更难解释。

如果后续需要，可以做一个很小的二维诊断扫描：

```text
z around the heuristic value
a around the best observed value
```

## Dataset 策略

第一版可以使用 `xyz_v2_bench` 内部 deterministic generator，和 `test_spatial.py` 保持一致。

如果结果要进入论文正文，应切换为：

```text
tests/dataset_generator.py
```

生成的 shared datasets。

这样不同 `a` 会在完全相同的 Alice/Bob 集合上做 paired comparison。

推荐策略：

- Smoke mode：可以使用 internal generator。
- Main fixed-`M` 和 threshold mode：如果可行，使用 shared datasets。

## JSON 输出

使用 `benchmark.v1` rows。

Probe rows 应包含：

```text
experiment = "circular_a"
record_type = "probe"
algorithm = "xyz_v2"
variant = "circular_a=<value>"
mode = "circular"
d
l
k
M
z
circular_a
successes
trials
success_rate
ci_low
ci_high
bits
bit_C_over_d
status
```

Threshold summary rows 应包含：

```text
record_type = "threshold"
best_M
best_C_over_d
final_success_rate
final_ci_low
final_ci_high
target_success_rate
threshold_policy
```

Fixed-`M` summary rows 应包含：

```text
record_type = "aggregate"
M
C_over_d
circular_a
success_rate
ci_low
ci_high
```

## 输出目录

推荐输出目录：

```text
tests/results/circular_a/
```

推荐文件：

```text
raw.jsonl
raw.csv
summary.jsonl
summary.csv
summary.md
run_config.json
errors.log
```

## CLI 设计

建议参数：

```text
--d-values
--l-values
--k-values
--a-values
--mode fixed-m|threshold
--m-values
--target-success-rate
--probe-trials
--final-trials
--trials
--ci-confidence
--threshold-policy
--skip-build
--dry-run
--limit
--output-dir
--base-seed
--max-set-size
--set-size-scale
```

Smoke 示例：

```bash
python tests/test_circular_a.py \
  --mode fixed-m \
  --d-values 100 \
  --l-values 6 \
  --k-values 2 \
  --a-values 0,0.3333333333,0.6 \
  --trials 5 \
  --limit 3 \
  --output-dir tests/results/circular_a_smoke
```

Threshold 示例：

```bash
python tests/test_circular_a.py \
  --mode threshold \
  --d-values 1000,3000 \
  --l-values 6 \
  --k-values 2 \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --probe-trials 30 \
  --final-trials 100 \
  --target-success-rate 0.95 \
  --output-dir tests/results/circular_a
```

## 结果解释

预期结果不一定有平滑、普适的最优值。最佳 `a` 可能依赖：

- `d`；
- `M`；
- `z`；
- finite-size effects；
- `RangeLength` 的整数 rounding；
- `k`。

summary 应报告：

```text
best observed a for each d/l/k
whether a = 1/3 remains competitive
whether improvements are larger than the confidence intervals
```

如果 `a = 1/3` 接近最优，就保留当前默认值，并把实验作为 sanity check。如果另一个 `a` 持续更好，也应该先确认它在多个 `d` 上都表现稳定，再修改默认值。

## 实现顺序

1. 在 `XYZ-v2/hash.cpp` 和 `XYZ-v2/hash.h` 中暴露 `circular_a`。
2. 在 `tests/benchmarks/xyz_v2_bench.cpp` 中新增 `--circular-a` 和输出字段。
3. 先实现 `tests/test_circular_a.py` 的 fixed-`M` 模式。
4. 用 `tests/json_verifier.py --strict` 校验 smoke 输出。
5. 增加 threshold-search 模式。
6. 运行主 `k = 2` threshold grid。
7. 可选运行 `k = 3,4` 的 diagnostic circular scans。

## 完成标准

这项任务完成的标准：

- 参数化实现能复现当前默认 `a = 1/3`；
- fixed-`M` 扫描能输出合法 JSON 和可读 summary；
- threshold 扫描能为代表性 `d` 找出 best observed `a`；
- 所有输出 row 都通过 strict JSON verification；
- summary 清晰说明是否值得修改 `a`。

## 当前运行状态

实现和 smoke test 已经存在，但 paper-facing 主网格还没有跑。

已完成的 smoke 覆盖：

```text
fixed-M smoke with d = 100, l = 6, k = 2
threshold smoke with tiny d/trial settings
strict JSON verification for smoke outputs
```

仍缺少：

```text
d in {1000, 3000, 10000}
k = 2
main threshold grid over a-values
optional k = 3,4 diagnostic circular scans
```
