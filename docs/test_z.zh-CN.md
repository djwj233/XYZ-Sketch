# `tests/test_z.py` 设计与使用说明

本文档描述已经实现的 XYZ-v2 `z` 敏感性实验。它说明代表性参数如何选择、`z` 如何扫描、`tests/test_z.py` 如何运行，以及如何验证输出是否合理。

## 实验目标

目标是理解 XYZ-v2 对 spatial-coupling 参数 `z` 有多敏感。

核心问题是：

```text
在固定 d、l、k 和 M 时，解码成功率如何随 z 变化？
```

这和 best-`M` 实验不同：

- `test_find_best_m.py` 搜索最小可用 `M`。
- `test_spatial.py` 通过搜索各 mode 的 best `M` 来比较 hash mode。
- `test_z.py` 固定 `M`，只扫描 `z`。

固定 `M` 很重要，否则实验会把 `z` 的影响和通信量变化混在一起。

## 代表性参数

脚本默认使用从 `tests/results/dlk_best_m_policy/raw.jsonl` 和前面 best-M 实验中总结出的代表性配置：

```text
d = 1000,  l = 6, k = 2, M = 217
d = 3000,  l = 6, k = 2, M = 600
d = 10000, l = 6, k = 2, M = 2000

d = 1000,  l = 6, k = 3, M = 278
d = 3000,  l = 6, k = 3, M = 834
d = 10000, l = 6, k = 3, M = 2780
```

选择这些配置的原因：

- `d = 100` 和 `d = 300` 有明显有限规模效应，成功率不够稳定。
- `d >= 1000` 更适合观察 `z` 的趋势。
- `l = 6` 是前面实验中主要使用的设置。
- `k = 2` 对应论文中主要讨论的 circular spatial coupling。
- `k = 3` 对应当前实现中使用 naive/non-circular spatial coupling 的情况。

## 扫描范围

默认扫描的 `z` 为：

```text
0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 32
```

脚本会计算并记录：

```text
RangeLength = M // (z + 1)
```

如果 `RangeLength` 太小，脚本会跳过对应的 `z`。默认阈值是：

```text
RangeLength >= max(2, k)
```

也可以用 `--min-range-length` 手动指定阈值。

## Mode 策略

默认使用：

```text
--mode spatial
```

这会沿用当前实验策略：

```text
k <= 2 -> circular spatial coupling
k >= 3 -> naive/non-circular spatial coupling
```

如果之后需要单独研究某个 mode，也可以显式传入：

```text
--mode random
--mode circular
--mode naive
```

## 输出内容

默认输出目录是：

```text
tests/results/z_sensitivity/
```

生成文件包括：

```text
raw.jsonl
raw.csv
summary.md
errors.log
```

每一行结果包含：

```text
algorithm
d
l
k
M
z
RangeLength
mode
trials
successes
success_rate
encode_avg_s
decode_avg_s
encode_median_s
decode_median_s
bits
bit_C_over_d
field_C_over_d
seed
ca
cb
```

其中：

```text
field_C_over_d = M * l / d
bit_C_over_d = bits / (32 * d)
```

同一组 `d/l/k/M` 下，改变 `z` 时这两个通信量字段应该保持不变。

## 随机种子策略

为了公平比较，同一组 `d/l/k/M` 下所有 `z` 使用同一个 base seed：

```text
seed = base_seed + 1000000 * config_index
```

C++ benchmark 内部会使用：

```text
trial_seed = seed + trial_index
```

这样不同 `z` 会看到同一组生成数据。

## 编译和使用

脚本可以自动编译 C++ benchmark：

```bash
python tests/test_z.py --dry-run
python tests/test_z.py --limit 2 --trials 5
```

如果已经存在 `build/xyz_v2_bench.exe`，可以跳过编译：

```bash
python tests/test_z.py --skip-build --limit 2 --trials 5
```

运行一个小的 `k = 2` smoke test：

```bash
python tests/test_z.py \
  --skip-build \
  --d-values 1000 \
  --l-values 6 \
  --k-values 2 \
  --m-values 217 \
  --z-values 0,1,2,3,4,5,8 \
  --trials 10 \
  --output-dir tests/results/z_smoke_k2
```

运行一个小的 `k = 3` smoke test：

```bash
python tests/test_z.py \
  --skip-build \
  --d-values 1000 \
  --l-values 6 \
  --k-values 3 \
  --m-values 278 \
  --z-values 0,1,2,3,4,5,8 \
  --trials 10 \
  --output-dir tests/results/z_smoke_k3
```

运行默认代表性扫描：

```bash
python tests/test_z.py --skip-build
```

## 主要参数

```text
--d-values, --l-values, --k-values, --m-values
    自定义固定配置，四个参数必须一起提供，并且逗号分隔列表长度必须一致。

--z-values
    自定义要扫描的 z。省略时使用默认 z 列表。

--mode
    spatial、random、circular 或 naive。默认是 spatial。

--trials
    每个 z 的 trial 数。

--min-range-length
    跳过 M // (z + 1) 小于该阈值的 z。

--limit
    只运行前 N 个计划任务，适合快速检查。

--output-dir
    指定输出目录。
```

## 如何解读

对每组 `d/l/k/M`，重点观察：

```text
z -> success_rate
z -> decode_avg_s
z -> RangeLength
```

可以关注：

- 成功率最高的 `z`。
- 达到目标成功率的最小 `z`。
- 是否存在较宽的稳定 `z` 区间。
- 启发式 `round(M^(1/3) / 3)` 是否落在表现较好的区域。

注意事项：

- 本实验固定 `M`，不会为每个 `z` 重新搜索 best `M`。
- 小 trial 数只适合 smoke test。
- `spatial` mode 下的 `z = 0` 不完全等同于 random hashing。
- random-hash 对比属于 `test_spatial.py` 的目标，不是本实验的重点。

