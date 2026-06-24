# 实验规划说明

本文档把当前 `TODO.md` 中的事项整理成下一阶段实验工作的执行规划。它只做规划，不涉及具体实现：重点说明应该测什么、如何组织工作，以及在重写论文实验部分前应该产出哪些材料。

## 目标

下一阶段实验应该从四个方向增强说服力：

1. 更细致地覆盖 `d`、`l`、`k` 参数空间。
2. 直接比较带 spatial coupling 和不带 spatial coupling 的 XYZ-Sketch。
3. 展示 spatial coupling 参数 `z` 的敏感性，避免让 `z` 看起来像没有解释的 magic parameter。
4. 在可行的情况下加入更多外部 baseline，而不仅是当前的 IBLT 和 minisketch。

最后可以选择性地加入一个偏应用侧的实验，例如 Git repository snapshot reconciliation，用来展示 practical relevance。

## 当前基础

仓库里已经有：

- `XYZ-v1`：基于多项式和 RFR 的版本。
- `XYZ-v2`：基于 multivariate cell 的版本，当前默认使用 spatial coupling。
- `IBLT`：IBLT baseline。
- `finalResult.txt`：已有的时间和通信量结果。

目前主要缺的不是 XYZ-v2 核心算法，而是系统化的实验框架：参数扫描、重复试验、结构化输出，以及可直接用于论文的图表。

## 工作包 1：`d`、`l`、`k` 参数扫描

### 目的

测量主要算法参数变化时，通信量、编码时间、解码时间和成功率如何变化。

### 建议扫描范围

`d` 建议采用若干对数尺度取值，例如：

- `10`、`30`、`100`、`300`、`1,000`、`3,000`
- `10,000`、`30,000`、`100,000`、`300,000`
- 如果机器能够承受，再加入 `1,000,000`

`l` 建议取一小组值：

- `2`、`3`、`4`、`6`、`8`、`10`、`16`、`20`

`k` 建议取：

- `2`、`3`、`4`

每组配置不要只跑一次，而应该跑多次。建议大规模配置跑 `30` 次，小中规模配置跑 `100` 次。

### 记录指标

至少记录：

- `d`
- `l`
- `k`
- `M`
- `z`
- spatial coupling 模式
- 总试验次数
- 解码成功次数
- 成功率
- 平均编码时间
- 平均解码时间
- 编码时间中位数
- 解码时间中位数
- 通信量 bit 数
- 归一化通信量，例如 `bits / (d * 32)` 或 `C / d`

### 预期产出

该工作包应该产出 CSV 或 JSONL 结果文件，后续可以转成论文表格和图。

## 工作包 2：Spatial Coupling vs Non-Spatial Coupling

### 目的

单独隔离 spatial coupling 的收益，让 reviewer 能清楚看到性能提升不是由其他参数选择造成的。

### 设计

做成成对实验：

- 使用 `SpatialCoupling` 的 XYZ-v2。
- 使用 `RandomHash` 的 XYZ-v2。

在可行情况下，保持 `d`、`l`、`k`、目标通信量和试验次数一致。

对每组 `d, l, k`，搜索达到目标成功率所需的最小通信量。建议目标包括：

- `50%` 成功率，用于阈值型图。
- `95%` 或 `99%` 成功率，用于实际性能型图。

### 记录指标

记录：

- 达到目标成功率所需的最小 `C / d`
- 对应配置下的编码和解码时间
- 如果能统计，记录失败模式

### 预期产出

该工作包应该产出一张表或图，对比 spatial coupling 和 non-spatial coupling 的 `C / d`。这很可能是最重要的新实验之一。

## 工作包 3：`z` 敏感性实验

### 目的

解释 `z` 如何影响性能，避免让它看起来像隐藏的 magic parameter。

### 设计

固定若干代表性的 `d`、`l`、`k`，然后扫描 `z`。

建议固定配置：

- `k = 2`
- `l = 6`
- 如果可行，`d` 取 `{10,000, 100,000, 1,000,000}`

建议 `z` 取值：

- `0`，在适用时作为无 coupling 或近似无 coupling 的参考
- `1`、`2`、`4`、`8`、`16`、`25`、`32`、`64`
- `M^(1/3) / 3` 启发式附近的若干值

### 记录指标

记录：

- 成功率
- 通信量
- 编码和解码时间
- `RangeLength = M / (z + 1)`

### 预期产出

建议画图：x 轴是 `z`，y 轴可以是成功率或最小 `C / d`。如果数据支持，论文中应强调 `z` 有一个较宽的可用范围，而不是只有单点最优。

## 工作包 4：额外 Baseline

### 目的

加强与其他实用 set reconciliation 方法的对比。

### 候选 Baseline

TODO 中提到的候选包括：

- Parity Bitmap Sketch，对应论文 "Space- and Computationally-Efficient Set Reconciliation via Parity Bitmap Sketch"。
- Practical Rateless Set Reconciliation。

### 推荐策略

除非必要，不建议从零开始重写这些方法。优先检查是否有公开实现，以及许可证是否允许用于实验。

对每个候选方法：

1. 寻找实现或 artifact。
2. 确认它的输入格式和算法假设。
3. 尽可能复用当前 XYZ-v2 的 synthetic dataset generator。
4. 测量相同指标：通信量、编码时间、解码时间、成功率。
5. 明确记录假设不完全一致的地方。

### 风险

该工作包可能比较耗时，因为外部代码经常存在构建问题或假设不兼容。它价值很高，但不应该阻塞 XYZ-Sketch 核心实验的更新。

## 工作包 5：应用侧实验

这是可选项，应在核心实验完成之后再开始。

### 候选：Git Repository Snapshot Reconciliation

目标是构造一个真实感较强的 workload：两个 snapshot 大部分 object ID 相同，只有少量差异。

可能做法：

1. 选择一个或多个公开 Git 仓库。
2. 从两个相近 snapshot 中提取 commit、tree 或 blob object ID。
3. 用确定性方式把 object ID 映射到 32-bit field element。
4. 在这些集合上运行 XYZ-v2、IBLT 和已有 baseline。
5. 报告通信量、运行时间，以及真实 symmetric difference size。

### 注意

该实验的作用是展示 practical relevance，而不是替代受控 synthetic experiments。它更适合作为 case study。

## 实验框架与输出建议

在跑大规模实验前，建议先给现有代码加一层小型实验框架。

推荐输出格式：

```text
algorithm,d,l,k,M,z,mode,trials,successes,success_rate,encode_avg_s,decode_avg_s,encode_median_s,decode_median_s,bits,C_over_d,seed
```

为了可复现性，使用确定性 seed；但不同 trial 应允许 seed 变化。

推荐产出：

- 原始 CSV 或 JSONL 结果。
- 简短 README，说明每个实验如何运行。
- 生成表格和图的脚本。
- 最终可放入论文的图表。

## 建议优先级

1. 建立结构化实验框架。
2. 对 XYZ-v2 跑 `d/l/k` 参数扫描。
3. 跑 spatial coupling vs non-spatial coupling。
4. 跑 `z` 敏感性实验。
5. 如果有合适公开实现，加入外部 baseline。
6. 加入可选的应用侧实验。
7. 基于新结果重写 experiment section。

## 重写实验部分时应回答的问题

重写后的实验部分应该清楚回答：

- XYZ-v2 距离理论通信目标有多近？
- Spatial coupling 到底带来了多少收益？
- 方法对 `z` 有多敏感？
- 与 IBLT、minisketch 以及新增 baseline 相比，运行时间代价如何？
- 实践中应该如何选择参数？
- XYZ-Sketch 的优势在哪里，tradeoff 又在哪里？
