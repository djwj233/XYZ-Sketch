# Figure 1(b)：固定 M 通信前沿实验计划

## 1. 实验目标

Figure 1(b) 用来观察差异规模 `d` 增大时，拟合得到的 circular 启发式策略所需的通信比率：

```text
横轴 = d
纵轴 = 固定 M 在实测成功率不低于 0.9 时对应的 R_w30
```

新流程不再搜索或二分 `M`。每个 `d` 复用已有实验确定的一个 `M`，只测试一个启发式 `(a,z)` 配置，运行 100 次 trial，并判断该固定配置能否达到 90% 的目标成功率。

## 2. 实验范围

统一使用：

```text
d in {100, 300, 1000, 3000, 10000, 100000, 1000000}
k = 2
l = 6
trials = 100
target_success_rate = 0.9
confidence_interval = 95% Wilson
dedup_hashes = false
base_seed = 114514
```

固定配置如下：

| d | M | a | z | M*l/d | 预期 R_w30 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 26 | 1/3 | 1 | 1.560000 | 1.698667 |
| 300 | 67 | 1/3 | 1 | 1.340000 | 1.459111 |
| 1,000 | 211 | 1/3 | 2 | 1.266000 | 1.378533 |
| 3,000 | 596 | 1/3 | 2 | 1.192000 | 1.297956 |
| 10,000 | 1,948 | 1/3 | 4 | 1.168800 | 1.272693 |
| 100,000 | 18,155 | 1/3 | 8 | 1.089300 | 1.186127 |
| 1,000,000 | 178,767 | 1/3 | 16 | 1.072602 | 1.167944 |

`d=100` 使用 `M=26`。已有的更小取值在启发式点上没有达到目标：`M=23` 为 72/100，`M=24` 为 89/100。

前五组配置已经有 Figure 2 的 100-trial 模拟结果。`d=100000` 和 `d=1000000` 之前只运行了 20 trials，因此本次实验将为这两个点补足正式的 100-trial 验证。

这些 M 当前实际来自 Figure 2 结果，因为本地工作区没有完成的论文规模 Figure 1 或 Figure 3 输出。最终 source manifest 必须如实记录这一来源，不能声称这些 M 来自已经完成的 Figure 1/3 实验。

## 3. 启发式参数

使用新 Figure 2 黄色标记采用的拟合公式：

```text
C_orient / C_peel = 1.2081
C = (1/3) / 1.2081
a = C * (C_orient / C_peel) = 1/3
D = 0.5
delta = 0.1

z_continuous = D * (1-a)^(2/3) * (M / log(1/delta))^(1/3)
z = round(z_continuous)
```

runner 必须根据公式计算 `a` 和 `z`，然后检查结果是否与上表一致。表格只用于可复现性校验，不能成为另一套独立的启发式参数来源。

## 4. 模拟模型

主实验使用与新 Figure 2 相同的结构性 peeling 模拟器：

```text
tests/benchmarks/fig2_peeling_sim.cpp
```

每个 trial 根据 `(d,k,l,M,a,z)` 生成 circular coupling 随机超图，并检查 peeling 能否删除所有边。它不会构造完整集合，也不会执行 `XYZSketch::Decode()`、多项式重构、根查找、fingerprint 校验或最终集合差分比对。

这样做可以保证模型与产生固定 M 的实验一致，也使 `d=1000000` 的 100 trials 具有可执行性。因此论文正文和图注必须将这条曲线称为 **peeling simulation communication frontier**，不能称为端到端解码 benchmark。后续可以额外增加较小 `d` 上的端到端抽查，但不改变本次固定 M 主实验。

## 5. 通信量口径

模拟器当前主要报告结构成功率，`bits` 可能仍为 0。Figure 1(b) 必须根据 XYZ-v2 sketch 布局推导通信量：

```text
cell_bits = (floor(log2(2*l + 1)) + 1) + 32*l
bits = M * cell_bits
R_w30 = bits / (30*d)
```

当 `l=6` 时：

```text
cell_bits = 196
R_w30 = 196*M / (30*d)
```

输出中必须同时保留：

```text
field_C_over_d = M*l/d
R_w30 = M*cell_bits/(30*d)
```

这两个量相关，但不能混用。

## 6. Runner 设计

新增专用 runner：

```text
tests/test_figure1b_fixed_m.py
```

纳入版本管理的固定 M 配置文件为：

```text
tests/figure1b_fixed_m_config.csv
```

本实验不使用 `tests/test_frontier_xyz.py`，因为该 wrapper 会执行 M 的阈值搜索。新 runner 应完成：

1. 读取纳入版本管理的 `(d,M)` 配置表，或使用上述七组默认值。
2. 使用共享公式 helper 计算启发式 `a` 和 `z`。
3. 构建或复用 `build/fig2_peeling_sim`。
4. 每个 `(d,M)` 只启动一个模拟任务，并固定使用 `--trials 100`。
5. 添加 95% Wilson 区间和推导出的通信量字段。
6. 写入 `target_met = success_rate >= 0.9`。
7. 每完成一组就立即落盘，使 `--resume` 可以安全续跑。
8. 支持 `--jobs`，同时保证每组配置的 seed 确定且可复现。

计划命令：

```bash
python3 tests/test_figure1b_fixed_m.py \
  --trials 100 \
  --target-success-rate 0.9 \
  --jobs 2 \
  --output-dir tests/results/paper_fig1b_fixed_m
```

中断续跑命令：

```bash
python3 tests/test_figure1b_fixed_m.py \
  --trials 100 \
  --target-success-rate 0.9 \
  --jobs 2 \
  --resume \
  --skip-build \
  --output-dir tests/results/paper_fig1b_fixed_m
```

runner 和以上两条命令均已实现。

## 7. 输出约定

输出目录和文件：

```text
tests/results/paper_fig1b_fixed_m/raw.jsonl
tests/results/paper_fig1b_fixed_m/summary.jsonl
tests/results/paper_fig1b_fixed_m/summary.csv
tests/results/paper_fig1b_fixed_m/summary.md
tests/results/paper_fig1b_fixed_m/run_config.json
tests/results/paper_fig1b_fixed_m/errors.log
```

summary 必须包含：

```text
d, k, l, M
circular_a, z, z_continuous
trials, successes, success_rate
ci_low, ci_high, ci_method, ci_confidence
target_success_rate, target_met, status
cell_bits, bits, field_C_over_d, R_w30
seed, dedup_hashes, simulation_model
M_source_file, M_source_description
```

最终 summary 应当恰好有七行。

## 8. 绘图设计

新增：

```text
tests/plot_figure1b.py
```

绘图命令：

```bash
python3 tests/plot_figure1b.py \
  --input tests/results/paper_fig1b_fixed_m/summary.csv \
  --output-dir tests/results/paper_figures/figure1b_fixed_m
```

由于 `d` 跨越四个数量级，主图使用对数横轴：

```text
横轴 = d（log scale）
纵轴 = R_w30
折线和普通数据点 = target_met=true 的行
失败标记 = target_met=false 的行
```

不能把失败点静默画成“90% 成功率通信前沿”。如果某个固定 M 的成功次数少于 90，应在源数据中保留，并用不同的失败标记画出，但不能把它连接到通过验证的前沿折线上。禁止自动增大 M，也禁止隐藏地重新执行二分搜索。

计划输出：

```text
tests/results/paper_figures/figure1b_fixed_m.svg
tests/results/paper_figures/figure1b_fixed_m_source.csv
tests/results/paper_figures/figure1b_fixed_m_source.md
```

## 9. 验证清单

接受最终图片前必须检查：

1. 数据恰好包含七个互不重复的 `d` 和七行 summary。
2. 每行均为 `k=2`、`l=6`、`trials=100`、`a=1/3`。
3. 根据公式重新计算 `z`，并与记录的整数比较。
4. 独立重新计算 `bits`、`field_C_over_d` 和 `R_w30`。
5. 检查 `successes/trials == success_rate` 和 Wilson 区间。
6. 对 `summary.jsonl` 运行 strict JSON verifier。
7. 如实记录所有 `target_met=false` 行，不自动修改 M。
8. 在图注明确说明成功率来自 peeling simulation。

## 10. 实施顺序

1. 固定 M 配置、runner 和绘图器已经实现。
2. 使用 `d=100,300` 和 5 trials 做两点 smoke test。
3. 启用断点续跑，运行全部七组配置，每组 100 trials。
4. 验证结果，并检查所有低于 0.9 的点。
5. 使用 `plot_figure1b.py` 生成 SVG 和 source manifest。
6. simulation 图稳定后，再考虑增加端到端解码抽查。
