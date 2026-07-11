# Figure 1 服务器运行流程

本文档记录这台服务器上 Figure 1 的实际工程运行方式，包括入口脚本、参数、
输出文件和当前结果状态。

所有命令都从仓库根目录运行：

```bash
cd /root/XYZ-Sketch
```

## 范围

Figure 1 与 Figure 2、Figure 3 相互独立。

- Figure 1(a)：XYZ-v2 的 sharp-threshold 曲线。
- Figure 1(b)：只针对 XYZ 的 communication frontier。
- 代表性 tuple：`(k,l) = (2,3), (2,6), (3,4)`。
- 模式：`random`、`naive`、`circular`。
- 在当前代码中，`random` 是 iid hashing baseline。
- `naive` 和 `circular` 是两种 spatial-coupling 变体。

Figure 1 中 `a` 和 `z` 不是手写固定值，而是按公式计算：

```text
a = C * c_orient / c_peel, C = 1/3
z = D * (1-a)^(2/3) * (M/log(1/delta))^(1/3), D = 4/3
```

`c_orient` 和 `c_peel` 的常数与计算逻辑在 `tests/xyz_tuning.py` 中。
论文使用的几个 tuple 对应的 `a` 会写入每次实验的 run config。

## Figure 1(a)：Sharp Threshold

入口脚本：

```text
tests/test_xyz_sharp_threshold.py
```

服务器规模命令：

```bash
python3 tests/test_xyz_sharp_threshold.py \
  --d-values 10000 \
  --tuple-values 2:3,2:6,3:4 \
  --modes random,naive,circular \
  --trials 100 \
  --center-trials 10 \
  --window-fraction 0.06 \
  --min-window 20 \
  --max-window 120 \
  --step 3 \
  --target-success-rate 0.9 \
  --a-constant 0.3333333333 \
  --z-constant 1.3333333333 \
  --output-dir tests/results/paper_fig1_sharp_threshold
```

工程流程：

1. 构建或复用 `xyz_v2_bench`。
2. 对每个 `(k,l,mode)` 配置，先用 `--center-trials 10` 做小规模中心搜索，估计阈值中心 `M0`。
3. 只扫描窗口 `M0 +/- min(max(0.06*M0, 20), 120)`。
4. 使用 `--step 3`，即候选 `M` 每次间隔 3。
5. 每个候选 `M` 运行 `--trials 100`。
6. 写出原始曲线点和阈值 summary。

重要输出文件：

```text
tests/results/paper_fig1_sharp_threshold/raw.jsonl
tests/results/paper_fig1_sharp_threshold/raw.csv
tests/results/paper_fig1_sharp_threshold/summary.jsonl
tests/results/paper_fig1_sharp_threshold/summary.csv
tests/results/paper_fig1_sharp_threshold/summary.md
tests/results/paper_fig1_sharp_threshold/run_config.json
```

当前服务器状态：

- 这组实验结果已经存在。
- 当前 run config 位于
  `tests/results/paper_fig1_sharp_threshold/run_config.json`。
- 它使用 `--tuple-values 2:3,2:6,3:4`，因此不会误跑
  `--k-values` 和 `--l-values` 的笛卡尔积。
- 总共 9 个配置：3 个 tuple 乘以 3 个 mode。
- 已有备份目录：

```text
tests/results/paper_fig1_sharp_threshold_backup_20260709_065443
tests/results/paper_fig1_sharp_threshold_backup_20260709_222516
```

## Figure 1(b)：Communication Frontier

入口脚本：

```text
tests/test_frontier_xyz.py
```

服务器规模命令：

```bash
python3 tests/test_frontier_xyz.py \
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 \
  --tuple-values 2:3,2:6,3:4 \
  --modes random,naive,circular \
  --probe-trials 50 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --a-constant 0.3333333333 \
  --z-constant 1.3333333333 \
  --output-dir tests/results/paper_fig1_frontier
```

工程流程：

1. `tests/test_frontier_xyz.py` 是论文实验用 wrapper。
2. 它会按 tuple 列表拆成多个 shard。
3. 每个 tuple shard 会调用 `tests/test_spatial.py`。
4. 每个 shard 对每个 `d` 和 mode 搜索达到 90% 成功率所需的最小 `M`。
5. 预期最终会把各 shard 的 `probes` 和 `summary` 合并到顶层目录。

预期顶层输出文件：

```text
tests/results/paper_fig1_frontier/probes.jsonl
tests/results/paper_fig1_frontier/summary.jsonl
tests/results/paper_fig1_frontier/summary.csv
tests/results/paper_fig1_frontier/summary.md
tests/results/paper_fig1_frontier/run_config.json
```

当前服务器状态：

- `tests/results/paper_fig1_frontier` 顶层目前没有合并后的
  `summary.csv` 和 `run_config.json`。
- 但三个 shard 的输出存在：

```text
tests/results/paper_fig1_frontier/shards/k2_l3/
tests/results/paper_fig1_frontier/shards/k2_l6/
tests/results/paper_fig1_frontier/shards/k3_l4/
```

- 当前 shard 行数：

```text
k2_l3: 18 summary rows
k2_l6: 10 summary rows
k3_l4: 10 summary rows
total: 38 summary rows
```

- 当请求的顶层 `summary.csv` 不存在时，`tests/plot_figure1.py`
  现在可以直接读取这些 shard summary。

## 数据验证

把数据作为论文输入前，建议先运行 strict JSON verifier：

```bash
python3 tests/json_verifier.py tests/results/paper_fig1_sharp_threshold/raw.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_sharp_threshold/summary.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/shards/k2_l3/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/shards/k2_l3/summary.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/shards/k2_l6/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/shards/k2_l6/summary.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/shards/k3_l4/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/shards/k3_l4/summary.jsonl --strict
```

## 绘图

入口脚本：

```text
tests/plot_figure1.py
```

这台服务器上使用的绘图命令：

```bash
python3 tests/plot_figure1.py \
  --sharp-input tests/results/paper_fig1_sharp_threshold/raw.csv \
  --frontier-input tests/results/paper_fig1_frontier/summary.csv \
  --output-dir tests/results/paper_figures
```

已生成 SVG：

```text
tests/results/paper_figures/figure1a_sharp_threshold.svg
tests/results/paper_figures/figure1b_frontier.svg
tests/results/paper_figures/figure1_source_summary.md
```

当前 source summary 记录：

```text
Figure 1(a) raw rows read: 725
Figure 1(a) summary rows read: 9
Figure 1(b) rows read from shards: 38
Figure 1(b) unresolved rows marked, not hidden: 11
```

## 运行注意事项

- 如果 VSCode 连接可能断开，长实验应放在 `tmux` 里跑。
- `status=unresolved` 表示 final validation 没达到目标成功率，本身不等于程序崩溃。
- 如果 Figure 1(b) 要作为干净的最终 artifact，建议重新运行或修复 wrapper merge，
  让顶层 `summary.csv`、`summary.jsonl` 和 `run_config.json` 都存在。
