# Figure 3 服务器运行流程

本文档记录这台服务器上 Figure 3 的实际工程运行方式，包括入口脚本、实验流程、
命令、输出文件和当前结果状态。

所有命令都从仓库根目录运行：

```bash
cd /root/XYZ-Sketch
```

## 范围

Figure 3 用 XYZ-Sketch 和实用 set-reconciliation baseline 做对比。
同一次共享实验会生成三个 panel 需要的数据：

- Figure 3(a)：communication frontier，使用 `best_R_w30`。
- Figure 3(b)：update cost，使用 `update_avg_s_per_element`。
- Figure 3(c)：decode cost，使用 `decode_avg_s_per_difference`。

当前 frontier runner 支持的算法：

```text
xyz_v1, xyz_v2, iblt, minisketch, cpisync, riblt, negentropy
```

主实验入口：

```text
tests/test_compare_frontier.py
```

绘图入口：

```text
tests/plot_figure3.py
```

## 外部依赖

Figure 3 会使用外部 baseline 实现。干净运行前应先初始化 submodule：

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

除非传入 `--skip-build`，runner 会自动构建或准备 benchmark binary。

## XYZ-v2 参数策略

`xyz_v2` 当前默认使用公式选参，而不是 Figure 2 调参结果：

```text
a = C * c_orient / c_peel, C = 1/3
z = D * (1-a)^(2/3) * (M/log(1/delta))^(1/3), D = 4/3
```

实现位置：

```text
tests/xyz_tuning.py
```

当前 Figure 3 默认：

```text
(k,l) = (2,6)
a = 0.4026505079327622
z = 对每个候选 M 按公式动态计算
```

以后如果要切回 Figure 2 选出的 tuned 参数，可以传入：

```bash
--xyz-tuning tests/results/paper_fig2_z_star/summary.jsonl
```

## 科学重跑计划

现有 Figure 3 结果只能作为诊断数据。在修复下面的工作负载、通信量、统计方法和
计时定义之前，不能直接把现有实验扩展到更大的 `d` 并作为论文结果。

### 实验不变量

重跑时必须在所有 `d` 上保持以下条件不变：

1. 只使用一套集合规模比例。主实验计划采用 `ca = cb = 2d`，此时
   `common/d = 1.5`。删除当前 minimum size 和 `max_set_size` 导致的分段制度。
2. 对同一个 `d`，所有算法使用完全相同的 trial datasets。
3. search 和 final validation 使用互不重叠的数据集。用于选择参数的数据不能再次
   用于验证该参数。
4. 对支持 30-bit 元素的算法统一使用同一个 30-bit universe。Negentropy 这种原生
   256-bit ID 协议必须单独标注，不能无说明地当成 30-bit sketch。
5. 不再只给 XYZ 增加 final slack。要么精确验证搜索得到的参数，要么对所有固定容量
   算法统一采用由统计区间定义的保守上界。

分阶段使用以下 `d`：

```text
smoke:       100, 1000
main:        100, 300, 1000, 3000, 10000, 30000, 100000, 300000, 1000000
large-scale: 主网格通过验证后，再运行 3000000, 10000000
```

大规模数据必须增量生成并消费，不能在磁盘上同时保留几百个、每个包含约 `4d`
个元素的文本数据文件。

### 当前 runner 状态

runner 已经完成下一轮 smoke 前必须有的基础修复：

- 默认 workload 改为 `--set-size-policy fixed-ratio` 和
  `--set-size-ratio 2.0`，所以标准网格在偶数 `d` 上使用 `ca = cb = 2d`。
  旧的 minimum size / `max_set_size` 截断逻辑仍可通过
  `--set-size-policy legacy` 复现历史实验。
- search 和 final validation 现在使用互不相交的数据集切片。每个
  `(algorithm, d)` 会准备 `probe_trials + final_trials` 个共享 datasets；
  search 使用前一段，final validation 使用后一段。
- trial 聚合不再从 trial 0 继承通信字段。runner 会为 `bits`、
  `symbols_sent`、`rounds`、`client_bytes`、`server_bytes` 等可能随数据变化的
  字段记录 average、median 和 90th percentile。如果 `bits` 在 trials 间变化，
  主通信预算使用经验 90th percentile。
- RIBLT 计量现在把一个 coded symbol 记为
  `symbol_bits + 64-bit hash + 64-bit count`；当前默认 `symbol_bits=64`，
  因此是 192 bits/transmitted coded symbol。`field_bits` 对当前 wrapper 仍只是
  metadata，不代表已经实现了 30-bit compact serialization。
- runner 现在支持对接近成功的 final validation 做有限向上 retry。推荐使用
  `--final-retry-algorithms xyz_v2,iblt,riblt`、
  `--final-retry-growth 1.05`、`--final-retry-limit 4` 和
  `--final-retry-min-success-rate 0.75`。每次 retry 都在同一组 held-out final
  datasets 上重新验证，并记录 `final_retry_count`、`search_parameter`、
  `best_parameter` 和 `final_parameter_multiplier`。

这些修复使下一轮 `d <= 10000` smoke 具备工程诊断价值，但还不能替代下面的最终统计协议。

### 计划测试队列

Minisketch 加入每一次新的 correctness smoke 和核心对比队列。

| 队列 | 算法 | 用途 |
| --- | --- | --- |
| Q0：wrapper correctness | `xyz_v2,minisketch,iblt,riblt,negentropy` | 在 `d=100,1000` 验证差异恢复、通信计量和计时边界。 |
| Q1：核心 frontier | `xyz_v2,minisketch,iblt,riblt` | 主要的单向/固定预算通信对比。 |
| Q2：交互协议 | `negentropy` | 固定 frame，单独报告总字节数和轮次。 |
| Q3：可选附录 | `cpisync,xyz_v1` | 仅在通信计量和容量语义审计完成后运行。 |

下面的命令只用于立即确认当前 Minisketch wrapper 可以构建和运行：

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100,1000 \
  --algorithms minisketch \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9 \
  --output-dir tests/results/paper_fig3_minisketch_smoke
```

这次 smoke 不是论文数据，因为它仍使用小样本二分搜索，而不是最终的 grid/isotonic
统计协议。

### 必须完成的实现修复

开始论文质量的 Q1 前，还需要完成以下修改：

1. 对 XYZ、Minisketch 和 IBLT，用容量网格加 isotonic success-rate fit 替换带噪声的
   5-trial 二分。
2. 至少使用 50 个独立 search trials 和 200 个独立 final trials，并为推断出的 90%
   通信阈值报告 bootstrap 置信区间。
3. 有限 final retry 只能作为 smoke-run 修补策略，不能替代最终 estimator。它适合当前
   Figure 3 诊断，因为能用可控额外开销把接近 90% 的二分候选点修到通过；但论文质量
   Q1 仍应使用 grid/isotonic 估计。
4. RIBLT 使用足够大的 cap，测量每个 trial 实际需要的 coded symbols，以经验 90%
   分位数作为通信预算。计量真实序列化后的 coded symbol，必须包含 symbol、hash 和
   count；当前 wrapper 已修复基础的 192-bit coded-symbol 计量，但搜索策略仍是 cap
   search，还不是专门的 required-symbol distribution 实验。
5. Negentropy 不再把 `frame_size_limit` 当容量搜索。固定并记录 frame policy，
   初始采用 64 KiB，报告总字节数、轮次及其分布。如果要画通信 frontier，必须实现
   显式累计字节预算。
6. 保持历史输出目录不变，修正后的数据写入
   `tests/results/paper_fig3_v2_*`。

### 有限 final retry

对搜索型算法，推荐的 smoke-run 命令是：

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000 \
  --algorithms xyz_v2,iblt,riblt \
  --probe-trials 5 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --final-retry-algorithms xyz_v2,iblt,riblt \
  --final-retry-growth 1.05 \
  --final-retry-limit 4 \
  --final-retry-min-success-rate 0.75 \
  --job-timeout-s 0 \
  --output-dir tests/results/paper_fig3_v2_retry_frontier
```

这个模式不会 retry 明显很差的候选点。如果第一次 final validation 低于
`--final-retry-min-success-rate`，该点仍然保持 unresolved。这样可以避免错误搜索或坏
wrapper 触发大量额外 final validation。

### 通信指标

核心 frontier 的定义为：

```text
x = d
y = 达到 90% 成功率所需的最小序列化通信预算
normalization = transmitted_bits / (30*d)
```

各算法通信量口径：

| 算法 | 通信量 |
| --- | --- |
| XYZ-v2 | 选中 `M` 对应的序列化 sketch bits。 |
| Minisketch | capacity 乘 30-bit field width，并计入字节取整。 |
| IBLT | canonical serialized cell width 乘选中的 cell count。 |
| RIBLT | 成功解码所需 serialized coded-symbol bytes 的 90% 分位数。 |
| Negentropy | 固定 frame policy 下双向总字节数的分布；不混入 fixed-sketch frontier。 |

不要强制原始曲线单调。有限规模估计允许波动；论文主张应是带不确定性的收敛，因此图中
展示实测点、bootstrap 区间，以及可选且明确标注的 isotonic trend。

### 时间指标

时间实验必须从通信 frontier 中拆开，并使用通信实验选出的容量。所有 wrapper 统一暴露：

```text
sender_update_s_per_element
receiver_update_s_per_element
decode_or_reconcile_s_per_difference
```

使用进程内 warmup、重复测量、median 和 bootstrap 置信区间。不能继续比较当前混合口径：
XYZ 只计 Alice，RIBLT 计双方本地结构，而 Negentropy 把 storage construction 放进
reconciliation。

### 重跑准入条件

只有下面的 smoke assertions 全部通过，才能启动完整 Q1：

- 每个成功 row 都精确恢复 symmetric difference；
- 固定容量增加时，isotonic success estimate 不下降；
- 同一容量下 fixed-sketch reported bits 不随 dataset 改变；
- RIBLT wire bytes 与 coded-symbol 的真实序列化表示一致；
- search 和 validation dataset IDs 没有交集；
- 整个网格的 `ca/d` 和 `common/d` 保持常数；
- Q0 和 Q1 输出中都包含 Minisketch。

## 历史全算法实验

下面的命令和结果数量描述以前的运行。保留它们用于审计，但不能把它们当作修正后的
论文实验继续运行。

全 baseline 的服务器规模命令：

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 \
  --algorithms xyz_v1,xyz_v2,iblt,minisketch,cpisync,riblt,negentropy \
  --probe-trials 30 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --job-timeout-s 1800 \
  --a-constant 0.3333333333 \
  --z-constant 1.3333333333 \
  --output-dir tests/results/paper_fig3_compare_frontier
```

当前服务器状态：

- 输出目录已存在：

```text
tests/results/paper_fig3_compare_frontier
```

- `summary.jsonl` 当前有 45 行。
- 如果 7 个算法、11 个 `d` 全部完成，应该有 77 行 summary。
- 因此当前全算法目录不是完整最终结果。
- 后面一些大规模 job 因为 `--job-timeout-s 1800` 触发了 30 分钟超时。

重要输出文件：

```text
tests/results/paper_fig3_compare_frontier/probes.jsonl
tests/results/paper_fig3_compare_frontier/summary.jsonl
tests/results/paper_fig3_compare_frontier/summary.csv
tests/results/paper_fig3_compare_frontier/summary.md
tests/results/paper_fig3_compare_frontier/run_config.json
tests/results/paper_fig3_compare_frontier/errors.log
```

## 历史重点 subset 实验

以前为了减少运行时间使用了下面的算法集合，其中不包含 Minisketch：

```text
xyz_v2, iblt, riblt, negentropy
```

命令：

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 \
  --algorithms xyz_v2,iblt,riblt,negentropy \
  --probe-trials 5 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --job-timeout-s 0 \
  --xyz-final-m-offset 4 \
  --output-dir tests/results/paper_fig3_compare_frontier_subset \
  2>&1 | tee tests/results/paper_fig3_compare_frontier_subset/run.log
```

含义：

- 二分搜索里的每次 probe 只测 5 次。
- final validation 仍然测 100 次。
- `--job-timeout-s 0` 表示关闭每个 job 的 30 分钟时间限制。
- 对 `xyz_v2`，搜索得到的 `M` 会在 final validation 前额外加 4。
- 进度会同时输出到终端和 `run.log`。

当前服务器状态：

- 输出目录已存在：

```text
tests/results/paper_fig3_compare_frontier_subset
```

- `summary.jsonl` 当前有 36 行。
- 如果 4 个算法、11 个 `d` 全部完成，应该有 44 行 summary。
- 因此除非仍有后台进程在继续追加，否则这个 subset 目录也还不是完整最终结果。
- 不要把新的 Minisketch 队列追加到这个目录。修正后的队列必须使用新的
  `paper_fig3_v2_*` 输出目录。

重要输出文件：

```text
tests/results/paper_fig3_compare_frontier_subset/probes.jsonl
tests/results/paper_fig3_compare_frontier_subset/summary.jsonl
tests/results/paper_fig3_compare_frontier_subset/summary.csv
tests/results/paper_fig3_compare_frontier_subset/summary.md
tests/results/paper_fig3_compare_frontier_subset/run_config.json
tests/results/paper_fig3_compare_frontier_subset/run.log
```

## Runner 内部流程

对每个 `(algorithm,d)` job，`tests/test_compare_frontier.py` 会执行：

1. 构建或准备 benchmark binary。
2. 为当前 `(d, ca, cb, seed)` 生成 shared datasets。
3. 同一个 `d` 下的不同算法复用同一批 shared datasets。
4. 对算法对应的容量参数做 upper-bound search。
5. 二分搜索能通过 probe criterion 的最小参数。
6. 使用 `--final-trials` 做最终验证。
7. 每完成一个 job，就增量写出 `probes`、`summary`、`run_config` 和 `errors` 文件。

各算法搜索的容量参数：

```text
xyz_v1:      fixed
xyz_v2:      M
iblt:        cells
minisketch:  capacity
cpisync:     mbar
riblt:       max_symbols
negentropy:  frame_size_limit
```

默认目标成功率判定是 point estimate：

```text
--target-success-rate 0.9
--threshold-policy point
```

因此只有 final validation 达到至少 90% 成功率，summary 才会标记为
`ok`。如果 probe search 找到了候选参数，但 final validation 没过 90%，
summary 会标记为 `unresolved`。

## 时间指标

runner 会从 benchmark row 派生时间指标：

```text
update_avg_s_per_element = encode_avg_s / (ca + cb)
decode_avg_s_per_difference = decode_avg_s / d
```

重要 caveat：

- `cpisync` 当前报告 `encode_avg_s=0`；它的 `decode_avg_s` 更接近完整 reconcile 时间。
- `negentropy` 也有同样的 timing caveat。
- 因此 Figure 3(b) 不能把 CPISync 或 Negentropy 的 update cost 解读为真实的 0。

## 数据验证

绘图前先验证选择的结果目录：

```bash
python3 tests/json_verifier.py tests/results/paper_fig3_compare_frontier_subset/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig3_compare_frontier_subset/summary.jsonl --strict
```

如果使用全算法目录：

```bash
python3 tests/json_verifier.py tests/results/paper_fig3_compare_frontier/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig3_compare_frontier/summary.jsonl --strict
```

## 绘图

绘制 subset 结果：

```bash
python3 tests/plot_figure3.py \
  --input tests/results/paper_fig3_compare_frontier_subset/summary.jsonl \
  --output-dir tests/results/paper_figures
```

绘制全算法结果：

```bash
python3 tests/plot_figure3.py \
  --input tests/results/paper_fig3_compare_frontier/summary.jsonl \
  --output-dir tests/results/paper_figures
```

生成的 SVG：

```text
tests/results/paper_figures/figure3a_communication.svg
tests/results/paper_figures/figure3b_update_cost.svg
tests/results/paper_figures/figure3c_decode_cost.svg
tests/results/paper_figures/figure3_source_summary.md
```

`tests/plot_figure3.py` 可以直接读取 CSV 或 JSONL。三个 panel 的横轴都使用
对数刻度；通信量和时间纵轴也使用对数刻度，避免不同数量级的算法互相压缩。

- 实心点和连线表示通过 90% final validation 的结果。
- 空心叉号表示有测量值、但 final validation 未达到 90% 的候选点；这些点不参与连线。
- `encode_avg_s=0` 被视为 update timing 未提供，而不是零成本。
- `final_ci_low/high` 是成功率区间，不是通信阈值区间，因此不画成 Figure 3(a) 的纵向误差条。
- 正式论文图如果不希望显示未通过复验的候选点，可额外传入 `--hide-unresolved`。

`tests/plot_figure3.py` 当前还没有 PNG/PDF 导出；现有绘图脚本输出无依赖 SVG。

## 后台运行

Figure 3 是长实验，建议放在 `tmux` 里跑：

```bash
cd /root/XYZ-Sketch
tmux new -s fig3
```

在 tmux 会话里启动实验后，用下面按键 detach：

```text
Ctrl-b d
```

之后重新进入：

```bash
tmux attach -t fig3
```

查看 subset 日志：

```bash
tail -f /root/XYZ-Sketch/tests/results/paper_fig3_compare_frontier_subset/run.log
```

## 运行注意事项

- `status=job_timeout` 表示该 job 触发了时间限制。
- `status=unresolved` 表示 final validation 没达到 90% 目标成功率。
- `xyz_v1` 在当前 wrapper 中是固定参数 baseline。
- `minisketch` 是很强的通信 baseline；当前数据不应直接用于声称
  XYZ-v2 在所有指标上全局最优。
- 对 IBLT/RIBLT/CPISync/Negentropy 的通信对比中，当前部分结果显示
  XYZ-v2 有竞争力，但不完整行必须在论文分析中明确处理。
