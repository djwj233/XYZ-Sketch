# Figure 2 端到端复现实验方案

## 1. 实验目标与两级启动门

Figure 2 protocol 为六种实现生成同口径结果，并比较：

1. normalized total payload；
2. update CPU time per input element；
3. decode CPU time per difference。

### 1.1 Protocol implementation gate

以下条件允许开始实现 wrapper、external IBLT serialization patch、golden tests、equivalence tests 和 smoke tests：

- threshold validation 通过；
- README、protocol profiles、candidate grids、wire specifications 和 expected golden vectors 完整；
- 独立协议复审结论为 `pass`，状态记为 `protocol_audited`。

该门不要求尚未实现的 patch hash、实际 golden bytes 或 build capability artifact。通过后只能产生实现与测试
artifact，不得运行 resource discovery、sealed confirmation 或 timing。

### 1.2 Formal-run gate

以下条件全部满足后才允许正式 trial：

- `d<3000` 的独立 `C/D` recalibration 已确认并冻结；
- sealed Figure 1(b)(c) holdout 的两个 frozen prediction 均达到 0.9；
- wrapper、允许的补丁、source/build/profile hash 已冻结；
- wire golden tests、difference-only equivalence tests、capability checks 和 smoke tests 全部通过；
- `candidate_budget.json` 与 dry-run manifest 通过实现审计；
- 独立实现复审结论为 `pass`，状态记为 `implementation_audited`。

Formal-run gate 未通过时不得运行可进入图表的 trial。

## 2. 论文依据与项目消歧

论文明确给出：

- Figure 2 使用完整 XYZ-Sketch；
- 对比 MiniSketch、CPISync、Rateless IBLT 和 conventional IBLT；
- 所有方法使用相同 workload 与 0.9 success target；
- communication、update time 和 decode time 是比较指标。

论文未公开各上游库的完整构造参数、wire encoding、capacity search、session metadata 和精确 timer boundary。
本 README 与 `PROTOCOL_PROFILES.md` 对这些内容作项目级预注册，不将其表述为论文原始设置。

## 3. 算法、源码与 presentation gate

| profile | 源码 | 角色 |
| --- | --- | --- |
| XYZ-Sketch | `XYZ-Sketch/` | 论文方法，`(k,ell)=(2,6)` |
| minisketch | `external/minisketch/` | BCH/PinSketch 实现 |
| external IBLT | `external/IBLT_Cplusplus/` | 固定 `N_HASH=4` 的上游 conventional IBLT |
| project IBLT | `IBLT/` | 本仓库自有 conventional IBLT |
| Rateless IBLT | `external/riblt/` | rate-compatible reconciliation |
| CPISync | `external/cpisync/` | characteristic-polynomial reconciliation |

`project IBLT` 是新增 baseline，不替代对应论文 conventional IBLT 的 `external IBLT`。六个 profile 都生成结果，
但绘图前必须冻结以下枚举之一：

```text
project_iblt_presentation = extended
project_iblt_presentation = main_additional_baseline
```

`extended` 表示主 Figure 2 画 XYZ-Sketch、minisketch、external IBLT、Rateless IBLT、CPISync，
project IBLT 单独进入 `Figure 2 extended`。`main_additional_baseline` 表示主图画六条曲线，标题和图注明确写
`Figure 2 reproduction plus an additional project-IBLT baseline`。当前该字段由用户延后冻结。该字段只影响
最终发布的图例和文件名，移至 plotting/publication gate；不阻断六个 profile 的 wrapper、golden/equivalence
测试、resource discovery、confirmation、timing 原始数据实现和生成。无论最终选择哪个枚举，固定生成并保留
不含 project IBLT 的五算法 paper-main 图；project IBLT 只能作为明确标注的 additional baseline 出现。

每个 source profile 记录 commit、license、compiler、flags、public API、patch diff 与 SHA-256。只允许
`PROTOCOL_PROFILES.md` 明确列出的 wrapper 或序列化补丁，不允许修改任何算法的 update、hash、purity、
subtract、recovery 或 peeling 逻辑。

## 4. Workload

Difference-size grid 固定为：

```text
d in {100, 300, 1,000, 3,000, 10,000, 30,000,
      100,000, 300,000, 1,000,000}
```

每个 `d`：

- `|A|=|B|=10,000,000`；
- `|A\B|=|B\A|=d/2`；
- universe 为 `F_998244353 \ {0}`；
- 元素编码为 30-bit unsigned integer；
- 每个 final probability point 使用 100 independent trials。

Figure 2 中 `d<3000` 的点不是 `C/D` 外推 holdout；它们仍是端到端比较点。`C/D` 的外推 holdout 标签只用于
参数冻结后运行的 Figure 1(b)(c)。Figure 2 的任何结果都不得反馈修改 `C_cal/D_cal`。

## 5. Paired dataset

同一个 `(domain,d,trial_index)` 的六种算法接收完全相同的差异元素。固定 `base_seed=114514`，dataset seed 为：

```text
SHA256("figure2|base_seed|domain|d|trial_index|dataset_role")[:64]
```

`dataset_role` 分别为 `identity,alice_order,bob_order`，不含 algorithm 或 config，因此保持 paired workload。

Algorithm-internal seed 单独派生：

```text
SHA256("figure2|base_seed|domain|d|trial_index|algorithm_id|profile_hash|internal_role")[:64]
```

Discovery、confirmation 和 timing 使用互不重叠的 domain：

```text
resource_discovery
sealed_confirmation
timing
```

`resource_discovery` 采用用户确认的 difference-only workload：Alice 只编码 `A-only` 的 `d/2` 个元素，Bob
只编码 `B-only` 的 `d/2` 个元素，二者不相交且合计恰为 `d`。该阶段只选择资源量，不进入正式概率、通信或
timing 图表。

`sealed_confirmation` 和 `timing` 始终构造完整 `|A|=|B|=10^7` 集合。Generator 使用 Floyd sampling
无放回构造公共部分和两个方向差异，再分别打乱 insertion order。每个 dataset 保存
`A/B/A-only/B-only` 流式 SHA-256。数据生成、manifest 校验和 ground-truth 构建不计入算法时间。

Implementation gate 必须对 XYZ-Sketch、external IBLT、project IBLT 和 Rateless IBLT 建立 equivalence
golden tests：固定 `|A|=|B|=1000,d=100`，比较 full-set subtraction 与 difference-only construction 的
residual state。固定 sketch 要求 canonical residual bytes 完全相同；Rateless IBLT 要求前 `3d` 个接收后
residual coded triples 与最终有方向输出完全相同。任一 profile 不满足 byte/state equivalence 时，不得使用
difference-only discovery。

Equivalence fixtures 使用
`SHA256("figure2|equivalence|profile_hash|fixture_index")[:64]` 的 `fixture_index=0,...,9`，并覆盖：

| profile | 固定资源配置 |
| --- | --- |
| XYZ-Sketch | `(M,a,z)=(10,0.2,1),(25,0.2,1),(40,0.2,1)` |
| external IBLT | `_expectedNumEntries in {50,100,150}` |
| project IBLT | `M in {80,190,300}` |
| Rateless IBLT | 比较前 300 个 residual coded triples，并在 cap `{100,200,300}` 比较 decode status/state/output |

全部 10 个 fixture 和全部表中配置都必须通过；不能以 aggregate rate 代替逐 byte/state 断言。

## 6. 统一成功判据

Trial 成功仅当：

- 算法没有报告失败；
- 输出的 `A\B` 与真值完全相同；
- 输出的 `B\A` 与真值完全相同；
- 输出没有重复、遗漏或额外元素；
- 接收端已真实解析计费的 algorithm payload bytes，而不是直接读取发送端对象。

只恢复无方向 symmetric difference 的 minisketch 由 Bob 查询本地 `B` 完成方向分类。Membership lookup
计入 decode CPU time，不增加通信量。

## 7. 固定 profile 与可搜索资源

[PROTOCOL_PROFILES.md](./PROTOCOL_PROFILES.md) 是 profile 和 wire format 的 authoritative source。固定语义如下：

- XYZ-Sketch：搜索 integer `M`；
- minisketch：`bits=30,capacity=d,decode_max_elements=d`，不定义 `fpbits`，不搜索低于 `d` 的容量；
- external IBLT：`N_HASH=4,valueSize=0`，搜索 `_expectedNumEntries`，按 actual cell count 去重；
- project IBLT：保持核心 hash-count 分支，搜索 integer `M`；
- Rateless IBLT：搜索 coded-symbol cap；
- CPISync：`m_bar=d,bits=30,epsilon=4,redundant=0,hashes=false,oneWay=true`，不搜索更小 bound。

`oneWay/twoWay`、exact-bound mode、field bits、hash mode、checksum width 和 implementation capability rule 不进入
per-`d` 调参。

## 8. Resource discovery 与 sealed confirmation

### 8.1 有限 candidate grids

Resource search 只在下表的预注册 ratio grid 上进行。Ratio 使用十进制定点整数生成，资源整数固定按
`floor(ratio*d+0.5)` 取整并去重。

| 算法 | ratio 定义 | coarse domain | coarse step | fine step | 最大执行候选数 |
| --- | --- | --- | ---: | ---: | ---: |
| XYZ-Sketch | `M/d` | `[0.10,0.40]` | 0.02 | 0.002 | 25 |
| external IBLT | `_expectedNumEntries/d` | `[0.50,1.50]` | 0.05 | 0.005 | 30 |
| project IBLT | `M/d` | `[0.80,3.00]` | 0.10 | 0.01 | 32 |

每个 `(algorithm,d)` 先运行全部 coarse candidates。若没有 coarse candidate 达到 0.9，状态为
`resource_out_of_grid`，不得向外扩展。若第一个 coarse candidate 已通过，它就是 grid-minimum candidate。
否则只在“最后一个未通过 coarse candidate”和“第一个通过 coarse candidate”的闭区间按 fine step 生成
候选。Coarse endpoints 不重复运行。最终选择只声称是该预注册 coarse-plus-selected-fine grid 中
`total_payload_bits` 最小的 passing candidate，不声称是全部整数资源中的全局最小。

任何 trial 前生成 `candidate_budget.json`，列出全部 coarse candidates、每个可能 crossing 对应的 fine list、
最大候选数和最坏 update 数。上表的最大执行候选数分别来自 coarse count 加一个 crossing interval 的 9 个
新 interior points。Coarse 结束后原子冻结唯一 fine manifest；fine candidates 复用同一组已锁定的 100 个
`resource_discovery` datasets，不生成新 seed domain。

Difference-only trial 的 Alice/Bob update 总数恰为 `d`。因此每个 `d` 的 discovery update 上界固定为：

```text
XYZ-Sketch:   25*100*d = 2500d
external IBLT:30*100*d = 3000d
project IBLT: 32*100*d = 3200d
```

在全部九个 `d` 上，`sum(d)=1,444,400`，对应上界分别为 3,611,000,000、4,333,200,000 和
4,622,080,000 次 element updates。Manifest 计算值必须不高于这些上界，否则 formal-run gate 失败。
Rateless discovery 固定 100 个 difference-only input trials，每 trial 最多产生 `3d` symbols，不允许动态提高上限。

### 8.2 通用状态机

对具有 search 参数的 XYZ-Sketch、external IBLT 和 project IBLT：

1. 在 `resource_discovery` domain 上，每个候选运行同一组 100 paired difference-only trials。
2. 按 formal profile 对该资源量计算 `total_payload_bits`；difference-only 只减少 update 输入，不缩短 sketch
   state 或 Rateless cap。按该 bit 数升序排列候选，bit 数相同时按资源参数升序。
3. 选择第一个 discovery success rate `>=0.9` 的候选。
4. 锁定 candidate id、profile hash 和 confirmation seed manifest。
5. 只对该候选运行一次使用完整 `10^7` 集合的 100-trial `sealed_confirmation`。
6. 在没有 `process_error/timeout/oom` 的前提下，confirmation success rate `>=0.9` 时成为 formal operating
   point；普通统计失败使状态为 `confirmation_failed`，并按 Section 8.2.1 的 refinement 规则处理。任一
   timeout/OOM 直接使当前点状态为 `timeout/oom`，不计算 success rate，后续更大 `d` 为
   `not_run_after_resource_limit`。

`process_error`、wrapper exception 或 malformed engine output 均为实现错误：先保存当前 checkpoint 和 error log，
随后把整个 formal run 标为 `failed`，不得进入 discovery/confirmation 的 Bernoulli rate。

### 8.2.1 Operating-point refinement

2026-07-19 冻结以下 refinement 规则，用于 formal source run 中状态为 `confirmation_failed` 的点：

1. 已确认点、timeout/OOM 点和 `not_run_after_resource_limit` 点不进入 refinement；旧 trial 不重跑。
2. 从原 operating point 的下一个更大预注册资源候选开始，不修改 candidate grid，也不重新运行 discovery。
3. 每个候选使用新的独立 100-trial full-set confirmation block。Seed domain 固定为
   `sealed_confirmation_refinement_<attempt>`，同一 `(d,trial,attempt)` 的算法继续使用 paired dataset。
4. 第一个达到至少 `90/100` 成功的候选成为 refined operating point；同一资源不做统计性重复。
5. 未达到 `90/100` 时继续到下一个更大候选，直到通过或耗尽预注册候选。
6. Refined operating point 只补跑自己的 timing：5 个成功 dataset，每个 dataset 三次 measured repetitions，
   无 warm-up，统计量仍为 `E[runtime | decode success]`。
7. 原 formal run 保持不可变；refinement 写入独立 artifact，并通过 source aggregate SHA-256、executable
   SHA-256、profile manifest SHA-256 和 frozen-parameter SHA-256 绑定来源。

本轮 refinement 的固定目标为：XYZ-Sketch 的 `d in {3,000,10,000,30,000}`、external IBLT 的
`d in {1,000,10,000,100,000}`，以及扩展图 Project IBLT 的 `d=100`。MiniSketch 与 CPISync 的资源
timeout 仍按自然右截断处理，不由 refinement 绕过。

### 8.3 XYZ-Sketch

Search resource 为 grid 产生的 integer `M`。每个 `M` 重新计算 `z_raw/z`，保持冻结的 `C_cal/D_cal` 与 `a`。

### 8.4 external IBLT

Search resource 为 grid 产生的 `_expectedNumEntries`。不同 expected 值产生相同 actual cell count 时只运行最小 expected。
排序和通信比较使用 actual serialized bytes。Hash count 固定为 4，不存在 `h=3/5` 分支。

### 8.5 project IBLT

Search resource 为 grid 产生的 integer `M`。
Wrapper 通过 `capacity_factor=(M-0.5)/d` 构造并断言 `cell_count()==M`。Core 根据
`d` 自动选择 hash count；该分支不是 search 参数。

### 8.6 minisketch 与 CPISync

两者的资源由精确 difference bound `d` 唯一确定，没有 discovery candidate selection。它们直接在
`sealed_confirmation` domain 运行 100 trials。任一 trial 失败仍按统一成功判据计入失败，不临时增大 capacity
或 `m_bar`。

### 8.7 Rateless IBLT

在 100 个 difference-only `resource_discovery` trials 中记录成功解码所需的 symbol count。每个 trial 最多
生成 `3d` 个 symbols；达到上限仍未解码时记录 `required_symbols=3d+1`。排序为
`q[1]<=...<=q[100]`。固定 cap 为 nearest-rank 90th percentile：

```text
cap = q[ceil(0.9*100)] = q[90]
```

若 `q[90]>3d`，状态为 `resource_out_of_grid`。否则在 100 个使用完整 `10^7` 集合的全新 sealed confirmation
trials 中每次发送完整 cap 个 symbols。即使提前解码也不缩短正式 payload。Confirmation 失败时不得增加 cap
或创建统计性重试。

## 9. 通信量

Alice 和 Bob 预先共享 algorithm、`d`、`w=30`、已选 `M/cap`、冻结 profile 和公共随机种子。Wrapper 不发送
envelope、metadata 或 parameter section。XYZ、MiniSketch、两个 IBLT 和 Rateless IBLT 只计 algorithm state；
CPISync 计上游 `CommString` 真实 transcript，因此其上游参数协商保留并计费。

```text
R = total_payload_bits/(30d)
total_payload_bits = state_bits + control_bits
```

对每个 sealed-confirmed `(algorithm,d)`，Figure 2(a) 的 `state_bits`、`control_bits` 和
`total_payload_bits` 分别取成功 confirmation trials 中实际 payload accounting 的算术平均，失败 trial 不进入通信量
聚合。因此 Figure 2(a) 估计 `E[actual payload bits | decode success]/(30d)`。固定长度 sketch 的均值等于其确定
长度；CPISync 的上游 transcript 采用实际变长序列化，其聚合 bits 允许为非整数。每条 raw row 仍必须独立满足
`state_bits+control_bits=total_payload_bits`。

计入：

- fixed sketch 的完整 canonical state bytes；
- algorithm state 内的 counter、fingerprint、hash、field value 和末字节 padding；
- CPISync 上游自己发送的 control 与 polynomial payload；
- CPISync `CommString(base64=false)` transmit counters 记录的全部 upstream bytes。

排除：

- TCP/IP、socket、文件、JSON、日志和 benchmark process framing；
- dataset manifest 与 ground truth；
- wrapper magic、version、algorithm id、flags、length、reserved bytes、参数副本和 status；
- 没有进入 wire 的 C++/Go object padding 和 allocator capacity。

每条 row 同时保存 field-by-field accounting 和实际 buffer length。二者不相等时 row 状态为
`wire_accounting_mismatch`，不得进入图表。

## 10. Timing

### 10.1 主计时口径

Figure 2 主 panel 使用确定性 in-memory byte transfer，并累计 sender、transfer copy 和 receiver 的 CPU time。
Linux 实现使用 `CLOCK_THREAD_CPUTIME_ID`，等待、线程调度和 transport wall time 不进入主 panel。

CPISync 按 protocol profile 的 transcript mode 顺序执行：先计 Alice 由 `SyncClient` 生成 upstream transcript
的 CPU，再计 immutable transcript copy 的 CPU，最后计 Bob 的 `SyncServer` upstream decode CPU。它不创建并行 endpoint
线程。Loopback wall time 不进入主图。

### 10.2 Update time

```text
t_update = (cpu_update_A + cpu_update_B)/(|A|+|B|)
```

Timer 从已经初始化的算法对象接收第一个元素前开始，在最后一个 update 返回后结束。计入 update 内部 hashing、
field arithmetic 和 algorithm allocation；排除 dataset generation、输入容器准备、CPISync `DataObject` 构造、
MiniSketch Bob membership-index 构造、manifest、serialization 和 logging。Project IBLT 在 timer 外准备 movable
input vector，但 `Encode()` 内部的 table 初始化和 allocation 计时。

### 10.3 Decode time

```text
cpu_decode_total = cpu_sender + cpu_transfer_copy + cpu_receiver
t_decode = cpu_decode_total/d
```

计时从发送端开始构造 on-wire state 或第一条 protocol message 开始，到 Bob 产生最终有方向差集为止。计入：

- serialization、in-memory transfer copy 和 parsing；
- local sketch subtraction/merge；
- peeling、algebraic recovery和 protocol interaction；
- Rateless fixed-cap sketch serialization、subtraction 和 decode；
- minisketch membership direction classification；
- 输出形成所需排序和去重。

Residual SHA-256、ground-truth comparison、审计 serialization 和结果写盘不计时。

### 10.4 Repetition 与统计

Timing 的 estimand 固定为 `E[运行时间 | 解码成功]`。每个已确认 operating point 必须收集 5 个成功的
`timing`-domain datasets；5 是成功 dataset 数，不是总 attempt 数。对每个 `(algorithm,d)`，attempt index 从 0
连续递增，每个新 index 用独立 seed 生成新 dataset。相同 `(d,attempt_index)` 在仍需采样的算法之间保持 paired，
但各算法独立累计成功数，已经收满 5 个的算法停止采样。

每个 attempt 不执行 warm-up，直接执行 3 次 measured repetitions。只有三次 measured repetitions 全部满足
Section 6 的成功判据时，该 attempt 才是成功 dataset；三次耗时的算术平均是该 dataset 的一次观测。任一次出现
`decode_failed` 或 `wrong_output`，整个 attempt 记为失败，其全部原始 row
保留但任何耗时都不进入统计，然后使用新的 attempt index 重试。统计失败没有重试上限，直至该 `(algorithm,d)`
收满 5 个成功 datasets。

主图报告 5 个成功 dataset means 的算术平均，分别估计条件 update/decode time。95% interval 使用固定 seed
`figure2_timing_bootstrap` 做 10,000 次 dataset-level percentile bootstrap；每个 bootstrap sample 重新计算算术
平均并报告 2.5% 和 97.5% quantile。不得把同一 dataset 的三次 repetition 当作三个独立样本，也不得让失败
attempt 的 CPU time 进入点估计或 interval。每点必须记录 `attempted_datasets`、`failed_datasets`、
`successful_datasets=5`。

`process_error` 是实现或运行环境错误，保存当前 measured checkpoints 和 error log 后将整个 run 原子标为
`status=failed,failure_reason=process_error,failed_stage=timing`，不作为统计失败无限重试。任何已有
`process_error/not_run_after_process_error` checkpoint 都是永久 fatal 证据；即使 run state 被错误恢复为
`timing_running`，resume 仍必须在生成新 dataset 前拒绝。`timeout/OOM` 仍按已批准的资源上限停止该算法，并按
Section 11 处理当前及更大 `d`；只有资源上限允许 timing point 缺失。

## 11. 环境控制

- Resource discovery 与 sealed confirmation 固定使用 8 个独立进程，分别绑定物理 CPU `0,...,7`；trial seed、
  checkpoint path 与临时 dataset 由 `(domain,d,trial_index)` 唯一确定，worker 调度不进入随机种子；
- discovery 与 confirmation 的并行输出按 trial identity 排序汇总，不使用这些并行进程采集的 CPU time 作为
  timing 图数据；
- probability worker 共享停止状态；任一 timeout/OOM 后该算法不再领取新 trial，任一 process error 后所有 worker
  不再领取新 trial。已经在执行的 subprocess 允许结束并作为诊断 row 保留，但资源失败点不计算统计 rate；
- formal timing 固定只使用 CPU 0 单进程串行执行；开始 timing 前全部 probability worker 必须退出，算法之间、
  dataset 之间和 repetition 之间均禁止并发；
- performance governor，记录实际频率和 turbo 状态；
- 记录 CPU、microcode、RAM、kernel、compiler、Go version、NTL 和 build flags；
- 每个算法的 profile/build hash 在全 run 内不变；
- 禁止 timing 阶段算法间并发 benchmark；
- 超时和内存上限在 run config 中预注册。

CPISync 或其他算法达到资源上限时，该点记录 `timeout` 或 `oom`；后续更大 `d` 记录
`not_run_after_resource_limit`。不外推缺失数值，不延长曲线。

## 12. 结果文件

```text
results/figure-2/<run_id>/
  run_config.json
  dataset_manifest.jsonl
  profile_manifest.json
  candidate_budget.json
  equivalence_golden_results.json
  resource_discovery.jsonl
  confirmation.jsonl
  timing.jsonl
  timing_attempts.jsonl
  timing_summary.json
  aggregate.csv
  finalization_manifest.json
  wire_golden_results.json
  source_manifest.md
  environment.md
  figure2a.svg
  figure2a.pdf
  figure2a.png
  figure2b.svg
  figure2b.pdf
  figure2b.png
  figure2c.svg
  figure2c.pdf
  figure2c.png
  figure2-combined.svg
  figure2-combined.pdf
  figure2-combined.png
  errors.log
```

`figure2-combined.{svg,pdf,png}` 将三个 paper-main panel 横向排列并共用一个图例，固定不包含 project IBLT。
当 `project_iblt_presentation=extended` 时，另生成
`figure2-extended-{a,b,c}.{svg,pdf,png}`；这些图只增加 project IBLT，不改变主 `figure2{a,b,c}` 的六条曲线。
当取值为 `main_additional_baseline` 时不生成 extended 文件，主 `figure2{a,b,c}` 固定包含七条曲线。

Probability row 至少包含：

- `run_id,algorithm,profile_hash,d,trial_index,domain,candidate_id`；
- resource 参数、`state_bits,control_bits,total_payload_bits,R_w30`；
- dataset 与 internal seed、四个 set SHA-256；
- success、failure reason、两个有方向输出 SHA-256；
- source/build/patch/frozen-parameter hashes。

Timing repetition row 另含两端 update CPU、sender/transfer/receiver decode CPU、repetition id 和 CPU id。
`timing_attempts.jsonl` 每个 dataset attempt 一行，含 attempt status、三次 repetition 完成数、失败原因以及仅在
3/3 成功时形成的两个 dataset mean。`timing_summary.json` 每点记录 attempted/failed/successful 计数、条件均值
和 bootstrap interval。

MiniSketch 使用固定 `capacity=d` 的 deterministic exact-bound profile。`d=10,000` 的扩展点不重复运行
Bernoulli confirmation，只运行完整 `10^7` 集合的 timing；独立 domain 为
`timing_minisketch_d10000_extension`。该点同样串行收集五个成功 dataset，每个 dataset 三次 measured
repetition，失败 dataset 不进入算术平均。

## 13. 绘图

| panel | y 轴 | x 轴 |
| --- | --- | --- |
| (a) | `R=total_payload_bits/(30d)` | `d`，log |
| (b) | `E[update CPU | decode success]` ns/input element | `d`，log；y 轴 log |
| (c) | `E[decode CPU | decode success]` ns/difference | `d`，log；y 轴 log |

图例由 Section 3 的 `project_iblt_presentation` 唯一决定，且其余五条始终按 Section 3 表格顺序。Figure 2(a)
只画 sealed-confirmed operating point，不构造未定义的 capacity error bar；
confirmation success rate 和 Wilson interval 放入 accompanying table。Timing panels 使用 Section 10.4 的
dataset-level bootstrap interval，并且只画 `timing_status=complete` 且 `successful_datasets=5` 的点。任何
confirmation-failed、out-of-grid、timeout/OOM 或不完整 timing 点的对应可绘制字段固定为 null；plotter 还会独立
复查这些状态，不能仅凭非空数值出图。

绘图按完整有序 `d` grid 检查每个算法；任一注册 `d` 缺失或不可绘制就结束当前 curve/confidence-band segment，
不得跨点连接或外推。连续 segment 分别画 polyline/band；singleton segment 只画 marker，不画插值线或 band。
当 panel 只有一个不同 `d` 时使用非零 log-space x span。每张图写入 source aggregate SHA-256、run id 和
profile manifest SHA-256。
`project_iblt_presentation` 未冻结时允许完成全部原始实验和 aggregate，但 publication gate 保持关闭，不生成
包含 project IBLT 的发布图。

## 14. 验收清单

- [ ] 六种算法共享完全相同的 paired `A/B`。
- [ ] 每个 formal workload 都使用完整 `10^7` 集合。
- [ ] Difference-only discovery equivalence golden tests 全部通过。
- [ ] `candidate_budget.json` 证明每个算法和 `d` 的候选数与 update 上界不超过 Section 8 的固定预算。
- [ ] 六个 protocol profile 与 golden accounting tests 通过。
- [ ] external IBLT 只含序列化接口补丁且 `N_HASH=4`。
- [ ] project IBLT 独立成曲线且核心逻辑未改。
- [ ] `project_iblt_presentation` 已冻结，标题、图注和 output filenames 与枚举分支一致。
- [ ] 只有 cell/resource quantity 进入 search，语义参数已冻结。
- [ ] 每个 searched point 只有一次 sealed confirmation。
- [ ] process error 不进入概率统计；confirmation timeout/OOM 不可能产生 `confirmed`。
- [ ] Rateless percentile 固定为 `q[90]`，confirmation 失败后不增加 cap。
- [ ] `state_bits+control_bits=total_payload_bits` 与实际 wire bytes 相等。
- [ ] Wrapper payload bytes 固定为 0；CPISync 只保留上游 transcript control。
- [ ] 主 timer 是 sender、transfer copy 与 receiver CPU 之和，CPISync 使用顺序 transcript mode。
- [ ] minisketch direction classification 计入 decode CPU，Bob membership-index 构造不计时。
- [ ] residual hash 和其他审计 artifact 工作全部位于 timer 外。
- [ ] 每个非资源受限 timing point 均为 `attempted=failed+successful` 且 `successful=5`，失败 attempt 不进入耗时。
- [ ] Figure 2(a) 只含 confirmed 点，Figure 2(b)(c) 只含完整 5-success timing 点。
- [ ] 所有 output 与有方向 ground truth 精确相等。
- [ ] `C/D` artifact 与 Figure 1(b)(c) holdout hash 已冻结。
- [ ] 未读取 `/root/XYZ-Sketch` 的任何旧文件、数据或结果。

Protocol implementation gate 通过后才能实现 wrapper；全部验收完成且 implementation audit 为 `pass` 后，
Figure 2 才能进入 formal-run 阶段。
