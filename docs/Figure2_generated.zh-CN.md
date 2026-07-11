# Figure 2 生成流程

本文档记录当前服务器上 Figure 2 的实际生成流程。

## 1. 旧 Figure 2 阈值网格

旧 Figure 2 实验为每个 `(a,z)` 组合搜索达到目标成功率所需的最小 `M`。

结果目录：

```text
tests/results/paper_fig2_az_grid
```

关键文件：

```text
tests/results/paper_fig2_az_grid/summary.jsonl
tests/results/paper_fig2_az_grid/summary.csv
tests/results/paper_fig2_az_grid/probes.jsonl
tests/results/paper_fig2_az_grid/run_config.json
```

当前规模：

```text
summary.jsonl: 495 rows
```

旧结果现在不直接作为最终 Figure 2 结论使用，只用于给新实验提供固定 `M` 候选。

## 2. 提取固定 M 候选

脚本：

```text
tests/extract_fig2_m_candidates.py
```

命令：

```bash
python3 tests/extract_fig2_m_candidates.py \
  --input tests/results/paper_fig2_az_grid/summary.jsonl \
  --output-dir tests/results/paper_fig2_m_candidates \
  --include-unresolved-with-m
```

该脚本做以下工作：

1. 从旧 Figure 2 summary 中读取非空 `best_M`。
2. 如果 unresolved 行仍然有 `best_M`，也保留为候选来源。
3. 按 `M*l/d` 对相近预算分桶合并。
4. 每个 bin 保留中位数 `M` 作为代表候选。

当前候选提取配置：

```json
{
  "c_over_d_bin_width": 0.1,
  "include_unresolved_with_m": true,
  "input_rows": 495,
  "full_candidate_rows": 240,
  "candidate_rows": 43
}
```

输出文件：

```text
tests/results/paper_fig2_m_candidates/m_candidates.csv
tests/results/paper_fig2_m_candidates/m_candidates.jsonl
tests/results/paper_fig2_m_candidates/m_candidates.md
tests/results/paper_fig2_m_candidates/run_config.json
```

## 3. 新 Figure 2(a)：固定 M 的 peeling simulation

runner：

```text
tests/test_fig2_fixed_m_sim.py
```

C++ 模拟器：

```text
tests/benchmarks/fig2_peeling_sim.cpp
```

实验逻辑：

```text
固定 d,k,l,M
扫描 circular a 和 z
运行 hypergraph peeling simulation
记录 peeling_success_rate
```

这不是完整 XYZ 解码实验。它不会运行 `XYZSketch::Decode()`、多项式重构、根查找或代数校验。它测量的是结构层面的 peeling 成功率。

模拟器复刻 `XYZ-v2/hash.cpp` 中的 circular hash 几何：

```text
RangeLength = M / (z + 1)
base_range = M - floor(a * RangeLength) + 1
bucket = (base + offset) % M
```

默认行为：

```text
dedup_hashes = false
trials = 100
```

运行命令：

```bash
python3 tests/test_fig2_fixed_m_sim.py \
  --m-candidates tests/results/paper_fig2_m_candidates/m_candidates.csv \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --z-values 0,1,2,3,4,5,6,8,10,12,16 \
  --output-dir tests/results/paper_fig2_fixed_m_sim
```

中断后继续：

```bash
python3 tests/test_fig2_fixed_m_sim.py \
  --m-candidates tests/results/paper_fig2_m_candidates/m_candidates.csv \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --z-values 0,1,2,3,4,5,6,8,10,12,16 \
  --resume \
  --skip-build \
  --output-dir tests/results/paper_fig2_fixed_m_sim
```

输出目录：

```text
tests/results/paper_fig2_fixed_m_sim
```

输出文件：

```text
raw.jsonl
summary.jsonl
summary.csv
summary.md
run_config.json
```

当前规模：

```text
summary.jsonl: 4257 rows
summary.csv: 4258 lines including header
```

校验命令：

```bash
python3 tests/json_verifier.py tests/results/paper_fig2_fixed_m_sim/summary.jsonl --strict
```

校验结果：

```text
checked=4257 failures=0
```

## 4. 备份

新的 Figure 2(a) 固定 M simulation 结果已备份到：

```text
tests/results/backups/figure2a_fixed_m_sim_20260710_074929
```

备份文件：

```text
raw.jsonl
summary.jsonl
summary.csv
summary.md
run_config.json
```

## 5. 绘制 Figure 2(a)

绘图脚本：

```text
tests/plot_figure2_fixed_m.py
```

命令：

```bash
python3 tests/plot_figure2_fixed_m.py \
  --input tests/results/paper_fig2_fixed_m_sim/summary.csv \
  --output-dir tests/results/paper_figures/figure2a_fixed_m \
  --only all \
  --target-success-rate 0.9
```

Figure 2(a) 定义：

```text
每张 SVG 固定一个 d
每个 panel 固定一个 M
横轴 = circular a
纵轴 = z
颜色 = peeling_success_rate
黄色框 = 离数据拟合启发式点最近的已实验网格 cell
```

标记仍使用实现公式的形式，但 `C`、`D` 是从当前 Figure 2 数据拟合得到的经验常数：

```text
c_orient/c_peel = 1.2081
C = (1/3) / 1.2081 = 0.27591535
a_marker = C * c_orient/c_peel = 1/3
D = 0.5
delta = 0.1
z_marker = D * (1-a_marker)^(2/3) * (M/log(1/delta))^(1/3)
```

拟合时首先最大化黄框成功率达到 `0.9` 的 panel 数量，然后最大化黄框平均成功率。
数据只能稳定识别 `a=1/3` 这一实验列；固定该列后，最优评分对应的 `D` 区间约为
`[0.3085,0.6235]`，这里选取区间内部且较简洁的 `D=0.5`。

相比原先的 `C=1/3,D=4/3`，当前 43 个 panel 上的结果为：

```text
达标 panel: 37 -> 41
黄框平均成功率: 0.93465 -> 0.98837
相对每个 panel 最佳格子的平均损失: 0.06140 -> 0.00767
```

`z_marker` 保留为连续值；黄色框选择离 `(a_marker,z_marker)` 最近的已实验
`(a,z)` 网格。图中 panel 标题同时输出连续启发式点和最终标记的网格点。

这些常数是公式形状下的经验拟合结果，不应称为独立于实验数据的理论预测。

这些值可以通过以下参数覆盖：

```text
--marker-c
--marker-c-orient-over-c-peel
--marker-d
--marker-delta
```

输出：

```text
tests/results/paper_figures/figure2a_fixed_m/figure2a_fixed_m_d100.svg
tests/results/paper_figures/figure2a_fixed_m/figure2a_fixed_m_d300.svg
tests/results/paper_figures/figure2a_fixed_m/figure2a_fixed_m_d1000.svg
tests/results/paper_figures/figure2a_fixed_m/figure2a_fixed_m_d3000.svg
tests/results/paper_figures/figure2a_fixed_m/figure2a_fixed_m_d10000.svg
tests/results/paper_figures/figure2a_fixed_m/figure2a_fixed_m_index.md
```

## 6. 绘制 Figure 2(b)

Figure 2(b) 使用同一个绘图脚本生成。

定义：

```text
对每个固定 (d,M)，选择 peeling_success_rate >= 0.9 的最大 z。
该值记为 z_star。
如果没有任何点达到 0.9，则选择成功率最高的点，并标记为 below_target。
```

输出：

```text
tests/results/paper_figures/figure2a_fixed_m/figure2b_fixed_m_z_star.svg
tests/results/paper_figures/figure2a_fixed_m/figure2b_fixed_m_z_star_source.csv
```

当前 Figure 2(b) 源表：

```text
43 rows
42 target_met
1 below_target
```

## 7. d=100000 扩展实验（旧 pilot）

本节记录最初的 `+100,+200,+300` pilot，仅保留用于结果追溯。当前大规模实验
已经改用 [Figure2-large-d.zh-CN.md](Figure2-large-d.zh-CN.md) 定义的统一流程，
`d=100000` 的新候选为 `18440,18940,19940`。

### 7.1 二分选择 M

脚本：

```text
tests/select_fig2_d100000_m.py
```

该脚本固定当前数据拟合启发式：

```text
d = 100000
k = 2
l = 6
a = 1/3
D = 0.5
delta = 0.1
z(M) = round(D * (1-a)^(2/3) * (M/log(1/delta))^(1/3))
trials = 20
target_success_rate = 0.9
```

运行命令：

```bash
python3 tests/select_fig2_d100000_m.py \
  --output-dir tests/results/paper_fig2_d100000_m_search
```

所有 probe 使用相同的 20 个 trial seeds。二分结果：

```text
M = 17954: 16/20 = 0.80
M = 17955: 19/20 = 0.95
empirical threshold M = 17955
```

按 `M+100,+200,+300` 生成的固定预算为：

```text
18055,18155,18255
```

输出：

```text
tests/results/paper_fig2_d100000_m_search/threshold_probes.jsonl
tests/results/paper_fig2_d100000_m_search/threshold_probes.csv
tests/results/paper_fig2_d100000_m_search/threshold_summary.json
tests/results/paper_fig2_d100000_m_search/m_candidates.csv
tests/results/paper_fig2_d100000_m_search/m_candidates.jsonl
tests/results/paper_fig2_d100000_m_search/m_candidates.md
```

### 7.2 fixed-M 网格

运行命令：

```bash
python3 tests/test_fig2_fixed_m_sim.py \
  --m-candidates tests/results/paper_fig2_d100000_m_search/m_candidates.csv \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --z-values 0,1,2,3,4,5,6,8,10,12,16 \
  --trials 20 \
  --shared-trial-seeds \
  --skip-build \
  --output-dir tests/results/paper_fig2_d100000_fixed_m_sim
```

`--shared-trial-seeds` 保证三个固定 `M` 及其所有 `(a,z)` 都使用相同的 20 个
trial seeds，使格子间和 `M` 之间的差异主要来自参数而不是输入样本变化。

结果：

```text
rows = 297
json_verifier failures = 0

M=18055: heuristic z=7.5806, marked (a,z)=(1/3,8), success=0.95, panel best=1.00
M=18155: heuristic z=7.5946, marked (a,z)=(1/3,8), success=1.00, panel best=1.00
M=18255: heuristic z=7.6085, marked (a,z)=(1/3,8), success=1.00, panel best=1.00
```

### 7.3 绘图

```bash
python3 tests/plot_figure2_fixed_m.py \
  --input tests/results/paper_fig2_d100000_fixed_m_sim/summary.csv \
  --output-dir tests/results/paper_figures/figure2_d100000 \
  --only all \
  --target-success-rate 0.9
```

输出：

```text
tests/results/paper_figures/figure2_d100000/figure2a_fixed_m_d100000.svg
tests/results/paper_figures/figure2_d100000/figure2b_fixed_m_z_star.svg
tests/results/paper_figures/figure2_d100000/figure2b_fixed_m_z_star_source.csv
```

该二分阈值只使用 20 trials。`0.9` 等价于至少 `18/20` 次成功，Wilson 95%
置信区间仍然很宽；`M=17955` 应称为粗略经验阈值，而不是精确的 90% 成功率边界。

## 8. 主要注意事项

新的 Figure 2 测量的是：

```text
peeling_success_rate
```

它不是完整 XYZ 端到端解码成功率。论文中应表述为结构层面的 hypergraph peeling simulation，而不是完整协议解码实验。

## 9. 大规模统一流程

`d>=10^5` 的当前标准入口为：

```bash
python3 tests/run_figure2_large_d.py --d-values 1000000,10000000
```

完整的 M 搜索分辨率、连续通过规则、按 d 缩放的 M 间距、自适应 z 网格、
并行策略、恢复语义和输出结构见：

```text
docs/Figure2-large-d.zh-CN.md
```

新 `d=100000` 标准结果：

```text
stable threshold M = 17940
candidate M = 18440,18940,19940
offsets = +500,+1000,+2000
rows = 324
json_verifier failures = 0
marked success = 1.00,1.00,1.00
target cells = 34,59,82
```

输出图片：

```text
tests/results/paper_figures/figure2_large_d/d100000/figure2a_fixed_m_d100000.svg
```
