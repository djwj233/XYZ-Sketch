# `tests/test_spatial.py` 设计规划

本文档规划 spatial coupling 隔离实验，用于比较带 spatial coupling 的 XYZ-v2 和不带 spatial coupling 的 XYZ-v2。本文档不实现代码。

## 实验目标

目标是测量 spatial coupling 的收益：比较达到目标解码成功率所需的最小通信量。

核心问题是：

```text
在相同 d、l、k 和目标成功率下，启用 spatial coupling 后，C/d 能降低多少？
```

主要指标应为：

```text
best_C_over_d = best_M * l / d
```

其中 `best_M` 是经验上可行的最小 cell 数量。

## 为什么需要单独脚本

现有 `tests/test_dlk.py` 做的是固定参数网格扫描。它适合观察趋势，但不适合公平比较 spatial coupling 模式。

为了公平比较，每种 mode 都应该允许选择自己的最佳 `M`。否则某个 mode 可能只是因为共享的 `M` 太小而显得很差。

因此，该实验应使用类似 `tests/find_best_m.py` 的阈值搜索。

## 建议脚本名称

```text
tests/test_spatial.py
```

## 需要比较的模式

该实验最终应比较三种模式：

```text
random
circular
naive
```

### `random`

这是不带 spatial coupling 的版本。每个 hash 都均匀映射到 `[0, M)`。

它对应当前 `XYZ-v2/hash.cpp` 中的 `RandomHash` namespace。

### `circular`

这是论文中提到的环形 spatial coupling 变体。空间窗口超过数组末尾时会绕回。

它预计在 `k = 2` 时效果较好，但在更大的 `k` 下表现较差。

### `naive`

这是非环形 spatial coupling。空间窗口不会绕回。

它通常需要比 circular 更大的 `M`，但对于 `k >= 3`，它是更合适的 spatial-coupling baseline。

## 所需 C++ Benchmark 改动

当前 `XYZ-v2/xyz_v2_bench.cpp` 支持：

```bash
--mode spatial
```

但 circular 和 naive 的实际选择目前是在 `XYZ-v2/hash.cpp` 中根据全局 `k` 决定的。

为了该实验，C++ benchmark 应显式暴露 hash modes：

```bash
--mode random
--mode circular
--mode naive
```

推荐实现方式：

1. 在 `XYZ-v2/hash.cpp` 中加入全局 hash-mode enum 或整数。
2. 加入 setter，例如：

   ```cpp
   enum class HashMode { Random, Circular, Naive };
   void SetHashMode(HashMode mode);
   ```

3. 修改 `h(i, x)`，根据所选 mode 分发。
4. 让 `xyz_v2_bench.cpp` 解析 `--mode random|circular|naive`。
5. 保留旧行为，将：

   ```text
   --mode spatial
   ```

   映射为：

   ```text
   k <= 2 -> circular
   k >= 3 -> naive
   ```

   这样可以保持 `test_dlk.py` 和 `find_best_m.py` 的兼容性。

## 公平比较策略

对每组配置：

```text
d, l, k, mode, target_success_rate
```

脚本应寻找达到目标成功率所需的最小 `M`。

这意味着 `random`、`circular`、`naive` 不强制共享同一个 `M`，而是比较各自所需的 `C/d`。

## 推荐配置

先从小而有意义的网格开始：

```text
d in {1000, 3000, 10000}
l in {4, 6, 8}
k in {2, 3}
modes:
  for k = 2: random, circular, naive
  for k = 3: random, naive
```

对于 `k = 3`，可以把 circular 作为诊断 mode 加入，但不应作为主要 spatial-coupling 代表，因为论文说明 circular 在 `k` 大于 2 时表现较差。

脚本稳定后，再扩展到：

```text
d in {100, 300, 1000, 3000, 10000, 30000, 100000}
l in {2, 3, 4, 6, 8, 10}
k in {2, 3, 4}
```

## 目标成功率

推荐默认值：

```text
target_success_rate = 0.95
probe_trials = 30
final_trials = 100
```

用于 smoke test 时：

```text
target_success_rate = 0.9
probe_trials = 10
final_trials = 20
```

成功条件应定义为：

```text
successes >= ceil(target_success_rate * trials)
```

## 搜索策略

复用 `tests/find_best_m.py` 的核心思路：

1. 选择下界：

   ```text
   lo = max(k, ceil(d / l))
   ```

2. 根据 mode 选择初始上界：

   ```text
   random:   initial_factor = 2.5
   circular: initial_factor = 1.5
   naive:    initial_factor = 2.5
   ```

   这些只是起点。

3. 翻倍增大 `hi`，直到该 mode 成功或达到：

   ```text
   max_C_over_d = 8.0
   ```

4. 二分搜索最小可行 `M`。
5. 用更多 trial 验证 `best_M`。

## `z` 的选择

`z` 只对 spatial modes 有意义。

对 `circular` 和 `naive`，使用：

```text
z = max(0, round(M^(1/3) / 3))
```

对 `random`，使用：

```text
z = 0
```

脚本仍应为每个 probe 记录 `z`。

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
    """Create d/l/k/mode configurations."""

def modes_for_k(k: int, include_diagnostic_circular: bool) -> list[str]:
    """Return modes to test for a k value."""

def choose_z(mode: str, m: int) -> int:
    """Return z for this mode and M."""

def initial_factor(mode: str, k: int) -> float:
    """Return initial upper-bound factor."""

def run_probe(binary: Path, config: dict, m: int, trials: int, seed: int) -> dict:
    """Run one benchmark probe."""

def works(row: dict, target: float) -> bool:
    """Check whether a probe reaches the target."""

def find_best_m(binary: Path, config: dict) -> tuple[int | None, list[dict]]:
    """Find smallest M for one config/mode."""

def final_validate(binary: Path, config: dict, best_m: int) -> dict:
    """Validate best M with more trials."""

def write_outputs(probes: list[dict], summaries: list[dict]) -> None:
    """Write JSONL and CSV outputs."""
```

## 输出文件

推荐输出目录：

```text
tests/results/spatial/
```

推荐文件：

```text
tests/results/spatial/probes.jsonl
tests/results/spatial/summary.jsonl
tests/results/spatial/summary.csv
tests/results/spatial/errors.log
```

## 输出字段

每条 summary 应包含：

```text
d
l
k
mode
best_M
best_C_over_d
z_at_best_M
target_success_rate
probe_trials
final_trials
final_successes
final_success_rate
encode_avg_s
decode_avg_s
status
seed
```

`status` 应为：

```text
ok
unresolved
benchmark_error
```

## 主要对比方式

对每组 `d/l/k`，最终表格应便于比较：

```text
random C/d
circular C/d
naive C/d
spatial improvement over random
```

对于 `k = 2`，关键对比是：

```text
random vs circular
```

对于 `k >= 3`，关键对比是：

```text
random vs naive
```

如果也测量 `k >= 3` 的 circular，应标记为 diagnostic。

## 测试计划

### 1. Dry Run

脚本应支持：

```bash
python tests/test_spatial.py --dry-run
```

它应打印计划运行的 `d/l/k/mode` 配置和搜索边界。

### 2. Benchmark Mode Smoke Test

在运行完整脚本前，手动测试 C++ benchmark：

```bash
build/xyz_v2_bench.exe --d 1000 --l 6 --k 2 --m 217 --z 2 --mode circular --trials 5 --seed 114514 --ca 10000 --cb 10000 --format jsonl
build/xyz_v2_bench.exe --d 1000 --l 6 --k 2 --m 217 --z 0 --mode random --trials 5 --seed 114514 --ca 10000 --cb 10000 --format jsonl
build/xyz_v2_bench.exe --d 1000 --l 6 --k 3 --m 300 --z 2 --mode naive --trials 5 --seed 114514 --ca 10000 --cb 10000 --format jsonl
```

预期：

- 所有 mode 都应运行并输出合法 JSON。
- `random` 可能需要比 spatial modes 更大的 `M`。
- `circular` 在 `k = 2` 时应保持较好表现。

### 3. 单配置脚本 Smoke Test

运行：

```bash
python tests/test_spatial.py \
  --d-values 1000 \
  --l-values 6 \
  --k-values 2 \
  --modes random,circular,naive \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9
```

预期：

- 脚本应为每个 mode 生成一条 summary。
- `circular` 所需的 `C/d` 应小于或接近 `random`。

### 4. `k = 3` Smoke Test

运行：

```bash
python tests/test_spatial.py \
  --d-values 1000 \
  --l-values 6 \
  --k-values 3 \
  --modes random,naive \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9
```

预期：

- `naive` 应作为 spatial 代表。
- 结果应显示 spatial coupling 是否相对 random 降低了 `C/d`。

### 5. 失败处理

使用很小的最大通信预算：

```bash
python tests/test_spatial.py --max-C-over-d 1.05
```

预期：

- 部分 mode 应被标记为 `unresolved`。
- 脚本应继续运行其他配置。

## 解释注意事项

该实验应被解释为当前实现下所需通信成本的经验对比。它不证明理论阈值。

重要 caveats：

- `best_M` 依赖目标成功率和 trial 数。
- 小 `d` 会有明显有限规模效应。
- `z` 是启发式选择，后续应单独研究。
- 解释结果时不要混用 `circular` 和 `naive`；它们是不同的 spatial-coupling 变体。

## 与其他脚本的关系

- `tests/test_dlk.py`：固定网格扫描 `d/l/k`。
- `tests/find_best_m.py`：对单一算法 mode 做通用 best-`M` 搜索。
- `tests/test_spatial.py`：按 spatial mode 分组做 best-`M` 搜索，专门用于隔离 spatial coupling 的收益。

## 编译和使用指南

当前实现使用：

- `XYZ-v2/hash.cpp` 和 `XYZ-v2/hash.h`：支持可选择的 hash mode。
- `XYZ-v2/xyz_v2_bench.cpp`：执行 benchmark。
- `tests/test_spatial.py`：按 mode 搜索 best-`M`。

### Benchmark Modes

benchmark 现在接受：

```text
--mode random
--mode circular
--mode naive
--mode spatial
```

`spatial` 是兼容模式：

```text
k <= 2 -> circular
k >= 3 -> naive
```

### 手动 Benchmark Smoke Test

从仓库根目录运行：

```powershell
g++ -std=c++17 -O2 XYZ-v2\xyz_v2_bench.cpp -o build\xyz_v2_bench.exe
build\xyz_v2_bench.exe --d 1000 --l 6 --k 2 --m 217 --z 2 --mode circular --trials 5 --seed 114514 --ca 10000 --cb 10000 --format jsonl
build\xyz_v2_bench.exe --d 1000 --l 6 --k 2 --m 217 --z 0 --mode random --trials 5 --seed 114514 --ca 10000 --cb 10000 --format jsonl
build\xyz_v2_bench.exe --d 1000 --l 6 --k 3 --m 300 --z 2 --mode naive --trials 5 --seed 114514 --ca 10000 --cb 10000 --format jsonl
```

### 脚本 Dry Run

```bash
python tests/test_spatial.py --dry-run
```

单独查看 `k = 2` 的 dry run：

```bash
python tests/test_spatial.py --dry-run --d-values 1000 --l-values 6 --k-values 2 --modes random,circular,naive
```

### 脚本 Smoke Tests

对于 `k = 2`：

```bash
python tests/test_spatial.py \
  --skip-build \
  --d-values 1000 \
  --l-values 6 \
  --k-values 2 \
  --modes random,circular,naive \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9 \
  --output-dir tests/results/spatial_smoke_k2
```

对于 `k = 3`：

```bash
python tests/test_spatial.py \
  --skip-build \
  --d-values 1000 \
  --l-values 6 \
  --k-values 3 \
  --modes random,naive \
  --probe-trials 10 \
  --final-trials 20 \
  --target-success-rate 0.9 \
  --output-dir tests/results/spatial_smoke_k3
```

### 默认完整运行

```bash
python tests/test_spatial.py
```

默认输出：

```text
tests/results/spatial/probes.jsonl
tests/results/spatial/summary.jsonl
tests/results/spatial/summary.csv
```

### 关于小 trial 数的注意事项

当使用较小 trial 数，例如 `probe_trials = 10`、`final_trials = 20` 时，二分可能找到一个通过 probe 但没有通过 final validation 的边界 `M`。这种情况下 summary 里的 status 会是 `unresolved`。

如果想得到更稳定的结果，使用：

```bash
python tests/test_spatial.py --probe-trials 30 --final-trials 100 --target-success-rate 0.95
```
