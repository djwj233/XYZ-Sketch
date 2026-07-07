# `tests/test_compare_basic.py` 设计规划

本文档规划一个基础的跨算法对比实验。它说明 `tests/test_compare_basic.py` 应该如何比较本仓库已有算法，以及新加入的外部 baseline 子项目。

本文档不实现代码。

## CPISync 接入规划

下一步先从 `external/cpisync` 开始接入外部 baseline。CPISync 是 characteristic-polynomial 路线的经典 set reconciliation 实现，适合作为 XYZ-v2 和 IBLT 之外的对照。

重要约束：

```text
不要修改或新增 external/cpisync 下的任何文件。
```

所有适配代码和构建产物都应放在本项目侧，例如：

```text
tests/benchmarks/cpisync_bench.cpp
tests/test_compare_basic.py
build/cpisync/
build/cpisync_bench.exe
```

### 接口选择

优先使用 CPISync 项目已有单元测试中的高层接口。`external/cpisync/tests/unit/CPITest.cpp` 已经展示了可行路径：

1. 用 `GenSync::Builder()` 构造 Alice 和 Bob。
2. 设置 `setProtocol(GenSync::SyncProtocol::CPISync)`。
3. 设置 `setBits(bits)`、`setErr(64)`、`setMbar(m_bar)`。
4. 用 `DataObject` 插入 Alice/Bob 的元素。
5. 调用 `forkHandle(Alice, Bob, false)`。
6. 从 `forkHandleReport` 读取 `success`、`bytesRTot + bytesXTot` 和 `totalTime`。

这条路线的好处是可以直接拿到成功率、协议通信字节数和总耗时，不需要改动 CPISync 内部实现。

如果高层接口在构建或通信方式上遇到问题，再考虑低层 `CPI` 类。但低层接口未必直接暴露完整协议统计，因此它只作为备选方案。

### Benchmark Wrapper

新增的 wrapper 应放在：

```text
tests/benchmarks/cpisync_bench.cpp
```

它应读取当前 compare 实验已经使用的共享 dataset 文件：

```bash
build/cpisync_bench.exe \
  --dataset tests/tmp/compare_basic/d1000_seed114514_trial0.sets \
  --d 1000 \
  --mbar-factor 1.2 \
  --bits 30 \
  --epsilon 64 \
  --redundant 0 \
  --hashes false \
  --format jsonl
```

`cpisync_bench` 通常每次只处理一个 dataset 文件，然后由 `tests/test_compare_basic.py` 在 Python 侧聚合多次 trial。这和现在 XYZ-v2、IBLT 的共享 dataset 模式保持一致。

### 参数策略

CPISync 需要一个差异数量上界 `m_bar`。实验中用：

```text
m_bar = ceil(mbar_factor * d)
```

因此 `mbar_factor` 对 CPISync 的意义类似于 IBLT 的 `capacity_factor`。

初始参数建议：

```text
bits = 30
epsilon = 64
redundant = 0
hashes = false
```

当前共享 dataset 的元素满足 `1 <= x < 998244353`，因此 `bits = 30` 足够覆盖输入范围。先关闭内部 hashing，可以让通信量和正确性更容易解释。之后如果需要支持更大元素范围，可以从 dataset 的最大值推导 `ceil(log2(max_value + 1))`。

### Python Adapter

在 `tests/test_compare_basic.py` 中新增 `CPISyncAdapter`：

1. `build()` 尝试在 `build/cpisync/` 中 out-of-tree 构建 `external/cpisync`，或构建本项目侧的 `tests/benchmarks/cpisync_bench.cpp` wrapper。
2. 如果缺少 NTL、GMP、CppUnit、CMake 或上游 CMake 需要的 allocator/profiler 库，不让整个 compare 实验失败，而是为 CPISync 结果写入 `status = "unavailable"`。
3. `make_jobs()` 扫描 `--mbar-factors`。
4. `run()` 对每个共享 dataset 调用一次 `build/cpisync_bench.exe`，再聚合 trial 结果。

### 输出字段

CPISync 的归一化结果建议包含：

```text
algorithm = "cpisync"
implementation = "external/cpisync"
variant = "mbar_factor=<value>"
d
ca
cb
trials
successes
success_rate
reconcile_avg_s
bits
bytes
bits_per_difference
bit_C_over_d
mbar
mbar_factor
bits_param
epsilon
redundant
hashes
dataset_mode
dataset_dir
status
```

CPISync 是交互式两方协议，因此通信量应解释为协议实际传输字节数，而不是固定 sketch 大小。如果无法自然拆分 encode/decode 时间，就记录 `reconcile_avg_s`；为了兼容 summary，也可以暂时令 `encode_avg_s = 0`，`decode_avg_s = reconcile_avg_s`。

### Smoke Test

实现后先跑小规模测试：

```bash
python tests/test_compare_basic.py \
  --algorithms cpisync \
  --d-values 100 \
  --trials 3 \
  --mbar-factors 1.0,1.2,1.5 \
  --keep-datasets \
  --output-dir tests/results/compare_cpisync_smoke
```

预期结果：

1. 如果依赖缺失，`raw.jsonl` 中应出现 `status = "unavailable"`，脚本正常结束。
2. 如果依赖齐全，应输出成功率、协议通信字节数和 reconciliation 时间。
3. 先从小 `d` 开始，因为 characteristic-polynomial 方法在参数变大时可能明显慢于 sketch-based 方法。

## CPISync 使用方式

CPISync adapter 实现后，可以先单独跑 smoke test：

```bash
python tests/test_compare_basic.py \
  --algorithms cpisync \
  --d-values 100 \
  --trials 3 \
  --mbar-factors 1.0,1.2,1.5 \
  --keep-datasets \
  --output-dir tests/results/compare_cpisync_smoke
```

预期行为：

1. CPISync 和 XYZ-v2、IBLT 使用同一种 shared dataset 文件格式。
2. 在 Windows 或缺少 CPISync 依赖的机器上，结果可能是 `status = "unavailable"`，这属于可接受结果，不应导致整个 compare 脚本失败。
3. 在 POSIX-like 环境并且 NTL/GMP 等依赖齐全时，应输出协议通信字节数和 reconciliation 时间。

三种算法一起跑时使用：

```bash
python tests/test_compare_basic.py \
  --algorithms xyz_v2,iblt,cpisync \
  --d-values 100,300,1000 \
  --trials 10 \
  --capacity-factors 1.5,2.0 \
  --mbar-factors 1.0,1.2,1.5 \
  --output-dir tests/results/compare_basic_cpisync
```

这个命令仍然是 paired comparison：每个 workload/trial 只生成一份 dataset，然后把同一份数据传给所有被选中的算法。

## 剩余 Baseline 接入总规划

下一步要补齐 `XYZ-v1`、`external/IBLT_Cplusplus`、`external/minisketch`、`external/riblt` 和 `external/negentropy`。原则和 CPISync 一样：

```text
不要修改或新增 XYZ-v1、XYZ-v2、IBLT 或 external/* 下的任何文件。
```

所有 wrapper、临时文件、构建产物都放在本项目侧：

```text
tests/benchmarks/<algorithm>_bench.cpp
tests/benchmarks/<algorithm>_bench.go
tests/test_compare_basic.py
build/<algorithm>_bench(.exe)
build/<external-project>/
tests/tmp/
```

所有算法都继续使用同一套 shared dataset：

1. `tests/test_compare_basic.py` 为每个 workload/trial 生成一份 dataset。
2. 每个算法通过 `--dataset PATH` 读取完全相同的 Alice/Bob 集合。
3. 每个 wrapper 对单个 dataset 输出一行 JSONL。
4. Python 侧把多次 trial 聚合为一行 summary。
5. 如果某个 external baseline 在当前平台无法构建或缺少依赖，输出 `status = "unavailable"`，不要中断整个 compare。

建议的算法名：

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

默认运行仍然应保持轻量，例如 `xyz_v2,iblt`；外部 baseline 由用户显式指定。

### `XYZ-v1`

接入 `XYZ-v1` 的目的是回答：XYZ-v2 相比原始 XYZ sketch 到底提升了多少。

实现规划：

1. 新增 `tests/benchmarks/xyz_v1_bench.cpp`。
2. 只读引用 `XYZ-v1/XYZ-v1.cpp`。
3. 支持 `--dataset PATH`、`--d`、`--trials`、`--seed`、`--ca`、`--cb`、`--format jsonl`。
4. 对每个 dataset 设置 XYZ-v1 使用的全局 `D`。
5. 从 dataset 计算 Alice-only 和 Bob-only 差异，用来校验 `Decode` 结果。
6. 通信量使用现有 `to_bitstring(Alice).size()`，保持和 XYZ-v1 原实现一致。

建议输出：

```text
algorithm = "xyz_v1"
implementation = "local"
variant = "basic"
d
ca
cb
success_rate
encode_avg_s
decode_avg_s
bits
bits_per_difference
bit_C_over_d
dataset_mode
status
```

注意：XYZ-v1 没有 XYZ-v2 的 spatial 参数体系，第一版应把它作为 “原始算法在容量 D 下的结果” 来比较，不要强行套用 XYZ-v2 的 best-M 策略。

### `external/IBLT_Cplusplus`

这个 baseline 主要用于和本地 IBLT 互相校验。

实现规划：

1. 新增 `tests/benchmarks/iblt_cpp_bench.cpp`。
2. 编译时只读引用 `external/IBLT_Cplusplus/iblt.cpp`、`murmurhash3.cpp`、`utilstrencodings.cpp`。
3. 使用公开接口 `IBLT(size_t expectedNumEntries, size_t valueSize)`。
4. Alice 和 Bob 分别构建 IBLT，然后相减并调用 `listEntries`。
5. 使用 dataset 计算出的 Alice-only/Bob-only 差异校验结果。
6. 扫描 `capacity_factor`，令 `expectedNumEntries = ceil(capacity_factor * d)`。
7. `valueSize` 先尝试 key-only；如果实现要求 value，则使用 4 字节 value 或把 key 自身作为 value。

建议输出：

```text
algorithm = "iblt_cpp"
implementation = "external/IBLT_Cplusplus"
variant = "capacity_factor=<value>"
capacity_factor
expected_entries
value_size
cells
cell_bits
hash_count
bits
```

如果它的 cell 数、hash 数或内存布局和本地 IBLT 不一致，应在结果中明确记录，不要强行使用本地 IBLT 的通信量公式。

### `external/minisketch`

Minisketch 是成熟的 PinSketch 实现，适合作为近最优固定 sketch baseline。

实现规划：

1. 在 `build/minisketch/` 中 out-of-tree 构建 `external/minisketch`。
2. 新增 `tests/benchmarks/minisketch_bench.cpp`。
3. 优先使用 C API。
4. 当前 dataset 元素小于 `998244353`，因此先用 `field_bits = 30`。
5. 令 `capacity = ceil(capacity_factor * d)`。
6. Alice/Bob 分别构建 sketch，merge 后 decode symmetric difference。
7. 校验 decode 得到的 symmetric difference 是否等于 dataset 的真实 symmetric difference。
8. 初始通信量先统计 Alice 序列化 sketch：`minisketch_serialized_size(sketch) * 8`。

建议命令：

```bash
build/minisketch_bench.exe \
  --dataset tests/tmp/compare_basic/d1000_seed114514_trial0.sets \
  --d 1000 \
  --capacity-factor 1.0 \
  --field-bits 30 \
  --format jsonl
```

建议输出：

```text
algorithm = "minisketch"
implementation = "external/minisketch"
variant = "capacity_factor=<value>"
field_bits
capacity
capacity_factor
bits
decode_count
```

预期：`capacity >= d` 时应稳定成功；`capacity < d` 时应失败或 decode 不完整。

### `external/riblt`

RIBLT 是 rateless 方法，适合测试未知 `d` 或逐步发送 coded symbols 的场景。

实现规划：

1. 新增 `tests/benchmarks/riblt_bench.go`。
2. 不在 `external/riblt` 中新增 Go 文件；如果需要 Go module glue，放在 `tests/benchmarks/go/` 或 `build/riblt/`。
3. 通过本项目侧 wrapper 引用 `external/riblt`。
4. 按 `external/riblt/example_test.go` 实现 `uint64` item 类型，提供 `XOR` 和 `Hash`。
5. Alice 使用 `riblt.Encoder`，Bob 使用 `riblt.Decoder`。
6. 逐个发送 coded symbol，直到 `Decoded()` 成功或达到上限。
7. 扫描 `symbol_factor`，令 `max_symbols = ceil(symbol_factor * d)`。
8. 通信量为 `symbols_sent * symbol_bits`。由于实现用 `uint64`，第一版可用 `symbol_bits = 64`，同时记录 `field_bits = 30` 作为输入元素有效位宽。

建议输出：

```text
algorithm = "riblt"
implementation = "external/riblt"
variant = "symbol_factor=<value>"
symbol_factor
symbols_sent
max_symbols
symbol_bits
field_bits
bits
```

注意：RIBLT 是 rateless，不应只按固定 sketch 大小解释。固定参数模式下记录最多发送多少 symbols；目标成功率模式下记录实际需要多少 symbols。

### `external/negentropy`

Negentropy 是 range-based set reconciliation，依赖记录的排序结构，不是普通无序集合 sketch。

实现规划：

1. 新增 `tests/benchmarks/negentropy_bench.cpp`。
2. 只读 include `external/negentropy/cpp` 下的 header-only C++ 实现。
3. 第一版使用 `negentropy::storage::Vector`。
4. 把 dataset value 转成 32 字节 ID，可以用确定性 zero-padding 或 hash。
5. 显式设置 timestamp 策略：
   - `timestamp_mode=value`：timestamp 等于整数值，有序结构最强。
   - `timestamp_mode=constant`：所有 timestamp 相同，只剩 ID 字典序。
   - `timestamp_mode=random`：由 seed 确定的伪随机 timestamp。
6. 在单进程内模拟 client/server 消息循环：`initiate()` 和 `reconcile()` 交替执行。
7. 累计所有 client-to-server 和 server-to-client 消息字节数。
8. 校验最终 have/need 是否等于 Alice-only/Bob-only 差异。
9. 扫描 `frame_size_limit`，包括 `0` 表示不限制 frame。

建议输出：

```text
algorithm = "negentropy"
implementation = "external/negentropy"
variant = "frame_size=<value>,timestamp=<mode>"
frame_size_limit
timestamp_mode
rounds
client_bytes
server_bytes
bits
ordered_workload = true
```

注意：Negentropy 的性能强依赖 timestamp/order 分布。summary 中应把它标记为 ordered-workload baseline，避免和无序集合 sketch 直接混在一起解释。

## 全部 Baseline 的建议测试顺序

不要一次性把所有实现混在一起调试，建议按下面顺序逐个加：

```text
1. xyz_v1
2. iblt_cpp
3. minisketch
4. riblt
5. negentropy
```

每加一个 baseline，先跑单算法 smoke test，再跑 paired comparison：

```bash
python tests/test_compare_basic.py \
  --algorithms <new_algorithm> \
  --d-values 100 \
  --trials 3 \
  --keep-datasets \
  --output-dir tests/results/compare_<new_algorithm>_smoke
```

然后再和已有算法一起跑：

```bash
python tests/test_compare_basic.py \
  --algorithms xyz_v2,iblt,<new_algorithm> \
  --d-values 100,300,1000 \
  --trials 10 \
  --output-dir tests/results/compare_<new_algorithm>_paired
```

最终全量对比可以使用：

```bash
python tests/test_compare_basic.py \
  --algorithms xyz_v1,xyz_v2,iblt,iblt_cpp,minisketch,cpisync,riblt,negentropy \
  --d-values 100,300,1000,3000,10000 \
  --trials 30 \
  --capacity-factors 1.2,1.3,1.4,1.5,2.0 \
  --mbar-factors 1.0,1.2,1.5 \
  --symbol-factors 1.2,1.35,1.5,1.8,2.0 \
  --frame-size-limits 0,50000 \
  --timestamp-modes value,constant \
  --output-dir tests/results/compare_all_basic
```

如果某些 external baseline 在当前平台不可用，结果中保留 `status = "unavailable"`，其它算法继续完成。

## 当前实现状态

`tests/test_compare_basic.py` 现在已经识别全部规划中的算法名：

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

当前 wrapper 状态：

```text
xyz_v1      已实现，真实本地 wrapper
xyz_v2      已实现，真实本地 wrapper
iblt        已实现，真实本地 wrapper
iblt_cpp    已实现，真实 external/IBLT_Cplusplus wrapper
cpisync     已接入骨架；Windows/非 POSIX 构建下返回 unavailable
minisketch  已接入骨架；在链接 libminisketch 前返回 unavailable
riblt       已接入骨架；缺少 Go 或 module wiring 时返回 unavailable
negentropy  已接入骨架；在链接 C++ 实现前返回 unavailable
```

所有 wrapper 仍然读取同一份 shared dataset。`status = "unavailable"` 表示当前机器或当前构建路径还没有启用对应 external 依赖，不代表 compare 脚本失败。

全算法 smoke test：

```bash
python tests/test_compare_basic.py \
  --algorithms xyz_v1,xyz_v2,iblt,iblt_cpp,minisketch,cpisync,riblt,negentropy \
  --d-values 100 \
  --trials 1 \
  --capacity-factors 1.3 \
  --mbar-factors 1.0 \
  --symbol-factors 1.5 \
  --frame-size-limits 0 \
  --timestamp-modes value \
  --output-dir tests/results/compare_all_smoke \
  --keep-datasets
```

## 近期修复目标：统一 Seed 和 Dataset

当前第一版 `test_compare_basic.py` 已经可以比较 `XYZ-v2` 和本地 `IBLT`，但还有两个需要先修复的问题：

1. 各算法现在只共享 `d`、`ca`、`cb`，但 benchmark 内部仍然各自生成数据，因此不是严格的 paired comparison。
2. IBLT 的 `capacity_factor` variant 在 summary 中没有保留下来，导致多个 IBLT 行都显示为 `local`。

下一步应先修复这些问题，再继续接入 `minisketch` 等外部 baseline。

### 共享 Dataset 策略

对于每个 workload，统一使用：

```text
workload_seed = base_seed + 1000000 * workload_index
trial_seed = workload_seed + trial_index
```

`tests/test_compare_basic.py` 应用 `trial_seed` 在 Python 中生成唯一的一对集合，并把同一个 dataset 文件传给所有算法。

输出行中的 `seed` 应表示共享的 `workload_seed`，并额外记录：

```text
dataset_mode = "shared_file"
dataset_dir
```

### Dataset 文件格式

推荐格式：

```text
# compare-dataset-v1 ca=<number> cb=<number> d=<number> seed=<number> trial=<number>
A <ca>
123
456
...
B <cb>
789
...
```

parser 应忽略空行和以 `#` 开头的注释行。

推荐临时目录：

```text
tests/tmp/compare_basic/
```

这些临时 dataset 文件不应该提交。

### Dataset 生成算法

Python 生成器应该复现当前 benchmark 的逻辑：

1. 生成 `max(ca, cb)` 个互不相同的 base values。
2. Alice 取前 `ca` 个 base values。
3. Bob 取前 `cb` 个 base values。
4. 令：

   ```text
   imbalance = abs(ca - cb)
   replacements = (d - imbalance) / 2
   ```

5. 在公共前缀中选择 `replacements` 个不重复位置。
6. 用新的、不重复的值替换 Bob 在这些位置上的值。
7. 分别 shuffle Alice 和 Bob。

生成值应为正的 30-bit 整数：

```text
1 <= x < 2^30
```

### C++ Benchmark 需要新增的接口

两个本地 benchmark 都应该支持：

```text
--dataset PATH
```

当传入 `--dataset` 时：

- 忽略内部随机生成。
- 从文件读取 Alice 和 Bob。
- 从文件推断或验证 `ca`、`cb` 和真实对称差。
- 对该 dataset 只运行一个 trial。

`tests/benchmarks/xyz_v2_bench.cpp` 需要增加 `dataset_path`、`load_dataset(path)` 和 `run_trial_on_data(opt, data)`。

`tests/benchmarks/iblt_bench.cpp` 也需要增加 `dataset_path` 和 `load_dataset(path)`，并从读取的集合中计算期望的 `a_diff` 和 `b_diff`。

### 修复 IBLT Variant

当前 IBLT raw 输出里：

```text
variant = "local"
```

但比较脚本应该保留 job variant：

```text
variant = "capacity_factor=1.5"
variant = "capacity_factor=2"
```

推荐输出：

```text
implementation = "local"
variant = "capacity_factor=<value>"
```

### 补充测试

修复共享 dataset 后，应至少跑：

```bash
python tests/test_compare_basic.py \
  --algorithms xyz_v2,iblt \
  --d-values 1000 \
  --trials 5 \
  --capacity-factors 2.0 \
  --output-dir tests/results/compare_smoke_shared_dataset
```

预期：

- 两个算法使用同一批 dataset 文件。
- `raw.jsonl` 包含 `dataset_mode = "shared_file"`。
- IBLT 行显示 `variant = "capacity_factor=2"`。

再补一个 IBLT 低容量扫描：

```bash
python tests/test_compare_basic.py \
  --algorithms iblt \
  --d-values 1000,3000,10000 \
  --trials 50 \
  --capacity-factors 0.7,0.8,0.9,1.0,1.1,1.2,1.3,1.4,1.5 \
  --output-dir tests/results/compare_iblt_factor_scan
```

这样可以观察 IBLT 的成功率边界，而不是只看到所有 capacity factor 都 100% 成功。

## 实验目标

目标是在相同的合成 workload 下，比较实用 set reconciliation 算法。

核心问题是：

```text
在相同集合大小和对称差 d 下，各算法在通信量、编码时间、解码时间和成功率上表现如何？
```

这个实验不同于前面只研究 XYZ 的脚本：

- `test_dlk.py` 研究 XYZ-v2 参数。
- `test_spatial.py` 隔离 XYZ-v2 内部 spatial coupling 的收益。
- `test_z.py` 研究 `z` 的敏感性。
- `test_compare.py` 应该在共享数据集上比较不同 reconciliation 算法。

## 要比较的算法

仓库当前有这些候选实现：

```text
XYZ-v2                  本地实现
IBLT                    本地实现
external/minisketch     外部 baseline
external/cpisync        外部 baseline
external/riblt          外部 baseline
external/negentropy     外部 baseline
external/IBLT_Cplusplus 外部 baseline
```

第一版应当渐进实现，不要一开始就试图完整接入所有外部代码库。

推荐阶段：

```text
Phase 1: XYZ-v2 + local IBLT
Phase 2: minisketch
Phase 3: external IBLT_Cplusplus
Phase 4: cpisync and riblt
Phase 5: negentropy, only if its ordered-set assumptions can be represented fairly
```

这样即使某个外部依赖有编译问题，第一版脚本仍然是有用的。

## 公平性策略

在同一个 trial 中，所有算法都应该接收同一组生成输入集合。

每个 trial 生成两个集合：

```text
A, B
|A| = ca
|B| = cb
|A symmetric_difference B| = d
```

沿用现有 benchmark 脚本的数据生成策略：

```text
ca = max(1000, d * set_size_scale), capped by max_set_size
cb = ca - (d % 2)
```

脚本应该向每个算法 benchmark 传入相同的 `seed + trial_index`。如果某个算法 benchmark 用其他语言实现，adapter 应该：

1. 使用同一个生成好的 dataset 文件，或者
2. 精确复现同一个确定性生成器。

更稳妥的设计是在 Python 中先生成 dataset 文件，再传给每个 adapter。

## Dataset 格式

使用简单的按行文本格式，方便 C++、Go 和 shell adapter 读取。

推荐的单 trial dataset 文件：

```text
# ca=<number> cb=<number> d=<number> seed=<number>
A
123
456
...
B
789
...
```

不过，每个 trial 都写一个文件可能比较慢。第一版对本地 XYZ-v2 可以先避免中间文件，因为 `xyz_v2_bench.cpp` 已经包含生成器。对于外部 baseline，基于文件的 adapter 通常会更容易。

推荐的长期布局：

```text
tests/tmp/compare/d1000_seed114514_trial0.sets
tests/tmp/compare/d1000_seed114515_trial1.sets
```

这些临时文件不应该提交。

## 参数网格

先从一个较小的网格开始：它要足够展示趋势，但不能大到让外部库构建和运行占满工作量。

推荐 smoke grid：

```text
d in {1000}
set_size_scale = 10
trials = 10
algorithms = xyz_v2, iblt
```

推荐 basic grid：

```text
d in {100, 300, 1000, 3000, 10000}
set_size_scale = 10
trials = 30
algorithms = xyz_v2, iblt, minisketch
```

推荐 extended grid：

```text
d in {100, 300, 1000, 3000, 10000, 30000, 100000}
set_size_scale in {10, 100}
trials = 100 for small d
trials = 30 for large d
```

对于 XYZ-v2，使用前面实验得到的代表性参数：

```text
l = 6
k = 2
mode = spatial
M chosen by the current best-M policy
z = round(M^(1/3) / 3)
```

对于本地 IBLT，脚本应该暴露一个等价的容量系数，例如：

```text
iblt_cell_factor = 1.5, 2.0, 2.5, 3.0
```

对于需要把差集大小作为容量参数的算法，使用：

```text
capacity = ceil(capacity_factor * d)
```

## 统一指标

每个算法 adapter 都应该产生相同的逻辑字段：

```text
algorithm
variant
d
ca
cb
trials
successes
success_rate
encode_avg_s
decode_avg_s
encode_median_s
decode_median_s
bits
bits_per_difference
bit_C_over_d
seed
status
```

其中：

```text
bits_per_difference = bits / d
bit_C_over_d = bits / (32 * d)
```

对于 XYZ-v2，还要记录：

```text
l
k
M
z
mode
field_C_over_d = M * l / d
```

对于 IBLT 类方法，还要记录：

```text
cells
hash_count
cell_bits
capacity_factor
```

对于 minisketch 类方法，还要记录：

```text
field_bits
capacity
```

## Benchmark Adapter 设计

`test_compare.py` 应该把每个算法视为一个具有统一接口的 adapter。

推荐的 Python 结构：

```python
class BenchmarkAdapter:
    name: str

    def build(self, root: Path, build_dir: Path, skip_build: bool) -> None:
        """Build this adapter if needed."""

    def make_jobs(self, config: dict) -> list[dict]:
        """Return benchmark jobs for this algorithm and config."""

    def run(self, job: dict, dataset: Path | None) -> dict:
        """Run one benchmark job and return one normalized result row."""
```

推荐第一批 adapter：

```text
XYZV2Adapter
LocalIBLTAdapter
MinisketchAdapter
```

`cpisync`、`riblt` 和 `negentropy` 的 adapter 可以在理解其构建方式和输入输出格式之后再加入。

## C++ Benchmark 二进制

复用现有 XYZ-v2 benchmark：

```text
tests/benchmarks/xyz_v2_bench.cpp -> build/xyz_v2_bench.exe
```

本地 IBLT 代码目前有 `speedtest.cpp` 和 `iblttest.cpp`，但还没有暴露相同的 JSONL 接口。较干净的做法是之后添加一个小的 benchmark 二进制：

```text
tests/benchmarks/iblt_bench.cpp -> build/iblt_bench.exe
```

它应该接受：

```bash
build/iblt_bench.exe \
  --d 1000 \
  --trials 30 \
  --seed 114514 \
  --ca 10000 \
  --cb 10000 \
  --capacity-factor 2.0 \
  --format jsonl
```

对于外部 baseline，优先使用很薄的 wrapper 二进制或脚本，并输出同样的 JSONL 行格式。

## 外部 Baseline 接入计划

### `external/minisketch`

Minisketch 是最高优先级的外部 baseline，因为它成熟并且和本实验直接相关。

接入计划：

1. 从 `external/minisketch` 构建库。
2. 在 `baselines/minisketch_bench.cpp` 或 `tests/baselines/minisketch_bench.cpp` 下添加一个小 C++ wrapper。
3. 如果可行，使用 32-bit 输入元素。
4. 扫描 `capacity_factor`。
5. 输出统一的 JSONL。

### `external/IBLT_Cplusplus`

它可以作为本地 IBLT 实现的交叉检查。

接入计划：

1. 检查它的 API 和构建要求。
2. 只有在当前平台上容易编译时才添加 adapter。
3. 主要把它作为诊断 baseline，不一定作为主要 IBLT 结果。

### `external/cpisync`

CPISync 是经典 characteristic-polynomial baseline，但可能需要更多配置。

接入计划：

1. 先验证该项目是否能在本地构建。
2. 确认它支持 32-bit 还是更大的整数元素。
3. 等 minisketch 和本地 IBLT 稳定之后再加入。

### `external/riblt`

RIBLT 很有价值，因为它是 rateless 的，在 `d` 未知时也很实用。

接入计划：

1. 检查 Go 实现是否能暴露 CLI benchmark。
2. 使用传输 coded symbols 的数量作为通信指标进行比较。
3. 明确记录它的交互模型不同于固定大小 sketch。

### `external/negentropy`

Negentropy 是 range-based 的，并且假设 key 有序。它有用，但不总是能直接和随机无序集合比较。

接入计划：

1. 只有在决定如何公平表示 ordered workloads 之后才加入。
2. 明确报告它的 ordered-set 假设。
3. 如果没有 caveat，不要把它和 unordered-set 结果混在一起解释。

## 搜索策略

`test_compare.py` 有两种有用模式。

### 固定参数模式

使用固定算法参数，测量成功率、时间和通信量。

这是最简单的第一版。

示例：

```bash
python tests/test_compare.py \
  --algorithms xyz_v2,iblt \
  --d-values 1000,3000 \
  --trials 10
```

### 目标成功率模式

搜索达到目标成功率所需的最小通信量。

当比较具有不同容量参数的算法时，这种方式更公平。

示例：

```bash
python tests/test_compare.py \
  --algorithms xyz_v2,iblt,minisketch \
  --d-values 1000,3000,10000 \
  --target-success-rate 0.95 \
  --search-capacity
```

第一版可以从固定参数模式开始。目标成功率模式可以复用 `test_spatial.py` 的思路。

## 推荐脚本函数

```python
def repo_root() -> Path:
    """Return repository root."""

def ensure_dirs(root: Path, output_dir: Path | None) -> dict[str, Path]:
    """Create output and build directories."""

def parse_list_args(args) -> dict:
    """Parse comma-separated d values, algorithms, and capacity factors."""

def choose_set_sizes(d: int, max_set_size: int, scale: int) -> tuple[int, int]:
    """Choose ca and cb consistently with earlier scripts."""

def make_dataset(seed: int, ca: int, cb: int, d: int) -> tuple[list[int], list[int]]:
    """Generate one deterministic pair of sets."""

def write_dataset(path: Path, alice: list[int], bob: list[int], metadata: dict) -> None:
    """Write one dataset file for external adapters."""

def build_adapters(adapters: list[BenchmarkAdapter], root: Path, skip_build: bool) -> None:
    """Build all selected algorithm adapters."""

def make_jobs(args, adapters: list[BenchmarkAdapter]) -> list[dict]:
    """Expand the parameter grid into algorithm-specific jobs."""

def run_job(job: dict) -> dict:
    """Run one algorithm job and return a normalized row."""

def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write raw results."""

def write_csv(path: Path, rows: list[dict]) -> None:
    """Write CSV results."""

def write_summary(path: Path, rows: list[dict]) -> None:
    """Write a human-readable comparison summary."""
```

## 输出目录

推荐输出目录：

```text
tests/results/compare_basic/
```

推荐文件：

```text
tests/results/compare_basic/raw.jsonl
tests/results/compare_basic/raw.csv
tests/results/compare_basic/summary.md
tests/results/compare_basic/errors.log
tests/results/compare_basic/run_config.json
```

## Summary 格式

summary 应该按 workload 分组：

```text
d, ca, cb
```

每组内部列出：

```text
algorithm
variant
success_rate
bits_per_difference
bit_C_over_d
encode_avg_s
decode_avg_s
status
```

对于目标成功率模式，突出显示成功算法中通信量最小的结果。

## CLI 设计

建议参数：

```text
--algorithms
    逗号分隔的算法列表。例如：xyz_v2,iblt,minisketch。

--d-values
    逗号分隔的对称差大小。

--trials
    每个配置的 trial 数。

--capacity-factors
    逗号分隔的 capacity-based 算法容量系数。

--target-success-rate
    搜索模式使用的目标成功率。

--search-capacity
    启用 best-capacity 搜索，而不是固定参数运行。

--skip-build
    使用已有 benchmark 二进制。

--dry-run
    打印计划任务，不实际运行。

--limit
    只运行前 N 个任务。

--output-dir
    覆盖输出目录。

--base-seed
    可复现实验的种子。

--max-set-size
    限制生成集合大小。

--set-size-scale
    ca/cb 相对于 d 的缩放系数。
```

## 测试计划

### 1. Dry Run

```bash
python tests/test_compare.py --dry-run --algorithms xyz_v2,iblt --d-values 1000 --trials 3
```

预期：

- 脚本打印计划 workload 和选中的算法。
- 不执行 benchmark 二进制。

### 2. 仅 XYZ-v2 Smoke Test

```bash
python tests/test_compare.py \
  --algorithms xyz_v2 \
  --d-values 1000 \
  --trials 5 \
  --output-dir tests/results/compare_smoke_xyz
```

预期：

- 输出包含一行 XYZ-v2 结果。
- 这一行和 `xyz_v2_bench.cpp` 的输出口径一致。

### 3. XYZ-v2 vs 本地 IBLT Smoke Test

```bash
python tests/test_compare.py \
  --algorithms xyz_v2,iblt \
  --d-values 1000 \
  --trials 5 \
  --capacity-factors 2.0 \
  --output-dir tests/results/compare_smoke_iblt
```

预期：

- 输出包含每个 algorithm/variant 的一行结果。
- 两个算法使用相同的 `d`、`ca`、`cb` 和 seed 策略。

### 4. Minisketch Smoke Test

在 minisketch adapter 实现之后：

```bash
python tests/test_compare.py \
  --algorithms minisketch \
  --d-values 1000 \
  --trials 5 \
  --capacity-factors 1.0,1.2,1.5 \
  --output-dir tests/results/compare_smoke_minisketch
```

预期：

- 通信量应随配置的 capacity 增长。
- 当 capacity 至少达到真实差集大小时，成功率应较高。

### 5. 失败处理测试

使用故意很小的 capacity 运行：

```bash
python tests/test_compare.py \
  --algorithms iblt,minisketch \
  --d-values 1000 \
  --trials 5 \
  --capacity-factors 0.5
```

预期：

- 一些行应显示低成功率或 `status = failed_decode`。
- 脚本应继续运行其他算法。

## 解释注意事项

重要 caveats：

- 算法并不总是具有相同的交互模型。RIBLT 是 rateless 的，而 XYZ-v2 和 minisketch 是固定大小 sketch。
- Negentropy 是 range-based 的，不能不加说明地把它当作通用 unordered-set baseline。
- 有些算法可能需要知道或估计 `d`；需要报告实验是否给了它们真实 `d`。
- 通信量统计必须仔细记录。应统计传输的 sketch 字节，而不只是内部 cell。
- 外部 baseline 的构建失败应记录为 `status = unavailable`，不能让整个对比中断。

## 推荐第一版实现

第一版有用实现只需要做这些：

```text
1. Build/reuse xyz_v2_bench.
2. Add or build a JSONL benchmark for local IBLT.
3. Run fixed-parameter comparison for xyz_v2 and iblt.
4. Write raw.jsonl, raw.csv, and summary.md.
```

然后把 minisketch 作为第一个外部 baseline 加入。之后再尝试 `cpisync`、`riblt` 和 `negentropy`。
