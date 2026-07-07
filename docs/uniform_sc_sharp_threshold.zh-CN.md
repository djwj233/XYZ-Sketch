# XYZ Uniform vs Spatial-Coupling Sharp-Threshold 计划

本文档规划下面两种算法形态的 sharp-threshold 实验：

```text
XYZ-uniform
XYZ-SC
```

这里先不实现代码。目标是展示当 `M` 穿过临界区域时，解码成功率如何变化，并比较 spatial coupling 是否让转变位置左移或变得更尖锐。

## 动机

现有 threshold-search 脚本回答的是：

```text
达到目标成功率所需的最小已测试 M 是多少？
```

sharp-threshold 实验问的是另一个问题：

```text
阈值附近完整的成功率曲线长什么样？
```

如果算法存在 sharp threshold，那么在临界值附近，`M` 的小幅增加应该会让成功率快速从大多失败转为大多成功。

该实验应分别为 uniform placement 和 spatial coupling 提供图形和表格证据。

## 定义

使用 XYZ-v2 作为实现。

```text
XYZ-uniform = XYZ-v2 with --mode random
XYZ-SC = XYZ-v2 with spatial coupling enabled
```

对 `XYZ-SC`，推荐默认使用：

```text
--mode spatial
```

这会保留当前实现的自动策略：

```text
k = 2     -> circular spatial coupling
k >= 3   -> naive/non-circular spatial coupling
```

诊断实验中，脚本也应该允许显式指定 mode：

```text
--modes random,spatial
--modes random,circular
--modes random,naive
```

主要面向论文的对比应使用：

```text
random vs spatial
```

除非某个章节明确讨论 circular 或 naive 变体。

## 建议脚本

建议未来脚本：

```text
tests/test_xyz_sharp_threshold.py
```

它应复用：

```text
tests/benchmarks/xyz_v2_bench.cpp
tests/statistics.py
tests/json_schema.py
tests/dataset_generator.py
```

不应修改任何算法子项目。

## 高层实验设计

对每个配置：

```text
d, l, k, mode
```

脚本应该：

1. 估计阈值中心 `M0`。
2. 在 `M0` 附近生成密集 `M` 网格。
3. 对每个 `M` 运行 benchmark。
4. 记录每个 `M` 的成功率和置信区间。
5. 汇总阈值位置和转变宽度。

输出应支持这样的图：

```text
x-axis: C/d or M
y-axis: success_rate
bands: ci_low to ci_high
series: random vs spatial
```

## 选择阈值中心

有两个实用方案。

### 方案 A：使用已有 threshold 结果

如果已经有 `tests/results/spatial/summary.jsonl` 或其它 threshold-search 输出，可以作为输入：

```text
--threshold-summary tests/results/spatial/summary.jsonl
```

对每个 `(d, l, k, mode)`，读取：

```text
point_best_M
best_M
ci_low_best_M
```

推荐中心优先级：

```text
point_best_M if available
best_M otherwise
```

这样可以避免重复做粗略阈值搜索。

### 方案 B：脚本内部估计

如果没有提供 summary，则内部运行一次快速搜索。可以复用 `test_spatial.py` 的基本逻辑：

```text
find a working upper bound
binary search by point threshold
use that M as M0
```

第一版可以保持简单。密集扫描才是主要结果。

## 阈值附近的 M 网格

给定 `M0` 后，用相对或绝对窗口在它附近扫描。

推荐默认值：

```text
window_fraction = 0.20
min_window = 8
points = 41
```

计算：

```text
radius = max(min_window, ceil(window_fraction * M0))
M_min = max(k, ceil(d / l), M0 - radius)
M_max = M0 + radius
```

然后在 `M_min` 和 `M_max` 之间选择均匀间隔的整数值，去重并排序。

对小 `d`，网格可以每个整数都扫：

```text
step = 1
```

对更大的 `d`，使用固定点数，避免成本失控。

## 参数网格

从较聚焦的网格开始：

```text
d in {1000, 3000, 10000}
l = 6
k in {2, 3}
modes = {random, spatial}
```

如果运行时间可接受，再扩展：

```text
d in {100, 300, 1000, 3000, 10000, 30000}
l in {4, 6, 8}
k in {2, 3, 4}
modes = {random, spatial}
```

如果要做论文质量的曲线，优先：

```text
d in {3000, 10000}
l = 6
k in {2, 3}
```

这些规模足够展示阈值行为，同时仍比较可控。

## Trial 数量

sharp-threshold 图需要每个点有足够 trials。

推荐默认值：

```text
trials = 100
ci_confidence = 0.95
ci_method = wilson
```

快速 smoke test：

```text
trials = 5 or 10
```

论文质量曲线：

```text
trials >= 200 near the steep transition
```

脚本后续可以支持 adaptive trials，但第一版应使用每个点固定 trial 数。

## z 策略

对 uniform mode：

```text
z = 0
```

对 spatial modes：

```text
z = max(0, round(M^(1/3) / 3))
```

这与其它脚本当前使用的启发式一致。

脚本也应允许：

```text
--fixed-z <int>
```

用于诊断运行，但默认应保持 adaptive。

## Dataset 策略

当前 `xyz_v2_bench` 支持内部生成和可选 dataset files。该实验可以接受两种模式：

```text
internal_generator
shared_file
```

推荐第一版：

```text
dataset_mode = internal_generator
```

原因：现有 threshold-search 脚本使用 internal generation，sharp-threshold 脚本第一版应先匹配它们的行为。

后续再加入：

```text
--dataset-mode shared_file
```

以复用 `tests/dataset_generator.py`，让 random-vs-spatial 曲线使用完全相同的 per-trial datasets。

## 输出文件

推荐输出目录：

```text
tests/results/xyz_sharp_threshold/
```

文件：

```text
raw.jsonl
raw.csv
summary.jsonl
summary.csv
summary.md
run_config.json
errors.log
```

`raw.jsonl` 应包含每个 `(d, l, k, mode, M)` 扫描点的一行。

使用：

```text
schema_version = benchmark.v1
experiment = xyz_sharp_threshold
record_type = aggregate
algorithm = xyz_v2
variant = mode
```

## Raw Row 字段

每个 raw row 应包含：

```text
d
l
k
M
z
mode
ca
cb
seed
trials
successes
success_rate
ci_low
ci_high
ci_method
ci_confidence
bits
bits_per_difference
bit_C_over_d
field_C_over_d
encode_avg_s
decode_avg_s
encode_median_s
decode_median_s
dataset_mode
status
```

额外字段：

```text
scan_id
M0
M_offset
C_over_d_offset
grid_index
grid_size
threshold_source
```

## Summary 指标

对每个 `(d, l, k, mode)` 汇总：

```text
point_M_50
point_M_95
ci_low_M_95
transition_M_min
transition_M_max
transition_width_M
transition_C_over_d_min
transition_C_over_d_max
transition_width_C_over_d
max_slope
```

定义：

```text
point_M_50 = success_rate >= 0.50 的最小 M
point_M_95 = success_rate >= 0.95 的最小 M
ci_low_M_95 = ci_low >= 0.95 的最小 M
transition_M_min = ci_high >= 0.10 的最小 M
transition_M_max = ci_low >= 0.90 的最小 M
transition_width_M = transition_M_max - transition_M_min
```

`max_slope` 可以从相邻扫描点估计：

```text
delta success_rate / delta C_over_d
```

这些是经验描述，不是理论证明。

## 比较 Uniform 和 SC

对每个 `(d, l, k)`，比较：

```text
uniform_M_95
sc_M_95
uniform_C_over_d_95
sc_C_over_d_95
relative_improvement = (uniform_C_over_d_95 - sc_C_over_d_95) / uniform_C_over_d_95
transition_width_uniform
transition_width_sc
```

预期解释：

- 如果 SC 符合预期，它的曲线应该左移，即需要更小的 `C/d`。
- 转变也可能更尖锐，但这是经验问题。
- 如果曲线大量重叠，则应报告该配置下 spatial coupling 没有清晰改善。

## CLI 草案

推荐 CLI：

```powershell
python tests\test_xyz_sharp_threshold.py ^
  --d-values 1000,3000,10000 ^
  --l-values 6 ^
  --k-values 2,3 ^
  --modes random,spatial ^
  --trials 100 ^
  --ci-confidence 0.95 ^
  --threshold-summary tests\results\spatial\summary.jsonl ^
  --output-dir tests\results\xyz_sharp_threshold
```

Smoke test：

```powershell
python tests\test_xyz_sharp_threshold.py ^
  --d-values 100 ^
  --l-values 6 ^
  --k-values 2 ^
  --modes random,spatial ^
  --trials 5 ^
  --points 7 ^
  --output-dir tests\results\xyz_sharp_threshold_smoke ^
  --skip-build
```

## 测试计划

### Dry Run

```powershell
python tests\test_xyz_sharp_threshold.py --dry-run --d-values 100 --l-values 6 --k-values 2 --modes random,spatial --points 7
```

预期：

```text
打印计划扫描点
显示每个 mode 的 M0 和 M grid
不运行 benchmark
```

### Smoke Run

运行上面的 smoke command。

然后校验：

```powershell
python tests\json_verifier.py tests\results\xyz_sharp_threshold_smoke\raw.jsonl --strict
```

预期：

```text
random 和 spatial 都产生 rows
success_rate 通常随 M 增加，允许有噪声
CI 字段存在且合法
summary files 被写出
```

### 一致性检查

当测得的 success 非单调时，脚本应该 warn，而不是 fail。有限 trials 下非单调是可能的。

有用的 warning：

```text
相邻 M 的 success_rate 下降超过 0.30
没有任何点达到 0.50
没有任何点达到 0.95
所有点 success_rate = 1.0，说明网格过高
所有点 success_rate = 0.0，说明网格过低
```

## 画图计划

第一版脚本不需要生成图，但输出应该能直接用于画图。

后续推荐图：

```text
one panel per (d, l, k)
x-axis = C/d
y-axis = success_rate
line = mode
ribbon = [ci_low, ci_high]
vertical marker = point_M_95 or ci_low_M_95
```

summary table 应在画图前就提供论文可用的数值。

## 风险

1. 如果 `M0` 估计不好，密集网格可能错过转变区。
   - 缓解：检测 all-zero/all-one 曲线，并建议扩大窗口。
2. 成功率可能有噪声。
   - 缓解：使用 Wilson 区间和足够 trials。
3. `random` 可能比 `spatial` 需要大得多的 `M`。
   - 缓解：每个 mode 分别估计 `M0`，不要共享一个中心。
4. `spatial` 是自动 mode。
   - 缓解：同时记录 `mode` 和显式 `z`；必要时运行显式 `circular`/`naive` 诊断。

## 完成标准

该任务完成时应满足：

```text
tests/test_xyz_sharp_threshold.py 存在
它能围绕每个 mode 自己的 M0 扫描 random 和 spatial modes
raw rows 使用 benchmark.v1 并包含 CI 字段
summary rows 标出 50%、95% 和 CI-lower-bound thresholds
strict JSON verification 通过
smoke run 完成
输出足以绘制 success-rate-vs-C/d 曲线
```
