# 寻找最佳 `M` 规划文档

本文档规划一个后续脚本，用于为每组参数寻找最小合适的 `M`，尤其是用于比较不同 `k` 时的空间需求。本文档不实现代码。

## 动机

当前的 `d/l/k` 扫描使用固定启发式来选择 `M`。这足够做第一轮观察，但不适合作为公平比较不同 `k` 的方法。

特别是：

- 现有 XYZ-v2 实验主要是围绕 `k = 2` 调参的。
- Circular spatial coupling 在 `k = 2` 时效果较好。
- Naive/non-circular spatial coupling 需要更大的 `M`。
- 对于 `k >= 3`，复用 `k = 2` 的通信预算会让结果显得过差。

因此，在比较 `k = 2`、`k = 3`、`k = 4` 之前，应该先搜索达到目标解码成功率所需的最小 `M`。

## 目标

对每组配置：

```text
d, l, k, z policy, hash mode, target success rate
```

寻找最小的 `M`，使 XYZ-v2 在重复 trial 中达到目标成功率。

主要输出应包括：

```text
best_M
C_over_d = best_M * l / d
measured_success_rate
best_M 下的 encode/decode 时间
```

## 建议脚本名称

推荐后续脚本命名为：

```text
tests/test_find_best_m.py
```

它应该和 `tests/test_dlk.py` 分开，因为阈值搜索和固定网格扫描是两类不同实验。

## C++ Benchmark 依赖

脚本应复用：

```text
tests/benchmarks/xyz_v2_bench.cpp
```

当前 benchmark 已支持：

```bash
--d
--l
--k
--m
--z
--trials
--seed
--mode spatial
--ca
--cb
--format jsonl
```

二分搜索过程中，脚本应通过精确的 `--m` 值调用 benchmark。

## 搜索目标

可以使用一个或多个目标成功率：

```text
0.50 用于阈值型探索
0.95 用于实践参数
0.99 在 trial 数足够大时使用
```

第一版推荐目标：

```text
target_success_rate = 0.95
```

不过，当 trial 数较小时，`0.95` 的意义有限。例如 `20` 次 trial 时，最接近的实际门槛是：

```text
19/20 = 0.95
20/20 = 1.00
```

因此脚本应将成功条件定义为：

```text
successes >= ceil(target_success_rate * trials)
```

## 二分搜索假设

搜索假设如下单调性：

```text
如果某个 M 可行，那么更大的 M 通常也应该可行。
```

这在目标概率意义上是成立的，但实际测得的成功率会受随机性影响，因为不同 `M` 可能对应不同随机 trial。

为了降低噪声，单次搜索中的所有 `M` 候选值应使用相同 base seed。这样不同 `M` 之间的比较更稳定。

## 搜索流程

对每组配置：

1. 选择下界 `lo`。
2. 选择上界 `hi`。
3. 增大 `hi`，直到它可行。
4. 在 `lo` 和 `hi` 之间二分。
5. 用更多 trial 重新验证最终的 `best_M`。
6. 保存所有原始 probe 记录和最终 summary。

### 下界

安全下界可以设为：

```text
lo = max(k, ceil(d / l))
```

这大致对应 `C/d >= 1`。

对于很小的 `d`，可以额外保证：

```text
lo >= 1
```

### 初始上界

使用一个保守起点：

```text
hi = ceil(initial_factor * d / l)
```

建议 `initial_factor`：

```text
k = 2: initial_factor = 1.5
k = 3: initial_factor = 2.5
k = 4: initial_factor = 3.5
```

这些只是起始值。如果 `hi` 不可行，就翻倍：

```text
hi = hi * 2
```

直到成功或达到最大限制。

### 最大限制

为了避免实验失控，设置：

```text
max_C_over_d = 8.0
max_M = ceil(max_C_over_d * d / l)
```

如果在该限制内没有找到可行的 `M`，则将该配置标记为 unresolved。

## `z` 的选择

有两种可能策略。

### 策略 A：`z` 依赖 `M`

对每个候选 `M`，重新计算：

```text
z = max(0, round(M^(1/3) / 3))
```

这种方式简单，并且会随搜索范围自适应。

### 策略 B：固定 `z`

在一次搜索中固定 `z`，通常根据初始或预期 `M` 选择。

这种方式能隔离 `M` 的影响，但如果 `z` 选得不好，结果可能变差。

第一版推荐：

```text
使用策略 A。
```

后续 `z` 敏感性应由单独实验处理。

## Hash 模式策略

使用：

```text
k = 2: circular spatial coupling
k >= 3: naive/non-circular spatial coupling
```

当前该策略已在 `XYZ-v2/hash.cpp` 中通过全局 `k` 选择。

脚本可以继续传入：

```bash
--mode spatial
```

circular 和 naive 的具体选择目前由 C++ 代码决定。

## 推荐参数网格

先从小规模开始：

```text
d in {1000, 3000, 10000}
l in {4, 6, 8}
k in {2, 3}
trials_per_probe = 20
final_trials = 100
target_success_rate = 0.95
```

之后再扩展：

```text
d in {100, 300, 1000, 3000, 10000, 30000, 100000}
l in {2, 3, 4, 6, 8, 10}
k in {2, 3, 4}
trials_per_probe = 30
final_trials = 100
```

大 `d` 应在脚本稳定后再加入。

## Python 脚本结构

推荐函数：

```python
def repo_root() -> Path:
    """Return repository root."""

def ensure_dirs(root: Path) -> dict[str, Path]:
    """Create output directories."""

def build_benchmark(root: Path) -> Path:
    """Build or locate xyz_v2_bench."""

def make_grid(args) -> list[dict]:
    """Create d/l/k configurations."""

def choose_z(m: int, policy: str) -> int:
    """Choose z for a candidate M."""

def run_probe(binary: Path, config: dict, m: int, trials: int, seed: int) -> dict:
    """Run one benchmark probe and return parsed JSON."""

def works(row: dict, target: float) -> bool:
    """Return whether a benchmark row meets the target success count."""

def find_upper_bound(binary: Path, config: dict) -> tuple[int, list[dict]]:
    """Find a working hi value, collecting raw probes."""

def binary_search_m(binary: Path, config: dict) -> tuple[int | None, list[dict]]:
    """Find the smallest working M."""

def final_validate(binary: Path, config: dict, best_m: int) -> dict:
    """Re-test best M with more trials."""

def write_outputs(raw_probes: list[dict], summaries: list[dict]) -> None:
    """Write raw and summary outputs."""
```

## 输出文件

推荐目录：

```text
tests/results/best_m/
```

推荐文件：

```text
tests/results/best_m/probes.jsonl
tests/results/best_m/summary.jsonl
tests/results/best_m/summary.csv
tests/results/best_m/errors.log
```

### `probes.jsonl`

包含寻找上界和二分搜索期间的每一次 benchmark 调用结果。

建议额外加入字段：

```text
search_id
phase = upper_bound | binary_search | final_validate
candidate_M
target_success_rate
required_successes
```

### `summary.jsonl` / `summary.csv`

每组被搜索配置一行：

```text
d,l,k,best_M,best_C_over_d,z_policy,target_success_rate,
probe_trials,final_trials,final_successes,final_success_rate,
encode_avg_s,decode_avg_s,status
```

`status` 应为：

```text
ok
unresolved
benchmark_error
```

## 测试计划

### 1. 单元级 Dry Run

脚本应支持：

```bash
python tests/test_find_best_m.py --dry-run
```

它应该打印计划运行的配置，而不调用 benchmark。

### 2. 单配置 Smoke Test

运行：

```bash
python tests/test_find_best_m.py \
  --d-values 1000 \
  --l-values 6 \
  --k-values 3 \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9
```

预期行为：

- 脚本应先尝试一个较小或初始 `M`。
- 如果失败，就增大 `M`。
- 最终应找到一个可行 `M`，大致落在手工测试成功的范围附近。

根据当前手工测试：

```text
d=1000, l=6, k=3
M=217 failed
M=300 succeeded
```

因此合理结果应找到接近该区间的 `best_M`，具体取决于 trial 数和 seed。

### 3. 与已知 `k = 2` 配置对照

运行：

```bash
python tests/test_find_best_m.py \
  --d-values 1000 \
  --l-values 6 \
  --k-values 2 \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9
```

预期行为：

- 找到的 `M` 应接近或低于现有调参值 `217`。
- 如果明显更大，应检查搜索逻辑和 `z` 策略。

### 4. 可复现性测试

用相同 seed 运行同一个命令两次。如果所有候选 probe 都使用确定性 seed，则结果应完全一致。

### 5. 失败处理测试

使用一个人为设置得很小的 `max_C_over_d`，例如：

```bash
python tests/test_find_best_m.py --max-C-over-d 1.05
```

预期行为：

- 部分配置应被标记为 `unresolved`。
- 脚本不应崩溃。

## 解释注意事项

结果不应被解释为精确数学阈值。它是在以下条件下得到的经验阈值：

- 选定的随机 seed 策略；
- 选定的 trial 数；
- 选定的 `z` 策略；
- 当前 hash 实现；
- 当前数据生成器。

如果要作为论文级结果，最终选出的 `best_M` 应用更多 trial 重新验证，并最好使用多组独立 seed。

## 重要注意点

当测得的成功率有噪声时，二分搜索可能产生误导。例如：

```text
M = 280 偶然成功
M = 290 偶然失败
M = 300 成功
```

为降低这个问题：

- 使用足够多的 probe trials。
- 对不同候选 `M` 使用确定性 seed。
- 用更多 trial 重新验证最终的 `best_M`。
- 可选地在 final validation 阶段额外测试 `best_M - 1` 和 `best_M + 1`。

