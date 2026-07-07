# IBLT Uniform vs Spatial-Coupling 对比计划

本文档规划如何加入 IBLT-uniform 和 IBLT-SC 对比。这里先不实现代码。

目标是在 IBLT 算法族内部比较 spatial coupling 的效果，方式与现有 XYZ-uniform vs XYZ-SC 实验保持一致。

## 当前状态

仓库当前已有：

```text
IBLT/iblt.cpp
tests/benchmarks/iblt_bench.cpp
tests/test_compare_basic.py
```

本地 IBLT 实现是标准 uniform-placement IBLT：

```text
每个 item 更新 hash_count 个 cell，这些 cell 均匀选自 [0, cell_count)
```

`tests/benchmarks/iblt_bench.cpp` 暴露：

```text
--d
--trials
--seed
--ca
--cb
--capacity-factor
--dataset
--format jsonl
```

它目前没有 placement mode。因此现有 local IBLT rows 应解释为：

```text
IBLT-uniform
```

## 目标

加入受控对比：

```text
IBLT-uniform
IBLT-SC
```

两种变体应使用：

```text
相同 cell 结构
相同 peeling decoder
尽量相同 hash count
相同输入数据集
相同通信量统计方式
```

唯一应该变化的是 item-to-cell placement rule。

## 重要约束

不要修改算法子项目文件：

```text
IBLT/
external/
XYZ-v1/
XYZ-v2/
```

任何新的 benchmark 或实验实现都应放在：

```text
tests/
tests/benchmarks/
```

这样可以保持子模块和参考实现干净。

## 定义

### IBLT-uniform

当前 local IBLT 行为：

```text
h_i(x) = uniform hash into [0, N)
```

其中：

```text
N = ceil(capacity_factor * d)
```

每个 item 更新 `hash_count` 个 cell。

### IBLT-SC

一种 spatially coupled IBLT placement rule。

使用：

```text
g0(x): base position
g_i(x): offset inside a coupling window
h_i(x): g0(x) + g_i(x)
```

推荐第一版实现：

```text
non-circular spatial coupling
```

其中：

```text
g0(x) in [0, N - W]
offset_i(x) in [0, W)
h_i(x) = g0(x) + offset_i(x)
```

这里：

```text
N = total cell count
W = coupling window size
```

窗口可以由 `z` 参数控制：

```text
W = max(hash_count, floor(N / (z + 1)))
```

这与现有 XYZ 脚本中的含义类似：更大的 `z` 表示更小的 coupled range。

后续 benchmark 也可以支持 circular SC：

```text
h_i(x) = (g0(x) + offset_i(x)) mod N
```

但第一轮 IBLT-SC 对比应使用一个主要 SC 规则，避免解释混乱。

## 实现策略

创建新的 benchmark wrapper，例如：

```text
tests/benchmarks/iblt_sc_bench.cpp
```

该文件应包含测试侧 IBLT 实现，或一个小 wrapper class，复刻本地 IBLT 的 cell 操作：

```text
count
key_sum
key_check
```

之所以新建 wrapper，而不是修改 `IBLT/iblt.cpp`，是因为当前 IBLT class 隐藏了 hash 函数和 cell update 位置。Spatial coupling 改的正是这一层。

新 wrapper 应暴露：

```text
--mode uniform|spatial
--capacity-factor F
--hash-count K
--z Z
--dataset PATH
```

对 `--mode uniform`，它应尽量复现当前 `iblt_bench.cpp` 行为，作为一致性检查。

对 `--mode spatial`，它应使用 SC placement rule。

## 通信量统计

保持和 local IBLT benchmark 相同的 cell layout：

```text
cell = tuple<int, uint32_t, uint32_t>
cell_bits = sizeof(cell) * 8
bits = cell_count * cell_bits
bit_C_over_d = bits / (32 * d)
```

报告：

```text
cells
cell_bits
hash_count
capacity_factor
bits
bits_per_difference
bit_C_over_d
```

这样 IBLT-uniform 和 IBLT-SC 可以直接比较。

## 脚本设计

建议脚本：

```text
tests/test_iblt_spatial.py
```

它应是 threshold-search 风格脚本，类似 `tests/test_spatial.py`，但用于 IBLT。

对每个配置：

```text
d, mode, hash_count, target_success_rate
```

搜索达到目标成功率所需的最小 `capacity_factor` 或 `cell_count`。

推荐搜索变量：

```text
cell_count
```

因为 `capacity_factor` 是派生值：

```text
capacity_factor = cell_count / d
```

不过 CLI 可以暴露更友好的 factor bounds：

```text
--min-capacity-factor
--max-capacity-factor
```

内部使用：

```text
lo = ceil(min_capacity_factor * d)
hi = ceil(max_capacity_factor * d)
```

## 为什么搜索 Cell Count 而不是固定 Factors？

固定 factor 网格适合 smoke test：

```text
capacity_factor in {1.0, 1.2, 1.5, 2.0, 2.5}
```

但公平的 SC 对比应该报告达到同一目标成功率所需的最小通信量。

因此：

```text
fixed-grid mode = diagnostic
threshold-search mode = main result
```

## 参数网格

从小规模开始：

```text
d in {100, 300, 1000}
modes = {uniform, spatial}
hash_count = auto
target_success_rate = 0.95
probe_trials = 20
final_trials = 100
```

之后扩展：

```text
d in {1000, 3000, 10000, 30000}
modes = {uniform, spatial}
hash_count in {3, 4}
target_success_rate in {0.95, 0.99}
```

尽可能使用 shared datasets：

```text
dataset_mode = shared_file
```

这很重要，因为 IBLT-uniform 和 IBLT-SC 应在完全相同的 Alice/Bob sets 上测试。

## Hash Count 策略

当前 local IBLT 使用：

```text
d < 200 -> hash_count = 4
d >= 200 -> hash_count = 3
```

新 benchmark 应支持：

```text
--hash-count auto
--hash-count 3
--hash-count 4
```

推荐第一轮对比：

```text
hash_count = auto
```

之后再加入显式 `3` 和 `4` 作为诊断实验。

## z / Window 策略

对 uniform mode：

```text
z = 0
```

对 spatial mode：

```text
z = max(0, round(cell_count^(1/3) / 3))
```

脚本也应允许：

```text
--fixed-z Z
```

raw output 必须记录：

```text
z
window_size
```

这样后续才能解释结果。

## JSON 输出

使用 `benchmark.v1`。

推荐 experiment name：

```text
iblt_spatial_threshold
```

Probe rows：

```text
record_type = "probe"
algorithm = "iblt"
variant = "uniform" or "spatial"
implementation = "tests/benchmarks/iblt_sc_bench"
```

Summary rows：

```text
record_type = "threshold"
```

必需字段：

```text
d
ca
cb
seed
dataset_mode
mode
capacity_factor
cells
hash_count
cell_bits
z
window_size
trials
successes
success_rate
ci_low
ci_high
bits
bits_per_difference
bit_C_over_d
encode_avg_s
decode_avg_s
status
```

## 输出文件

推荐输出目录：

```text
tests/results/iblt_spatial/
```

文件：

```text
probes.jsonl
summary.jsonl
summary.csv
summary.md
run_config.json
errors.log
```

summary 应并排比较 uniform 和 spatial：

```text
d
hash_count
uniform_cell_count
spatial_cell_count
uniform_bit_C_over_d
spatial_bit_C_over_d
relative_improvement
uniform_ci_low
spatial_ci_low
```

## Smoke Tests

### Benchmark Wrapper Smoke

实现 wrapper 后：

```powershell
build\iblt_sc_bench.exe --d 100 --trials 5 --seed 114514 --ca 1000 --cb 1000 --mode uniform --capacity-factor 2.0 --hash-count auto --format jsonl
build\iblt_sc_bench.exe --d 100 --trials 5 --seed 114514 --ca 1000 --cb 1000 --mode spatial --capacity-factor 2.0 --hash-count auto --z 1 --format jsonl
```

预期：

```text
两者都输出合法 JSON
uniform output 接近现有 iblt_bench 行为
spatial output 记录 z 和 window_size
```

### Script Smoke

```powershell
python tests\test_iblt_spatial.py ^
  --d-values 100 ^
  --modes uniform,spatial ^
  --probe-trials 5 ^
  --final-trials 10 ^
  --target-success-rate 0.95 ^
  --output-dir tests\results\iblt_spatial_smoke
```

然后校验：

```powershell
python tests\json_verifier.py tests\results\iblt_spatial_smoke\probes.jsonl tests\results\iblt_spatial_smoke\summary.jsonl --strict
```

## 正确性检查

实现应检查：

```text
decoded Alice-only set equals expected Alice-only set
decoded Bob-only set equals expected Bob-only set
相同 capacity_factor 下 uniform 和 spatial 的 cell_count 相同
bits 从 cell_count * cell_bits 计算
不同 modes 复用同一批 shared datasets
```

对 `uniform` mode，用若干运行和现有 `tests/benchmarks/iblt_bench.cpp` 比较。运行时间不必完全一致，但在相同 hash count 和 cell count 下，成功率和通信量统计应该接近或一致。

## 结果解释

可能结果：

1. IBLT-SC 比 IBLT-uniform 需要更少 cells。
   - 这支持 spatial coupling 的收益不只属于 XYZ。
2. IBLT-SC 和 uniform 类似。
   - 这说明 spatial-coupling 收益可能依赖 XYZ 的代数/cell 结构。
3. IBLT-SC 更差。
   - 这也有价值；应报告为 SC rule 并不会自动改善所有 peeling-based sketch。

不要假设 XYZ-SC 的改善会自动转移到 IBLT。实验应给出经验答案。

## 风险

1. SC placement rule 可能产生边界效应。
   - 记录 mode 是 circular 还是 non-circular。
2. Peeling 在局部耦合下的行为可能不同于 XYZ。
   - 报告完整 success curve 或 threshold summary，不只看单点。
3. hash 函数变化可能意外改变 baseline。
   - 保留 uniform-mode 与现有 IBLT benchmark 的一致性检查。
4. 通信量统计可能不一致。
   - 固定 cell layout，并报告 `cell_bits`。

## 完成标准

该任务完成时应满足：

```text
tests/benchmarks/iblt_sc_bench.cpp 存在
tests/test_iblt_spatial.py 存在
uniform 和 spatial modes 在相同 datasets 上运行
probe 和 summary 输出使用 benchmark.v1
记录 CI 字段
strict JSON verification 通过
summary 报告 spatial 相对 uniform 的 improvement
现有 IBLT-uniform 行为被保留为对照点
```
