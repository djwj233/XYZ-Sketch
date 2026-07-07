# External Baseline 真实接入规划

本文档规划如何把已经 scaffold 的 external baseline adapter 补成论文对比中可用的真实测量 baseline。这里只做规划，不包含具体实现。

## 目标

目标是让 external set reconciliation baseline 进入和 XYZ-v2、XYZ-v1、本地 IBLT、IBLT-SC 相同的 benchmark 架构：

```text
shared dataset -> thin adapter -> benchmark.v1 JSON row -> common summary
```

最终对比要回答：

```text
在同一组生成的 Alice/Bob 集合、同一个目标差异规模 d 下，每种实用 reconciliation 方法需要多少通信量和时间才能成功？
```

## 仓库规则

外部项目只作为源码输入。不要修改或新增这些目录下的文件：

```text
external/*
XYZ-v1/
XYZ-v2/
IBLT/
```

所有 glue code、benchmark wrapper、临时构建文件、生成的 helper 文件都应放在：

```text
tests/benchmarks/
tests/
tests/tmp/
build/
tests/results/
```

如果某个 external 项目需要 CMake build 目录、Go module wrapper、日志或生成配置，都要放在 external 子项目之外。

## 当前状态

compare 脚本已经识别这些算法：

```text
xyz_v1
xyz_v2
iblt
iblt_cpp
minisketch
cpisync
riblt
negentropy
```

当前接入状态：

```text
xyz_v1      真实本地 wrapper
xyz_v2      真实本地 wrapper
iblt        真实本地 wrapper
iblt_cpp    真实 external/IBLT_Cplusplus wrapper
minisketch  真实 wrapper；当前环境可构建并运行
cpisync     已 scaffold/optional；依赖平台和外部依赖
riblt       真实 wrapper 路径已存在；当前环境缺 Go，所以 unavailable
negentropy  真实代码路径已存在；当前环境缺 OpenSSL headers/libs，所以 unavailable
```

下一步工作应尽量启用这些依赖环境的 row，同时继续保留 unsupported platform 下的 `status = "unavailable"`。

## 优先级顺序

推荐实现顺序：

```text
1. minisketch
2. riblt
3. negentropy
4. cpisync
5. 必要时 polish iblt_cpp reporting
```

原因：

- `minisketch` 是最干净的 fixed-sketch baseline，并且和 set reconciliation 直接相关。
- `riblt` 具有实际意义，因为它是 rateless 的，适合 `d` 不精确已知的场景。
- `negentropy` 有价值，但有 ordered/range-based 假设，结果需要明确 caveat。
- `cpisync` 是经典 baseline，但当前依赖和进程模型更容易受平台影响，尤其是 Windows。
- `iblt_cpp` 已经是真实 adapter，主要用于和本地 IBLT 互相校验。

## 共享 Benchmark 契约

每个 external adapter 都应接受同一种 dataset 格式：

```text
--dataset PATH
--d D
--format jsonl
```

adapter 每次读取一个 dataset，运行一个 trial，并向 stdout 输出一个 `benchmark.v1` JSON 对象。

Python compare 脚本负责跨 trial 聚合。compare 运行中，external adapter 不应自己生成随机数据。

必需行为：

- 从 shared dataset 文件读取 Alice 和 Bob 集合。
- 根据加载的数据计算真实 Alice-only 和 Bob-only difference。
- 在这组完全相同的数据上运行 external algorithm。
- 如果算法暴露了足够信息，校验 decoded output 是否等于真实 difference。
- 用明确的统计口径报告通信量，单位为 bits 和 bytes。
- 真实成功 benchmark row 使用 `status = "ok"`。
- 当前机器无法构建或使用该 adapter 时，输出 `status = "unavailable"` 和 `unavailable_reason`。
- row 必须能通过 `tests/json_verifier.py --strict`。

## 通用输出字段

所有 adapter 应填充 common schema 字段：

```text
schema_version = "benchmark.v1"
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
dataset_mode = "shared_file"
success
successes
success_rate
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

如果某个算法没有自然的 encode/decode 切分，就把总 protocol 时间放进 `reconcile_s`，然后按现有 schema 策略把 encode/decode 置零或省略。

## 通信量统计口径

这些 baseline 的交互模型不同，summary 不能隐藏统计了什么。

推荐口径：

```text
XYZ / IBLT / minisketch:
  统计传输的 fixed sketch size。

RIBLT:
  统计直到 decode 成功实际发送的 coded symbols；失败时统计配置的发送上限。

CPISync:
  统计所有消息的实测 protocol bytes。

Negentropy:
  统计所有 round 中 client-to-server 和 server-to-client 的 message bytes 之和。
```

row 中应包含算法特有字段，便于解释图表：

```text
communication_model = "fixed_sketch" | "rateless" | "interactive"
rounds
messages
symbols_sent
capacity
capacity_factor
mbar
mbar_factor
```

## `external/minisketch`

### 用途

Minisketch 应作为主要的近最优 fixed-sketch baseline。

### 构建规划

在 external 项目外构建：

```text
build/minisketch/
```

然后构建：

```text
tests/benchmarks/minisketch_bench.cpp -> build/minisketch_bench(.exe)
```

wrapper 应链接 out-of-tree 构建出的 `libminisketch`，并启用真实 adapter 路径，例如使用 `ENABLE_REAL_MINISKETCH` 编译定义。

### Benchmark 规划

使用 C API：

```text
minisketch_create(...)
minisketch_add_uint64(...)
minisketch_merge(...)
minisketch_decode(...)
minisketch_serialized_size(...)
```

推荐参数：

```text
field_bits = 30
capacity = ceil(capacity_factor * d)
```

当前 dataset generator 会保证 value 小于 `998244353`，所以 30-bit field 足够。

成功条件：

- decoded symmetric difference 完全等于 dataset 的真实 symmetric difference。
- PinSketch 本身不天然区分方向，因此 direction-specific 校验要谨慎处理。

通信量：

```text
bits = minisketch_serialized_size(sketch) * 8
```

### Smoke Test

```bash
python tests/test_compare_basic.py \
  --algorithms minisketch \
  --d-values 1000 \
  --trials 5 \
  --capacity-factors 1.0,1.1,1.2 \
  --output-dir tests/results/compare_minisketch_smoke
```

预期：

- `capacity_factor >= 1.0` 通常应成功。
- 通信量应随 `capacity` 线性增长。
- JSON row 应通过 strict verifier。

## `external/riblt`

### 用途

RIBLT 应代表 rateless reconciliation 家族。当 difference size 不精确已知时，它很有价值。

### 构建规划

不要在 `external/riblt` 下新增 module 文件。

使用本项目侧路径：

```text
tests/benchmarks/riblt_bench.go
tests/benchmarks/go/riblt_adapter/
build/riblt/
```

如果需要 Go module，在 `external/riblt` 外创建，并用本地 `replace` 指向只读的 external checkout。

### Benchmark 规划

参考 `external/riblt/example_test.go` 中的 item type 模式。

实现一个 `uint64` item type，包含：

```text
XOR
Hash
```

流程：

1. 把 Alice values 加入 RIBLT encoder。
2. 把 Bob values 加入 RIBLT decoder。
3. 持续生成 coded symbols，直到 decode 成功或达到 symbol cap。
4. 校验 decoded Alice-only 和 Bob-only values 是否等于 dataset。

推荐参数：

```text
max_symbols = ceil(symbol_factor * d)
```

通信量：

```text
bits = symbols_sent * symbol_bits
```

同时报告 `field_bits = 30`，用于区分实际实现成本和 lower-bound normalized cost。

### Smoke Test

```bash
python tests/test_compare_basic.py \
  --algorithms riblt \
  --d-values 1000 \
  --trials 5 \
  --symbol-factors 1.2,1.5,2.0 \
  --output-dir tests/results/compare_riblt_smoke
```

预期：

- `symbol_factor` 增大时 success 应提升。
- row 应报告 `symbols_sent`。
- low-capacity 下 decode 失败是正常实验结果，不应导致 benchmark crash。

## `external/negentropy`

### 用途

Negentropy 是 ordered/range-based synchronization baseline。它有价值，但不能在没有 caveat 的情况下直接当成 unordered fixed-sketch 竞争者。

### 构建规划

使用 header-only C++ 实现：

```text
external/negentropy/cpp
```

构建：

```text
tests/benchmarks/negentropy_bench.cpp -> build/negentropy_bench(.exe)
```

不要往 `external/negentropy` 写入生成文件。

### Benchmark 规划

第一版使用 `negentropy::storage::Vector`。

把每个整数 dataset value 转成 Negentropy 需要的 ID 格式。使用确定性映射即可，例如：

```text
uint64 value -> 32-byte zero-padded or hashed ID
```

暴露 timestamp modes：

```text
timestamp_mode = value
timestamp_mode = constant
timestamp_mode = random
```

面向论文的初始结果建议使用 `timestamp_mode = random`，或者把 `timestamp_mode = value` 明确标为 ordered workload。

运行一个 in-process client/server message loop：

```text
client initiate
server reconcile
client reconcile
...
```

协议完成或达到最大 round 数后停止。

通信量：

```text
bits = 8 * (client_bytes + server_bytes)
```

输出必须包含：

```text
communication_model = "interactive"
ordered_workload = true
timestamp_mode
rounds
client_bytes
server_bytes
```

### Smoke Test

```bash
python tests/test_compare_basic.py \
  --algorithms negentropy \
  --d-values 1000 \
  --trials 5 \
  --frame-size-limits 0 \
  --timestamp-modes random,value \
  --output-dir tests/results/compare_negentropy_smoke
```

预期：

- 结果可能随 timestamp mode 大幅变化。
- summary 应单独分组或明确标注 Negentropy。
- 如果 adapter 无法准确校验方向，要显式报告这个限制。

## `external/cpisync`

### 用途

CPISync 是经典 characteristic-polynomial set reconciliation baseline。它有历史和科学价值，但可能更慢、更难构建。

### 构建规划

保持 CPISync 为 optional。

优先路径：

```text
cmake -S external/cpisync -B build/cpisync
cmake --build build/cpisync
```

备选路径：

```text
compile tests/benchmarks/cpisync_bench.cpp with selected read-only sources from external/cpisync/src
```

在 Windows 上，如果 upstream 的进程/IPC 或依赖假设不适配当前环境，真实 adapter 可以继续保持 unavailable。

### Benchmark 规划

使用 upstream tests 已经验证过的高层路径：

```text
GenSync
CPISync
DataObject
forkHandle(...)
```

推荐参数：

```text
mbar = ceil(mbar_factor * d)
bits_param = 30
epsilon = 64
redundant = 0
hashes = false
```

通信量：

```text
bits = 8 * measured_protocol_bytes
```

如果 upstream 暴露 round-trip bytes 和 excess bytes，就分别记录到算法特有字段。

### Smoke Test

```bash
python tests/test_compare_basic.py \
  --algorithms cpisync \
  --d-values 100 \
  --trials 3 \
  --mbar-factors 1.0,1.2,1.5 \
  --output-dir tests/results/compare_cpisync_smoke
```

预期：

- unsupported 机器上输出合法 unavailable rows。
- supported 机器上报告实测 protocol bytes 和总 reconciliation time。
- 从小 `d` 开始，不要把 CPISync 作为第一个大规模 baseline。

## `external/IBLT_Cplusplus`

这个 adapter 已经是真实实现。剩余工作主要是 reporting polish：

- 确认 `bits`、`cells`、`cell_bits`、`hash_count` 反映 external 实现的真实布局。
- 在 comparison 中保持 `implementation = "external/IBLT_Cplusplus"`。
- 用它作为 local IBLT-uniform 和 IBLT-SC 的诊断对照。

## `tests/test_compare_basic.py` 需要的更新

脚本应保留现有 shared-dataset 流程，并为每个 external baseline 增加真实 build/run 路径。

推荐修改：

1. 默认 algorithms 继续保持轻量，例如 `xyz_v2,iblt`。
2. 尽量增加 external dependency auto-detection。
3. 如有需要，加入显式开关：

   ```text
   --enable-real-minisketch
   --enable-real-riblt
   --enable-real-negentropy
   --enable-real-cpisync
   ```

   默认可以 auto-detect，这些开关用于强制尝试真实构建。

4. build 失败时保留 unavailable fallback rows。
5. 把 build error 写入 `errors.log`。
6. 一个 external adapter 失败不能中断其它算法。
7. 用 `tests/json_verifier.py` 校验所有最终 rows。

## 测试策略

对每个 external baseline：

1. 先跑单算法 dry run。
2. 只构建该 adapter。
3. 用 `d = 100` 或 `d = 1000` 跑小规模 smoke test。
4. 严格校验 JSON。
5. 与 `xyz_v2` 和 `iblt` 在同一批 dataset 上跑 paired comparison。
6. 检查 success rate 是否随 capacity-like 参数单调改善。
7. 确认后再加入更大的 comparison run。

推荐 verifier 命令：

```bash
python tests/json_verifier.py \
  --input tests/results/<experiment>/raw.jsonl \
  --strict
```

## 论文结果分组

最终论文 summary 不应把不可直接比较的通信模型混在一个无说明表格里。

推荐分组：

```text
Fixed sketches:
  XYZ-v2, XYZ-v1, IBLT, IBLT_Cplusplus, minisketch

Spatial-coupled variants:
  XYZ-SC, IBLT-SC

Rateless:
  RIBLT

Interactive protocols:
  CPISync, Negentropy
```

如果必须放在同一个表格里，需要包含 `communication_model` 和 caveat columns。

## 完成标准

这项任务完成的标准：

- `minisketch`、`riblt`、`negentropy` 至少在一个 supported development environment 上产生真实 rows，或者用清晰依赖原因输出 documented unavailable rows。
- `cpisync` 要么在 POSIX-like 环境中真实可用，要么明确记录当前 Windows setup 不支持。
- 没有任何 wrapper 往 `external/*` 写文件。
- 所有 row 都使用 shared datasets。
- 所有 row 都通过 strict JSON verifier。
- `summary.md` 清晰区分 fixed-sketch、rateless 和 interactive baseline。
