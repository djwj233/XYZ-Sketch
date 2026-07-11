# XYZ-Sketch

XYZ-Sketch 是一个面向集合协调（set reconciliation）的 C++ sketch。Alice 和 Bob
分别持有集合 `A`、`B`，目标是在集合很大、对称差
`d = |(A \ B) union (B \ A)|` 较小时，用接近 `d` 个域元素的通信恢复带方向的完整差集。

本仓库包含：

- `XYZ-Sketch/`：XYZ-Sketch 的完整实现；
- `IBLT/`：论文端到端比较使用的本地 conventional IBLT；
- `external/`：MiniSketch、Rateless IBLT、CPISync 等固定版本的上游实现；
- `tests/benchmarks/`：统一数据格式下的 C++/Go benchmark adapter；
- `tests/*.py`：参数搜索、概率实验、数据校验和绘图入口；

对应论文草稿为 *Toward Optimal Time-Space Tradeoffs for Set Reconciliation*。
仓库内 PDF 仅用于核对，不是构建依赖。

## 当前状态

代码已经统一到以下正式实验口径：

- 成功必须精确恢复 `A \ B` 和 `B \ A`，不只检查 decode 是否结束；
- 概率结果默认使用 `100` 个独立 final trials；
- 参数搜索默认每个 probe 使用 `30` 个 trials；
- 目标成功率为 `0.9`，并输出 95% Wilson 区间；
- 同一组参数比较默认复用相同数据集或相同 trial seeds；
- 任意 trial 未完成时，聚合状态为 `incomplete`，不能被阈值搜索接受；
- update 指标统一为“从空状态构造 Alice、Bob 两个 sketch 并插入全部元素”的
  amortized 时间，再除以 `|A|+|B|`；
- 正式完整运行默认不设置 job timeout；需要限时 smoke test 时必须显式传入 timeout；
- 端到端 `run_config.json` 记录 CLI、Git revision、Python、编译器、CPU 数和内存；其他驱动至少记录完整 CLI。

## 环境

推荐 Ubuntu 20.04 或更新版本。基础依赖：

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential git python3 golang \
  libntl-dev libgmp-dev libgoogle-perftools-dev
```

建议使用 Python 3.8+、GCC 9+、Go 1.21。初始化固定版本的第三方实现：

```bash
git submodule update --init --recursive
```

CPISync 依赖 NTL、GMP、tcmalloc 和 pthread。构建脚本在依赖不足时会生成一个
`unavailable` stub；正式实验前必须检查输出中的 `implementation` 和 `status`，不能把
stub 当作真实基线。

## 最小使用示例

XYZ-Sketch 的参考程序：

```bash
g++ -std=c++17 -O2 XYZ-Sketch/sample.cpp -o build/xyz_sketch_sample
./build/xyz_sketch_sample
```

论文 benchmark 的统一小规模 smoke test：

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100 \
  --probe-trials 3 \
  --final-trials 5 \
  --job-timeout-s 300 \
  --output-dir artifacts/smoke_figure2
```

smoke test 只检查构建、数据流和输出格式，不是论文数据。

## 数据和指标

默认域为 `F_998244353`，元素非零，论文归一化 word width 为 `w=30`。
共享数据文件由 `tests/dataset_generator.py` 生成，包含两个无重复集合及完整元数据。

主要指标：

```text
R_w30 = transmitted_bits / (30 * d)
update_avg_s_per_element = build_both_sketches_s / (ca + cb)
decode_avg_s_per_difference = decode_or_reconcile_s / d
```

固定 sketch 的 `bits` 是实际序列化 payload。Rateless IBLT 使用发送 coded symbols 的
P90 通信量；CPISync 使用 client 侧发送与接收字节之和。XYZ 当前 `bits` 不包含双方预先
约定的 `M,k,l,a,z` 配置；论文应将这些参数明确写成 shared public configuration，或者
定义并计入协议头。

严格校验任意正式 JSONL：

```bash
python3 tests/json_verifier.py PATH/summary.jsonl --strict
```

严格校验会拒绝 trial 数不完整、`success_rate` 不一致、通信字段不一致的结果。

## 启发式参数

正式实验入口当前使用：

```text
C = 0.27591534917087435
D = 0.5
delta = 0.1
```

实现约定为：

```text
a = C * c_orient / c_peel
z = round(D * (1-a)^(2/3) * (M/log(1/delta))^(1/3))
```

## 正式重跑论文实验

每次正式运行应写入独立的新目录。长任务建议在 `tmux` 中执行。

### 1. Figure 1(a)：完整实现 sharp threshold

```bash
python3 tests/test_xyz_sharp_threshold.py \
  --d-values 10000 \
  --tuple-values 2:3,2:6,3:4 \
  --modes random,naive,circular \
  --trials 100 \
  --points 41 \
  --a-constant 0.27591534917087435 \
  --z-constant 0.5 \
  --delta 0.1 \
  --output-dir artifacts/paper_fig1_sharp_threshold_formal

python3 tests/json_verifier.py \
  artifacts/paper_fig1_sharp_threshold_formal/raw.jsonl --strict
python3 tests/json_verifier.py \
  artifacts/paper_fig1_sharp_threshold_formal/summary.jsonl --strict

python3 tests/plot_figure1.py \
  --sharp-input artifacts/paper_fig1_sharp_threshold_formal/raw.csv \
  --sharp-summary artifacts/paper_fig1_sharp_threshold_formal/summary.csv \
  --frontier-input /tmp/no-frontier.csv \
  --output-dir artifacts/paper_figures_formal/figure1a
```

### 2. Figure 1(b,c) 和 Appendix Figure 3：理想 cell peeling

小规模候选 `M` 的完整上游流程是：完整 XYZ a/z threshold search、提取候选 `M`、
固定 `M` 理想 peeling 重测。

```bash
python3 tests/test_az_grid.py \
  --d-values 300,1000,3000,10000 \
  --l-values 6 --k-values 2 \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --z-values 0,1,2,3,4,5,6,8,10,12,16 \
  --probe-trials 30 --final-trials 100 \
  --output-dir artifacts/paper_heatmap_threshold_formal

python3 tests/extract_fig2_m_candidates.py \
  --input artifacts/paper_heatmap_threshold_formal/summary.jsonl \
  --output-dir artifacts/paper_heatmap_candidates_formal

python3 tests/test_fig2_fixed_m_sim.py \
  --m-candidates artifacts/paper_heatmap_candidates_formal/m_candidates.csv \
  --trials 100 --jobs 6 \
  --output-dir artifacts/paper_heatmap_fixed_m_formal
```

`test_fig2_fixed_m_sim.py` 默认对所有 grid cells 使用相同 trial seeds，以减少参数间比较
噪声。需要独立 seeds 时显式传 `--independent-trial-seeds`。

大规模 `d=100000,1000000` workflow：

```bash
python3 tests/run_figure2_large_d.py \
  --d-values 100000,1000000 \
  --trials 100 --jobs 6 \
  --output-root artifacts/paper_heatmap_large_d_formal \
  --figure-root artifacts/paper_figures_formal/appendix_figure3_large
```

最后使用 `plot_figure2_selected_panels.py --input ...` 选择正文和附录 panel。

### 3. Figure 2：五算法端到端 frontier

这一步会非常慢，尤其是 MiniSketch decode、CPISync 和大 `d`。默认参数已经是
30 probe trials、100 final trials、五个论文算法、共享数据集和无 timeout。

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000 \
  --algorithms xyz_sketch,iblt,minisketch,riblt,cpisync \
  --fixed-parameter-algorithms minisketch,cpisync \
  --probe-trials 30 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --a-constant 0.27591534917087435 \
  --z-constant 0.5 \
  --delta 0.1 \
  --job-timeout-s 0 \
  --keep-datasets \
  --output-dir artifacts/paper_fig2_end_to_end

python3 tests/json_verifier.py \
  artifacts/paper_fig2_end_to_end/summary.jsonl --strict

python3 tests/plot_figure2_end_to_end.py \
  --input artifacts/paper_fig2_end_to_end/summary.jsonl \
  --output-dir artifacts/paper_figures_formal/figure2 \
  --hide-unresolved
```

## 输出与版本控制

实验目录通常包含：

```text
run_config.json   完整参数和环境
probes.jsonl      搜索过程
raw.jsonl         原始测量
summary.jsonl     机器可读汇总
summary.csv       绘图输入
summary.md        人工检查表
errors.log        timeout、构建或解析错误
```

生成的数据和图默认写入 `artifacts/`。准备 artifact 时，应同时归档运行配置、原始测量、汇总数据、校验输出与最终图像。

## 代码质量检查

```bash
python3 -m py_compile tests/*.py
python3 tests/json_verifier.py artifacts/paper_fig2_end_to_end/summary.jsonl --strict
git diff --check
```

对论文结果做任何合并前，先保证每个 `status=ok` 的 threshold row 满足：

```text
trials == completed_trials == attempted_trials == final_trials
error_trials == 0
successes / trials == success_rate
```
