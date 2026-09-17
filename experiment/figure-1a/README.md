# Figure 1(a) 从零复现实验方案

Protocol version：`figure1a-reduced-v1`。

## 1. 文档目的与边界

本文档给出复现 `finalpaper.pdf` 中 Figure 1(a) 的完整实验设计与已冻结执行口径。当前
`figure1a-reduced-v1` 已完成 coarse、100-trial dense scan 和确定性出图。

复现工作遵循以下边界：

- 论文依据仅为 `/root/finalpaper.pdf`。
- 实现依据仅为 `/root/XYZ-Sketch-experiment` 中当前代码。
- 不读取或使用 `/root/XYZ-Sketch` 中的旧文件。
- 不使用旧实验脚本、旧结果或旧图表数据作为输入。
- 最终目标是从原始 trial 重新生成一张结构和含义与 Figure 1(a) 相同的图，而不是拟合或描摹论文图片。

> **执行依赖（2026-07-15）**：按 `../figure-1bc/README.md` 只使用 `d<3000` 的 training data
> 独立产生并冻结 `C_cal/D_cal`，再运行 sealed Figure 1(b)(c) holdout；`delta` 固定为 `0.1`。
> `z` 的整数化规则、`SC-naive` 的 `a=0` 口径已经确认。正式 trial 的集合基数按 Section 16.4
> 的 revision 决策固定为 `|A|=|B|=2d`。
> Figure 1(a) 的正式 manifest 只读取
> `../figure-1bc/results/calibration/frozen_parameters.json`，不直接使用论文报告常数。

论文中最相关的位置如下：

- Section 2.2：`ell`-peelability、`ell`-orientability 和阈值定义。
- Section 3.1：XYZ-Sketch、high-capacity cell 和全局 peeling。
- Section 3.2：D-RFR、纯 cell 恢复和验证。
- Section 3.3：naive spatial coupling 与 circular trick。
- Section 4.4：`a` 和 `z` 的启发式选择。
- Section 6.1：数据、trial 数、成功判据和通信量归一化。
- Section 6.2：Figure 1(a) 的结论和校准常数。
- Appendix A.2：`c^peel` 和 `c^orient` 的计算公式及数值表。
- Appendix E：更新、减法、cell 解码和全局 peeling 的伪代码。

## 2. Figure 1(a) 的实验目标

Figure 1(a) 不是运行时间实验。它验证两个结构性结论：

1. 当 sketch 通信量逐渐增加时，完整 XYZ-Sketch 的解码成功率是否出现尖锐转变？
2. circular spatial coupling 是否能把成功率转变移动到更低的通信量位置？

图中固定 `d = 10,000`，分为三个 panel：

| Panel | `(k, ell)` | 含义 |
| --- | ---: | --- |
| 左 | `(2, 3)` | 每个元素触碰 2 个 cell，每个纯 cell 最多恢复 3 个差异元素 |
| 中 | `(2, 6)` | 每个元素触碰 2 个 cell，每个纯 cell 最多恢复 6 个差异元素 |
| 右 | `(3, 4)` | 每个元素触碰 3 个 cell，每个纯 cell 最多恢复 4 个差异元素 |

每个 panel 包含三条曲线：

| 图例 | 本文名称 | Placement 定义 |
| --- | --- | --- |
| `iid` | 独立全表哈希 | 每个元素的 `k` 个位置独立分布在全部 `M` 个 cell 上 |
| `SC-naive` | terminated/naive spatial coupling | `k` 个位置落在同一个不回绕的局部窗口中 |
| `SC-circular` | circular spatial coupling | 局部窗口允许从末尾回绕到开头，anchor 范围由 `a` 控制 |

横轴和纵轴分别为：

\[
  x = \mathcal R = \frac{\text{total on-wire payload bits}}{30d},
  \qquad
  y = \frac{\text{successful trials}}{\text{all trials}}.
\]

## 3. 论文明确给出的固定设置

论文原始 Figure 1(a) 报告以下参数；本项目除集合基数外保持这些参数：

| 参数 | 值 | 来源或解释 |
| --- | ---: | --- |
| 有限域 | `F_998244353` | Section 6.1 |
| `w` | `30` bit | `ceil(log2(998244353)) = 30` |
| `d` | `10,000` | Figure 1 图注 |
| `cardinality(A)` | `10,000,000` | Section 6.1 原始设置；本 revision 改为 `2d` |
| `cardinality(B)` | `10,000,000` | Section 6.1 原始设置；本 revision 改为 `2d` |
| `cardinality(A \ B)` | `5,000` | 两个集合等大且差异均分 |
| `cardinality(B \ A)` | `5,000` | 两个集合等大且差异均分 |
| 每个点的 trial 数 | `100` | Section 6.1 |
| 目标成功率 | `0.9` | Section 6.1 |
| `C` | 约 `0.276` | Section 6.2 的小规模校准结果 |
| `D` | 约 `0.5` | Section 6.2 的小规模校准结果 |

论文报告的 `C≈0.276` 和 `D≈0.5` 只作为外部对照值。本次 from-scratch 复现必须先执行独立的
小规模校准，并将重新得到的 `C_cal/D_cal` 用于 Figure 1(a)，见 Section 16。

本项目 revision 固定 `|A|=|B|=2d=20,000` 且 `d=10,000`，每个正式 trial 构造为：

- 公共部分 `S`：`15,000` 个元素；
- Alice 独有部分 `D_A`：`5,000` 个元素；
- Bob 独有部分 `D_B`：`5,000` 个元素；
- `A = S union D_A`；
- `B = S union D_B`。

三部分必须两两不交，并且所有元素都属于 `F_998244353 \ {0}`。

## 4. 当前实现与实验概念的映射

正式写实验程序前，需要按下面的映射使用当前实现，不能另外实现一个理想 hypergraph 模拟器。
论文明确说明 Figure 1(a) 使用完整 C++ XYZ-Sketch，而不是 Figure 1(b)(c) 的 ideal-cell simulator。

### 4.1 完整解码路径

每个 trial 必须走完以下路径：

1. 用相同配置初始化 Alice 和 Bob 的 XYZ-Sketch。
2. 将 `A` 的所有元素按随机顺序插入 Alice sketch。
3. 将 `B` 的所有元素按独立随机顺序插入 Bob sketch。
4. 序列化 Alice sketch，并按相同全局参数反序列化。
5. 用反序列化后的 Alice sketch 减去 Bob sketch。
6. 对 residual sketch 运行当前 D-RFR cell recovery。
7. 对候选纯 cell 运行当前 rehash verification。
8. 运行全局 `ell`-peeling，直到 residual 为空或无法继续。
9. 将结果分别与真实 `A \ B`、`B \ A` 比较。

当前代码职责如下：

| 当前文件 | Figure 1(a) 中的职责 |
| --- | --- |
| `XYZ-Sketch/XYZSketch.cpp` | cell 更新、sketch 减法、D-RFR 调用、rehash verification、全局 peeling、序列化 |
| `XYZ-Sketch/hash.cpp` | naive/circular placement、MurmurHash 位置计算、`a` 和 `z` 的离散化 |
| `XYZ-Sketch/tools.cpp` | 有限域、多项式、RFR 和 root finding |
| `XYZ-Sketch/murmur3.cc` | placement 哈希 |

### 4.2 三种 placement 在当前实现中的表示

当前 hash API 只有 `NAIVE` 和 `CIRCULAR` 两个显式 mode。实验程序将来应按以下方式映射：

| 曲线 | 当前 hash mode | `z` | `a` |
| --- | --- | ---: | ---: |
| `iid` | `NAIVE` | `0` | `0` |
| `SC-naive` | `NAIVE` | 按 Section 7 计算 | `0` |
| `SC-circular` | `CIRCULAR` | 按 Section 7 计算 | `a_{k,ell}` |

当 `NAIVE` 使用 `z=0` 时，`RangeLength=M` 且 anchor 只能为 0，当前位置退化为
`MurmurHash(x, i) mod M`。因此它可作为当前实现中的 iid 全表 placement。

### 4.3 必须锁定的实现选项

- 开启 hash-location de-duplication。论文 Section 3.1.2 明确写明删除重复位置。
- 不额外加入论文未在当前 cell state 中实现的 fingerprint 字段；当前 cell 只有 count 和 polynomial。
- 保留 rehash verification，不能只根据 residual degree 判断纯 cell。
- Alice、Bob 和 decoder 必须共享同一组 `k, ell, M, a, z` 和哈希约定。
- 使用 Section 8 的 canonical parameter header 传输 `k,ell,M,a,z` 和 placement flags；接收端只从该 header
  恢复配置，不从进程外静默注入参数。

## 5. `c^peel` 与 `c^orient` 的计算规范

这两个值不能从图中反推，也不应手工抄成缺少来源的 magic constants。阈值计算器直接实现
Appendix A.2 的公式，并用论文表格做数值验证。

定义 Poisson 上尾：

\[
  Q(\xi,r) = \Pr[\operatorname{Pois}(\xi) \ge r].
\]

除 `(k,ell)=(2,1)` 外，peelability threshold 为：

\[
  c^{\mathrm{peel}}_{k,\ell}
  = \min_{\xi>0}
  \frac{\xi}{k Q(\xi,\ell)^{k-1}}.
\]

最小点也可通过下面的方程校验：

\[
  Q(\xi,\ell)
  = (k-1)\xi\Pr[\operatorname{Pois}(\xi)=\ell-1].
\]

orientability threshold 先求解：

\[
  k\ell
  = \xi^* \frac{Q(\xi^*,\ell)}{Q(\xi^*,\ell+1)},
\]

再计算：

\[
  c^{\mathrm{orient}}_{k,\ell}
  = \frac{\xi^*}{k Q(\xi^*,\ell)^{k-1}}.
\]

### 5.1 数值算法

当前阈值计算器必须满足以下规范：

1. 使用 IEEE 754 double precision。
2. Poisson tail 通过稳定的 CDF/tail 实现计算，不用有限样本模拟。
3. `c^peel` 使用一维有界最小化，并用驻点方程做第二次校验。
4. `c^orient` 先扩大区间直到根被夹住，再用二分或 Brent 方法求根。
5. 根和目标函数的收敛误差不高于 `1e-12`。
6. 文本输出小数点后 12 位；进入实验配置时保存完整 double 值。
7. 单元测试必须在四位小数上匹配论文 Appendix Table 3。

### 5.2 三组 operating point 的预期值

| `(k,ell)` | `c^peel` | `c^orient` | `c^peel/c^orient` |
| ---: | ---: | ---: | ---: |
| `(2,3)` | `2.5747013735` | `2.8774628058` | `0.89478` |
| `(2,6)` | `4.9376453624` | `5.9644362395` | `0.82784` |
| `(3,4)` | `2.7467258764` | `3.9970126256` | `0.68719` |

如果计算结果不能匹配上表，必须停止后续实验，先修正阈值计算。

## 6. circular 参数 `a`

论文 Section 4.4.1 给出的规则是：

\[
  a_{k,\ell}
  = C\frac{c^{\mathrm{peel}}_{k,\ell}}
          {c^{\mathrm{orient}}_{k,\ell}},
  \qquad C \approx 0.276.
\]

下表按论文对照值 `C=0.276` 计算，仅用于将独立校准结果与论文报告值比较。正式配置始终使用
`C_cal` 重新计算：

| `(k,ell)` | `a_{k,ell}`（预期） |
| ---: | ---: |
| `(2,3)` | `0.246959779` |
| `(2,6)` | `0.228485990` |
| `(3,4)` | `0.189665736` |

`a` 对一个 `(k,ell)` panel 固定，不随 `M` 或 trial 改变。`iid` 和 `SC-naive` 不使用这个值，
应显式记录为 `a=0`，避免结果文件含义不清。

## 7. coupling 参数 `z`

论文 Section 4.4.2 给出的规则是：

\[
  z_{k,\ell}
  = D(1-a_{k,\ell})^{2/3}
    \left(\frac{M}{\log(1/\delta)}\right)^{1/3},
  \qquad D \approx 0.5.
\]

实验程序的 `z` 是整数，因此每个结果 row 必须同时保存：

- 公式得到的浮点 `z_raw`；
- 采用的取整规则；
- 实际传给实现的整数 `z`。

`delta` 固定为 `0.1`，对应目标失败率 0.1。对 `z_raw` 按 `floor(z_raw+0.5)` 四舍五入到最近整数，
且该规则在整个实验中保持不变。

对 `SC-circular`，公式中的 `a` 使用 Section 6 的 `a_{k,ell}`。对 `SC-naive`，将它视为
`a=0` 的 terminated placement，并在同一公式中代入 `a=0`。`iid` 固定 `z=0`。

因为公式含 `M`，正式扫描每个 `M` 时都应重新计算一次 `z_raw` 和整数 `z`，不能只在曲线中心
计算一次后静默固定。若一个扫描区间内取整后的 `z` 恰好不变，结果文件仍应逐 row 记录它。

## 8. 通信量的精确计算

当前实现中每个 cell state 序列化：

- `ell` 个有限域系数，每个系数 30 bit；
- 一个模 `2ell+1` 的 count，需要 `ceil(log2(2ell+1))` bit；
- 当前没有序列化 fingerprint。

因此：

\[
  b_{cell}(\ell)
  = 30\ell + \lceil\log_2(2\ell+1)\rceil,
\]

\[
  \text{logical_state_bits}
  = M b_{cell}(\ell),
  \qquad
  \text{state_bits}=8\left\lceil\frac{M b_{cell}(\ell)}{8}\right\rceil.
\]

三个 panel 的 cell bit 数为：

| `ell` | polynomial bits | count bits | bits/cell |
| ---: | ---: | ---: | ---: |
| `3` | `90` | `3` | `93` |
| `6` | `180` | `4` | `184` |
| `4` | `120` | `4` | `124` |

统一使用 session model B。每个 message 采用 `../figure-2/PROTOCOL_PROFILES.md` Section 3 的 24-byte
公共 envelope，以及 Section 4 的 20-byte XYZ parameter section。Envelope flags 记录
`iid/naive/circular` label；parameter section 记录实际 core mode，其中 iid 使用 naive core mode 与
`a=0,z=0`，SC-naive 使用 naive core mode，SC-circular 使用 circular core mode。

因此：

\[
  control\_bits=(24+20)\times 8=352,
  \qquad
  total\_payload\_bits=state\_bits+352,
\]

\[
  \mathcal R=\frac{total\_payload\_bits}{30d}.
\]

正式结果中的 `logical_state_bits` 必须等于实际 `to_bitstring()` 长度，`state_bits` 必须等于真实 wire
buffer 的 byte-aligned 长度，`total_payload_bits` 必须等于发送 buffer 总长度。任一断言不一致时配置无效。
不要用 C++ 对象内存占用、`sizeof(Cell)` 或整数容器大小替代 wire 长度。

Implementation gate 的 `M=2` golden accounting 固定为：

| `(k,ell)` | logical state | wire state | control | total |
| ---: | ---: | ---: | ---: | ---: |
| `(2,3)` | 186 | 192 | 352 | 544 bits |
| `(2,6)` | 368 | 368 | 352 | 720 bits |
| `(3,4)` | 248 | 248 | 352 | 600 bits |

## 9. `M` 的初始中心与扫描策略

Figure 1(a) 的自变量本质上是 `M`，绘图时再转换成 `R`。不能只测达到 90% 的一个点；每条曲线
必须同时包含低成功、转变和高成功区域。

### 9.1 理论中心只用于开始搜索

对 iid placement，初始中心取：

\[
  M_0^{iid} = \left\lceil\frac{d}{c^{peel}_{k,ell}}\right\rceil.
\]

对 naive coupling，用论文 Lemma 11 的长度损失作初始估计：

\[
  M_0^{naive}
  = \left\lceil\frac{z+1}{z}\frac{d}{c^{orient}_{k,ell}}\right\rceil.
\]

对 circular placement，用 Section 4.4.2 的全局密度关系作初始估计：

\[
  M_0^{circular}
  = \left\lceil\frac{z+1}{z+a}\frac{d}{c^{orient}_{k,ell}}\right\rceil.
\]

由于 `z` 又依赖 `M`，对两个 spatial mode 迭代计算 `M -> z -> M`，直到整数 `M` 不再改变。

下表按论文对照值 `C=0.276`、`D=0.5`、`delta=0.1` 和最近整数取整规则计算，只用于对照。
正式 scan manifest 必须使用冻结的 `C_cal/D_cal` 重新生成：

| `(k,ell)` | `M0 iid` | `M0 naive` | `M0 circular` |
| ---: | ---: | ---: | ---: |
| `(2,3)` | `3884` | `4055` | `3975` |
| `(2,6)` | `2026` | `2012` | `1983` |
| `(3,4)` | `3641` | `3003` | `2893` |

这些数不是预期答案，也不能作为图中的阈值线；它们只是 coarse scan 的起点。有限长度、哈希离散化、
纯 cell 误判和 root finding 都可能移动实际转变位置。

### 9.2 两阶段扫描

第一阶段为 coarse scan：

1. 以各自的 `M0` 为中心，先扫描 `M0` 的正负 15%。
2. coarse 横轴间隔控制在 `Delta R <= 0.01`。
3. 每个 coarse 点先运行 20 个独立 trial。
4. 找到最大的 `M` 满足 `success_rate <= 0.05`，以及最小的后续 `M` 满足
   `success_rate >= 0.95`；二者构成需要加密的局部转变区间。
5. 如果任一端不存在，按 10% 的 `M0` 向对应方向扩展，直到两端都出现。

实现固定取下表给出的最大整数步长作为唯一 coarse step。令
`J=ceil(0.15*M0/step)`，初始 grid 为 `M=M0+j*step, j=-J..J`，因此一定包含 `M0` 并至少覆盖正负 15%。
第 `r` 次向外扩展将对应方向覆盖半径增加到 `(0.15+0.10r)M0`，新增点继续与 `M0` 使用同一整数 congruence
class，不改变步长或重测已有点。

按 `d=10,000` 计算，`Delta R <= 0.01` 对应的最大 coarse `M` 步长约为：

| `ell` | 最大 coarse `Delta M` |
| ---: | ---: |
| `3` | `30` |
| `6` | `16` |
| `4` | `24` |

第二阶段为正式 dense scan：

1. 使用 coarse scan 找到的局部转变区间：左端为最大的 `p<=0.05` 点，右端为最小的后续
   `p>=0.95` 点。
2. 两端各增加 5 个 dense step，确保图中能看到平台。
3. dense 横轴间隔控制在 `Delta R <= 0.002`。
4. 每个 dense 点运行论文要求的 100 个独立 trial。
5. 不用 coarse 的 20 个 trial 与正式 100 个 trial 拼接；正式曲线的每个点统计口径必须一致。

固定使用以下 dense `M` 步长：

| `ell` | dense `Delta M` |
| ---: | ---: |
| `3` | `6` |
| `6` | `3` |
| `4` | `4` |

## 10. 每个 trial 的数据生成

### 10.1 唯一性与均匀性

每个正式 trial 都重新生成数据，不能在 100 个 trial 中只改变 insertion order。生成过程应为：

1. 从 `F_998244353 \ {0}` 无放回抽取 `25,000` 个元素。
2. 前 `15,000` 个作为公共部分 `S`。
3. 接下来的 `5,000` 个作为 `D_A`。
4. 最后的 `5,000` 个作为 `D_B`。
5. 分别构造 `A` 和 `B`，然后使用独立 PRNG stream 打乱插入顺序。

无放回抽样固定使用 Floyd sampling 算法，在整数区间 `[0, 998244351]` 上均匀抽取
`25,000` 个互异值，再统一加 1 映射到非零域元素。Floyd sampling 使用
`std::mt19937_64` 和 `std::uniform_int_distribution<uint64_t>`。完成抽样后必须检查范围、非零和
全局唯一性。Floyd 输出使用同一个 dataset RNG 做一次 Fisher-Yates shuffle，再按上述顺序划分三部分；
该规则避免依赖 `unordered_set` iteration order。

### 10.2 随机种子层次

固定公开 `base_seed=114514`。每个具体 seed 定义为字符串
`figure1a|base_seed|phase|k|ell|trial_index|role` 的 SHA-256 摘要前 64 bit。`phase` 固定为
`coarse` 或 `dense`，其中 `role` 分别为：

- dataset identity seed；
- Alice insertion-order seed；
- Bob insertion-order seed；
- decoder/root-finding seed；
- hash-family seed（即使当前实现使用固定 MurmurHash seed，也保留该记录字段）。

Canonical role literals 固定为：

```text
dataset_identity
alice_insertion_order
bob_insertion_order
decoder_root_finding
hash_family
```

摘要前 8 bytes 按 big-endian 解释为 `uint64_t`。Floyd sampling 和双方 shuffle 分别直接用对应 64-bit seed
构造 `std::mt19937_64`。当前 core root finder 使用 32-bit `std::mt19937`；wrapper 将 decoder seed 拆成
`high32,low32`，按该顺序构造 `std::seed_seq{high32,low32}` 后调用全局 root RNG 的 `seed()`。

同一 `phase,k,ell,trial_index` 下所有 `M` 和三种 mode 使用同一组 trial dataset，以形成 paired comparison；
`M/mode` 只改变 sketch 配置。Coarse 与 dense 的 dataset domain 完全隔离，即使 `M` 重合也不得复用 trial。
Dense `M` 列表必须在解封 dense seed domain 前由 coarse artifact 冻结。每个结果 row 记录 `phase`、
`base_seed`、`trial_index` 和所有派生 seed。

## 11. 成功与失败的判定

一个 trial 只有同时满足下列条件才记为成功：

1. decoder 没有返回失败；
2. 恢复的正向集合恰好等于 `A \ B`；
3. 恢复的负向集合恰好等于 `B \ A`；
4. 两个方向均没有重复、遗漏或多余元素；
5. peeling 完成后所有 residual cell 均回到空状态。

不能使用以下弱判据：

- 只比较恢复元素总数是否为 `d`；
- 只比较无方向的 symmetric difference；
- 只要 decoder 没有抛异常就视为成功；
- 只要 ideal hypergraph 可 peel 就视为完整实现成功。

失败固定细分为：

- `decode_failed`：无法继续 peeling 或最终 residual 非空；
- `wrong_alice_only`；
- `wrong_bob_only`；
- `duplicate_output`；
- `serialization_mismatch`；
- `process_error`。

Figure 的 y 值只合并成总成功率，但细分原因用于排查异常。

## 12. 统计方法

对一个固定 `(k,ell,mode,M)`，令 100 个 trial 中成功数为 `s`，则：

\[
  \hat p = s/100.
\]

同时计算 95% Wilson binomial confidence interval。不要使用 `p +/- 1.96 sqrt(p(1-p)/n)` 的普通
正态区间，因为它在 `p` 接近 0 或 1 时表现较差。

需要从 dense scan 提取：

- 第一个 `success_rate >= 0.5` 的 `M` 和 `R`；
- 第一个 `success_rate >= 0.9` 的 `M` 和 `R`；
- 第一个 Wilson 下界 `>=0.9` 的 `M` 和 `R`；
- 从成功率 0.1 到 0.9 的转变宽度；
- 相邻点出现明显非单调下降时的 warning。

有限 trial 下轻微非单调是正常统计噪声，不能删除不符合预期的点。正式 Figure 1(a) 不使用单调
拟合或平滑，直接连接主数据点。

## 13. 结果文件规范

将来实现时，每次正式运行必须写入新的 run directory，不能覆盖之前结果，并保存：

| 文件 | 内容 |
| --- | --- |
| `run_config.json` | 所有参数、seed 派生规则、编译参数和代码 commit |
| `trials.jsonl` | 每个原始 trial 一行 |
| `aggregate.csv` | 每个 `(k,ell,mode,M)` 的聚合统计 |
| `aggregate.jsonl` | 与 CSV 相同但保留完整类型 |
| `environment.txt` | OS、CPU、内存、编译器版本 |
| `errors.log` | 失败进程和异常 |
| `figure1a.svg` | 矢量图 |
| `figure1a.pdf` | 论文插图格式 |
| `figure1a.png` | 人工审阅格式 |
| `source_manifest.md` | 图使用了哪个结果文件及其 SHA-256 |

每条 aggregate row 必须包含：

- `run_id, git_commit, d, k, ell, mode, M`；
- `C, D, delta, a_raw, a, z_raw, z, z_rounding`；
- `set_size_A, set_size_B, difference_A, difference_B`；
- `trials, successes, success_rate, ci_low, ci_high`；
- `logical_state_bits,state_bits,control_bits,total_payload_bits,bits_per_cell,R_w30`；
- `dedup_hashes, fingerprint_enabled, base_seed`；
- `status`。

## 14. 绘图规范

最终图采用一个横向三 panel 布局，panel 顺序固定为 `(2,3)`、`(2,6)`、`(3,4)`。

固定视觉编码：

| mode | 颜色 | 线型 |
| --- | --- | --- |
| iid | 蓝色 | 实线 |
| SC-naive | 红色 | 虚线 |
| SC-circular | 绿色 | 点线 |

绘图要求：

1. x 轴使用实际序列化长度计算的 `R_w30`，不用 `M ell/d` 替代。
2. y 轴固定 `[0,1]`。
3. 显示原始 empirical point，并用线连接相邻 `M`。
4. 以浅色 error bar 或 band 显示 Wilson 95% interval。
5. 在 `y=0.9` 位置画水平参考线。
6. 在每条曲线首次达到 0.9 的 `R` 处画同色竖直点线。
7. 不静默平滑、不删除失败点、不手工移动阈值线。
8. 每个 panel 使用该 panel 全部数据的最小/最大 `R` 各外扩 5% 作为 x 范围，并显示真实刻度。
9. 图注写清 `d=10,000`、每点 100 trials、完整实现、`C/D/delta` 和取整规则。

## 15. 分阶段执行与验收

### 阶段 A：实现前审计

- 验证 `d<3000` calibration artifact、sealed Figure 1(b)(c) holdout 与 confirmation status。
- 验证 `delta=0.1` 和 `D_cal` 换算关系。
- 复核 Section 16 的两项已确认决策。
- 冻结当前 Git commit。
- 确认 sample 能正确恢复两个方向的差异。
- 确认三种 placement 映射和 de-duplication 选项。
- 确认序列化长度断言。

### 阶段 B：阈值与配置验证

- 数值计算三组 `c^peel/c^orient`。
- 在四位小数上匹配 Appendix Table 3。
- 计算并人工复核 `a`。
- 对每个计划 `M` 保存 `z_raw/z`。
- 生成只含配置、不运行 trial 的 scan manifest 供人工批准。

### 阶段 C：最小正确性测试

- 使用很小的 `d` 和少量 trial 验证数据不变量与两个方向的成功判定。
- 分别覆盖 iid、naive、circular。
- 验证 Alice 序列化/反序列化后结果不变。
- 验证失败不会被记为成功。

这一步只检查程序正确性，不能混入正式结果。

### 阶段 D：coarse scan

- 使用 Section 9 的 20-trial 配置找全每条曲线的 0 到 1 转变区间。
- 检查 9 条曲线都有低成功端和高成功端。
- 固化 dense scan 的 `M` 列表并人工批准。

### 阶段 E：正式 dense scan

- 运行 9 个 `(tuple,mode)` shard。
- 每个点 100 个正式 trial。
- 每完成一个点立即原子落盘，支持中断续跑。
- 不因结果不符合预期而重跑或换 seed；只有明确程序错误才能作废 run。

### 阶段 F：统计和出图

- 验证每点恰好 100 个有效 trial。
- 计算成功率与 Wilson interval。
- 生成图和 source manifest。
- 随机抽取 trial 重新解码，确认原始记录可重现。

### 最终验收清单

- [ ] 9 条曲线全部存在。
- [ ] 每条曲线覆盖明显失败区、转变区和明显成功区。
- [ ] 每个正式点恰好 100 个独立 trial。
- [ ] 所有 trial 使用 `d=10,000` 和正确的双向差异。
- [ ] 正式 workload 严格使用 `|A|=|B|=2d=20,000`。
- [ ] `c^peel/c^orient` 匹配论文表格。
- [ ] 独立 `C/D` calibration 已确认，且 `delta=0.1`。
- [ ] `a/z` 可由配置文件重新计算。
- [ ] `state_bits/control_bits/total_payload_bits` 等于实际 wire 长度且满足 cell-bit 断言。
- [ ] 成功判据是精确带方向恢复。
- [ ] 图只读取本次 from-scratch 原始结果。
- [ ] 图、结果和配置均记录代码 commit 与 SHA-256。
- [ ] 没有使用 `/root/XYZ-Sketch` 的旧文件或旧结果。

## 16. 决策记录

### 16.1 独立校准 `C` 和 `D`

论文 Section 6.2 说明作者先在较小实例上校准，得到 `C≈0.276`、`D≈0.5`，再将其固定用于其余实验，
但没有给出校准实例、候选网格、评价函数和 tie-breaking rule。本项目采用
`../figure-1bc/README.md` 定义的 `d<3000` 独立再校准 protocol，重新产生 `C_cal/D_cal`；参数冻结后
Figure 1(b)(c) 只作 sealed holdout，再绘制 Figure 1(a)。

论文报告的 `0.276/0.5` 只用于比较校准结果，不参与候选选择，也不在九条正式曲线中使用。

### 16.2 `delta` 的定义与取值

Section 4.4.2 的 `z` 公式含 `log(1/delta)`，Section 6.1 又给出目标成功率 0.9，但 Figure 1(a) 图注
没有明确说明公式中的代入。本项目固定使用目标失败率口径：`delta=1-0.9=0.1`。Figure 1(b)(c)
先校准可识别组合量 `gamma`，再按
`D_cal=gamma_cal*log(1/delta)^(1/3)` 换算 `D_cal`。

### 16.3 已确认：`z` 离散化与 naive coupling

- 对 `z_raw` 使用 `floor(z_raw+0.5)` 得到整数 `z`。
- `SC-naive` 按 `a=0` 代入同一 `z` 公式。
- `SC-circular` 使用对应的 `a_{k,ell}`。
- `iid` 固定 `a=0,z=0`。

### 16.4 已确认：revision reduced-cardinality workload

- 每个正式 trial 完整编码 `|A|=|B|=2d=20,000` 的两个集合；公共部分为 `15,000`。
- 这不是 difference-only workload；Alice、Bob 仍分别构造、打乱、编码并通过真实 wire subtraction/decode。
- 正式结果使用当前实现的 30-bit 序列化、rehash verification 和启用 de-duplication 的 placement。
- 结果和图注必须标记 `reduced-cardinality revision`，不得声称集合基数仍为论文原始 `10^7`。
- 实现测试必须固定差异元素并改变公共集合大小，验证 subtraction 后 residual state bytes 和带方向 decode 完全一致。

本变更创建新的 `figure1a-reduced-v1` protocol 和 Figure 1(a) run identity。现有 `C_cal/D_cal` 校准只依赖
ideal hypergraph 的 `(d,M,k,ell)`，不读取 Alice/Bob cardinality，因此继续使用同一冻结 calibration artifact，
不重新拟合参数。不同 Figure 1(a) workload 不得在同一次 run 中混用。
