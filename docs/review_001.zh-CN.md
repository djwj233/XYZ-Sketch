# Review 001：实验系统状态与下一步修改

本文档记录对最近这份项目审核意见的判断。总体看，这份审核基本准确：当前仓库已经有不少能 smoke-test 的实验组件，但距离规划文档里的完整论文级实验系统还有差距。

## 总体判断

审核的主结论是正确的。

## 状态更新

原始 review 中的一些问题现在已经修复或部分实现：

```text
已修复    tests/test_compare_basic.py 中的 failed_decode 聚合问题
已修复    SetCircularA 不再 clamp；CLI 仍负责参数校验
已完成    XYZ-v2 第一阶段 per-item hash-location deduplication
部分完成  XYZ threshold 风格脚本的 shared-dataset migration
部分完成  external baselines：minisketch 和 iblt_cpp 可真实运行；riblt/negentropy/cpisync 仍依赖环境
未完成    plotting/table generation
未完成    application-side experiments
未完成    轻量 verifier 之外的完整 schema 语义
未完成    可选的 IBLT-SC hash deduplication
```

shared dataset 方面，`tests/test_spatial.py` 和 `tests/test_circular_a.py` 现在已经支持 `--shared-datasets`。剩余 paper-facing 候选包括 `tests/test_xyz_sharp_threshold.py`、`tests/test_z.py`、`tests/test_find_best_m.py`，以及如果 `tests/test_dlk.py` 的结果进入最终表格，也需要考虑迁移。

当前项目已经不是空架子，已经有：

- 统一 benchmark row 的 normalization 和 verification helper；
- 独立 dataset generator；
- XYZ-v2 的 `d/l/k`、best-`M`、spatial、`z`、sharp-threshold、circular-`a` 脚本；
- IBLT uniform-vs-spatial 实验；
- shared-dataset compare 基础设施；
- 真实可跑的 `minisketch` 和 `IBLT_Cplusplus` baseline；
- 已 scaffold 或受环境依赖影响的 `riblt`、`negentropy`、`cpisync` baseline。

但它还没有达到规划文档中完整 paper-ready 的状态。主要缺口是：

- compare 聚合逻辑曾经会错误处理正常 decode failure；现在已经修复；
- external baseline 可用性不均衡；
- 一些 XYZ threshold 风格脚本仍使用内部生成器，而不是 shared paired datasets；
- per-item hash-location deduplication 已在 XYZ-v2 中实现；IBLT-SC dedup 仍是可选/未完成项；
- application-side 实验和 plotting/figure pipeline 尚未实现；
- 一些规划文档描述的输出布局和 workload 参数比当前代码更丰富，文档和实现已有分叉。

## 判断正确的部分

### 统一 JSON

正确。`tests/json_schema.py` 和 `tests/json_verifier.py` 已存在，并且已有 smoke 输出可以通过 strict verification。

重要细节：这目前是实用的 normalization/verifier 层，还不是完整 canonical schema 系统。它会检查通用字段和指标一致性，但还没有完全强制所有算法特有字段和语义要求。

### Dataset Generator

正确。`tests/dataset_generator.py` 已存在，并用于 shared-dataset compare。

重要细节：它目前主要实现一种 workload policy。docs 中提到的 `difference_policy`、`timestamp_policy` 和更多 workload family 还没有真正参数化。

### 核心 XYZ 和 IBLT 实验

正确。这些脚本已经存在，并有可用 smoke 路径：

```text
tests/test_dlk.py
tests/test_find_best_m.py
tests/test_spatial.py
tests/test_z.py
tests/test_xyz_sharp_threshold.py
tests/test_iblt_spatial.py
tests/test_circular_a.py
```

需要注意的是，一些 XYZ threshold 风格实验仍然使用 `xyz_v2_bench` 内部 deterministic generator。这对于 smoke test 和单算法扫描可以接受，但弱于严格的 paired shared-dataset comparison。`test_spatial.py` 和 `test_circular_a.py` 现在已经支持 shared paired datasets。

### Circular `a`

正确。`circular_a` 已经在这些位置暴露：

```text
XYZ-v2/hash.cpp
XYZ-v2/hash.h
tests/benchmarks/xyz_v2_bench.cpp
tests/test_circular_a.py
```

当前实现通过：

```text
floor(circular_a * RangeLength)
```

并默认：

```text
circular_a = 1/3
```

来保持旧的硬编码 `RangeLength / 3` 行为。

审核也正确指出：目前只有 smoke-level 结果，还没有跑代表性 `d` 上的主网格。

### External Baseline

正确。

当前状态：

```text
minisketch       当前环境真实可跑
iblt_cpp         真实可跑
riblt            真实 wrapper 已存在，但当前环境缺 Go，所以 unavailable
negentropy       真实代码路径已存在，但当前环境缺 OpenSSL headers/libs，所以 unavailable
cpisync          optional；当前 Windows 环境下基本 unavailable
```

这需要同步反映到文档中。旧文档里仍说 `minisketch` 只是 scaffold 的内容已经过时。

### Hash Deduplication

原始 review 当时的判断是正确的，但现在已经部分修复。XYZ-v2 现在支持：

```text
--dedup-hashes true|false
```

并且在 `Update()`、`Extract()` 和 `PureCellVerify()` 中使用同一个 per-item location helper。若后续需要 IBLT-SC 的 ablation，那里仍是 open。

### 绘图和应用侧实验

正确。当前输出主要是 JSON/CSV/Markdown summary。还没有 paper-ready plotting/table-generation pipeline。

Git repository snapshot reconciliation 之类的应用侧实验也没有实现。

## 已修复问题：Compare 聚合

审核正确指出了 `tests/test_compare_basic.py` 中一个真实聚合 bug。这个问题现在已经修复。

当前行为：

```python
ok_rows = [row for row in trial_rows if row.get("status") == "ok"]
```

之后只用 `ok_rows` 聚合。

问题：

- 低容量下 decode failure 是一个合法 trial outcome。
- `minisketch`、`riblt` 或 `negentropy` 这类 wrapper 可能输出 `status = "failed_decode"`，但这仍然是有效 benchmark row。
- 排除这些 row 会把 success rate 偏高。
- 如果所有 trial 都 decode 失败，aggregate 甚至可能变成 `benchmark_error`，语义上是错的。

期望行为：

- trial-level `failed_decode` 应计为一个完成的 trial，且 `successes = 0`。
- 只要 benchmark 进程正常运行，aggregate row 通常仍应是 `status = "ok"`。
- `status = "benchmark_error"`、`parse_error`、`unavailable` 应保留给基础设施、构建或运行时错误。

推荐修法：

```text
valid_trial_statuses = {"ok", "failed_decode"}
valid_rows = rows whose status is in valid_trial_statuses
successes = sum(row.successes for valid_rows)
trials = len(valid_rows)
success_rate = successes / trials
aggregate status = "ok"
```

如果所有 row 都是 `unavailable`，保持 `record_type = "unavailable"`。

如果只有 process errors，保持 `record_type = "error"`。

如果 valid trials 和 process errors 混在一起，可以聚合 valid trials，同时记录：

```text
attempted_trials
completed_trials
error_trials
```

作为可选诊断字段。

当前状态：已实现。`tests/test_compare_basic.py` 现在把 `{"ok", "failed_decode"}` 视为有效完成 trial 状态，基于有效 rows 聚合 successes，并记录 attempted/completed/error trial counts。

## 小问题：Circular `a` 的 Reject 和 Clamp 语义

审核指出 CLI 和 library-level 行为不一致，这是对的：

- `xyz_v2_bench` 会 reject 非法 `--circular-a`。
- `SpatialCoupling::SetCircularA()` 会把值 clamp 到 `[0, 1)`。

当前状态：已修复。`SpatialCoupling::SetCircularA()` 现在直接赋值，`xyz_v2_bench` 继续负责拒绝非法用户输入。

之前推荐的修改：

- CLI validation 保持不变。
- library setter 最好语义明确。考虑到当前 C++ 代码整体不太用 exception，一个合理选择是：

```cpp
void SetCircularA(double value) {
    CircularA = value;
}
```

然后要求调用者负责 validation。

另一个选择是保留 clamping，但在文档中明确说明。就实验语义而言，所有用户输入边界都 reject 非法值会更干净。

除非以后出现新的 public entry point 接受未校验的 `circular_a`，否则这不再是 open issue。

## 小问题：中文文档编码

审核说 `docs/test_circular_a.zh-CN.md` 看起来乱码。当前 workspace 中按 UTF-8 读取是正常的。

可能原因：

- 文件被非 UTF-8 默认编码查看；
- 或审核看到的是较旧版本。

推荐动作：

- 所有 docs 保持 UTF-8，不依赖终端默认 code page；
- 如果乱码再次出现，把文件重写为 UTF-8 without BOM。

目前除非能复现，否则不需要代码修改。

## 推荐优先级

### Priority 1：保留 Compare 聚合回归覆盖

聚合修复已经实现。后续应保留一个 smoke 命令或 regression test，确保正常的 `failed_decode` trial row 会参与聚合。

验收测试：

- 故意跑一个低容量 baseline，例如低于差异规模的 `minisketch` 或 `iblt`。
- 输出应是 aggregate row，并满足：

```text
status = "ok"
success_rate < 1
trials = requested trial count
```

而不是 `benchmark_error`。

### Priority 2：更新 Baseline 状态文档

更新 external-baseline docs 和 todo-list 状态：

```text
minisketch: 当前环境真实可跑
iblt_cpp: 真实可跑
riblt: wrapper 已实现，需要 Go toolchain
negentropy: 真实代码路径已实现，需要 OpenSSL
cpisync: optional / platform-sensitive
```

这样可以避免后续混淆“只是 scaffold”和“已实现但当前环境 unavailable”。

### Priority 3：决定 XYZ Threshold 脚本的 Shared-Dataset 策略

对于 paper-facing 结果，需要决定是否把 shared dataset 接到这些脚本：

```text
tests/test_find_best_m.py
tests/test_spatial.py
tests/test_z.py
tests/test_xyz_sharp_threshold.py
tests/test_circular_a.py
```

推荐策略：

- quick smoke 和 exploratory runs 保留 internal generator；
- final paired comparisons 增加 `--shared-datasets` 或类似选项。

### Priority 4：运行缺失的主网格

运行或安排非 smoke grid：

```text
circular_a main threshold grid
XYZ sharp-threshold representative grid
IBLT uniform/SC representative grid
external baseline compare where dependencies are available
```

### Priority 5：增加 Plot/Table Pipeline

增加绘图脚本，用于：

```text
success_rate vs M
success_rate vs circular_a
best_C_over_d by algorithm
threshold confidence intervals
```

输出建议放在：

```text
tests/results/<experiment>/figures/
```

### Priority 6：扩展 Hash Deduplication 实验

XYZ-v2 现在已经支持：

```text
--dedup-hashes true|false
```

剩余工作是运行 planned comparison，并且如果需要，把同样思路扩展到 IBLT-SC。

### Priority 7：应用侧实验

等核心 paper figures 稳定后，再做 Git snapshot 或类似 application workload。

## 建议的立即 Patch 列表

1. 保留或增加一个能故意产生 `failed_decode` 的 smoke 命令，确认聚合正确。
2. 更新 external baseline 状态文档。
3. 增加或保留说明：circular-a 和 dedup 当前主要是 smoke-level 结果，主网格仍需运行。
4. 继续把剩余 paper-facing XYZ 脚本迁移到 shared-dataset 模式。

## 最终评价

这份审核很有用，而且大部分判断准确。下一步最好不要继续开新实验，而是先加固 compare pipeline：

```text
keep aggregation regression coverage -> update docs -> run main grids -> add plotting
```

这个顺序能先保证结果正确，再投入更大的实验计算。
