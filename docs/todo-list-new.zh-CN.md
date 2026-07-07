# 论文 Figure TODO List

本文档按照主办方提出的三个主要 figure 任务，重新整理后续工作。

重点是说明哪些已经实现，哪些只是部分可用，哪些还需要构建或跑到论文规模。

## 全局实验设置

目标设置：

- 随机生成集合 `A, B subset U`。
- 让 `A` 和 `B` 包含较大的共同部分。
- 固定对称差大小 `diff = d`。
- 输入顺序随机 shuffle。由于这些 sketch 是 canonical 的，顺序不应影响正确性。
- 固定 universe word size：

```text
w = log2 V = 30
```

- 使用均摊通信指标：

```text
R = sketch_length_bits / (d * w)
```

- 若没有特别说明：

```text
confidence interval = 95%
target_success_rate = 0.9
```

## 当前设置状态

### 已经实现

- `tests/dataset_generator.py` 已经能生成大重叠、固定差异大小 `d` 的 synthetic sets。
- `tests/test_compare_basic.py` 和 `tests/test_iblt_spatial.py` 已经使用 shared paired datasets。
- `tests/test_spatial.py` 和 `tests/test_circular_a.py` 现在支持 `--shared-datasets`。
- 大多数 benchmark row 已经报告：

```text
bits
bits_per_difference
bit_C_over_d = bits / (32*d)
success_rate
encode_avg_s
decode_avg_s
ci_low / ci_high in threshold-style scripts
```

- 多个 threshold 脚本已经支持 Wilson 95% 置信区间。
- threshold 脚本中的 `target_success_rate` 可配置。

### 需要标准化

- 论文指标应使用 `R = bits / (30*d)`，但当前通用字段 `bit_C_over_d` 是 `bits / (32*d)`。
- 需要增加派生字段或绘图转换：

```text
R_w30 = bits / (30*d)
```

- 主文实验应使用 `target_success_rate = 0.9`。现有一些文档和默认值仍使用 `0.95`。
- paper-facing paired comparison 应尽量使用 `--shared-datasets`。
- 如果 `tests/test_xyz_sharp_threshold.py`、`tests/test_z.py`、`tests/test_find_best_m.py` 的结果要进入论文图，需要迁移到 shared dataset。

## Figure 1：XYZ-Sketch 理论主张

目标：证明 XYZ-Sketch 的实验行为符合理论主张。

代表性 tuples：

```text
(k,l) in {(2,3), (2,6), (3,4)}
a = 0
```

placement variants：

```text
iid / uniform
SC / spatial coupling
```

当前代码中最接近的 mode 名称是：

```text
iid      -> mode=random
SC       -> mode=naive 或 circular/spatial，取决于 k 和实验定义
```

对主办方这版设置，circular-style SC 应显式使用 `a = 0`。

## Figure 1(a)：Sharp Threshold

目标图：

- 固定一个足够大的 `d`。
- 固定 `z`。
- 横轴：`R = bits / (30*d)`。
- 纵轴：success rate。
- 曲线：`{(k,l)-pair} * {iid, SC}`。
- 标出 95% 置信区间。

预期结果：

- 所有 variants 都出现 sharp threshold。
- SC 的 threshold 应小于 iid。

### 当前支持

主要由以下脚本部分支持：

```text
tests/test_xyz_sharp_threshold.py
tests/test_spatial.py
```

`tests/test_xyz_sharp_threshold.py` 已经可以围绕中心 `M` 扫描，并记录带置信区间的 success-rate 曲线。

`tests/test_spatial.py` 可以为不同 mode 搜索 threshold，并支持 shared datasets。

### 缺口

- `test_xyz_sharp_threshold.py` 还不支持 shared paired datasets。
- 它当前汇总 `M@50`、`M@95` 和 CI-low `M@95`；论文需要目标 `0.9`。
- 它报告的是 `bit_C_over_d = bits/(32*d)`，不是 `R = bits/(30*d)`。
- 需要固定主办方指定的 tuple set，并在适用时使用 `a=0`。
- 需要 Figure 1(a) 绘图脚本。

### 需要完成

1. 增加或使用绘图转换 `R_w30 = bits / (30*d)`。
2. 对以下配置运行 `test_xyz_sharp_threshold.py`：

```text
d = one large representative value
(k,l) in {(2,3), (2,6), (3,4)}
modes in {random, SC}
fixed z
target_success_rate = 0.9 for summaries
```

3. 如果论文严谨性需要，把 `test_xyz_sharp_threshold.py` 迁移到 shared datasets。
4. 从 `raw.jsonl` 生成 Figure 1(a)。

状态：

```text
partial: 扫描基础设施已存在
open: 论文规模运行、R_w30 指标、shared datasets、绘图
```

## Figure 1(b)：Communication Frontier

目标图：

- 横轴：`d`。
- 纵轴：`R = bits / (30*d)` at 90% success probability。
- `z` 应取最优值，或者在有理由时使用启发式。
- 曲线：`{(k,l,a)-tuple} * {iid, SC}`。
- 标出置信区间。
- 为了美观，可以考虑从 `d >= 100` 开始。

预期结果：

- 每条曲线应收敛到某个值。
- 该值应接近理论预测。
- SC 应优于 iid。

### 当前支持

部分由以下脚本支持：

```text
tests/test_spatial.py
tests/test_find_best_m.py
tests/test_circular_a.py
tests/test_z.py
```

`test_spatial.py` 可以搜索不同 placement mode 的 best `M`。

`test_find_best_m.py` 可以搜索单个配置的 best `M`。

`test_z.py` 可以扫描 `z`，但目前更像 sensitivity scan，不是完整 frontier search。

### 缺口

- 当前没有单个脚本完整搜索：

```text
d values
(k,l,a) tuples
placement variant iid/SC
z optimization
target_success_rate = 0.9
```

- 现有 threshold 脚本默认常常是 `0.95`，不是 `0.9`。
- 输出需要从 `bit_C_over_d` 转成 `R_w30`。
- 需要明确 `z` 策略：

```text
heuristic z(d)
or empirical z*(d)
```

- 需要对推断出的 frontier 给出置信区间，而不仅是单个 probe 的成功率置信区间。
- 需要 Figure 1(b) 绘图脚本。

### 需要完成

1. 定义精确 `d` 网格，例如：

```text
d in {100, 300, 1000, 3000, 10000}
```

2. 定义精确 tuple 网格，先从：

```text
(k,l,a) in {(2,3,0), (2,6,0), (3,4,0)}
```

开始。

3. 实现或改造 frontier 脚本，暂定：

```text
tests/test_frontier_xyz.py
```

也可以扩展 `tests/test_spatial.py` 来扫描：

```text
target_success_rate = 0.9
d grid
tuple grid
mode in {random, SC}
z policy
```

4. 增加输出字段或绘图转换：

```text
R_w30
z_policy
z_selected
frontier_target_success_rate = 0.9
```

5. 生成 Figure 1(b)。

状态：

```text
partial: threshold-search 组件已存在
open: 统一 frontier 脚本/运行、z 策略、绘图
```

## Figure 2：`(a,z)` 的影响

目标：分析 circular 参数 `a` 和 coupling 参数 `z` 对性能的影响。

## Figure 2(a)：`(a,z)` 热力图

目标图：

- 固定一个代表性 `d`。
- 热力图：

```text
x-axis = a
y-axis = z
color = R at 90% success probability
```

预期结果：

- 调整 `a` 和 `z` 确实能改善通信。

### 当前支持

部分由以下脚本支持：

```text
tests/test_circular_a.py
tests/test_z.py
```

`test_circular_a.py` 可以扫描 `a`，支持 threshold mode，支持 shared datasets，并记录置信区间。

`test_z.py` 可以扫描 `z`。

### 缺口

- 当前没有脚本扫描完整 `(a,z)` 二维网格，并为每个 cell 搜索 `M`。
- `test_circular_a.py` 根据 `M` 用启发式选择 `z`，没有对每个 `a` 暴露完整 `z` 网格。
- `test_z.py` 不扫描 `a`。
- 需要 heatmap-ready 输出。
- 需要 `target_success_rate = 0.9`。
- 需要 `R_w30 = bits/(30*d)`。

### 需要完成

1. 创建或扩展脚本：

```text
tests/test_az_grid.py
```

或者给 `tests/test_circular_a.py` 增加：

```text
--z-values
--target-success-rate 0.9
--mode threshold
```

2. 对每个 `(a,z)`：

```text
find minimum M reaching 90% success
record best_M, R_w30, success_rate, ci_low, ci_high
```

3. 对同一 `d` 和 trial index，在不同 `(a,z)` cell 之间使用 shared datasets。
4. 生成 Figure 2(a) heatmap。

状态：

```text
partial: a 和 z 分别扫描已存在
open: 联合 (a,z) threshold grid 和 heatmap
```

## Figure 2(b)：`z_theory(d)` vs `z*(d)`

目标图：

- 横轴：`d`。
- 纵轴：`z`。
- 两条曲线：

```text
z_theory(d)
z*(d) from experiments
```

这张图可能是可选的，但最好先生成第二条实验曲线。

### 当前支持

部分由以下脚本支持：

```text
tests/test_z.py
```

它可以对代表性 `(d,l,k,M)` 配置扫描 `z`。

### 缺口

- 它当前不会为每个 `z` 搜索 threshold `M`。
- 它不会输出干净的 `z*(d)` frontier。
- 它不会和显式的 `z_theory(d)` 字段比较。
- 它仍使用 internal generator，而不是 shared paired datasets。

### 需要完成

1. 在代码或配置文件中显式定义 `z_theory(d)`。
2. 扩展 frontier 或 `(a,z)` grid 脚本，输出：

```text
d
z_theory
z_star
R_w30_at_z_star
```

3. 如果最终保留该图，生成 Figure 2(b)。

状态：

```text
partial: z scan 已存在
open: z*(d) 提取和理论曲线比较
```

## Figure 3：和其它算法对比

目标：比较调参后的 XYZ 和实用 set reconciliation baselines。

默认 XYZ 设置：

```text
(k,l) = (2,6)
choose tuned (a,z)
target_success_rate = 0.9
```

参赛算法：

```text
XYZ
IBLT
minisketch
possibly other external baselines
```

## Figure 3(a)：Communication

目标图：

- 横轴：`d`。
- 纵轴：`R = bits / (30*d)`。
- 所有概率性算法都按 90% 成功率测量。

### 当前支持

部分由以下脚本支持：

```text
tests/test_compare_basic.py
tests/test_iblt_spatial.py
```

`test_compare_basic.py` 可以在 shared datasets 上对比多个算法。

已实现或已有骨架的 baselines 包括：

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

当前环境状态：

```text
minisketch and iblt_cpp are real and usable
riblt requires Go
negentropy requires OpenSSL headers/libs
cpisync is optional/platform-sensitive
```

### 缺口

- `test_compare_basic.py` 当前比较固定参数网格；它不会自动搜索每个算法达到 90% 成功率的最小通信。
- 需要来自 Figure 2 或启发式的 tuned XYZ `(a,z)`。
- 需要为 IBLT 和 minisketch 做可比较的 threshold search。
- 需要 `R_w30`。
- 每个绘图点需要置信区间。

### 需要完成

1. 先确定 `(k,l)=(2,6)` 下 tuned XYZ 的 `(a,z)`。
2. 实现 threshold/frontier comparison 脚本，暂定：

```text
tests/test_compare_frontier.py
```

或者给 `test_compare_basic.py` 增加 threshold-search mode。

3. 对每个算法和每个 `d`，找到达到 `0.9` 成功率的最小通信。
4. 所有算法使用 shared datasets。
5. 生成 Figure 3(a)。

状态：

```text
partial: shared compare 基础设施已存在
open: per-algorithm 90% frontier search 和绘图
```

## Figure 3(b)：Update Cost

目标图：

- 横轴：`d`。
- 纵轴：average update time per element。

### 当前支持

部分支持：

- benchmark 已经报告 `encode_avg_s`。
- 对 sketch-building 算法，update cost 可近似为：

```text
encode_avg_s / number_of_inserted_elements
```

### 缺口

- 当前 JSON 没有一致报告：

```text
update_avg_s_per_element
update_total_elements
```

- 一些 baseline 不自然区分 update time 和其它 encoding/protocol setup。
- 需要统一分母：

```text
|A| for Alice sketch build
or |A| + |B| if both sides are encoded in the benchmark
```

### 需要完成

1. 决定 update-time 定义。
2. 在 Python summary 中增加派生字段：

```text
update_avg_s_per_element
update_denominator
```

3. 如有必要，在 benchmark wrapper 内增加更细粒度计时。
4. 生成 Figure 3(b)。

状态：

```text
partial: encode timing 已存在
open: 标准化 update-cost metric
```

## Figure 3(c)：Decode Cost

目标图：

- 横轴：`d`。
- 纵轴：amortized decode time per element。

### 当前支持

部分支持：

- benchmark 已经报告 `decode_avg_s`。
- compare 输出保留 decode timing 字段。

### 缺口

- 需要统一分母：

```text
d
or number of recovered differences
```

对 set reconciliation 来说，使用 `d` 作为分母可能最干净。

- 一些 interactive baseline 使用 `reconcile_avg_s`；它和 decode cost 的关系需要文档说明。

### 需要完成

1. 定义：

```text
decode_avg_s_per_difference = decode_avg_s / d
```

或者另一个约定好的分母。

2. 在 summary 或 plotting code 中增加派生字段。
3. 生成 Figure 3(c)。

状态：

```text
partial: decode timing 已存在
open: 标准化均摊 decode metric 和绘图
```

## 推荐执行顺序

1. 标准化论文指标：

```text
R_w30 = bits / (30*d)
target_success_rate = 0.9
95% CI
shared datasets for paired comparisons
```

2. 用代表性 sharp-threshold run 产出 Figure 1(a)。
3. 运行 Figure 3 前所需的 `(a,z)` tuning。
4. 产出 XYZ-only 的 Figure 1(b) communication frontier。
5. 产出 Figure 2(a)，并可选产出 Figure 2(b)。
6. 为 Figure 3(a) 实现 per-algorithm 90% frontier search。
7. 为 Figure 3(b,c) 增加或更新 per-element timing metrics。
8. 生成绘图脚本和最终 figure tables。

## 可能需要的新脚本

```text
tests/test_frontier_xyz.py       # Figure 1(b)，可复用 test_spatial 逻辑
tests/test_az_grid.py            # Figure 2(a)，也可扩展 test_circular_a
tests/test_compare_frontier.py   # Figure 3(a)，per-algorithm 90% frontier
tests/plot_paper_figures.py      # 从 JSON/CSV 输出生成 Figures 1-3
```

其中一些可以作为现有脚本的扩展实现，而不是新建文件。但 figure 任务应该有稳定命令和输出目录。

## 论文结果目录建议

建议目录：

```text
tests/results/paper_fig1_sharp_threshold/
tests/results/paper_fig1_frontier/
tests/results/paper_fig2_az_grid/
tests/results/paper_fig2_z_star/
tests/results/paper_fig3_compare_frontier/
tests/results/paper_fig3_timing/
tests/results/paper_figures/
```

## 总结

当前仓库状态：

```text
Figure 1(a): 已有 sharp-threshold 脚本部分支持
Figure 1(b): threshold 组件存在，但统一 frontier run 未完成
Figure 2(a): a 和 z 分别扫描存在，联合 heatmap 未完成
Figure 2(b): z scan 存在，z*(d) 提取未完成
Figure 3(a): shared compare 存在，90% frontier search 未完成
Figure 3(b): encode timing 存在，update-cost metric 未完成
Figure 3(c): decode timing 存在，amortized decode metric 未完成
```

