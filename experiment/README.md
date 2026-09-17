# XYZ-Sketch 论文实验复现总方案

> 状态更新（2026-09-16）：本目录已包含完整实验实现和最终选用的图表。
> Figure 1(a) 最终 dense run 为 627 个点、62,700 trials；Figure 1(b)(c)
> 已完成参数冻结和 holdout；Figure 2 已完成 v4 最终汇总与出图。
> Figure 2 的 `complete` 表示流程结束，MiniSketch/CPISync 的部分大规模点仍受资源限制。
> 下文保留最初的实验设计；Figure 2 的最终口径以 `figure-2/V4_EXTENSION_PROTOCOL.md`
> 和最终 aggregate 为准。Git 只保存精选小型结果，原始大体量数据保留在本机。
> 构建、结果索引和存档范围见 [REPRODUCING.md](REPRODUCING.md)。

## 1. 总目标

本目录从零复现 `/root/finalpaper.pdf` 的 Figure 1(a)、Figure 1(b)(c) 和 Figure 2。所有数据、参数、
程序与图表均从当前 `/root/XYZ-Sketch-experiment` 重新产生。

硬性边界：

- 不读取或使用 `/root/XYZ-Sketch` 中的旧文件；
- 不使用旧实验脚本、旧结果或旧图表数据；
- 不从论文图片反推或手工拟合结果点；
- 每个图只读取本次 run 的结构化原始结果；
- artifact、代码 commit、配置与图之间通过 SHA-256 建立可追踪关系。

## 2. 目录与职责

```text
experiment/
  README.md                 # 本总方案
  threshold/                # c^peel/c^orient 数学计算与已完成校验
  figure-1bc/README.md      # d<3000 独立再校准与 sealed 双尺度 holdout
  figure-1a/README.md       # 完整 XYZ-Sketch sharp-threshold 曲线
  figure-2/README.md        # 五种论文方法加 project IBLT baseline 的端到端协议
  figure-2/PROTOCOL_PROFILES.md # 六种实现的固定 profile 与 wire format
```

| 模块 | 输入 | 输出 | 当前状态 |
| --- | --- | --- | --- |
| threshold | Appendix A.2 公式 | `validated_thresholds.json` | 代码与全表验证已完成 |
| Figure 1(b)(c) | threshold、`d<3000` calibration、`d>=3000` holdout | 两张 heatmap、`frozen_parameters.json` | 参数 selected，holdout complete，最终 heatmap 已生成 |
| Figure 1(a) | threshold、冻结参数、完整 XYZ-Sketch | 9 条 sharp-threshold 曲线 | reduced-cardinality 62,700-trial dense 与出图已完成 |
| Figure 2 | 冻结参数、共享数据集、六种实现 profile | paper-main/extended presentation、space/update/decode | v4 最终汇总与五算法正文图完成；保留资源受限点状态 |

## 3. 唯一执行顺序

```text
threshold validation
        |
        v
independent C/D recalibration on d<3000
        |
        v
fixed-(d,M) paired relative selection
        |
        v
freeze selected C_cal / gamma_cal / delta / D_cal
        |
        v
sealed Figure 1(b)(c) holdout on d>=3000
        |
        +-------------------------+
        |                         |
        v                         v
Figure 1(a) full implementation  Figure 2 end-to-end comparison
```

Figure 1(b) 与 Figure 1(c) 是同一个 sealed holdout experiment 的两个 scale heatmap，不是两个实验。
两者不参与 `C_cal/gamma_cal` 的选择。`d<3000` 的 calibration 完成相对选择并冻结参数后才解封 Figure 1(b)(c)；
两个 holdout frozen prediction 均达到 0.9 后，Figure 1(a) 与 Figure 2 使用同一份冻结文件开展。

任何下游实验不得自行重新计算、调整或覆盖 `C/D/delta`。

## 4. 全局固定口径

### 4.1 数学与参数

- threshold 直接实现 Appendix A.2，不用模拟估计；
- `delta=0.1`，语义为目标失败率；
- 先校准 `C_cal` 和可识别组合量
  `gamma_cal=D_cal/log(1/delta)^(1/3)`；
- `D_cal=gamma_cal*log(1/delta)^(1/3)`；
- `z=floor(z_raw+0.5)`；
- `SC-naive` 使用 `a=0`；
- `SC-circular` 使用 `a=C_cal*c^peel/c^orient`；
- hash-location de-duplication 开启。

论文报告的 `C≈0.276,D≈0.5` 仅作为校准结果的外部对照，不参与候选选择或正式运行。

### 4.2 正式集合

Figure 2 的正式 trial 以及论文原始 Figure 1(a) 设置为：

- universe 为 `F_998244353 \ {0}`；
- `|A|=|B|=10^7`；
- 差异在两个方向均分；
- 使用 Floyd sampling 无放回生成唯一元素；
- Alice/Bob insertion order 独立打乱；
- Figure 2 sealed confirmation/timing 不用 difference-only workload 替代。

Figure 1(a) 按 revision 决策使用 `|A|=|B|=2d=20,000`，公共部分 `15,000`，两侧独有各 `5,000`；
仍完整编码双方集合，不使用 difference-only workload。该图必须标注 reduced-cardinality revision。

Figure 2 的 resource discovery 只负责选择资源量，按其 README 使用 difference-only workload。该优化必须先
通过 full-set subtraction 与 difference-only residual 的 byte/state equivalence golden tests，且 discovery
数据不进入正式图表。

Figure 1(b)(c) 是理想 hypergraph experiment，只生成 `d` 条 edge，不构造完整集合。

### 4.3 概率与统计

- probability curve 或 heatmap 每个正式点 100 trials；
- 目标 success rate 为 0.9；
- Figure 1(b)(c) v3 calibration 是固定 `(d,M)` 的相对候选选择，不用 0.9 作为候选通过门；
- 同一比较组使用 paired datasets/edges；
- 报告 point rate 与 Wilson 95% interval；
- search/discovery、holdout、下游 confirmation/validation、timing 使用隔离 seed domain；
- 不合并不同统计角色的 trials；
- 不删除非单调点或失败点。

### 4.4 通信量

\[
\mathcal R=\frac{\text{actual serialized algorithm payload bits}}{30d}.
\]

统一使用 session model B。每个算法都发送规范的 protocol envelope 和参数 header；固定 sketch 统计发送方
state 与 header，interactive protocol 统计双方全部 state/control payload。排除 TCP/IP、日志和 dataset
manifest，包含算法必需 metadata、长度、counter、checksum 与 padding。所有结果分别报告
`state_bits,control_bits,total_payload_bits`，且 `R=total_payload_bits/(30d)`。禁止用对象内存或理论 capacity
替代实际 wire buffer。

### 4.5 Seed 派生

全局 `base_seed=114514`。每个实验按各自 README 定义的 canonical seed string 取 SHA-256 前 64 bit。
所有 raw row 保存 `base_seed`、domain tag、trial index 和派生 seed。

## 5. Artifact 状态机

Protocol 与 implementation audit 分开。文档状态：

```text
protocol_planned -> protocol_audited
                 \-> protocol_failed
```

实现与正式运行状态：

```text
implementation_planned -> implemented -> smoke_validated -> implementation_audited
                                                       \-> implementation_failed
implementation_audited -> formal_running -> complete -> audited
                                      \-> failed
```

Calibration 额外包含：

```text
coarse_complete -> fine_running -> discovery_complete -> selected
                                   \-> relative_search_boundary
```

规则：

- `failed`、历史 `confirmation_failed` 或 `relative_search_boundary` artifact 保留，不覆盖；
- 只有确认实现错误并作废整个 run 后，修复程序才能创建新 run id；
- `frozen_parameters.json` 不原地修改；
- 图表只读取 `complete` artifact；
- 独立审计通过后才标记 `audited`。

## 6. Run identity 与 manifest

Run id 固定格式：

```text
<experiment>-<UTC timestamp>-<git short sha>-<config sha prefix>
```

每个 run directory 必须包含：

- canonical `run_config.json`；
- Git commit 与 dirty-worktree diff hash；
- build manifest；
- environment manifest；
- raw trials；
- aggregate results；
- errors log；
- source manifest；
- 输入与输出 SHA-256。

JSON canonicalization 使用 UTF-8、sorted keys、无 NaN/Infinity。config SHA-256 基于 canonical JSON bytes。

## 7. 模块启动门

### 7.1 Threshold -> Figure 1(b)(c)

启动 Figure 1(b)(c) 前验证：

- `threshold/VALIDATION.md` 显示 6 tests passed；
- `validated_thresholds.json` 含 48 entries；
- 最大 peel residual 为 `2.4313884239290928e-14`；
- 最大 orient residual 为 `1.3500311979441904e-13`；
- 文件 SHA-256 为
  `ef3f0c89d96ab326ed5c33340210b37033e47b033e9f124811cce7c80ef83b87`。

### 7.2 Figure 1(a) formal-run gate

下游启动门：

- 所有 calibration data 都满足 `d<3000`；
- 每个 calibration `d` 的宽 `M` grid 同时覆盖 global-zero prefix、transition 和 global-one suffix；
- calibration 固定点相对目标和 tie-breaking 未改变；
- C 覆盖全部合法网格，selected gamma 距已测试 gamma 上界至少 0.050；
- `delta=0.1`；
- `C_cal,gamma_cal,D_cal,a_cal` 可从 raw data 重算；
- `frozen_parameters.json` status 为 `selected`；
- Figure 1(b)(c) 在冻结后才解封且未反馈修改参数；
- Figure 1(b)(c) 两个 frozen prediction 均达到 0.9；
- artifact 输入 SHA-256 完整。

任一条件不满足，Figure 1(a) 不生成 formal scan manifest。

### 7.3 Figure 2 两级 gate

Figure 2 protocol implementation gate 只要求协议文档完整且独立协议复审为 `pass`。通过后允许实现 wrapper、
允许的 external IBLT patch、golden/equivalence tests 和 smoke tests，不允许 formal trial。

Figure 2 formal-run gate 另要求 Section 7.2 的 calibration/holdout 条件、补丁/build/profile hash、golden 与
equivalence tests、capability checks、`candidate_budget.json`、dry-run manifest 和独立 implementation audit
全部通过。详细状态机以 `figure-2/README.md` Section 1 为准。

## 8. 分实验文档

### 8.1 Threshold

阅读：`threshold/README.md` 与 `threshold/VALIDATION.md`。

审计重点：Poisson tail 数值稳定性、临界方程、特殊点 `(2,1)`、Table 3 全表匹配和输出 hash。

### 8.2 Figure 1(b)(c)

阅读：`figure-1bc/README.md`。

审计重点：`d<3000` training 与 `d>=3000` holdout 隔离、宽 `M` bracket、ideal simulator 与当前 hash
离散规则一致性、固定 `(d,M)` paired relative selection、完整合法 C 轴、大范围 adaptive D 轴和冻结 artifact。

### 8.3 Figure 1(a)

阅读：`figure-1a/README.md`。

审计重点：三组 `(k,ell)`、iid/naive/circular 映射、完整 D-RFR 路径、revision `2d` workload、实际 30-bit
serialization、M scan、精确双向成功判据和 9 条曲线。

### 8.4 Figure 2

阅读：`figure-2/README.md` 与 `figure-2/PROTOCOL_PROFILES.md`。

审计重点：六种算法代码来源、固定语义 profile、只搜索资源量、单次 sealed confirmation、协议级 bit
accounting、方向恢复、双方 CPU timer 边界、resource-limit 处理和三 panel 数据来源。

## 9. 独立审计流程

审计 agent 按以下顺序工作：

1. 只读审计四份 README 和 threshold code，不修改文件。
2. 检查论文 section/figure 引用是否支持文档中的每个固定事实。
3. 检查跨文档的 `d,k,ell,C,D,delta,a,z` 和 trial 口径一致。
4. 检查每个公式、单位和归一化分母。
5. 检查 calibration 是否存在 information leakage 或事后选择。
6. 检查 Figure 1(a)/2 是否只能读取冻结参数。
7. 检查第三方算法比较是否改变问题定义或漏算通信/time。
8. 按严重性输出 findings，并引用具体文件行号。

审计结论只允许：

- `pass`：无阻断问题；
- `pass_with_nonblocking_findings`：只有不改变实验含义的问题；
- `fail`：公式、参数、成功判据、数据、统计、通信或依赖关系存在阻断问题。

所有 finding 在实现前关闭；关闭方式是修改 README 并记录 decision log，不在实验代码中静默绕过。

## 10. 实现阶段的变更纪律

- README 是实验协议的 authoritative source；
- 实现不能引入 README 未定义的参数默认值；
- CLI default 必须逐项等于 README；
- dry-run 先生成完整 scan manifest，由人工和审计 agent 复核；
- smoke test 使用独立 run id，不进入正式 aggregate；
- 正式运行开始后锁定代码 commit 和 config hash；
- 运行中断只允许从已原子落盘的完整 point 继续；
- 任何算法错误修复都会使该 commit 下全部正式点失效。

## 11. 当前进度

| 工作项 | 状态 |
| --- | --- |
| 论文 37 页阅读与实验定义提取 | 完成 |
| threshold 计算代码 | 完成 |
| Appendix Table 3 全表校验 | 完成 |
| Figure 1(a) README | 完成 |
| Figure 1(b)(c) README | 完成 |
| Figure 2 README | 完成 |
| 首轮独立文档审计 | `fail`，findings 已关闭 |
| 第二轮独立文档审计 | `fail`，除 project IBLT 展示位置外正在本轮关闭 |
| Figure 1(b)(c) simulator 实现 | 未开始 |
| Figure 1(a) runner 实现 | 未开始 |
| Figure 2 wrappers 实现 | 未开始 |
| 正式实验运行 | 未开始 |
