# 实验 TODO 列表

本文档整理 XYZ-Sketch 项目下一阶段的实验与工程任务。它只是一份规划清单；每个条目在真正实现前，都应进一步展开成具体脚本或 benchmark 设计。

## 优先级复核结论

原列表把“带置信区间的阈值搜索”放在第一位。检查当前代码状态后，这个顺序应该调整。更合理的依赖顺序是：

```text
优先级 1：统一 JSON schema 和独立 dataset generator
优先级 2：带置信区间的统计阈值搜索
优先级 3：sharp-threshold 实验
优先级 4：算法族对比，包括 IBLT-uniform/SC 和 XYZ-uniform/SC
优先级 5：补全 external baseline 的真实接入
优先级 6：每个元素的 hash-location update 前去重
优先级 7：circular trick 参数 a
```

原因：置信区间、sharp-threshold 曲线和跨算法对比都依赖统一的 trial 记录和 shared dataset。因此基础架构应先做，尽管统计实验才是最重要的科学结果。

下面的详细章节保留了部分原有布局。实际优先级以本节复核结论和文末建议执行顺序为准。

## 当前状态快照

阅读下面较早的任务列表时，使用这些状态标签：

```text
[done]     已实现并通过 smoke
[partial]  部分脚本或 baseline 已实现，但还不完整
[open]     仍需要实现或运行完整实验
```

当前快照：

```text
[done]     benchmark.v1 normalization helper 和轻量 strict verifier
[done]     独立 dataset_generator.py
[done]     test_compare_basic.py 中的 failed_decode 聚合修复
[done]     XYZ-v2 第一阶段 --dedup-hashes 支持
[partial]  shared dataset migration：test_spatial.py 和 test_circular_a.py 已完成
[partial]  external baselines：minisketch 和 iblt_cpp 可真实运行；riblt/negentropy/cpisync 受环境限制
[partial]  多个脚本已有置信区间和 threshold rollup
[open]     paper-ready plotting/table generation
[open]     application-side workload experiments
[open]     轻量 verifier 之外的完整 canonical schema 语义
[open]     可选的 IBLT-SC hash-location deduplication
```

## 优先级 2：带统计置信区间的阈值搜索

### 目标成功率的置信区间

目标：报告达到目标成功率所需的最小通信/容量参数，并同时给出不确定性。

任务：

- 给阈值搜索结果加入置信区间。
- 对于 `0.99` 这样的目标成功率，报告达到该目标的最小 `M`。
- 报告该 `M` 处成功率估计值的置信区间。
- 同时报告阈值本身的不确定性，例如：
  - 成功率置信区间下界达到 `0.99` 的最小 `M`；
  - 成功率点估计达到 `0.99` 的最小 `M`；
  - 置信区间与目标成功率相交的一组 `M` 范围。

建议方法：

- 对 success/failure 试验使用二项分布置信区间。
- 优先使用 Wilson 或 Clopper-Pearson 区间，而不是简单正态近似。
- 保存 `trials`、`successes`、`success_rate`、`ci_low`、`ci_high`、`target_success_rate` 和 `threshold_policy`。

候选脚本：

```text
tests/test_find_best_m.py
tests/test_spatial.py
tests/test_threshold.py
```

原始计划中的目标输出。当前脚本可能使用 `probes.jsonl`、`raw.jsonl` 和 `summary.jsonl`；当前约定见 `docs/results_layout.zh-CN.md`：

```text
tests/results/<experiment>/raw.jsonl
tests/results/<experiment>/thresholds.csv
tests/results/<experiment>/summary.md
```

## 优先级 3：Sharp Threshold 实验

目标：实验性展示 sharp threshold 现象，即在临界 `M` 附近，小幅增加 `M` 会让成功率从大多失败快速跃迁到大多成功。

任务：

- 对代表性的 `(d, l, k)` 设置，在经验阈值附近密集扫描 `M`。
- 在每个 `M` 上使用足够多 trials，让跃迁曲线可见。
- 绘制或汇总 success rate 随 `M` 和 `C/d` 的变化。
- 为每个成功率点记录置信区间。
- 比较不同设置下阈值是否同样尖锐：
  - uniform placement；
  - spatial coupling；
  - 不同 `k`；
  - 不同 `d`。

建议参数：

```text
d in {1000, 3000, 10000}
l = 6
k in {2, 3}
trials >= 100 near the threshold
M grid: dense around the estimated threshold
```

预期结果：

- 一条展示相变式跃迁的成功率曲线。
- 一个近似阈值 `M` 和 `C/d` 表。
- 一段解释：这是经验证据，不是理论阈值证明。

## 优先级 1A：统一 JSON Benchmark 架构

目标：让所有算法和实验输出同一种机器可读 JSON 格式，便于管理、比较和画图。

任务：

- 定义 per-trial 行和 aggregated 行的统一 JSON schema。
- 让所有 benchmark wrapper 输出该 schema 或兼容子集。
- 清晰区分以下概念：
  - workload metadata；
  - algorithm parameters；
  - dataset generation parameters；
  - per-trial result；
  - aggregated statistics；
  - build/runtime status。
- 对不可用 baseline 使用 `status = "unavailable"`，不要让整个实验崩掉。

建议通用字段：

```text
schema_version
experiment
algorithm
variant
implementation
d
ca
cb
seed
trial
trials
dataset_id
dataset_path
dataset_mode
success
successes
success_rate
ci_low
ci_high
bits
bytes
bits_per_difference
bit_C_over_d
encode_s
decode_s
reconcile_s
status
unavailable_reason
error
```

目标输出目录结构。当前脚本可能使用 `raw.jsonl`、`probes.jsonl`、`summary.jsonl`、`raw.csv`、`summary.csv` 和 `summary.md`；当前约定见 `docs/results_layout.zh-CN.md`：

```text
tests/results/<experiment>/raw_trials.jsonl
tests/results/<experiment>/raw_aggregated.jsonl
tests/results/<experiment>/summary.md
tests/results/<experiment>/run_config.json
tests/results/<experiment>/errors.log
```

## 优先级 4：算法族对比

目标：在 IBLT-like 和 XYZ-like 算法族内部，对比 uniform placement 与 spatial coupling 的收益。

需要包含的算法：

```text
IBLT-uniform
IBLT-SC
XYZ-uniform
XYZ-SC
```

额外 baseline：

```text
local IBLT
external IBLT_Cplusplus
minisketch
CPISync
RIBLT
Negentropy
XYZ-v1
XYZ-v2
```

任务：

- 明确定义每个算法族里的 `uniform` 和 `SC` 分别是什么意思。
- 确保所有变体读取同一份生成数据。
- 在可能的地方使用可比较的容量参数。
- 固定参数实验报告成功率、时间和通信量。
- 阈值搜索实验报告达到目标成功率所需的最小通信量。

重要 caveat：

- 一些 baseline 交互模型不同。RIBLT 是 rateless，CPISync 和 Negentropy 是 interactive，Minisketch 是 fixed sketch。summary 中需要分组展示，并明确通信量统计口径。

## 优先级 1B：独立 Dataset Generator

目标：把数据生成逻辑拆成可复用模块，让所有实验使用完全一致的 workload 定义。

任务：

- 创建独立 dataset generator 模块。
- 在以下脚本中复用：
  - `test_compare_basic.py`；
  - 阈值搜索实验；
  - spatial-coupling 实验；
  - 未来画图或复现实验脚本。
- 让数据生成参数可配置。

候选文件：

```text
tests/dataset_generator.py
```

建议参数：

```text
d
ca
cb
seed
trial
set_size_scale
max_set_size
value_modulus
value_bits
overlap_policy
difference_policy
shuffle_policy
timestamp_policy
duplicate_policy
```

建议 API：

```python
def choose_set_sizes(d: int, scale: int, max_set_size: int) -> tuple[int, int]:
    ...

def make_dataset(config: DatasetConfig, trial: int) -> Dataset:
    ...

def write_dataset(path: Path, dataset: Dataset) -> None:
    ...

def load_dataset(path: Path) -> Dataset:
    ...

def dataset_id(config: DatasetConfig, trial: int) -> str:
    ...
```

预期收益：

- 所有算法都在同一组输入集合上比较。
- 数据来源更容易审计。
- 后续可以改变 workload 结构，而不必复制粘贴生成逻辑。

## 优先级 5：补全 External Baseline 的真实接入

目标：把已经 scaffold 的 baseline adapter 尽量补成真实可测的 baseline。

当前状态：

```text
xyz_v1      已有真实 wrapper
xyz_v2      已有真实 wrapper
iblt        已有真实 wrapper
iblt_cpp    已有真实 wrapper
cpisync     已接入骨架；当前 Windows 环境下 unavailable
minisketch  真实 wrapper；当前环境可构建并运行
riblt       真实 wrapper 路径已存在；当前环境缺 Go，所以 unavailable
negentropy  真实代码路径已存在；当前环境缺 OpenSSL headers/libs，所以 unavailable
```

任务：

- 将 `minisketch` 保留在真实 baseline 集合中，并用它做 failed-decode 聚合 smoke test。
- 在安装 Go 的机器上，让 `riblt` 通过本项目侧 Go wrapper/module 运行，不修改 `external/riblt`。
- 在安装 OpenSSL headers/libs 的机器上，让 `negentropy` 调用 C++ 实现。
- 保持 `cpisync` 为 optional，因为它依赖 POSIX-style 进程/通信支持和外部库。
- 对不支持的平台继续保留 `status = "unavailable"` fallback。

为什么这是优先级 5，而不是优先级 1：

- Baseline 对最终对比很重要，但核心 XYZ/IBLT 阈值实验可以先推进，不必等所有 external baseline 完全可用。
- 统一 JSON 和 dataset generator 会让后续 baseline 接入更干净。

## 优先级 6：Update 前对 Hash 位置去重

想法：对同一个元素 `x`，在 update sketch 前手动去重：

```text
h_1(x), ..., h_k(x)
```

动机：

- 理论上，当同一个元素的 `k` 个位置发生碰撞的概率很低时，这可能不会显著改变模型。
- 在证明或解释中，对每个元素的 update 位置去重，可能让更新规则更干净：每个元素更新一组互不相同的 cell。

任务：

- 增加一个可选实现参数：

```text
--dedup-hashes true|false
```

- 比较去重前后的成功率和通信量。
- 测量在小 `M` 或大 `k` 时，去重是否改变行为。
- 在结果确认安全前，默认行为保持不变。

建议实验：

```text
d in {1000, 3000, 10000}
k in {2, 3, 4}
modes in {uniform, spatial}
dedup_hashes in {false, true}
```

预期结果：

- 如果曲线几乎不可区分，则只在有助于简化解释时使用去重。
- 如果阈值附近存在差异，则明确记录差异，并保留两个 mode。

## 优先级 7：Circular Trick 中的参数 `a`

目标：研究 circularized placement 中参数 `a` 在什么时候最优。

背景：

Circular trick 使用一种可环绕的 placement rule，让 coupled range 可以从最后一个 cell wrap 到第一个 cell。论文中等价地描述了：

```text
g0: U -> [0, 2 + a)
g_i: U -> [0, 1)
a in [0, 1)
```

并使用类似下面的 circularized 映射：

```text
h_i(x) = 1 + (g0(x) + g_i(x)) mod M
```

具体缩放方式取决于实现里的 `M`、`z` 和 coupled-window 定义。

任务：

- 将 `a` 暴露成显式 benchmark 参数。
- 扫描 `[0, 1)` 中的多个 `a` 值。
- 比较成功率和所需 `M`。
- 优先关注 circular coupling 预期有效的情况，尤其是 `k = 2`。
- 对于 `k >= 3`，除非数据表明有意义，否则 circular 结果应标记为 diagnostic。

建议网格：

```text
a in {0.0, 0.1, 0.2, ..., 0.9}
d in {1000, 3000, 10000}
l = 6
k in {2, 3}
target_success_rate in {0.95, 0.99}
```

预期输出：

```text
tests/results/circular_a/raw.jsonl
tests/results/circular_a/thresholds.csv
tests/results/circular_a/summary.md
```

解释问题：

- 哪个 `a` 使所需 `M` 最小？
- 最优 `a` 是否依赖 `d`？
- 最优 `a` 是否依赖 `k`？
- 实践中 `a = 0` 或接近边界的值是否已经足够？

## 建议执行顺序

1. 定义统一 JSON schema。
2. 拆出 `tests/dataset_generator.py`。
3. 给现有 threshold-search 脚本加入置信区间。
4. 对 XYZ-uniform 和 XYZ-SC 跑 sharp-threshold 实验。
5. 加入 IBLT-uniform 和 IBLT-SC 对比。
6. 按论文需要补全 external baseline 的真实接入。
7. 测试每个元素 update 前的 hash-location 去重。
8. 如果时间允许，或证明叙事需要，再研究 circular 参数 `a`。

