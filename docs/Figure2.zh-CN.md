# Figure 2 规划

本文档规划论文 Figure 2 的实验 pipeline。

Figure 2 研究 circular 参数 `a` 和 coupling 参数 `z` 对 XYZ-Sketch 性能的影响。它还应该为 Figure 3 的最终 baseline 对比提供调参后的 `(a,z)`。

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

Figure 2 的主指标是：

```text
R_w30 = bits / (30*d)
```

主要 XYZ 设置建议为：

```text
k = 2
l = 6
mode = circular
```

因为 `a` 只对 circular spatial coupling 有直接含义。如果需要，也可以把 `(k,l)=(2,3)` 加入诊断，但第一版论文图应控制网格规模，保证能稳定跑完。

## 当前支持

相关已有脚本：

```text
tests/test_circular_a.py
tests/test_z.py
tests/test_spatial.py
tests/test_frontier_xyz.py
tests/benchmarks/xyz_v2_bench.cpp
```

当前能力：

- `xyz_v2_bench` 已支持 `--circular-a`。
- `test_circular_a.py` 可以扫描 `a`，包括 threshold mode。
- `test_z.py` 可以在固定 `M` 时扫描 `z`。
- `test_spatial.py` 已有 threshold search、shared dataset、Wilson CI，以及 `R_w30` 相关 summary 字段。

本次实现已经解决：

- `tests/test_az_grid.py` 可以扫描完整 `(a,z)` 二维网格，并为每个 cell 搜索最小 `M`。
- `tests/extract_fig2_z_star.py` 可以从网格 summary 中提取 `z_star(d)` 和对应的 `a_star(d)`。

剩余缺口：

- `test_z.py` 是固定 `M` 扫描，不能直接得到 90% 成功率下的 `R_w30`。
- `test_circular_a.py` 当前按启发式选择 `z`，没有为每个 `a` 暴露完整 `z` 网格。
- 还没有 Figure 2 heatmap 或 `z_theory(d)` 对比的绘图脚本。

## Figure 2(a): `(a,z)` 热力图

### 目标

固定一个代表性 `d`，展示二维 `(a,z)` 网格中，达到 90% 成功率所需通信 threshold 的变化。

图像定义：

```text
x-axis = a
y-axis = z
color = R_w30 at target_success_rate = 0.9
```

预期结果：

- 调整 `a` 和 `z` 应该能明显改变所需通信量。
- 最优区域应能给 Figure 3 提供实用调参。
- heatmap 可能包含 invalid 或 unresolved cell；这些 cell 应和高通信量 cell 区分显示。

### 推荐参数

Smoke 网格：

```text
d = 300
k = 2
l = 6
mode = circular
a in {0.0, 0.3333333333, 0.6}
z in {0, 1, 2, 3}
probe_trials = 5
final_trials = 10
target_success_rate = 0.9
```

论文网格：

```text
d = 3000 or 10000
k = 2
l = 6
mode = circular
a in {0.0, 0.1, 0.2, 0.3333333333, 0.4, 0.5, 0.6, 0.75, 0.9}
z in {0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16}
probe_trials >= 30
final_trials >= 100
target_success_rate = 0.9
threshold_policy = point
```

如果运行时间过长，可以缩小为：

```text
a in {0.0, 0.2, 0.3333333333, 0.5, 0.75}
z in {0, 1, 2, 3, 4, 6, 8, 12}
```

### 实现计划

已实现 paper-facing 脚本：

```text
tests/test_az_grid.py
```

职责：

1. 构建或定位 `build/xyz_v2_bench`。
2. 展开 `d`、`k`、`l`、`a`、`z` 网格。
3. 对每个 `(d,k,l,a,z)` cell，搜索达到 `target_success_rate` 的最小 `M`。
4. 使用 `final_trials` 对选出的 `M` 做最终验证。
5. 对相同 `(d, ca, cb, seed)` 的所有 cell 尽量使用 shared paired datasets。
6. 记录 `R_w30`、Wilson 置信区间、计时、选出的 `M` 和状态。
7. 写出 heatmap-ready 的 JSONL/CSV summary。

threshold search 复用 `test_spatial.py` 的思想：

```text
initial upper bound -> doubling until success -> binary search -> final validation
```

但与 `test_spatial.py` 不同的是，`z` 必须由网格固定，不能由 `choose_z(M)` 启发式选择。

### 输出目录

推荐输出目录：

```text
tests/results/paper_fig2_az_grid/
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
experiment = paper_fig2_az_grid
record_type = threshold
algorithm = xyz_v2
variant = circular
d
l
k
mode = circular
circular_a
z
best_M
best_R_w30
best_C_over_d
final_success_rate
final_ci_low
final_ci_high
target_success_rate
threshold_policy
dataset_mode
status
```

状态约定：

```text
ok          cell 达到目标，且 final validation 通过
unresolved  在 max_C_over_d 内没有 M 达到目标
invalid     z 让 RangeLength 过小，或参数被 benchmark 拒绝
```

## Figure 2(b): `z_theory(d)` vs `z*(d)`

### 目标

比较理论或启发式选择的 `z` 与实验最优的 `z`。

图像定义：

```text
x-axis = d
y-axis = z
curves = z_theory(d), z_star(d)
```

这张图在最终论文中可能是可选的，但生成实验曲线 `z_star(d)` 很有用，因为它会指导 Figure 3 的参数选择。

### `z_star(d)` 定义

对每个 `d`，定义：

```text
z_star(d) = scanned grid 中 best_R_w30 最小的 z
```

平局规则：

1. 优先选择更小的 `best_R_w30`。
2. 如果差异在很小容忍范围内，选择更高的 `final_ci_low`。
3. 如果仍然平局，选择更小的 `z`。
4. 如果仍然平局，选择更接近 Figure 3 默认值的 `a`。

summary 同时记录对应的最优 `a`：

```text
a_star(d)
z_star(d)
R_w30_at_star
```

### `z_theory(d)` 策略

当前实现使用启发式：

```text
z_heuristic(M) = max(0, round(M^(1/3) / 3))
```

Figure 2(b) 第一版可以定义为：

```text
z_theory(d) = max(0, round(best_M_at_star(d)^(1/3) / 3))
```

如果后续证明给出不同公式，可以替换该字段含义，但保持输出字段名稳定：

```text
z_theory
z_theory_policy
```

### 推荐参数

Smoke：

```text
d in {300, 1000}
k = 2
l = 6
a in {0.0, 0.3333333333, 0.6}
z in {0, 1, 2, 3, 4}
probe_trials = 5
final_trials = 10
```

论文规模：

```text
d in {100, 300, 1000, 3000, 10000}
k = 2
l = 6
a grid = same as Figure 2(a)
z grid = same as Figure 2(a), possibly extended for large d
probe_trials >= 30
final_trials >= 100
```

### 实现计划

复用 `tests/test_az_grid.py` 的输出。提取脚本已实现为：

```text
tests/extract_fig2_z_star.py
```

职责：

1. 读取 `tests/results/paper_fig2_az_grid/summary.jsonl`。
2. 过滤 `status = ok`。
3. 按 `d,k,l` 分组。
4. 按平局规则选择 `(a_star,z_star)`。
5. 计算 `z_theory`。
6. 写出：

```text
tests/results/paper_fig2_z_star/summary.jsonl
tests/results/paper_fig2_z_star/summary.csv
tests/results/paper_fig2_z_star/summary.md
```

重要字段：

```text
experiment = paper_fig2_z_star
record_type = aggregate
d
l
k
a_star
z_star
R_w30_at_star
best_M_at_star
z_theory
z_theory_policy
delta_z = z_star - z_theory
source_summary
```

## 绘图计划

创建或扩展：

```text
tests/plot_paper_figures.py
```

也可以先创建更窄的脚本：

```text
tests/plot_figure2.py
```

Figure 2(a)：

- 读取 `paper_fig2_az_grid/summary.csv`。
- 将 rows pivot 成 `a x z` 矩阵。
- 使用 `best_R_w30` 作为颜色。
- 用单独 hatch 或中性色标记 `unresolved`/`invalid` cell。
- 如果图面仍然清晰，可以标注最佳 cell。

Figure 2(b)：

- 读取 `paper_fig2_z_star/summary.csv`。
- 随 `d` 绘制 `z_star` 和 `z_theory`。
- 如果 `d` 跨多个数量级，横轴使用 log-scale。

输出：

```text
tests/results/paper_figures/figure2a_az_heatmap.pdf
tests/results/paper_figures/figure2a_az_heatmap.png
tests/results/paper_figures/figure2b_z_star.pdf
tests/results/paper_figures/figure2b_z_star.png
```

## 验证

使用结果前运行：

```powershell
python tests\json_verifier.py tests\results\paper_fig2_az_grid\probes.jsonl --strict
python tests\json_verifier.py tests\results\paper_fig2_az_grid\summary.jsonl --strict
python tests\json_verifier.py tests\results\paper_fig2_z_star\summary.jsonl --strict
```

人工检查：

- 所有论文 row 使用 `target_success_rate = 0.9`。
- 所有论文 row 使用 `ci_confidence = 0.95`。
- 论文运行中 `dataset_mode` 应为 `shared_file`。
- 对 accepted cell，`RangeLength = M // (z + 1)` 不应过小。
- 最优 cell 不应是很低 `final_trials` 导致的偶然现象。

## 建议命令

Smoke heatmap：

```powershell
python tests\test_az_grid.py `
  --d-values 300 `
  --k-values 2 `
  --l-values 6 `
  --a-values 0,0.3333333333,0.6 `
  --z-values 0,1,2,3 `
  --probe-trials 5 `
  --final-trials 10 `
  --target-success-rate 0.9 `
  --shared-datasets `
  --output-dir tests\results\paper_fig2_az_grid_smoke
```

论文 heatmap：

```powershell
python tests\test_az_grid.py `
  --d-values 3000 `
  --k-values 2 `
  --l-values 6 `
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 `
  --z-values 0,1,2,3,4,5,6,8,10,12,16 `
  --probe-trials 30 `
  --final-trials 100 `
  --target-success-rate 0.9 `
  --shared-datasets `
  --output-dir tests\results\paper_fig2_az_grid
```

提取 `z_star(d)`：

```powershell
python tests\extract_fig2_z_star.py `
  --input tests\results\paper_fig2_az_grid\summary.jsonl `
  --output-dir tests\results\paper_fig2_z_star
```

## 当前状态

```text
Figure 2(a): data generation implemented
  tests/test_az_grid.py 已能运行联合 (a,z) threshold grid。
  heatmap 绘图仍未实现。

Figure 2(b): data extraction implemented
  tests/extract_fig2_z_star.py 已能提取 z_star(d)、a_star(d) 和 z_theory。
  绘图仍未实现。

Figure 3 dependency: open
  Figure 2 应输出 tuned (a,z)，尤其是 (k,l)=(2,6)。
```
