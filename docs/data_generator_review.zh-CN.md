# Shared Dataset Generator 审核与迁移规划

本文档梳理哪些实验脚本应该从 benchmark 内部 deterministic data generation 迁移到 `tests/dataset_generator.py` 生成的 shared paired datasets。

本文档最初是迁移规划。现在第一批迁移已经完成：`tests/test_spatial.py` 和 `tests/test_circular_a.py` 已经支持 shared dataset；剩余脚本继续按本文档的优先级推进。

## 问题

一些 XYZ threshold 类实验仍然调用 `tests/benchmarks/xyz_v2_bench.cpp`，但不传 `--dataset`。

在这种模式下，`xyz_v2_bench` 会根据以下参数内部生成数据：

```text
d, ca, cb, seed, trial index
```

这对 smoke test 或单算法探索性扫描已经够用，因为它是确定性的。但如果要做严格的论文级比较，不同参数或不同算法最好读取完全相同的 Alice/Bob sets。

更严格的策略应该是：

```text
one workload/trial -> one shared dataset file -> all compared configurations read that exact file
```

这样可以减少噪声，让 paired comparison 更干净。

## 当前 Shared-Dataset 基础设施

可复用 dataset 模块已经存在：

```text
tests/dataset_generator.py
```

它提供：

```python
DatasetConfig
choose_set_sizes(...)
make_dataset(...)
write_dataset(...)
load_dataset(...)
prepare_datasets(...)
```

benchmark 文件格式是：

```text
# compare-dataset-v1 ca=<...> cb=<...> d=<...> seed=<...> trial=<...>
A <count>
...
B <count>
...
```

大多数 benchmark adapter 已经支持 `--dataset`，包括：

```text
tests/benchmarks/xyz_v2_bench.cpp
tests/benchmarks/iblt_bench.cpp
tests/benchmarks/iblt_sc_bench.cpp
tests/benchmarks/xyz_v1_bench.cpp
tests/benchmarks/iblt_cpp_bench.cpp
tests/benchmarks/minisketch_bench.cpp
tests/benchmarks/cpisync_bench.cpp
tests/benchmarks/negentropy_bench.cpp
tests/benchmarks/riblt_bench.go
```

所以这主要是 Python 实验编排层的问题，不是 C++ benchmark 能力不足。

## 当前脚本状态

### 已经使用 Shared Datasets

```text
tests/test_compare_basic.py
tests/test_iblt_spatial.py
tests/test_spatial.py with --shared-datasets
tests/test_circular_a.py with --shared-datasets
```

这两个脚本是迁移时最好的参考。

`test_compare_basic.py`：

- 每个 workload/trial 生成一份 dataset；
- 把同一份 dataset 传给每个选中的算法；
- 在 Python 侧聚合 per-dataset trial rows。

`test_iblt_spatial.py`：

- 使用 `DatasetConfig` 和 `prepare_datasets`；
- 给 `iblt_sc_bench` 传 `--dataset`；
- 在 paired datasets 上比较 IBLT variants。

`test_spatial.py`：

- 默认仍保留旧的 internal generator 快速路径；
- 新增 `--shared-datasets`、`--dataset-dir` 和 `--keep-datasets`；
- 对同一个 `(d, ca, cb, seed)`，在 spatial modes、候选 `M` probes 和 final validation 之间复用同一批 dataset；
- 在 raw probes 和 summary 中记录 `dataset_mode = "shared_file"` 和 `dataset_dir`。

`test_circular_a.py`：

- 默认仍保留旧的 internal generator 快速路径；
- 新增 `--shared-datasets`、`--dataset-dir` 和 `--keep-datasets`；
- 对同一个 `(d, ca, cb, seed)`，在不同 `a` 值、fixed-`M` rows、threshold probes 和 final validation 之间复用同一批 dataset；
- 启用 `--shared-datasets` 时，不再让 paired comparison 的 seed 随 `a` 改变；
- 在 raw rows 和 summary 中记录 `dataset_mode = "shared_file"` 和 `dataset_dir`。

### 仍主要使用 Internal Generator

```text
tests/test_find_best_m.py
tests/test_z.py
tests/test_xyz_sharp_threshold.py
tests/test_dlk.py
```

这些脚本虽然 import 了 `choose_set_sizes`，但没有为 benchmark probe 生成 dataset 文件。它们依赖 benchmark 内部生成器，并输出 `dataset_mode = "internal_generator"`。

`test_spatial.py` 和 `test_circular_a.py` 在启用 `--shared-datasets` 后已经不属于这一类；但为了快速 smoke run，它们仍然保留旧默认行为。

## 哪些测试最应该先迁移？

### 优先级 1：`tests/test_spatial.py`

状态：已在 `--shared-datasets` 后实现。

原因：

- 它比较不同 mode：`random`、`circular`、`naive`、`spatial`。
- 这正是 paired datasets 最重要的场景。
- 如果不用 shared datasets，某个 mode 看起来更好或更差，可能只是因为它看到的是不同随机 workload。

迁移目标：

```text
For each d/l/k/seed/trial, generate one shared dataset.
Run every mode and every candidate M against that same trial list.
```

推荐模式：

```text
default: keep internal generator for compatibility
new option: --shared-datasets
```

这样不会破坏现有 quick runs。

### 优先级 2：`tests/test_circular_a.py`

状态：已在 `--shared-datasets` 后实现。

原因：

- 它比较很多 `a` 值。
- 相邻 `a` 的差异可能很小。
- paired datasets 可以降低方差，让 “best a” 的结论更可信。

迁移目标：

```text
For each d/l/k and each trial, reuse the same dataset across all a-values.
```

这应同时应用于：

```text
--mode fixed-m
--mode threshold
```

对于 threshold mode，同一个 `(d,l,k,seed)` 下，每个 `a` 的每个候选 `M` 都应使用同一组 probe datasets。

### 优先级 3：`tests/test_xyz_sharp_threshold.py`

原因：

- Sharp-threshold 曲线比较相邻 `M`。
- paired datasets 能让 transition curve 更干净。
- 曲线的噪声不应来自每个 `M` 看到不同 workload sample。

迁移目标：

```text
For each d/l/k/mode and each trial, reuse the same datasets across all M points.
```

这样能让阈值附近的 success-rate jump 更容易解释。

### 优先级 4：`tests/test_z.py`

原因：

- 这个脚本在固定 `d/l/k/M` 下比较不同 `z`。
- `z` 的影响可能比较微妙，因此 paired datasets 有帮助。

迁移目标：

```text
For each d/l/k/M and trial, reuse one dataset across all z-values.
```

这个迁移应该比较轻量，因为 `xyz_v2_bench` 已经支持 `--dataset`。

### 优先级 5：`tests/test_find_best_m.py`

原因：

- 它为单个配置搜索 threshold。
- 它不像 `test_spatial.py` 或 `test_circular_a.py` 那样是强 cross-configuration comparison。
- 内部 deterministic generation 对快速 threshold 估计可以接受。

不过，如果 best-`M` 结果要用于论文阈值，就应该支持 shared datasets。

迁移目标：

```text
Add --shared-datasets for final runs.
Keep internal generation as default for speed.
```

### 优先级 6：`tests/test_dlk.py`

原因：

- 它主要是大范围参数扫描，不是严格 paired comparison。
- 内部生成器对探索趋势可以接受。

除非 `test_dlk.py` 结果直接进入论文表格，否则迁移是 optional。

如果迁移，只在 `d/ca/cb` 相同的情况下跨不同 `l/k` 共享 dataset。

## 推荐 Shared-Dataset 策略

不要移除内部生成器，而是增加一个开关：

```text
--shared-datasets
```

禁用时：

```text
dataset_mode = "internal_generator"
```

启用时：

```text
dataset_mode = "shared_file"
dataset_dir = <path>
dataset_id = <id if available>
```

推荐额外参数：

```text
--dataset-dir
--keep-datasets
```

默认 dataset 目录：

```text
tests/tmp/<experiment>/
```

输出 row 应记录：

```text
dataset_mode
dataset_dir
dataset_id
```

如果第一版给所有脚本都加 `dataset_id` 工作量太大，先记录 `dataset_dir` 加已有 seed/trial metadata 也可以接受。

## Dataset 复用规则

关键设计问题是哪些配置应该共享同一份 dataset。

### 跨算法或 Mode Variants

始终共享。

例子：

```text
random vs circular vs naive
IBLT-uniform vs IBLT-SC
XYZ-v2 vs minisketch vs IBLT
```

### 跨内部参数值

通常共享。

例子：

```text
different a values
different z values
different M values on a sharp-threshold curve
different capacity factors for the same baseline
```

这样才能形成 paired comparisons。

### 跨不同 d 值

不共享。

不同 `d` 就是不同 workload。

### 跨不同 ca/cb 值

不要共享，除非 dataset generator 明确定义 nested workload relation。当前 generator 没有这个语义。

## 实现模式

每个迁移脚本应遵循这个结构。

### 1. 增加 CLI Flags

```python
parser.add_argument("--shared-datasets", action="store_true")
parser.add_argument("--dataset-dir", type=Path, default=None)
parser.add_argument("--keep-datasets", action="store_true")
```

### 2. 创建 Dataset Cache

用 workload identity 作为 cache key：

```python
dataset_cache_key = (d, ca, cb, seed, trials)
```

然后：

```python
DatasetConfig(d=d, ca=ca, cb=cb, seed=seed)
prepare_datasets(config, trials, dataset_dir)
```

### 3. 每个 Dataset 跑一次 Trial

不要一次 benchmark call 传：

```text
--trials N
```

而是对每个 dataset 调一次 benchmark：

```text
--trials 1 --dataset <path>
```

然后在 Python 侧聚合 trial rows。

这样 subprocess 次数会更多，但更清晰、更公平。

### 4. 保留旧 Fast Path

如果没有设置 `--shared-datasets`，保持旧行为：

```text
one benchmark call with --trials N and no --dataset
```

这适合 quick smoke tests。

## 聚合规则

使用 `test_compare_basic.py` 中已经修复过的规则：

```text
valid trial statuses = {"ok", "failed_decode"}
successes = sum(successes)
trials = number of valid rows
status = "ok" for a valid aggregate even if success_rate = 0
```

对于基础设施错误：

```text
unavailable -> record_type = "unavailable"
benchmark_error / parse_error -> record_type = "error"
```

这样可以避免把低容量 decode failure 错误当成 benchmark failure。

## 各脚本迁移说明

### `tests/test_spatial.py`

按以下 key 增加 dataset cache：

```text
d, ca, cb, seed
```

这些 datasets 应跨以下维度共享：

```text
mode
candidate M
final validation
```

推荐第一版 patch：

- 增加 `--shared-datasets`；
- 保持现有 threshold search；
- 修改 `run_probe()`，让它根据模式选择旧的一次性运行或 per-dataset 运行。

### `tests/test_circular_a.py`

datasets 应跨以下维度共享：

```text
a-values
candidate M values
fixed-M rows
threshold final validation
```

同一个 `(d,l,k)` 应使用同一个 workload seed，而不是让 seed 随 `a` 变化。当前脚本把 `a_index` 加进 seed；这对内部生成器可以接受，但不适合 paired comparison。

启用 `--shared-datasets` 时：

```text
seed should not vary with a
```

### `tests/test_xyz_sharp_threshold.py`

datasets 应跨以下维度共享：

```text
M grid points
mode values if comparing random vs spatial
```

这很重要，因为 sharp-threshold 图应该展示 `M` 的影响，而不是 trial sample 噪声。

### `tests/test_z.py`

datasets 应跨以下维度共享：

```text
z values for the same d/l/k/M
```

这个迁移应该比较容易。

### `tests/test_find_best_m.py`

把 shared datasets 作为 optional final-run mode 加进去。

对于 binary search：

- probe trials 可以使用 shared dataset files；
- 如果结果面向论文，final validation 应该使用 shared dataset files。

### `tests/test_dlk.py`

可选迁移。

如果迁移，只在以下参数相同的情况下跨 `l/k` 共享 datasets：

```text
d, ca, cb, seed
```

目前它的优先级低于 threshold/comparison 脚本。

## 输出兼容性

暂时不要重命名现有输出文件。docs 中提到过这些名字：

```text
raw_trials.jsonl
raw_aggregated.jsonl
thresholds.csv
```

但现有脚本使用：

```text
raw.jsonl
probes.jsonl
summary.jsonl
summary.csv
summary.md
```

shared-dataset 迁移不应该同时改输出文件名。保持文件名稳定，只更新 `dataset_mode` 相关字段。

输出布局重命名可以作为单独 cleanup task。

## 验收测试

对每个迁移脚本：

1. 跑 dry run。
2. 跑一个很小的 internal-generator smoke，并验证输出。
3. 跑一个很小的 shared-dataset smoke，并验证输出。
4. 检查 row 包含：

   ```text
   dataset_mode = "shared_file"
   dataset_dir
   ```

5. 运行 strict JSON verification：

   ```bash
   python tests/json_verifier.py <raw-or-summary-jsonl> --strict
   ```

6. 对 paired comparison 脚本，手动检查不同 variants 使用了同一个 `dataset_dir`。

## 推荐实现顺序

```text
1. tests/test_spatial.py
2. tests/test_circular_a.py
3. tests/test_xyz_sharp_threshold.py
4. tests/test_z.py
5. tests/test_find_best_m.py
6. tests/test_dlk.py, only if needed
```

这个顺序优先修复 paired comparison 最重要的实验。

## 第一版迁移的非目标

暂时不要新增 workload policies：

```text
difference_policy
timestamp_policy
duplicate_policy variants
ordered workloads
Git snapshot workloads
```

这些是独立的 dataset-generator 改进。眼下的问题不是 workload 不够丰富，而是可比较配置应该读取同一组生成 workload。

## 最终建议

这个问题重要，应该在跑大型 paper-facing grids 前解决。

第一份具体 patch 建议迁移 `tests/test_spatial.py`，因为它直接比较 hash modes。第二份建议迁移 `tests/test_circular_a.py`，因为相邻 `a` 值需要 paired datasets 才能让小差异可信。
