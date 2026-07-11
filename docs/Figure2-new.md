# Figure 2 新实验设计草案

本文档记录我对新 Figure 2 工作逻辑的理解，以及建议如何重写实验代码。

## 1. 目标变化

旧 Figure 2 的逻辑是：

1. 固定一组 `(d,k,l,a,z)`。
2. 对每个 `(a,z)` 单独搜索能达到目标成功率的最小 `M`。
3. heatmap 画的是每个 `(a,z)` 所需的通信量或 `best_M`。

这个流程的问题是：`a,z` 的比较和 `M` 的搜索混在一起。某个 `(a,z)` 看起来更好，可能只是因为它被搜索到了更合适的 `M`，而不是在同一通信预算下真的成功率更高。

新 Figure 2 应该改成：

1. 从已有 Figure 2 结果中提取候选 `M`。
2. 固定 `(d,k,l,M)`。
3. 在同一个固定 `M` 下扫描不同 `(a,z)`。
4. 直接观察每个 `(a,z)` 的模拟成功率。

也就是说，新图的核心问题从“每个 `(a,z)` 需要多大 `M`”改成“给定同样的 `M`，哪个 `(a,z)` 更容易成功”。

## 2. 如何使用已有 Figure 2 结果

已有结果仍然有价值，但只作为 `M` 候选来源使用。

建议从旧的

```text
tests/results/paper_fig2_az_grid/summary.jsonl
```

读取每一行的：

```text
d, k, l, circular_a, z, best_M, status, final_success_rate
```

然后按 `(d,k,l)` 分组，收集该组下面所有非空 `best_M`。这些 `best_M` 是旧实验在不同 `(a,z)` 下找到的阈值附近规模。新实验不再把旧的 `final_success_rate` 当作结论，只把 `best_M` 当成要重新测试的固定预算。

建议输出一个中间文件：

```text
tests/results/paper_fig2_m_candidates/m_candidates.jsonl
tests/results/paper_fig2_m_candidates/m_candidates.csv
```

每行代表一个候选固定规模：

```text
d, k, l, M, source_count, source_a_values, source_z_values, min_source_R_w30, max_source_R_w30
```

其中 `M` 应该去重。比如同一个 `(d,k,l)` 下，多个 `(a,z)` 可能给出同一个 `best_M`，新实验只需要对这个 `M` 跑一次完整 `(a,z)` 网格。

对于旧结果中的 `unresolved`：

- 如果该行仍然有非空 `best_M`，可以保留它作为候选 `M`。因为我们只是在借用它的预算位置，不继承它的成功/失败判断。
- 如果 `best_M` 为空，说明旧搜索没有找到可用预算，建议跳过。
- 后续文档和图注中要说明：旧实验只提供候选 `M`，新结论来自固定 `M` 下重新跑出的模拟成功率。

## 3. 新实验的数据形状

新实验的主表应该是一张固定 `M` 成功率表：

```text
d, k, l, M, circular_a, z, trials, successes, success_rate, ci_low, ci_high, seed
```

每一行表示：

在固定 `d,k,l,M` 下，使用某个 `(a,z)` 的 circular hashing 方式，跑 `trials` 次模拟 peeling，其中成功 `successes` 次。

建议目录：

```text
tests/results/paper_fig2_fixed_m_sim/
  run_config.json
  m_candidates.csv
  raw.jsonl
  summary.csv
  summary.jsonl
  summary.md
```

这里不需要二分搜索 `M`，所以不会有旧脚本里的 `probe/final` 两阶段。每个 `(d,M,a,z)` 只跑一次固定 trial 数。

## 4. 我对模拟实验的理解

`docs/sample.cpp` 做的不是完整 XYZ 解码，而是一个随机超图 peeling 模拟。

完整真实实验路径是：

```text
集合 A/B -> Encode -> sketch 相减 -> PureCellVerify -> Extract -> Decode
```

它包含真实元素、哈希、cell 中的多项式、根查找、代数校验、bitstring 大小等。

新模拟实验只保留最核心的图结构问题：

```text
d 条差异边 -> 每条边落到 k 个桶 -> 桶容量阈值 l -> peeling 能否删除全部边
```

也就是说，模拟实验关心的是：由 `(M,k,l,a,z)` 定义的空间耦合随机超图是否可剥离。它不再真正构造 `XYZSketch`，也不再跑 `PureCellVerify`、多项式重构、根查找或真实集合差分校验。

更严格地说，新模拟仍然会做 peeling 过程，但这个 peeling 只发生在抽象超图上；它不模拟 Alice/Bob 两侧差异的正负号、cell 里的多项式状态、根查找失败、重复根、有限域碰撞或代数 cancellation。因此它给出的应称为 peeling success rate，而不是端到端 decode success rate。

在这个模拟里：

- `d` 是边数，也就是差异元素数量。
- `M` 是桶数，对应现有 `XYZ-v2` 里的 sketch cell 数。
- `k` 是每条边连接的桶数。
- `l` 是一个桶能一次解出的最大局部负载。
- `z` 决定局部窗口长度：

```text
RangeLength = M / (z + 1)
```

- `a` 决定 circular base position 的范围。

现有 `XYZ-v2/hash.cpp` 中 circular 模式的公式是：

```text
shrink = floor(a * RangeLength)
base_range = clamp(M - shrink + 1, 1, M)
base = hash(x, 114514) % base_range
offset_i = hash(x, i) % RangeLength
bucket_i = (base + offset_i) % M
```

`docs/sample.cpp` 里的这行：

```cpp
int now = rng() % (n - len / 3 + 1);
```

可以理解为 `a = 1/3` 时的特例草图；后面的

```cpp
int d = rng() % len, x = (now + d) % n + 1;
```

对应在长度为 `RangeLength` 的局部窗口内取 offset，并用 modulo 实现 circular wrap-around。

因此新模拟 benchmark 应该按现有 `hash.cpp` 的参数化公式实现，而不是把 `1/3` 写死。

## 5. Peeling 成功条件

模拟过程建议如下：

1. 生成 `d` 条边。
2. 每条边根据 `(M,k,z,a)` 生成 `k` 个桶位置。
3. 维护：

```text
bucket_to_edges[bucket] = 当前桶中有哪些边
edge_to_buckets[edge] = 当前边连接了哪些桶
edge_alive[edge] = 这条边是否还没被 peel
degree[bucket] = 当前桶内未删除边数量
```

4. 初始化队列，把所有 `degree <= l` 的非空桶放进去。
5. 弹出一个桶，如果它当前仍满足 `degree <= l`，则认为这个桶可以解出其中所有未删除边。
6. 对这些边执行删除：从它们连接的所有桶中移除，更新 degree，并把新满足 `degree <= l` 的桶入队。
7. 如果最后删除了全部 `d` 条边，则本 trial 成功；否则失败。

这正是 `sample.cpp` 的核心逻辑：

```cpp
if(vec[i].size() <= l) q.push(i);
...
if(now == m) Success
```

这里要注意命名差异：`sample.cpp` 里的 `m` 是边数，约等于本文档里的 `d`；`sample.cpp` 里的 `n` 是桶数，约等于本文档里的 `M`。

## 6. 建议新增代码

我建议新增三个脚本/程序。

### 6.1 `tests/extract_fig2_m_candidates.py`

职责：

- 读取旧 Figure 2 的 `summary.jsonl` 或 `summary.csv`。
- 按 `(d,k,l)` 提取所有非空 `best_M`。
- 对 `M` 去重。
- 输出 `m_candidates.jsonl/csv`。

建议参数：

```bash
python3 tests/extract_fig2_m_candidates.py \
  --input tests/results/paper_fig2_az_grid/summary.jsonl \
  --output-dir tests/results/paper_fig2_m_candidates \
  --include-unresolved-with-m
```

### 6.2 `tests/benchmarks/fig2_peeling_sim.cpp`

职责：

- 实现快速、可复现的 peeling 模拟。
- 不包含真实 `XYZSketch`、集合生成、编码、解码、多项式操作。
- 输入一个固定 `(d,k,l,M,a,z,trials,seed)`。
- 输出一行 JSON。

建议参数：

```bash
./build/fig2_peeling_sim \
  --d 3000 \
  --k 2 \
  --l 6 \
  --M 591 \
  --a 0.3333333333 \
  --z 4 \
  --trials 100 \
  --seed 114514 \
  --format jsonl
```

建议输出字段：

```json
{
  "experiment": "paper_fig2_fixed_m_sim",
  "algorithm": "peeling_sim",
  "d": 3000,
  "k": 2,
  "l": 6,
  "M": 591,
  "circular_a": 0.3333333333,
  "z": 4,
  "range_length": 118,
  "circular_base_range": 552,
  "trials": 100,
  "successes": 912,
  "success_rate": 0.912,
  "seed": 114514
}
```

实现上不要直接复用 `docs/sample.cpp`，因为它有几个不适合作为实验程序的点：

- 参数硬编码。
- 使用 `random_device`，不利于复现。
- 全局数组 `N = 2e7 + 10`，内存开销大。
- 输出不是机器稳定解析的 JSON。
- `a = 1/3` 被写死在 `n - len / 3 + 1` 里。

但它的 hypergraph 构造和 peeling 思想可以照搬。

### 6.3 `tests/test_fig2_fixed_m_sim.py`

职责：

- 编译或调用 `fig2_peeling_sim`。
- 读取 `m_candidates.csv`。
- 对每个候选 `(d,k,l,M)` 扫描指定的 `a-values` 和 `z-values`。
- 汇总 JSONL/CSV/Markdown。
- 计算 Wilson CI，保持和现有实验格式一致。

建议命令：

```bash
python3 tests/test_fig2_fixed_m_sim.py \
  --m-candidates tests/results/paper_fig2_m_candidates/m_candidates.csv \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --z-values 0,1,2,3,4,5,6,8,10,12,16 \
  --trials 100 \
  --output-dir tests/results/paper_fig2_fixed_m_sim
```

## 7. 图应该怎么画

新 Figure 2(a) 可以画固定 `d,M` 下的 success-rate heatmap：

```text
x-axis: a
y-axis: z
color: success_rate
panel: 一个固定的 d,M
```

如果候选 `M` 太多，不建议全部画成论文图。可以用旧结果中比较有代表性的几个 `M`：

- 每个 `d` 下 `M` 的最小值、中位数、最大值。
- 或每个 `d` 下旧实验全局最优 `(a,z)` 对应的 `M`。
- 或选择 `M*l/d` 接近某几个固定通信预算的位置。

新 Figure 2(b) 可以画：

```text
fixed d,M 下最优 z_star 或 a_star 随 M/d 的变化
```

例如：

1. 对每个 `(d,M)`，找 success_rate 最大的 `(a,z)`。
2. 如果多个点并列，优先选更小通信复杂度解释上更自然的 `z`，或者选更接近理论启发式的 `z`。
3. 画 `z_star` vs `M*l/d` 或 `z_star` vs `d`。

但 Figure 2(b) 的具体定义需要在论文叙述中固定下来。新的实验逻辑下，`z_star(d)` 不再是“搜索到最小 M 的那个 z”，而是“固定 M 时成功率最好的 z”。

## 8. 工程注意点

1. 新旧 Figure 2 的输出目录必须分开，避免把 threshold-search 结果和 fixed-M simulation 结果混在一起。
2. `M`、`d`、`m` 的命名要统一。建议代码里只用：

```text
d = number of edges / differences
M = number of buckets / sketch cells
```

不要沿用 `sample.cpp` 中 `m` 表示边数、`n` 表示桶数的写法。

3. 模拟 benchmark 要固定随机种子，并记录 `seed`。
4. 同一组 `(d,M)` 下比较不同 `(a,z)` 时，建议使用相同 trial index 和 seed scheme，减少随机噪声。
5. 如果要尽量贴近当前 `XYZ-v2`，默认应使用 `dedup_hashes = false`。如果后续想研究去重 hash，也可以把它作为独立参数。
6. 当 `RangeLength = M / (z + 1)` 小于 1 或太小，应该标记为 `invalid`，不要让取模或空窗口产生未定义行为。
7. 模拟成功率只代表 peeling 图结构成功率，不代表真实 XYZ 解码端到端成功率。论文表述应避免把它直接说成完整协议成功率。
8. 如果论文需要和真实实现严格对齐，后续可以增加一个 signed simulation 版本：给每条边分配 A/B 符号，并检查局部 signed load 与真实 `PureCellVerify` 能力之间的差距。但第一版 Figure 2 新逻辑建议先保持 `sample.cpp` 这种无符号 peeling 模型。

## 9. 我建议的实施顺序

1. 先写 `extract_fig2_m_candidates.py`，确认旧结果能提取出合理的 `(d,k,l,M)` 列表。
2. 再写 `fig2_peeling_sim.cpp`，用几个小参数和 `docs/sample.cpp` 的思路对齐。
3. 写 `test_fig2_fixed_m_sim.py` 跑完整固定 `M` 网格。
4. 写新的绘图脚本，先输出 success-rate heatmap。
5. 最后再决定 Figure 2(b) 的定义，是画 `z_star`、`a_star`，还是画固定启发式曲线与最优点的差距。

## 10. 当前已实现代码

当前已经实现前三个实验入口：

```text
tests/extract_fig2_m_candidates.py
tests/benchmarks/fig2_peeling_sim.cpp
tests/test_fig2_fixed_m_sim.py
```

先从旧 Figure 2 结果提取固定 `M` 候选：

```bash
python3 tests/extract_fig2_m_candidates.py \
  --input tests/results/paper_fig2_az_grid/summary.jsonl \
  --output-dir tests/results/paper_fig2_m_candidates \
  --include-unresolved-with-m
```

默认会用 `--c-over-d-bin-width 0.1` 按 `M*l/d` 合并相近预算，并在每个 bin 中保留中位数 `M`。输出表里的 `merged_M_values` 记录该候选代表了哪些原始 `M`。如果要保留全部原始候选，可以加：

```bash
--c-over-d-bin-width 0
```

再运行固定 `M` 的 `(a,z)` peeling simulation 网格：

```bash
python3 tests/test_fig2_fixed_m_sim.py \
  --m-candidates tests/results/paper_fig2_m_candidates/m_candidates.csv \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --z-values 0,1,2,3,4,5,6,8,10,12,16 \
  --trials 100 \
  --output-dir tests/results/paper_fig2_fixed_m_sim
```

如果中途断掉，可以加：

```bash
--resume --skip-build
```

输出文件：

```text
tests/results/paper_fig2_fixed_m_sim/raw.jsonl
tests/results/paper_fig2_fixed_m_sim/summary.jsonl
tests/results/paper_fig2_fixed_m_sim/summary.csv
tests/results/paper_fig2_fixed_m_sim/summary.md
tests/results/paper_fig2_fixed_m_sim/run_config.json
```
