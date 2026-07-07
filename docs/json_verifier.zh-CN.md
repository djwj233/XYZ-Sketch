# JSON Schema 与 Verifier 规划

本文档规划所有 benchmark 和实验输出使用的统一 JSON 格式，以及对应的校验器。本文档不实现代码。

## 目标

项目当前有多个会产生 JSONL 的脚本和 wrapper：

```text
tests/test_compare_basic.py
tests/test_dlk.py
tests/test_spatial.py
tests/test_z.py
tests/test_find_best_m.py
tests/benchmarks/*_bench.cpp
tests/benchmarks/riblt_bench.go
```

它们都输出了有用的 JSON，但字段还没有由一个统一 schema 管理。有些行是 aggregated summary，有些是 probe row，有些是 benchmark row，还有一些是 unavailable-baseline row。

目标是引入：

```text
schema_version = "benchmark.v1"
一种规范 row 格式
一个 verifier 脚本
一条针对现有脚本的迁移路径
```

第一版应实用优先，不要过度设计。它应规范当前的 flat JSON 风格，同时为未来更结构化的记录留空间。

## 设计原则

1. 每一行 JSONL 都必须能独立解释。
2. 每一行都必须说明自己是什么类型的记录。
3. 每一行都必须包含足够的 workload 和参数信息，不能只能依赖 summary 才能解释。
4. 所有失败或 unavailable baseline 都应表示成 JSON 行，而不是数据缺失。
5. 允许算法特有字段，但通用字段必须有稳定名称和类型。
6. verifier 对未知 optional 字段可以 warning，但对缺失 required 字段应失败。
7. schema 应同时支持 per-trial row 和 aggregated row。

## Row 类型

用 `record_type` 区分每一行的语义：

```text
trial
aggregate
probe
threshold
unavailable
error
```

建议用法：

- `trial`：某算法在某个 dataset/trial 上的一次结果。
- `aggregate`：多次 trial 聚合成的一行。
- `probe`：阈值搜索中某个候选 `M` 或 capacity 的探测结果。
- `threshold`：阈值搜索的最终结果。
- `unavailable`：adapter 或依赖不可用。
- `error`：benchmark 失败、解析失败或命令失败。

当前脚本的大多数输出已经是 aggregated row。这些应使用：

```text
record_type = "aggregate"
```

`test_find_best_m.py` 和 `test_spatial.py` 中的 probe 应使用：

```text
record_type = "probe"
```

最终阈值 summary 应使用：

```text
record_type = "threshold"
```

## Canonical Flat Schema v1

第一版 schema 保持 flat，因为当前 C++ wrapper 已经输出 flat JSON。这样迁移成本最低。

所有 row 都必需的字段：

```text
schema_version: string
record_type: string
experiment: string
algorithm: string
variant: string
implementation: string
status: string
```

benchmark-like row 必需的 workload 字段：

```text
d: integer
ca: integer
cb: integer
seed: integer
dataset_mode: string
```

必需的 trial/statistical 字段：

```text
trials: integer
successes: integer
success_rate: number
```

必需的通信字段：

```text
bits: number
bits_per_difference: number
bit_C_over_d: number
```

必需的计时字段：

```text
encode_avg_s: number
decode_avg_s: number
encode_median_s: number
decode_median_s: number
```

常见 optional 字段：

```text
trial
trial_seed
dataset_id
dataset_path
dataset_dir
target_success_rate
ci_method
ci_confidence
ci_low
ci_high
threshold_policy
unavailable_reason
error
command
```

允许算法特有字段，例如：

```text
l
k
M
z
mode
field_C_over_d
RangeLength
capacity_factor
cells
hash_count
cell_bits
mbar
mbar_factor
field_bits
capacity
symbol_factor
symbols_sent
max_symbols
frame_size_limit
timestamp_mode
rounds
```

## Status 取值

允许的 `status`：

```text
ok
unavailable
benchmark_error
parse_error
failed_decode
unresolved
invalid
```

规则：

- `ok`：benchmark 正常运行并产生有效 row。
- `unavailable`：依赖、平台或 adapter 不可用。
- `benchmark_error`：benchmark 进程失败。
- `parse_error`：benchmark 输出不是合法 JSON。
- `failed_decode`：benchmark 正常运行，但某个 trial decode 失败。
- `unresolved`：阈值搜索无法确认目标成功率。
- `invalid`：verifier 发现 schema 违规。

对于 aggregate row，低成功率不应自动把 `status` 从 `ok` 改成 `failed_decode`。即使算法经常失败，这一行结果本身仍然可以是有效的。

## Experiment 名称

使用稳定的实验名：

```text
compare_basic
dlk_sweep
find_best_m
spatial_threshold
z_sensitivity
sharp_threshold
circular_a
dedup_hashes
```

每个脚本都应该显式设置 `experiment`。

## 各脚本迁移计划

### `tests/test_compare_basic.py`

当前角色：在 shared dataset 上做跨算法对比。

修改：

1. 增加 `schema_version = "benchmark.v1"`。
2. 增加 `experiment = "compare_basic"`。
3. 对 aggregated row 增加 `record_type = "aggregate"`。
4. 独立 dataset generator 完成后增加 `dataset_id`。
5. 继续允许算法特有字段。
6. unavailable baseline 也必须输出同样的 required common fields；无意义指标用 0。

推荐职责划分：

- C++/Go wrapper 可以继续输出较小的 flat row。
- `test_compare_basic.py` 负责把 wrapper 输出 normalize 成完整 schema row。

### `tests/test_dlk.py`

当前角色：对 `d`、`l`、`k` 做固定网格扫描。

修改：

1. 增加 `schema_version = "benchmark.v1"`。
2. 增加 `experiment = "dlk_sweep"`。
3. 增加 `record_type = "aggregate"`。
4. 增加 `variant`，例如 `variant = "spatial"` 或 `variant = "mode=<mode>"`。
5. 增加 `implementation = "XYZ-v2"`。
6. 在它改用 shared dataset generator 前，先设置 `dataset_mode = "internal_generator"`。

### `tests/test_find_best_m.py`

当前角色：二分搜索合适的 `M`。

修改：

1. probe row 使用 `record_type = "probe"`。
2. final row 使用 `record_type = "threshold"`。
3. 增加 `experiment = "find_best_m"`。
4. 实现置信区间后增加：

```text
ci_method
ci_confidence
ci_low
ci_high
threshold_policy
```

5. 保留 `target_success_rate`、`required_probe_successes` 和 `required_final_successes`。

### `tests/test_spatial.py`

当前角色：比较不同 placement mode 的阈值。

修改：

1. probe row 使用 `record_type = "probe"`。
2. summary row 使用 `record_type = "threshold"`。
3. 增加 `experiment = "spatial_threshold"`。
4. 使用 `variant = mode`，其中 `mode` 是 `random`、`circular` 或 `naive`。
5. 为 final validation 增加置信区间字段。

### `tests/test_z.py`

当前角色：扫描 `z` 的敏感性。

修改：

1. 增加 `schema_version = "benchmark.v1"`。
2. 增加 `experiment = "z_sensitivity"`。
3. 增加 `record_type = "aggregate"`。
4. 保留 `RangeLength` 作为算法特有字段。
5. 增加 `variant = "z=<value>"` 或保留 `variant = mode` 并显式记录 `z`。推荐保留 `variant = mode`，让 `z` 作为显式参数字段。

### C++ 和 Go Benchmark Wrapper

当前 wrapper 输出 flat JSON。有两种路线：

1. 最小 wrapper 输出：
   - wrapper 只输出自己自然知道的字段；
   - Python 脚本补全 schema 字段并 normalize。

2. 完整 wrapper 输出：
   - 每个 wrapper 都输出 `schema_version`、`record_type`、`experiment` 等字段。

推荐路线：

```text
现在使用最小 wrapper 输出。
由 Python orchestrator 脚本 normalize 成 benchmark.v1。
```

原因：这样可以避免在 C++、Go 和 Python 中重复维护 schema 逻辑。以后如果需要，再加共享 C++ JSON helper。

## Verifier 规划

新增校验脚本：

```text
tests/json_verifier.py
```

职责：

1. 读取一个或多个 JSONL 文件。
2. 按 `benchmark.v1` 校验每一行。
3. 根据 `record_type` 检查 required fields。
4. 检查字段类型。
5. 检查数值合理性：

```text
0 <= successes <= trials
0 <= success_rate <= 1
bits >= 0
bits_per_difference >= 0
bit_C_over_d >= 0
d > 0
ca > 0
cb > 0
```

6. 检查一致性：

```text
success_rate == successes / trials  (within tolerance)
bits_per_difference == bits / d      (within tolerance)
bit_C_over_d == bits / (32*d)        (within tolerance)
```

7. 对未知字段打印 warning。
8. 如果有任何 invalid row，非零退出。

CLI 设计：

```bash
python tests/json_verifier.py tests/results/compare_basic/raw.jsonl
python tests/json_verifier.py tests/results/**/*.jsonl --recursive
python tests/json_verifier.py tests/results/compare_basic/raw.jsonl --strict
```

选项：

```text
--schema benchmark.v1
--recursive
--strict
--allow-legacy
--max-errors N
```

## Legacy 兼容

很多现有结果文件没有 `schema_version`。verifier 应支持过渡模式：

```text
--allow-legacy
```

Legacy mode：

- 接受没有 `schema_version` 的 row；
- 在安全时推断缺失字段；
- 对缺少 schema-only 字段的情况给 warning，而不是 hard failure。

Strict mode：

- 要求 `schema_version = "benchmark.v1"`；
- 按 row type 要求所有 common fields；
- 新实验输出应使用 strict mode。

## 迁移顺序

推荐顺序：

1. 实现带 legacy 和 strict 模式的 `tests/json_verifier.py`。
2. 在 `tests/test_compare_basic.py` 中增加 normalization helpers。
3. 将 `test_compare_basic.py` 输出迁移到 `benchmark.v1`。
4. 迁移 `test_dlk.py` 和 `test_z.py`。
5. 迁移 `test_find_best_m.py` 和 `test_spatial.py`，包括 threshold row types。
6. 增加置信区间字段。
7. 在 summary 中说明 verifier 状态。

## 示例 Row

### Aggregate Row

```json
{
  "schema_version": "benchmark.v1",
  "record_type": "aggregate",
  "experiment": "compare_basic",
  "algorithm": "xyz_v2",
  "variant": "spatial",
  "implementation": "XYZ-v2",
  "status": "ok",
  "d": 1000,
  "ca": 10000,
  "cb": 10000,
  "seed": 114514,
  "dataset_mode": "shared_file",
  "dataset_id": "d1000_ca10000_cb10000_seed114514",
  "trials": 30,
  "successes": 29,
  "success_rate": 0.9666666667,
  "bits": 42532,
  "bits_per_difference": 42.532,
  "bit_C_over_d": 1.329125,
  "encode_avg_s": 0.00078,
  "decode_avg_s": 0.20761,
  "encode_median_s": 0.00075,
  "decode_median_s": 0.20111,
  "l": 6,
  "k": 2,
  "M": 217,
  "z": 2,
  "mode": "spatial"
}
```

### Unavailable Row

```json
{
  "schema_version": "benchmark.v1",
  "record_type": "unavailable",
  "experiment": "compare_basic",
  "algorithm": "cpisync",
  "variant": "mbar_factor=1.2",
  "implementation": "external/cpisync",
  "status": "unavailable",
  "unavailable_reason": "cpisync_bench was built without ENABLE_REAL_CPISYNC",
  "d": 1000,
  "ca": 10000,
  "cb": 10000,
  "seed": 114514,
  "dataset_mode": "shared_file",
  "trials": 30,
  "successes": 0,
  "success_rate": 0.0,
  "bits": 0,
  "bits_per_difference": 0.0,
  "bit_C_over_d": 0.0,
  "encode_avg_s": 0.0,
  "decode_avg_s": 0.0,
  "encode_median_s": 0.0,
  "decode_median_s": 0.0
}
```

### Threshold Row

```json
{
  "schema_version": "benchmark.v1",
  "record_type": "threshold",
  "experiment": "find_best_m",
  "algorithm": "xyz_v2",
  "variant": "spatial",
  "implementation": "XYZ-v2",
  "status": "ok",
  "d": 1000,
  "ca": 10000,
  "cb": 10000,
  "seed": 114514,
  "dataset_mode": "internal_generator",
  "target_success_rate": 0.99,
  "threshold_policy": "lower_ci_meets_target",
  "ci_method": "wilson",
  "ci_confidence": 0.95,
  "trials": 300,
  "successes": 298,
  "success_rate": 0.9933333333,
  "ci_low": 0.9761,
  "ci_high": 0.9982,
  "M": 225,
  "bits": 44100,
  "bits_per_difference": 44.1,
  "bit_C_over_d": 1.378125
}
```

## 待决定事项

1. 是否移除 `C_over_d`，只保留 `bit_C_over_d`？
   - 建议：暂时保留 `C_over_d` 作为 legacy alias，但标准字段使用 `bit_C_over_d`。

2. schema 是否应该改成 nested？
   - 建议：v1 保持 flat。以后如果需要，再考虑 nested v2。

3. wrapper 是否应该直接输出完整 schema？
   - 建议：第一阶段不要。先由 Python orchestrator normalize。

4. per-trial row 是否应强制要求？
   - 建议：新 threshold 实验应强制有 per-trial/probe 信息，但迁移完成前允许 aggregate-only legacy 输出。

