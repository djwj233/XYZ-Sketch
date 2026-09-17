# Figure 1(b)(c) 与 `C/D` 独立再校准方案

Protocol version：`figure1bc-v4`。

## 1. 实验角色

本目录包含两个严格隔离的阶段：

1. 使用 `d<3000` 的 ideal-cell hypergraph 数据独立再校准 `C` 和 `D`；
2. 参数冻结后，在 `d>=3000` 的 sealed holdout 上运行 Figure 1(b)(c)。

Figure 1(b) 与 Figure 1(c) 是同一个 holdout experiment 的两张 heatmap：

| 图 | `d` | `M` | 数据角色 |
| --- | ---: | ---: | --- |
| Figure 1(b) | 3,000 | 596 | holdout scale 1 |
| Figure 1(c) | 10,000 | 1,948 | holdout scale 2 |

Figure 1(b)(c) 的任何 trial 都不得参与候选生成、网格扩展、参数选择或 tie-break。该隔离规则保证
Figure 1(b)(c) 仍然检验小规模校准参数的跨规模外推表现。

本项目重新得到的参数标记为 `C_cal/D_cal`。论文报告的 `C=0.276,D=0.5` 只在参数冻结后用于数值对照，
不参与独立再校准。

## 2. 论文依据与项目消歧

论文明确给出：

- Section 4.4 的 `a/z` 启发式公式；
- Section 6.1 的 100 independent trials 和目标成功率 0.9；
- Section 6.2 的“只用更小规模实例校准，再固定参数”顺序；
- Figure 1(b) 的 `(d,M,k,ell)=(3000,596,2,6)`；
- Figure 1(c) 的 `(d,M,k,ell)=(10000,1948,2,6)`；
- Figure 1(b)(c) 使用 ideal-cell hypergraph simulator。

论文没有公开 calibration instances、候选网格、`z` 取整规则、目标函数和 tie-break。本 README 对这些内容
给出本复现项目的预注册定义，不把它们表述为论文原始设置。

## 3. 唯一合法 simulator

### 3.1 Hypergraph

每个 trial 生成 `d` 条不同 identity 的 edge，每条 edge 有两个 hash attempts，去重后的 support size 为 1 或 2，
顶点数为 `M`。Simulator 不构造大小为
`10^7` 的集合，不运行 D-RFR，不调用完整 XYZ-Sketch，也不引入 cell-level recovery randomness。

每条 edge 只生成固定的两个 endpoint，随后按完整实现执行 `sort/unique`，不做 rejection resampling。
两个 endpoint 碰撞时，该 edge 的 deduplicated support 只含一个 cell。Simulator adjacency 和 peeling 必须
支持 support size 为 1 或 2；该规则与当前 `HashLocations()` 完全一致。

### 3.2 Circular placement

对给定 `(M,a,z)`：

```text
RangeLength = floor(M/(z+1))
NaiveBaseRange = M-RangeLength+1
ExtraCircularAnchors = floor(a*RangeLength)
CircularBaseRange = min(M, NaiveBaseRange+ExtraCircularAnchors)
anchor = anchor_word mod CircularBaseRange
offset_i = offset_word_i mod RangeLength
endpoint_i = (anchor+offset_i) mod M
```

三个 word 分别取对应 seed SHA-256 digest 的前 32 bits，按 big-endian 解释。该 modulo 规则复用当前
`hash.cpp` 的离散化语义；同一 raw word 可在不同候选 range 上重新映射以保持 paired comparison。
其中 `0<=a<1`，`0<=z<M`。`z=0,a=0` 是无 coupling 对照。

Placement golden fixture 固定 `M=10,z=1,a=0.2`，因此
`RangeLength=5,NaiveBaseRange=6,CircularBaseRange=7`：

| anchor word | offset word 1 | offset word 2 | raw endpoints | deduplicated support |
| ---: | ---: | ---: | --- | --- |
| 8 | 3 | 8 | `(4,4)` | `{4}` |
| 8 | 3 | 4 | `(4,5)` | `{4,5}` |

Simulator 和独立 reference placement 必须逐 byte 产生这两个 support；第一行不得重抽。

### 3.3 `ell`-peeling

固定 `(k,ell)=(2,6)`。反复删除当前 residual degree 在 `[1,6]` 的任意 cell 及其全部 incident edges，
直到没有可删除 cell。删除顺序使用 cell id 升序的确定性队列。仅当 residual edge count 为 0 时 trial 成功。

## 4. 参数公式

阈值来自 `../threshold/validated_thresholds.json`：

\[
a=C\frac{c^{peel}_{2,6}}{c^{orient}_{2,6}}.
\]

论文的 `z` 公式为：

\[
z=D(1-a)^{2/3}\left(\frac{M}{\log(1/\delta)}\right)^{1/3}.
\]

固定 `delta=0.1`，并定义：

\[
\gamma=\frac{D}{\log(1/\delta)^{1/3}},\qquad
z=\gamma(1-a)^{2/3}M^{1/3}.
\]

Simulator 搜索 `C/gamma`，冻结时计算
`D_cal=gamma_cal*log(1/delta)^(1/3)`。每个配置保存 `z_raw`，实际 `z` 固定为
`floor(z_raw+0.5)`。

候选只有在 `0<=a<1` 且 `1<=z<M` 时合法。非法候选记录 `invalid_placement`，其 aggregate 固定为
`0/100`，在固定点相对评分中按失败处理，不能从评分数据删除。Bracket 分类只在判定 `global_one`
时排除非法候选，具体规则见 Section 5.3。

## 5. Calibration training domain

### 5.1 `d` 网格

训练规模固定为：

```text
d in {100, 200, 400, 600, 800, 1000, 1500, 2000, 2500}
```

所有 training scale 均满足 `d<3000`。`d>=3000` 的数据在参数冻结前不可生成。

### 5.2 候选参数网格

Coarse candidate grid：

```text
C     in {0.100, 0.125, ..., 0.600}
gamma in {0.150, 0.175, ..., 0.650}
```

Coarse grid 只选择 bracket 并提供低分辨率相对结果。Final fine grid 使用以下大范围：

```text
C     in {0.005,0.010,...,1.205}
gamma in {0.005,0.010,...,1.000}
```

`C=1.205` 是 validated threshold 下步长 `0.005` 上满足 `a<1` 的最大 C；下一个点 `1.210` 非法，因此 C 轴
覆盖全部合法正 C 网格。初始 gamma 上界对应 `D=1.320500478...`。若 winner 距 gamma 上界不足 `0.050`，
则以 gamma step `0.005` 向上增加宽 `0.250` 的 band，直至 winner 距已测试 gamma 上界至少 `0.050`；gamma
硬上限为 `4.000`，对应 `D=5.282001913...`。达到硬上限仍无内点 winner 时状态为
`relative_search_boundary`。所有 grid endpoint 使用十进制定点整数生成，不使用浮点累加。

### 5.3 宽 `M` bracket

对每个 training `d`，初始 coarse ratio grid 为：

```text
rho=M/d in {0.08, 0.09, ..., 0.45}
M=floor(rho*d+0.5)
```

重复的整数 `M` 去重后按升序运行。每个 `(d,M)` 对 coarse `C/gamma` grid 的所有不同离散 placement
运行 100 个 paired trials。分类定义为：

- `global_zero`：全部 coarse candidate record 均为 0 successes，非法候选已按 0 计入；
- `global_one`：至少存在一个合法 coarse candidate，且全部合法候选对应的不同 placement 均为
  100 successes；非法候选只从本项 bracket 分类排除，其 `0/100` record 仍保留并进入后续评分；
- `transition`：其余情况，包括不同 placement 分别为 0% 和 100% 的情况。

该分类避免一个在当前 `M` 上尚未达到 `z>=1` 的候选永久阻止高端 bracket，同时不改变该候选的观测值或
最终评分。此规则统一应用于所有 `(d,M)`，不针对单个候选或单次结果。

扫描结果必须同时具有一个低端 `global_zero` prefix 和一个高端 `global_one` suffix。若缺少低端 prefix，
依次加入 `rho=0.06,0.04,0.02,0.01`；若缺少高端 suffix，每轮向上增加宽度 0.10、步长 0.01 的 ratio band，
最高扩展到 `rho=1.45`。达到边界仍不能形成 bracket 时，run 状态为 `calibration_unbracketed`，不得拟合参数。

令 `rho_zero` 为低端连续 `global_zero` prefix 的最大 ratio，`rho_one` 为高端连续 `global_one` suffix
的最小 ratio。必须满足 `rho_zero<rho_one`。

### 5.4 Dense `M` grid

在闭区间 `[rho_zero,rho_one]` 内增加：

```text
rho_dense = rho_zero + j*0.0025
M=floor(rho_dense*d+0.5)
```

最后一个点强制包含 `rho_one`。最终 `M` grid 是全部 coarse、扩展和 dense 整数 `M` 的并集。该并集冻结后，
fine grid 及后续 C expansion bands 的全部候选在所有最终 `M` 上使用新的 `calibration_fine` paired domain
运行 100 trials。Coarse 数据只用于 bracket 和 coarse winner，不与 fine 数据合并。
`global_zero/global_one` 点提供转变两侧的边界证据，候选之间的区分主要来自 transition 数据。

## 6. 参数选择

### 6.1 固定点 paired comparison

Coarse winner 使用 coarse ratio grid 及扩展 grid 评分。Final winner 使用 fine grid 和全部 C expansion bands
在完整最终 M grid 上评分。对每个固定 `(d,M)`，所有候选使用相同的 placement words；映射到相同
`(CircularBaseRange,z)` 的候选共享 simulator trial。非法 placement 的 success count 固定为 0。

一个固定 `(d,M)` 只有在至少两个候选的 success count 不同时才是 informative point。全体候选在同一组
informative points 上评分；不得为不同候选删除不同 point。

### 6.2 唯一相对评分顺序

对每个候选，先在每个 training d 内对该 d 的 informative M points 求平均成功率，再令九个 d 等权。按以下
顺序选择 coarse winner，并以同一顺序选择最终 fine winner：

1. 九个 per-d mean success rate 的算术平均值最大；
2. 九个 per-d mean success rate 的最小值最大；
3. 对每个固定 point 的 `best_success_rate-success_rate` 再取平均，该 mean regret 最小；
4. 与 pointwise best success count 并列的 informative-point 比例最大；
5. pointwise competition rank 的平均值最小；
6. `C` 较小；
7. `gamma` 较小。

所有比较都基于整数 success count；只在输出时转换为 rate。该评分不要求候选在任何 point 达到预设的绝对
成功率，只比较同一固定 `(d,M)` 下不同 `C/D` 的相对表现。

### 6.3 大范围搜索与冻结

Section 5.2 的 C 轴覆盖全部合法范围；gamma/D 轴至少覆盖预注册大范围，并在 winner 靠近上界时继续扩展。
最终 winner 直接生成不可变
`results/calibration/<calibration_id>/frozen_parameters.json`，状态为 `selected`，包含
`C_cal,gamma_cal,D_cal,delta`、完整相对评分、gamma expansion history、配置哈希、代码哈希、threshold 哈希及
全部输入 artifact 哈希。Calibration 不再运行独立 90% confirmation；历史 v2 confirmation 数据不参与 v3
候选生成、评分或 tie-break。

## 7. Sealed Figure 1(b)(c) holdout

Holdout 只能在 `frozen_parameters.json` 状态为 `selected` 后解封。两个 scale 使用相同的基础 heatmap grid：

```text
a in {0.0, 0.1, 0.2, 0.3, 0.4, 0.5}
z in {0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16}
```

每个 grid cell 运行 100 trials。冻结参数在对应 `M` 上预测出的精确 `(a_cal,z_cal)` 与基础 grid 取并集；
该点以黄色边框标记。Figure 1(b) 和 Figure 1(c) 使用同一 holdout run id、同一 frozen-parameter hash 和
互相隔离的 seed domain。

Holdout 完成后不得依据 heatmap 修改 `C_cal/D_cal`。Holdout selected point 失败时如实报告，Figure 1(a)
和 Figure 2 不得启动。

## 8. 随机性与 paired trials

固定 `base_seed=114514`。共享 edge uniforms 的 seed 不含 `(C,gamma,a,z)`：

```text
SHA256("figure1bc|base_seed|domain|d|M|trial_index|edge_index|uniform_role")
```

`uniform_role` 分别为 `anchor_word,offset_word_1,offset_word_2`，每条 edge 恰好消费这三个角色且不重抽。同一
`(domain,d,M,trial_index,edge_index)` 下所有候选
使用相同 uniforms，再按各自 placement 做确定性离散映射。配置 identity 另行包含 `(C,gamma,a,z)`，但不得
改变共享 uniforms。

Domain 固定为：

```text
calibration_coarse
calibration_fine
holdout_figure1b
holdout_figure1c
```

不同 domain 的 seed 不复用。每个 trial 保存 placement-word stream SHA-256、初始 edge count、residual edge count
和 candidate/config id。

## 9. Artifact

```text
results/calibration/<calibration_id>/
  calibration_config.json
  m_bracket.csv
  trials.jsonl
  placement_groups.jsonl
  aggregate.csv
  relative_scores.csv
  relative_selection.json
  frozen_parameters.json
  source_manifest.md
  errors.log

results/holdout/<holdout_id>/
  run_config.json
  trials.jsonl
  placement_groups.jsonl
  aggregate.csv
  figure1b.svg
  figure1b.pdf
  figure1b.png
  figure1c.svg
  figure1c.pdf
  figure1c.png
  source_manifest.md
  errors.log
```

每条 aggregate row 至少包含：

- `run_id,domain,d,M,k,ell,C,gamma,a,z_raw,z,CircularBaseRange`；
- `trials,successes,success_rate,ci_low,ci_high`；
- `rho,m_grid_phase,global_classification,is_informative`；
- `dataset_seed,placement_words_sha256,config_sha256,threshold_sha256`；
- `is_frozen_prediction,status`。

`placement_groups.jsonl` 将每个 `(stage,d,M,placement_id)` 映射到完整 `candidate_ids`；`trials.jsonl` 通过
`candidate_group_id` 引用该映射，避免在 100 个 trials 中重复写相同候选列表。每个 trial row 仍保存
placement-word stream SHA-256、初始和 residual edge count、success 与 status。

`relative_scores.csv` 保存 coarse 与 final fine 的完整候选排名、等权 per-d mean、最差 per-d mean、mean regret、
pointwise-best tie fraction、mean pointwise rank 和唯一 selected row。`relative_selection.json` 另保存每轮 C
expansion 的范围与当轮 winner。

## 10. 图形规范

- x 轴为 `a`，数值递增；
- y 轴为 `z`，图上从大到小排列；
- color scale 固定为 `[0,1]`；
- cell 显示两位小数 success rate；
- 黄色边框只标精确 frozen prediction；
- Figure 1(b) 标注 `sealed holdout, scale 1`；
- Figure 1(c) 标注 `sealed holdout, scale 2`；
- 图注注明 `C/D` 来自独立的 `d<3000` recalibration。

### 10.1 Appendix Figure 3 完整 12 面板

Figure 3 是参数冻结后的局部 fixed-`M` landscape，不参与 `C_cal/gamma_cal/D_cal` 的生成、选择或修改。固定面板为：

| panel | `d` | `M` | panel | `d` | `M` |
| --- | ---: | ---: | --- | ---: | ---: |
| (a) | 300 | 67 | (g) | 10,000 | 1,948 |
| (b) | 300 | 72 | (h) | 10,000 | 2,036 |
| (c) | 1,000 | 211 | (i) | 100,000 | 18,155 |
| (d) | 1,000 | 224 | (j) | 100,000 | 18,940 |
| (e) | 3,000 | 596 | (k) | 1,000,000 | 178,767 |
| (f) | 3,000 | 621 | (l) | 1,000,000 | 183,767 |

每个 panel 先按冻结公式独立计算精确 `a_selected=a_cal`、`z_raw_selected` 和
`z_selected=floor(z_raw_selected+0.5)`，再构造唯一的 `7×5` 中心网格：

```text
a = a_selected + {-3,-2,-1,0,1,2,3} * 0.075
z_step = max(1, floor(z_selected/5 + 0.5))
z = z_selected + {-2,-1,0,1,2} * z_step
```

因此冻结预测必须严格位于从小到大计数的第 4 个 `a` 和第 3 个 `z`，即 zero-based center index `(2,3)`。
Renderer 必须同时验证 config axes、完整 35-cell Cartesian product、唯一 frozen marker 及 center index；任一条件
不满足时禁止出图。所有轴值都必须满足 `0<=a<1`、`z>=0`，不得绘制非法格或插值格。

每格使用 100 trials。Figure 3 使用新的 post-freeze word stream；seed material 仍为 Section 8 的规范字符串，
其中 `(engine domain,d,M)` 组合与 calibration 和 sealed holdout 的每个正式 point 均不同。Figure 3 runner 必须
验证 simulator executable SHA-256 与已完成 sealed holdout 的 `build_manifest.json` 完全相同，不能重新编译或
修改 placement/peeling 算法后运行。

完整图固定为 3 列×4 行，panel 顺序为 `(a)..(l)`；输出一个 composite SVG/PDF/PNG，并为每个 panel 输出独立
SVG/PDF/PNG。颜色范围固定 `[0,1]`，每格显示两位小数，黄色边框只标冻结预测的中心格。

### 10.2 Figure 3 宽轴探索与停止规则

Section 10.1 的局部等距网格只用于展示中心附近的稳定性。若大面积为 100%，另运行公开标记为 exploratory 的
宽轴 round；该 round 不替换 calibration 或 sealed holdout，也不得修改冻结中心。

Round 1 的 `a` 轴在 log-odds 空间以冻结 `a` 为中心：

```text
logit(a_i) = logit(a_selected) + i,  i in {-3,-2,-1,0,1,2,3}
```

中心值直接使用冻结 binary64，不做 logit 往返。`z` 轴固定为：

```text
{0, round_half_up(z/2), z, round_half_up(2.5z), round_half_up(6z)}
```

若 Round 1 未达到停止规则，Round 2 固定扩大为 log-odds step `1.5`，`z` 上侧改为 `4z` 和 `12z`；低侧不变。
两个 round 使用相同 `(domain,d,M,trial)` placement words，形成 paired axis comparison；Round 1 artifact 永久保留。

一个 panel 只有同时满足下列条件才计为清晰展示宽网格相对优势：

1. selected rate `>=0.9`；
2. `max_grid_rate-selected_rate<=0.05`；
3. 至少 25% cells 的 rate `<=selected_rate-0.25`；
4. `selected_rate-median_grid_rate>=0.10`。

12 个 panel 至少 8 个通过时停止。未达到时只能执行下一份预定义 round，不能按单个 panel 单独裁轴、删除格子或
修改通过阈值。宽轴图只能表述为“冻结点在所测宽网格上较优”，不能表述为独立参数确认或全局最优证明。

停止规则达到后允许生成 `dense11` 展示分辨率 profile。它不是新的范围扩张 round，不重新触发停止选择：

```text
logit(a_i) = logit(a_selected) + 0.6*i,  i in {-5,-4,...,4,5}
z axis = 已通过停止规则的 Round 1 z axis
grid = 5 rows x 11 columns
selected center index = (2,5), zero-based
```

`dense11` 与 Round 1 具有相同的两个 `a` 端点和完整 `z` 范围，只在横轴内部增加四列实测点。每个 panel 的
物理画布固定从 `500×280` 增至 `700×300`，完整图仍为 3 列×4 行。CLI 内部使用 `--round 3` 标识该
resolution profile；manifest 必须写入 `resolution_profile=dense11`，不得将其描述为第三轮参数范围搜索。

用户随后将最终展示尺寸冻结为合法 `square7` profile。横轴逐值等于 Round 1 的 7 个 `a`；纵轴为：

```text
z = {0, round_half_up(z_selected/2), z_selected,
     round_half_up(1.5*z_selected), round_half_up(2.5*z_selected),
     round_half_up(4*z_selected), round_half_up(6*z_selected)}
```

若取整发生相邻重复，后一个值最小递增到 `previous+1`；当前 12 个 panel 不发生该修正。Grid 固定为 7 行×7 列，
每个 cell 为正方形。冻结点位于 zero-based `(row,column)=(2,3)`：横向几何居中；对于 `z_selected=2` 的面板，
由于合法较小整数只有 `0,1`，纵向不要求几何居中。禁止为制造中心位置加入负 `z` 或重复 `z`。

CLI 内部使用 `--round 4` 标识 `resolution_profile=square7`；它与 `dense11` 一样是用户指定的最终展示 profile，
不参与 Round 1/2 的范围停止决策。

## 11. 启动门与验收

- [ ] threshold validation 的 48 个表项和 SHA-256 通过。
- [ ] calibration 只含 `d<3000`，holdout 只含 `d>=3000`。
- [ ] 每个 training `d` 都具有 global-zero prefix、global-one suffix 和 dense transition grid。
- [ ] paired uniforms seed 不含任何候选参数。
- [ ] 固定 32-bit-word golden fixture 逐 edge比较 simulator support 与独立复用当前 `HashLocations()`
      range/modulo/dedup 规则的 reference support，
      并覆盖两个 endpoint 碰撞后 support size 为 1 的情况。
- [ ] coarse/fine 固定点相对评分和 tie-break 可从 aggregate 独立重算。
- [ ] C 轴覆盖全部合法正网格，gamma expansion 停止时 selected gamma 距已测试上界至少 0.050。
- [ ] `frozen_parameters.json` 在 holdout 解封前生成并锁定哈希。
- [ ] Figure 1(b)(c) 未参与 calibration，且共享一个 holdout run identity。
- [ ] Figure 1(b)(c) 的 frozen prediction 均达到 0.9。
- [ ] simulator 未调用完整 XYZ-Sketch 或 D-RFR。
- [ ] 未读取 `/root/XYZ-Sketch` 的任何旧文件、数据或结果。

在全部验收项通过前，不得实现或运行 Figure 1(a) 与 Figure 2 的正式 runner。
