# Dataset Generator 改进计划

本文档规划把共享数据集生成逻辑拆到：

```text
tests/dataset_generator.py
```

这里先不实现代码。目标是让所有 benchmark 脚本使用同一套 workload 定义、seed 策略、数据集格式和元数据。

## 当前状态

目前最完整的 shared-dataset 逻辑写在 `tests/test_compare_basic.py` 里：

```text
choose_set_sizes()
make_dataset()
write_dataset()
prepare_datasets()
```

其它脚本，比如 `tests/test_dlk.py`、`tests/test_find_best_m.py`、`tests/test_spatial.py`，也重复了一部分 workload 策略，尤其是：

```text
choose_set_sizes()
seed 布局
ca/cb 选择
dataset_mode 元数据
```

这对早期实验是够用的，但后续对比会变脆弱。即使 benchmark row 已经使用统一 JSON schema，如果底层数据不是同一套规则生成的，结果仍然不容易严谨比较。

## 目标

1. 把数据集生成逻辑放进一个可复用模块。
2. 当实验目标是比较算法时，保证所有算法读取完全相同的 Alice/Bob 输入集合。
3. 保留现有 dataset 文件格式，让当前 benchmark wrappers 继续可用。
4. 让 workload 参数显式、可序列化。
5. 记录足够的元数据，保证每个 trial 可复现。
6. 同时支持 file-backed dataset 和 internal-generator 实验。
7. 不修改 external algorithm 子项目。

## 非目标

第一版不应该试图建模所有真实世界分布。它应该先保守地复现当前行为。

第一版暂不处理：

```text
heavy-tailed values
timestamp distributions
duplicate/multiset workloads
streaming updates
binary dataset format
large on-disk dataset cache eviction
```

这些可以等 generator 稳定后再补。

## Dataset 格式

保留当前文本格式：

```text
# compare-dataset-v1 ca=10000 cb=10000 d=1000 seed=114514 trial=0 trial_seed=114514
A 10000
...
B 10000
...
```

header 应该继续保持容易解析。值仍然一行一个整数，这样现有 C++/Go wrappers 都能读取。

generator 也应该支持把同一格式读回来：

```python
load_dataset(path: Path) -> Dataset
```

loader 对 verifier 测试、后续画图脚本和调试脚本都有用。

## 核心类型

使用小型 dataclass，让生成契约更明确：

```python
@dataclass(frozen=True)
class DatasetConfig:
    d: int
    ca: int
    cb: int
    seed: int
    value_modulus: int = 2_147_483_647
    min_value: int = 1
    overlap_policy: str = "replace_common_positions"
    shuffle_policy: str = "shuffle_both"
    duplicate_policy: str = "unique"

@dataclass(frozen=True)
class Dataset:
    alice: list[int]
    bob: list[int]
    metadata: dict[str, Any]
```

默认 `value_modulus` 要保持和 XYZ 的 field 兼容。如果后续 baseline 支持不同值域，可以把它作为显式参数暴露出来。

## Public API

第一版建议暴露：

```python
def choose_set_sizes(d: int, max_set_size: int, scale: int, minimum: int = 1000) -> tuple[int, int]:
    ...

def trial_seed(base_seed: int, trial: int) -> int:
    ...

def dataset_id(config: DatasetConfig, trial: int) -> str:
    ...

def make_dataset(config: DatasetConfig, trial: int = 0) -> Dataset:
    ...

def write_dataset(path: Path, dataset: Dataset) -> None:
    ...

def load_dataset(path: Path) -> Dataset:
    ...

def prepare_datasets(config: DatasetConfig, trials: int, output_dir: Path) -> list[Path]:
    ...
```

`prepare_datasets()` 应该成为 `test_compare_basic.py` 的主要入口。它生成：

```text
<output_dir>/<dataset_id>/trial0.sets
<output_dir>/<dataset_id>/trial1.sets
...
```

## 生成语义

第一版应该匹配当前 `make_dataset()` 行为：

1. 校验 `d >= abs(ca - cb)`。
2. 校验 `d` 和 `abs(ca - cb)` 奇偶性相同。
3. 计算：

```text
replacements = (d - abs(ca - cb)) / 2
```

4. 生成唯一 base values。
5. 用共享前缀构造 Alice 和 Bob。
6. 在 Bob 中替换 `replacements` 个位置为新的唯一值。
7. 分别 shuffle 两个集合。

这样保证：

```text
|A| = ca
|B| = cb
|A symmetric_difference B| = d
```

## CLI 接口

该模块也应该能作为小工具直接运行：

```powershell
python tests\dataset_generator.py --d 1000 --ca 10000 --cb 10000 --trials 5 --seed 114514 --output-dir tests\tmp\datasets
```

建议 CLI 参数：

```text
--d
--ca
--cb
--trials
--seed
--output-dir
--max-set-size
--set-size-scale
--value-modulus
--min-value
--dry-run
--manifest
```

如果省略 `--ca` 或 `--cb`，CLI 可以使用 `choose_set_sizes()`。

开启 `--manifest` 时，写出：

```text
manifest.json
```

其中记录每个生成的数据集路径和元数据。

## JSON Schema 集成

generator 生成的 metadata 应该能直接映射到 `benchmark.v1` row：

```text
dataset_id
dataset_path
dataset_dir
dataset_mode = "shared_file"
d
ca
cb
seed
trial
trial_seed
value_modulus
overlap_policy
shuffle_policy
duplicate_policy
```

`test_compare_basic.py` 应继续使用 shared dataset files，并设置：

```text
dataset_mode = "shared_file"
```

仍依赖 C++ 内部生成的脚本应设置：

```text
dataset_mode = "internal_generator"
```

后续如果 threshold-search 脚本的 benchmark wrapper 支持 `--dataset`，再把它们迁移到 shared files。

## 迁移计划

### Step 1：新增 `tests/dataset_generator.py`

把 `test_compare_basic.py` 中当前实现移动到共享模块，第一版保持行为完全一致。

通过模块 CLI 加 smoke test：

```powershell
python tests\dataset_generator.py --d 100 --ca 1000 --cb 1000 --trials 2 --seed 114514 --output-dir tests\tmp\dataset_generator_smoke
```

检查：

```text
生成两个文件
两个文件都能 load
set size 匹配 ca/cb
symmetric difference 等于 d
相同 seed 可以生成完全相同文件
不同 trial 生成不同文件
```

### Step 2：迁移 `test_compare_basic.py`

用 import 替换本地函数：

```python
from dataset_generator import DatasetConfig, choose_set_sizes, prepare_datasets
```

保持输出路径和 dataset 文件格式不变。

迁移后的预期行为：

```text
命令行不变
benchmark wrappers 不变
结果 JSON schema 不变
shared-file comparison 语义不变
```

### Step 3：共享 size 和 seed 策略

在这些脚本中使用 `choose_set_sizes()` 和共享 seed helper：

```text
tests/test_dlk.py
tests/test_find_best_m.py
tests/test_spatial.py
tests/test_z.py
```

这个阶段它们可以仍然使用 C++ internal generation，但 `ca`、`cb` 和 seed 策略应与公共 generator 保持一致。

### Step 4：可选的 shared-file threshold runs

如果相关 benchmark wrapper 在对应 mode 下支持 `--dataset`，可以增加选项：

```text
--dataset-mode internal_generator|shared_file
```

在清楚 runtime 和存储成本前，默认可以继续是 `internal_generator`。

## 测试计划

分三层测试。

### Generator Smoke Test

生成小数据集并读回：

```powershell
python tests\dataset_generator.py --d 10 --ca 100 --cb 100 --trials 3 --seed 1 --output-dir tests\tmp\dataset_generator_smoke
```

检查：

```text
sizes
difference count
metadata
determinism
```

### Compare Smoke Test

运行：

```powershell
python tests\test_compare_basic.py --algorithms xyz_v2,iblt --d-values 100 --trials 2 --capacity-factors 1.3 --output-dir tests\results\dataset_generator_compare_smoke --keep-datasets
```

然后校验 JSON：

```powershell
python tests\json_verifier.py tests\results\dataset_generator_compare_smoke\raw.jsonl --strict
```

### Regression Check

删除旧代码前，对固定 config 比较新旧生成文件。第一版应该对以下配置生成完全一致文件：

```text
d=100
ca=1000
cb=1000
seed=114514
trial in {0, 1, 2}
```

如果无法保持 byte-for-byte 一致，需要说明原因。第一版优先追求 byte-for-byte 兼容。

## 风险

1. 一些 wrapper 假设 value 落在特定 field 中。默认 `value_modulus` 要保持和 XYZ 兼容。
2. 大规模 shared-file 实验会产生很多文件。`test_compare_basic.py` 应继续保留 cleanup 行为。
3. 修改 seed 语义会影响旧结果。第一版应保留当前 seed layout。
4. 生成出的 symmetric difference 必须严格等于 `d`；生成后要加 validation。

## 完成标准

这个任务完成时应满足：

```text
tests/dataset_generator.py 存在
test_compare_basic.py 从 generator import，而不是自己维护数据生成逻辑
生成的数据集文件与所有 benchmark wrapper 兼容
strict JSON verification 仍然通过
上面的 smoke commands 通过
文档说明如何手动生成和检查 dataset
```

