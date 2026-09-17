# Figure 2 Protocol Profiles

## 1. 统一 workload

六种算法处理完全相同的 two-party reconciliation task：

- universe 为 `F_998244353 \ {0}`，元素使用 30-bit unsigned integer；
- Sealed confirmation 与 timing 中 Alice、Bob 各持有 `10^7` 个不同元素；resource discovery 按主 README
  使用经 equivalence golden tests 验证的 difference-only construction；
- `|A\B|=|B\A|=d/2`，因此 symmetric difference 恰为 `d`；
- 只要求 Bob 输出精确、有方向的 `A\B` 和 `B\A`；
- 目标 success probability 为 0.9；
- 算法语义参数在任何 search trial 前冻结；
- search 只改变算法为承载 `d` 所分配的资源量。

六个 profile 的 canonical order 固定为：

```text
XYZ-Sketch
minisketch
external IBLT
project IBLT
Rateless IBLT
CPISync
```

`external IBLT` 指 `external/IBLT_Cplusplus/`；`project IBLT` 指仓库根目录的 `IBLT/`。两者是独立曲线。

## 2. 固定语义参数与 search 参数

| 算法 | search 参数 | search 前冻结的参数 |
| --- | --- | --- |
| XYZ-Sketch | integer cell count `M` | `k=2,ell=6,C_cal,D_cal,delta=0.1,a/z` 规则、circular placement、dedup |
| minisketch | 无；capacity 固定为精确 bound `d` | field bits、implementation 选择规则、exact-bound mode |
| external IBLT | `_expectedNumEntries`，结果按 actual cell count 去重 | `N_HASH=4,valueSize=0`、upstream hash/checksum |
| project IBLT | integer cell count `M` | 当前核心根据 `d` 决定的 hash count、fingerprint seed 229 |
| Rateless IBLT | coded-symbol cap | 30-bit symbol、truncated SipHash-2-4、49-bit hash、25-bit signed count |
| CPISync | 无；`m_bar=d` | 30-bit element、`epsilon=4,redundant=0,hashes=false,oneWay=true` |

Cell count 或 symbol cap 是资源量。`oneWay`、exact-bound mode、field bits、checksum width 和 hash mode
决定协议语义，不得针对某个 `d` 或某批结果调优。

## 3. 共享 session 配置与通信计费

Alice 和 Bob 在 session 开始前共同知道 algorithm、`d`、`w=30`、已选 `M/cap`、冻结的 profile 和公共随机种子。
这些内容不发送，也不计入通信。实验 wrapper 不发送 magic、version、algorithm id、flags、length、reserved bytes
或 parameter section。

非 byte-aligned algorithm state 按各 profile 定义的 bit order 连续打包，末字节未使用的低位补 0；实际 padding
bits 计入 state。除 CPISync 外，payload 只有 algorithm state。CPISync payload 是上游 `CommString` 产生的完整
transcript，包括上游自己发送的控制字段。

结果报告：

```text
state_bits         = algorithm state 实际 bytes * 8
control_bits       = algorithm upstream 自己发送的控制 bytes * 8；仅 CPISync 非零
total_payload_bits = state_bits + control_bits
```

Figure 2(a) 使用 `total_payload_bits/(30d)`。任何 wrapper 或审计 artifact 均不计入。

## 4. XYZ-Sketch profile

固定：

```text
k=2
ell=6
hash_mode=CIRCULAR
dedup_hash_locations=true
delta=0.1
a=C_cal*c_peel(2,6)/c_orient(2,6)
z=floor(z_raw+0.5)
```

每个候选 `M` 重新计算 `z_raw`。`C_cal/D_cal` 只来自已确认的 `d<3000` calibration artifact。

State bit order 与当前 `to_bitstring()` 一致：cell id 升序；每个 cell 先写 counter 的 4 个 LSB-first bits，
再按 coefficient index 升序写 6 个 30-bit LSB-first coefficients。Logical state size 为 `184M` bits。

Search 只改变整数 `M`。Discovery 数据选出最小达到 0.9 的 `M`，随后只进行一次 sealed confirmation。

## 5. minisketch profile

固定：

```text
bits=30
capacity=d
decode_max_elements=d
implementation = 2 if minisketch_implementation_supported(30,2), else 0
```

当前 workload 保证 symmetric difference 恰为 `d`，上游保证 difference 不超过 capacity 时正确 decode，
因此 capacity 唯一固定为 `d`。本 profile 不调用 `minisketch_compute_capacity()`，也不定义 `fpbits`；
over-capacity/random-state false accept 不属于本实验输入模型。不得把 capacity 降到 `d` 以下后用随机成功率过线。

Implementation 只改变本机执行路径，不改变 serialized sketch。Capability rule 在 environment audit 时执行一次，
选定 id 写入 build manifest，之后所有 `d` 固定使用该 id。

State 使用 `minisketch_serialized_size()` 与 `minisketch_serialize()` 的实际 byte buffer。Alice 发送自己的 syndrome，
Bob deserialize 后与本地 syndrome merge，再用 `max_elements=d` decode。Bob 已持有的 `B` 在 timer 外准备为
membership index；对解出的 `d` 个元素做 membership query 并形成有方向输出计入 decode CPU time。建立输入集合的
membership 表不属于 MiniSketch update 或 decode。

## 6. external IBLT profile

固定上游 commit `db28fd0fd213b37714e7dfdea3ca2ca67e9f1c09`，保持：

```text
N_HASH=4
N_HASHCHECK=11
valueSize=0
key=zero-extended 30-bit element in uint64_t
```

Search 参数是 `_expectedNumEntries`. 上游实际 cell count 为：

```text
M = expected + floor(expected/2)
while M mod 4 != 0: M += 1
```

产生相同 `M` 的 expected 值是同一个候选，只保留最小 expected 值。

允许的上游补丁仅增加 canonical serialize/deserialize 和只读 `cell_count()`；不得修改构造公式、hash count、
hash seed、cell update、subtract、purity check 或 peeling。补丁 diff 和 SHA-256 在 formal build 前冻结。

每个 cell 连续写入 25-bit signed two's-complement `count`、30-bit `keySum` 和 32-bit `keyCheck`，共 87 logical
bits。所有 cell 连续 bit-pack，只允许末字节低位补零。State size 为 `ceil(87M/8)*8` bits。Vector capacity、
对象 padding 和 `DumpTable()` 文本不计入 wire size。

## 7. project IBLT profile

使用根目录 `IBLT/iblt.cpp` 原样算法：

```text
hash_count = 4 if d<200 else 3
fingerprint seed = 229
cell = (signed count, uint32 additive key sum, uint32 fingerprint xor)
```

Search 参数为 integer `M`。Wrapper 使用 `capacity_factor=(M-0.5)/d` 构造，使核心中的
`ceil(capacity_factor*d)` 确定得到 `M`，并断言公开 `cell_count()==M`；不能满足
断言的候选无效。不得修改 hash-count 分支、hash seeds、additive/XOR 更新规则、purity check 或 peeling。

`Encode()` 返回的 cell vector 是 wire source。每个 cell 固定 12 bytes：count 4 bytes、key sum 4 bytes、
fingerprint 4 bytes，均为 big-endian；state size 为 `96M` bits。

Wrapper 在 timer 外准备可移动的输入 vector，调用 `Encode(std::move(input))`，避免 batch API 的按值参数复制；
`Encode()` 内部的 table 初始化、allocation 和元素更新全部计入 update。Receiver 以 move 传入已解析的两张 table，
不为只读输入额外复制完整 table。

## 8. Rateless IBLT profile

使用 upstream commit `4afa6bc06cb2237d9ea273a51d97a7e05b3f573b`。Wrapper 定义 `uint32` symbol，
只使用低 30 bits，XOR 仍保持在 30-bit domain。`Hash()` 使用 SipHash-2-4 的低 49 bits；128-bit key
由 algorithm/config/trial seed 的 SHA-256 digest 前 16 bytes 派生；前 8 bytes big-endian 为 `k0`，后 8 bytes
big-endian 为 `k1`。该 key 属于共享公共随机性，不发送。

每个 coded symbol 的 canonical wire fields 为：

```text
Symbol: 30 unsigned bits
Hash:   49 unsigned bits
Count:  25-bit two's-complement signed integer
```

25-bit signed count 覆盖 `[-10^7,10^7]`。每个 coded symbol 按 `Symbol,Hash,Count` 顺序写入；每个字段内部
MSB-first，Count 使用 25-bit two's-complement。每个 coded symbol 共 104 logical bits，symbols 连续 bit-pack，
不逐 symbol 对齐。Symbol sequence index 由接收顺序隐含，不发送 index。

Formal session 发送完整 cap 个 symbols。固定 cap 已在 session 前共享，因此使用上游专门为 predetermined prefix
提供的 `riblt.Sketch`：Alice 和 Bob 在各自 update timer 内把元素加入长度 cap 的 sketch；Bob 收到 Alice 的 coded
symbols 后执行 `Subtract()` 和 `Decode()`。不发送 wrapper status byte。Self-test 必须逐 symbol 证明 `Sketch` 与旧
`Encoder` 产生的前 cap 个 coded symbols 完全相同。Search 参数只有 cap。

## 9. CPISync profile

使用 upstream commit `268c38fb130dd385469291288a3632b8c31e6e70` 和 `CPISync_HalfRound`：

```text
m_bar=d
bits=30
epsilon=4
redundant=0
hashes=false
oneWay=true
use_existing=false
Communicant=CommString(base64=false)
```

Bob 是 server/decoder。只要求 Bob 恢复两个有方向差集，因此 one-way 是与固定 sketch 的 Alice-to-Bob 方向
一致的唯一模式。`hashes=false` 保留真实 30-bit element，避免不必要的 hash collision 和返回原字符串轮次。
`epsilon=4` 使错误上界 `2^-4<=0.1`；`redundant=0` 要求上游从 epsilon 推导 redundancy，在本 profile 中
得到一个 verification point。

每个 universe element `x` 必须以 `DataObject(to_ZZ(x))` 构造，禁止经 decimal string、binary string 或
wrapper hash 转换。这样 `DataObject::to_ZZ()` 精确返回原 30-bit integer，`hashes=false` 时 field element
与其他五种算法的输入 identity 相同。`DataObject` 是调用者持有的输入集合表示，在 timer 外构造；update CPU
只计上游 `addElem()`。

CPISync 固定采用 one-way transcript mode，不实现双向内存 channel：

1. Alice 使用空的 `CommString(base64=false)` 顺序执行完整 `SyncClient`，生成 transcript；
2. `getString()` 返回的 upstream transcript 是完整 payload，不添加 wrapper bytes；
3. transcript 只复制一次；Bob 用 immutable transcript 构造 `CommString(transcript,false)`，顺序执行完整
   `SyncServer` 并恢复两个方向差异；
4. Alice transmit bytes 必须等于 transcript length，Bob receive bytes 必须等于同一长度；
5. 不启动 client/server 并行线程，不允许 endpoint 从自己刚写入的 stream 读取。

`keepAlive=false` 使 modulus、SyncID、`m_bar`、bits 和 epsilon 的上游协商 bytes 真实发送并计入
`control_bits`。Polynomial evaluation bytes、长度字段、成功/失败 flag 及上游要求的返回 payload 均按
`CommString` 的 transmit counters 计费；base64 不启用。

Decode CPU 分成 `alice_serialize_transcript_cpu`、`transcript_copy_cpu` 和 `bob_decode_cpu`，三者均用
`CLOCK_THREAD_CPUTIME_ID` 顺序测量并相加。等待和线程调度不存在。Golden fixture 必须断言 Bob 仅从 immutable
Alice transcript 精确恢复 `A\B` 与 `B\A`。

CPISync 不搜索 `m_bar<d`，因为该值是保证恢复的 difference bound，不是可牺牲正确性的空间旋钮。

CPISync transcript 保留上游实际变长 serialization，不做固定长度 padding。对 confirmed point，Figure 2(a) 使用
成功 sealed-confirmation trials 的实际 `state_bits`、固定 `control_bits` 和 `total_payload_bits` 的算术平均；每条
raw row 的 accounting 仍按实际 transmit counters 逐条校验。

## 10. Pre-implementation golden specifications

下表是 protocol version 1 的手算 expected vectors，不是已执行测试结果。Wrapper 实现后必须用以下小型配置
建立逐字段 golden tests。CPISync build
固定 LP64 ABI：`sizeof(long)=8,sizeof(int)=4`，不满足时 build 状态为 `abi_incompatible`。

| profile | 小型配置 | 预期 accounting |
| --- | --- | --- |
| XYZ | `M=2,k=2,ell=6` | state=total 368 bits |
| minisketch | `capacity=2` | logical state 60、serialized state=total 64 bits |
| external IBLT | `expected=2 -> M=4` | logical state 348、serialized state=total 352 bits |
| project IBLT | `d=2,M=3,h=4` | state=total 288 bits |
| Rateless IBLT | `cap=3` | logical state=serialized state=total 312 bits |
| CPISync | `A={1,2},B={2,3},m_bar=2` | upstream transcript=total 392 bits |

CPISync expected fixture 使用 modulus `1073741827`；三个 Alice evaluation 为 `(12,6,2)`，按上游 base
`1073741828` 打包后占 8 bytes。49 upstream bytes 分解为：modulus length/value 8 bytes、SyncID 与三个参数
21 bytes、Alice set size 8 bytes、packed evaluation vector length/value 12 bytes。Polynomial state 为 packed
value 的 8 bytes；其余 41 upstream bytes 为 control。Golden expected accounting 为
`state_bits=64,control_bits=328,total_payload_bits=392`。实现后的测试保存完整 upstream byte stream、
逐次 send 长度、总 byte 长度和 SHA-256，并断言 stream length 与 `Communicant` counters 相等。ABI 宽度变化
会改变 golden hash并使 build manifest 失效。

若真实 upstream bytes 与 expected vector 不一致，实现不得修改 wrapper 迎合 expected 数值。Protocol version 1
状态立即退回 `protocol_failed`；先依据固定源码修正文档和 expected vector，再通过新的独立 protocol audit。

## 11. Profile 冻结门

每个 profile 在 formal trial 前必须生成并通过实现审计：

- source commit、build flags 和本地补丁 SHA-256；
- 完整 profile JSON 与 canonical algorithm payload SHA-256；
- golden accounting test 结果；
- capability check，包括 minisketch implementation id；
- public API 调用清单；
- `core_algorithm_modified=false` 断言。

Profile hash 写入每条新 raw result。Profile 变化必须创建新 run identity。若变化只删除 wrapper bytes 或把固定-cap
RIBLT 从 `Encoder` 改为经逐 symbol 证明完全等价的 `Sketch` API，旧 probability/operating-point artifact 可由显式
migration manifest 复用；manifest 必须绑定父 artifact hash、payload 变换、equivalence evidence 和新 executable hash。
旧 timing 不得迁移。

## 12. Timing estimand

六种 profile 使用同一 timing 统计口径：`E[运行时间 | 解码成功]`。每个 `(algorithm,d)` 独立重试新的
timing-domain dataset，直到获得 5 个三次 measured repetitions 全部成功的 dataset。每个成功 dataset 先对三次
CPU time 取算术平均，再对 5 个 dataset means 取算术平均。`decode_failed`、`wrong_output` 以及未完成 attempt
的耗时不得进入点估计或 bootstrap interval；这些 attempt 只进入 attempted/failed 计数。统计失败没有重试上限，
但已批准的 timeout/OOM 资源停止规则保持有效。
资源停止前不足 5 个成功 datasets 时保留 attempted/failed/successful 诊断计数，但条件均值和 bootstrap interval
全部为 null。只有 `timing_status=complete` 且 `successful_datasets=5` 的点可进入 timing panels。
任何 timing measured repetition 的 `process_error` 永久使整个 run 失效；其 checkpoint 不得在 resume
时被分类为普通 failed attempt，也不得通过后续成功 datasets 覆盖。

所有 residual SHA-256、ground-truth comparison、artifact serialization 和文件写入均在 timer 外。输入集合容器、
MiniSketch Bob membership index、CPISync `DataObject` 以及已初始化算法对象在 timer 开始前准备完成。
