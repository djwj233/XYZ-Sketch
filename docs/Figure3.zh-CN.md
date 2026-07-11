# Figure 3 规划

本文档规划论文 Figure 3 的实验 pipeline。

Figure 3 用按启发式公式计算 `(a,z)` 的 XYZ-Sketch 与实用 set-reconciliation baselines 进行对比，并在同一批 shared workloads 上报告通信量、update cost 和 decode cost。Figure 2 输出的 tuned `(a,z)` 策略作为可选输入保留，后续可以通过 `--xyz-tuning` 切回。

## 共享实验设置

统一使用论文实验设置：

```text
A, B subset U
large common part
|A symmetric-difference B| = d
w = log2(V) = 30
R = sketch_length_bits / (d * w)
target_success_rate = 0.9
confidence_interval = 95%
```

所有算法都应运行在同一批 shared paired datasets 上：

```text
dataset_mode = shared_file
```

默认 XYZ 设置：

```text
algorithm = xyz_v2
k = 2
l = 6
mode = circular
a,z = heuristic formulas with C=1/3, D=4/3
```

如果 Figure 2 暂时还没有稳定调参结果，使用有记录的 fallback：

```text
a = 0
z = max(0, round(M^(1/3) / 3))
```

或者使用已完成的最大 Figure 2 grid 中的最佳 `(a,z)`。

## 参赛算法

主要算法：

```text
xyz_v2
iblt
minisketch
```

可选 baseline：

```text
xyz_v1
iblt_cpp
cpisync
riblt
negentropy
```

推荐论文策略：

- 主图只包含当前环境中真实、可构建、稳定的 baseline。
- appendix 或 caveat table 可以列出 unavailable/optional baseline，并显式记录 `status` 和 `unavailable_reason`。
- 论文图中不能把真实 baseline 静默替换成 stub。

## 当前支持

已有可复用脚本：

```text
tests/test_compare_basic.py
tests/test_frontier_xyz.py
tests/test_az_grid.py
tests/extract_fig2_z_star.py
tests/dataset_generator.py
```

已有 benchmark wrappers：

```text
tests/benchmarks/xyz_v2_bench.cpp
tests/benchmarks/xyz_v1_bench.cpp
tests/benchmarks/iblt_bench.cpp
tests/benchmarks/iblt_cpp_bench.cpp
tests/benchmarks/minisketch_bench.cpp
tests/benchmarks/cpisync_bench.cpp
tests/benchmarks/riblt_bench.go
tests/benchmarks/negentropy_bench.cpp
```

当前能力：

- `test_compare_basic.py` 可以构建并运行多个算法。
- 它已使用 shared paired datasets。
- 它写出 normalized JSON rows。
- 它记录 `bits`、`success_rate`、`encode_avg_s` 和 `decode_avg_s`。
- 若干 external baselines 已有真实 wrapper 或 optional/unavailable wrapper。

本次实现已经解决：

- `tests/test_compare_frontier.py` 已能对主要算法做 per-algorithm frontier search。
- frontier 脚本现在支持 `xyz_v1`、`xyz_v2`、`iblt`、`minisketch`、`cpisync`、`riblt` 和 `negentropy`。
- 脚本使用 shared paired datasets，并写出 `benchmark.v1` probes/summaries。
- 脚本会派生 `best_R_w30`、`update_avg_s_per_element` 和 `decode_avg_s_per_difference`。
- 默认不传 `--xyz-tuning`，脚本按公式计算 `a,z`；需要时仍可通过 `--xyz-tuning` 消费 Figure 2 的调参结果。

剩余缺口：

- `xyz_v1` 和 `riblt` 已接入 `test_compare_frontier.py`；`xyz_v1` 当前 wrapper 没有容量参数，因此作为固定参数 baseline；`riblt` 使用 `max_symbols` 搜索。`iblt_cpp` 已能通过 `test_compare_basic.py` smoke run，但尚未接入 frontier search。
- 已实现无依赖 SVG 绘图脚本 `tests/plot_figure3.py`。PNG/PDF 导出仍需要 matplotlib 后端或 SVG 转换步骤。

## Figure 3(a): Communication Frontier

### 目标

对每个算法和每个 `d`，找到达到 90% 成功率的最小通信量 `R_w30`。

图像定义：

```text
x-axis = d
y-axis = R_w30 at target_success_rate = 0.9
curves = algorithms
error bars/bands = threshold uncertainty / confidence intervals
```

预期结果：

- XYZ 应该展示较好的 communication/performance trade-off。
- minisketch 应该是强 set reconciliation baseline。
- IBLT variants 应该可用，但通常需要更多通信。

### 实现计划

已实现新的 paper-facing 脚本：

```text
tests/test_compare_frontier.py
```

职责：

1. 构建或定位选中算法的 benchmark binaries。
2. 对每个 `(d, seed, trial)` 只生成一次 shared dataset。
3. 对每个算法和 `d`，搜索达到 `target_success_rate = 0.9` 的最小通信参数。
4. 使用 `final_trials` 对选中参数做最终验证。
5. 将结果规范化为 `benchmark.v1`。
6. 派生 `R_w30 = bits / (30*d)`。
7. 记录 threshold uncertainty 字段。

### 有限 final retry

frontier runner 现在支持一个可选的 near-miss 修补步骤。目标是在保留当前二分搜索低开销
的同时，避免很多点只是因为参数略激进就停留在 unresolved。

策略：

```text
1. 正常搜索，得到 search_parameter。
2. 在 held-out final datasets 上做 final validation。
3. 如果 final_success_rate >= target_success_rate，接受该点。
4. 如果 final_success_rate 低于 final_retry_min_success_rate，保持 unresolved。
5. 否则把搜索得到的参数乘以 final_retry_growth，并重新做 final validation，最多
   重复 final_retry_limit 次。
```

推荐 smoke-run 设置：

```bash
--final-retry-algorithms xyz_v2,iblt,riblt
--final-retry-growth 1.05
--final-retry-limit 4
--final-retry-min-success-rate 0.75
```

这样每个 near-miss 点最多多跑四次 final validation，最终参数最多约为二分候选点的
`1.05^4 = 1.216` 倍。该策略适合 `xyz_v2`、`iblt` 和 `riblt`，不适合
`minisketch`、`cpisync` 这类固定参数 baseline。

summary 同时记录原始搜索结果和最终接受参数：

```text
search_parameter
best_parameter
final_retry_count
final_parameter_offset
final_parameter_multiplier
```

这是一个实用的 smoke-run 修补策略。论文质量的 estimator 仍应使用 capacity grid、
isotonic success-rate fitting 和 bootstrap confidence intervals。

推荐搜索参数：

```text
xyz_v2:
  search M
  fixed k = 2, l = 6
  fixed mode = circular
  use heuristic a,z policy by default

iblt:
  search capacity_factor or cells

minisketch:
  search capacity_factor
  field_bits = 30

iblt_cpp:
  search capacity_factor

cpisync:
  search mbar or mbar_factor

riblt:
  search capacity_factor or symbol count if wrapper supports it

negentropy:
  search implementation-specific capacity/byte budget if supported;
  otherwise report a fixed real run with caveat
```

第一版已经支持：

```text
xyz_v1, xyz_v2, iblt, minisketch, cpisync, riblt, negentropy
```

`cpisync` 使用 `mbar` 做 frontier 参数搜索；`negentropy` 使用 `frame_size_limit` 做 interactive frame-budget 搜索，图中纵轴仍使用实际总通信量。

### 输出目录

推荐输出目录：

```text
tests/results/paper_fig3_compare_frontier/
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

重要 summary 字段：

```text
experiment = paper_fig3_compare_frontier
record_type = threshold
algorithm
variant
d
best_parameter
best_parameter_name
search_parameter
final_retry_count
final_parameter_offset
final_parameter_multiplier
best_R_w30
best_bits
target_success_rate
final_success_rate
final_ci_low
final_ci_high
threshold_policy
dataset_mode
status
unavailable_reason
```

## Figure 3(b): Update Cost

### 目标

比较平均 update/build cost per input element。

图像定义：

```text
x-axis = d
y-axis = update_avg_s_per_element
curves = algorithms
```

推荐定义：

```text
update_denominator = ca + cb
update_avg_s_per_element = encode_avg_s / update_denominator
```

原因：

- 当前大多数 benchmark wrappers 在一次 run 中构建 Alice 和 Bob 两侧 sketch。
- 使用 `ca + cb` 能在算法之间保持一致。
- 如果未来某个 wrapper 只计 Alice，需要显式记录 `update_denominator = ca`。

在 `test_compare_frontier.py` 中新增或派生：

```text
update_avg_s_per_element
update_denominator
update_metric_policy = encode_avg_s/(ca+cb)
```

如果某个算法没有有意义的 update time，保留 row，但标记：

```text
update_status = unavailable
```

## Figure 3(c): Decode Cost

### 目标

比较 amortized decode/reconciliation cost per difference。

图像定义：

```text
x-axis = d
y-axis = decode_avg_s_per_difference
curves = algorithms
```

推荐定义：

```text
decode_avg_s_per_difference = decode_avg_s / d
decode_denominator = d
```

对 cpisync/negentropy 这类 interactive protocols，wrapper 可能把完整 reconciliation time 报告为 `decode_avg_s`。这可以接受，但必须文档化：

```text
decode_metric_policy = decode_or_reconcile_avg_s/d
```

新增或派生字段：

```text
decode_avg_s_per_difference
decode_denominator
decode_metric_policy
```

## 参数网格

Smoke：

```text
d in {100, 300}
algorithms = xyz_v1, xyz_v2, iblt, minisketch, cpisync, riblt, negentropy
probe_trials = 5
final_trials = 10
target_success_rate = 0.9
```

论文规模：

```text
d in {100, 300, 1000, 3000, 10000}
algorithms = xyz_v1, xyz_v2, iblt, minisketch, cpisync, riblt, negentropy
probe_trials >= 30
final_trials >= 100
target_success_rate = 0.9
confidence_interval = 95%
```

如果运行时间允许：

```text
add iblt_cpp to frontier search
```

## 从 Figure 2 读取调参

`test_compare_frontier.py` 应接受：

```text
--a-constant 0.3333333333
--z-constant 1.3333333333
```

策略：

- 对每个 `d`，如果 tuning 文件中有精确 `(a_star,z_star)`，则直接使用。
- 如果某个 `d` 缺失，使用最近的更小 `d`；若不存在，则使用最近的可用 `d`。
- 记录：

```text
xyz_tuning_source
xyz_circular_a
xyz_z
xyz_tuning_d
```

如果没有提供 tuning 文件：

```text
xyz_circular_a = 0
xyz_z_policy = round(M^(1/3)/3)
```

## 绘图计划

已实现第一版无依赖绘图脚本：

```text
tests/plot_figure3.py
```

它读取 frontier `summary.csv` 并写出 SVG 图。

后续可以创建或扩展：

```text
tests/plot_paper_figures.py
```

输入：

```text
tests/results/paper_fig3_compare_frontier/summary.csv
```

输出：

```text
tests/results/paper_figures/figure3a_communication.pdf
tests/results/paper_figures/figure3a_communication.png
tests/results/paper_figures/figure3b_update_cost.pdf
tests/results/paper_figures/figure3b_update_cost.png
tests/results/paper_figures/figure3c_decode_cost.pdf
tests/results/paper_figures/figure3c_decode_cost.png
```

当前已实现的 SVG 输出：

```text
tests/results/paper_figures/figure3a_communication.svg
tests/results/paper_figures/figure3b_update_cost.svg
tests/results/paper_figures/figure3c_decode_cost.svg
tests/results/paper_figures/figure3_source_summary.md
```

绘图规则：

- 横轴 `d` 使用 log-scale。
- Figure 3(a) 使用 `best_R_w30`。
- Figure 3(b) 使用 `update_avg_s_per_element`。
- Figure 3(c) 使用 `decode_avg_s_per_difference`。
- 主曲线排除 `status != ok` 的 row，但在 source summary 中记录被跳过的 row。
- 同时保存 `.pdf` 和 `.png`。

## 验证

绘图前运行：

```powershell
python tests\json_verifier.py tests\results\paper_fig3_compare_frontier\probes.jsonl --strict
python tests\json_verifier.py tests\results\paper_fig3_compare_frontier\summary.jsonl --strict
```

人工检查：

- 所有论文 row 使用 `target_success_rate = 0.9`。
- 所有论文 row 使用 `ci_confidence = 0.95`。
- 所有成功论文 row 使用 `dataset_mode = shared_file`。
- `best_R_w30 = best_bits / (30*d)`。
- 选中的 XYZ `(a,z)` 已被记录。
- unavailable external baselines 不应作为零成本点混入主曲线。

## 建议命令

Smoke：

```powershell
python tests\test_compare_frontier.py `
  --d-values 100,300 `
  --algorithms xyz_v1,xyz_v2,iblt,minisketch,cpisync,riblt,negentropy `
  --probe-trials 5 `
  --final-trials 10 `
  --target-success-rate 0.9 `
  --job-timeout-s 1800 `
  --a-constant 0.3333333333 `
  --z-constant 1.3333333333 `
  --output-dir tests\results\paper_fig3_compare_frontier_smoke
```

论文规模：

```powershell
python tests\test_compare_frontier.py `
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 `
  --algorithms xyz_v1,xyz_v2,iblt,minisketch,cpisync,riblt,negentropy `
  --probe-trials 30 `
  --final-trials 100 `
  --target-success-rate 0.9 `
  --job-timeout-s 1800 `
  --a-constant 0.3333333333 `
  --z-constant 1.3333333333 `
  --output-dir tests\results\paper_fig3_compare_frontier
```

当前已支持的扩展 baseline 运行：

```powershell
python tests\test_compare_frontier.py `
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 `
  --algorithms xyz_v1,xyz_v2,iblt,minisketch,cpisync,riblt,negentropy `
  --probe-trials 30 `
  --final-trials 100 `
  --target-success-rate 0.9 `
  --job-timeout-s 1800 `
  --a-constant 0.3333333333 `
  --z-constant 1.3333333333 `
  --output-dir tests\results\paper_fig3_compare_frontier_extended
```

## 当前状态

```text
Figure 3(a): primary data generation implemented
  tests/test_compare_frontier.py 已能为 xyz_v1、xyz_v2、iblt、minisketch、cpisync、riblt 和 negentropy 运行 per-algorithm threshold/frontier search。
  xyz_v1、cpisync、riblt 和 negentropy 已接入；iblt_cpp 仍需接入 frontier search。

Figure 3(b): primary data generation implemented
  tests/test_compare_frontier.py 已派生 update_avg_s_per_element。

Figure 3(c): primary data generation implemented
  tests/test_compare_frontier.py 已派生 decode_avg_s_per_difference。

Plotting: partial
  tests/plot_figure3.py 已能生成无依赖 SVG 图。
  PNG/PDF 导出仍未实现。
```
