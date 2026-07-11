# Figure 1 规划

本文档规划并记录 Figure 1 的论文实验 pipeline。Figure 1 的目标是证明 XYZ-Sketch 具有 sharp-threshold 行为，并展示 spatial coupling 对通信 frontier 的改进。

## 共享实验设置

统一使用论文中的实验设置：

```text
A, B subset U
large common part
|A symmetric-difference B| = d
w = log2(V) = 30
R = sketch_length_bits / (d * w)
target_success_rate = 0.9
confidence_interval = 95%
```

现有 benchmark row 已经报告：

```text
bits
bit_C_over_d = bits / (32*d)
success_rate
ci_low
ci_high
encode_avg_s
decode_avg_s
```

Figure 1 额外使用：

```text
R_w30 = bits / (30*d)
```

## Tuples 和 Modes

代表性参数组：

```text
(k,l) in {(2,3), (2,6), (3,4)}
```

默认使用：

```text
a = C * c_orient / c_peel，其中 C = 1/3
```

mode 映射：

```text
iid / uniform -> mode=random
SC            -> mode=naive
```

如果后续要把 circularized SC 放进 Figure 1，则使用：

```text
默认不传 `--circular-a`；如需手动覆盖 circular 参数时才使用 `--circular-a`。Figure 1 默认按 `a=C*c_orient/c_peel` 计算，`C=1/3`，并按公式计算 `z`，`D=4/3`。
```

## Figure 1(a): Sharp Threshold

目标：展示 success rate 随通信量 `R_w30` 的变化。

图像定义：

```text
x-axis = R_w30
y-axis = success_rate
curves = {(k,l)} x {iid, SC-naive, SC-circular}
error bars/bands = 95% CI
```

预期结果：

- 每条曲线都出现 sharp threshold。
- SC 相比 iid 的 threshold 应该更低。

当前实现入口：

```text
tests/test_xyz_sharp_threshold.py
```

已经补充的 Figure 1 字段：

```text
R_w30
point_M_90
point_R_w30_90
ci_low_M_90
ci_low_R_w30_90
circular_a
```

smoke 级运行示例：

```powershell
python tests\test_xyz_sharp_threshold.py `
  --d-values 1000 `
  --tuple-values 2:3,2:6,3:4 `
  --modes random,naive,circular `
  --trials 30 `
  --center-trials 10 `
  --window-fraction 0.06 `
  --min-window 20 `
  --max-window 80 `
  --step 3 `
  --target-success-rate 0.9 `
  --a-constant 0.3333333333 `
  --z-constant 1.3333333333 `
  --output-dir tests\results\paper_fig1_sharp_threshold
```

上面的命令使用 `--tuple-values`，因此只会运行 `(2,3)`、`(2,6)` 和 `(3,4)`。

论文规模建议：

```text
d = 10000 or larger if runtime allows
(k,l) in {(2,3), (2,6), (3,4)}
modes = random,naive,circular
trials >= 100
center_trials = 10
window_fraction = 0.06
min_window = 20
max_window = 120
step = 2
confidence = 0.95
```

新的推荐设置会在经验中心 `M0` 附近扫描更窄的区间，并用更小步长测试更多相邻
`M`。如果结果曲线两端没有同时出现明显失败和明显成功，需要优先增大
`max_window`，而不是单纯增加点数。

输出：

```text
tests/results/paper_fig1_sharp_threshold/raw.jsonl
tests/results/paper_fig1_sharp_threshold/summary.jsonl
tests/results/paper_fig1_sharp_threshold/summary.csv
tests/results/paper_fig1_sharp_threshold/summary.md
tests/results/paper_fig1_sharp_threshold/run_config.json
```

## Figure 1(b): Communication Frontier

目标：展示随着 `d` 增大，达到 90% 成功率所需的最小通信量 `R_w30`。

图像定义：

```text
x-axis = d
y-axis = R_w30 at target_success_rate = 0.9
curves = {(k,l,a)} x {iid, SC-naive, SC-circular}
error bars/bands = threshold uncertainty / success-rate CI
```

预期结果：

- 曲线随 `d` 增大逐渐接近极限值。
- SC 应该低于 iid。
- 数值应接近理论预测。

当前实现入口：

```text
tests/test_frontier_xyz.py
```

这个脚本是 Figure 1(b) 的 paper-facing wrapper。它会对指定 tuple 分 shard 调用：

```text
tests/test_spatial.py
```

然后合并输出到统一目录。这样二分搜索、shared dataset、Wilson CI 和 dedup-hash 逻辑仍然只有一份实现。

该 wrapper 默认启用 shared paired dataset，以保证 iid 和 SC 在同一组数据上比较。如果只是快速调试，可以额外加：

```text
--no-shared-datasets
```

smoke 级运行示例：

```powershell
python tests\test_frontier_xyz.py `
  --d-values 100,300,1000 `
  --tuple-values 2:6 `
  --modes random,naive,circular `
  --probe-trials 20 `
  --final-trials 50 `
  --target-success-rate 0.9 `
  --a-constant 0.3333333333 `
  --z-constant 1.3333333333 `
  --output-dir tests\results\paper_fig1_frontier
```

论文规模建议：

```text
d in {100, 300, 1000, 3000, 10000, 30000, 100000, 300000, 1000000, 3000000, 10000000}
(k,l) in {(2,3), (2,6), (3,4)}
a and z are computed from the theory constants with C=1/3 and D=4/3
modes = random,naive,circular
target_success_rate = 0.9
probe_trials >= 50
final_trials >= 100
```

对应命令：

```powershell
python tests\test_frontier_xyz.py `
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 `
  --tuple-values 2:3,2:6,3:4 `
  --modes random,naive,circular `
  --probe-trials 50 `
  --final-trials 100 `
  --target-success-rate 0.9 `
  --a-constant 0.3333333333 `
  --z-constant 1.3333333333 `
  --output-dir tests\results\paper_fig1_frontier
```

输出：

```text
tests/results/paper_fig1_frontier/probes.jsonl
tests/results/paper_fig1_frontier/summary.jsonl
tests/results/paper_fig1_frontier/summary.csv
tests/results/paper_fig1_frontier/summary.md
tests/results/paper_fig1_frontier/run_config.json
```

## 绘图要求

后续绘图脚本建议命名为：

```text
tests/plot_figure1.py
```

它应当：

- 读取 Figure 1(a) 的 `raw.jsonl` 和 Figure 1(b) 的 `summary.jsonl`。
- 如果缺少 `R_w30`，计算 `R_w30 = bits / (30*d)`。
- 按 `(k,l,mode)` 或 `(k,l,a,mode)` 分组。
- 绘制 95% CI band 或 error bar。
- 同时保存 `.pdf` 和 `.png`。
- 写出 `figure1_source_summary.md` 记录输入文件和命令。

## 验证

使用 Figure 1 数据前，运行 strict JSON verifier：

```powershell
python tests\json_verifier.py tests\results\paper_fig1_sharp_threshold\raw.jsonl --strict
python tests\json_verifier.py tests\results\paper_fig1_sharp_threshold\summary.jsonl --strict
python tests\json_verifier.py tests\results\paper_fig1_frontier\probes.jsonl --strict
python tests\json_verifier.py tests\results\paper_fig1_frontier\summary.jsonl --strict
```

还需要人工检查：

- 所有 row 使用 `target_success_rate = 0.9`。
- 所有 row 使用 `ci_confidence = 0.95`。
- `random = iid`，`naive/circular = SC variants` 的 mode 映射在图注或实验说明中写清楚。
- 每条 sharp-threshold 曲线都有足够的失败点和成功点，否则需要扩大扫描窗口。

## 当前状态

```text
Figure 1(a): implemented for data generation
  tests/test_xyz_sharp_threshold.py 已支持 R_w30、target 0.9 summary 和 circular_a。

Figure 1(b): implemented for data generation
  tests/test_frontier_xyz.py 已提供 paper-facing frontier wrapper。
  tests/test_spatial.py 已支持 best_R_w30、point/ci-low R_w30 和 circular_a。

Plotting: implemented
  tests/plot_figure1.py 已能从 sharp-threshold raw.csv 和 frontier summary.csv 生成 Figure 1(a)/(b) SVG。
```
