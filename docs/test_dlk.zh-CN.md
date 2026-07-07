# `tests/test_dlk.py` 设计规划

本文档规划第一份实验脚本：对 XYZ-v2 的 `d`、`l`、`k` 做更细致的参数扫描。本文档暂不实现脚本，只是在写代码前先明确接口和结构。

## 实验目标

该脚本应该测量 XYZ-v2 在不同参数下的表现：

- `d`：对称差异规模
- `l`：每个 cell 的解码容量
- `k`：每个元素映射到的 hash 位置数量

对每组配置，脚本应运行多次 trial，并记录成功率、时间、通信量和归一化通信量。

## 推荐架构

使用 Python 作为实验驱动，C++ 作为 benchmark 执行核心。

Python 负责：

- 生成 `d/l/k` 参数网格。
- 决定 `M`、`z`、trial 次数和 seed。
- 构建或定位 C++ benchmark binary。
- 反复调用 binary。
- 解析结构化输出。
- 写入原始 CSV 或 JSONL 结果。
- 可选地打印简洁的进度摘要。

C++ 负责：

- 运行真正的 XYZ-v2 encode/decode workload。
- 测量编码和解码时间。
- 校验正确性。
- 对每组配置或每次 trial 输出一条结构化记录。

Python 脚本不应该重新实现 XYZ-v2 逻辑。

## 所需 C++ Benchmark 接口

当前的 `XYZ-v2/speedtest.cpp` 可以作为参考，但它不适合自动参数扫描，因为参数是硬编码的。Python 脚本后续应调用一个小型 benchmark binary，其命令行接口建议如下：

```bash
xyz_v2_bench \
  --d 10000 \
  --l 6 \
  --k 2 \
  --m-factor 1.15 \
  --z 5 \
  --trials 30 \
  --seed 114514 \
  --mode spatial \
  --ca 10000000 \
  --cb 10000000 \
  --format jsonl
```

建议 binary 名称：

```text
build/xyz_v2_bench.exe
```

该 benchmark binary 后续可以基于 `XYZ-v2/speedtest.cpp` 改造实现。

## 命令行参数

C++ binary 应支持以下参数：

| 参数 | 是否必需 | 含义 |
| --- | --- | --- |
| `--d` | 是 | 目标对称差异规模。 |
| `--l` | 是 | cell 容量参数。 |
| `--k` | 是 | 每个元素的 hash 数量。 |
| `--m` | 否 | 精确 cell 数量；如果给出，覆盖 `--m-factor`。 |
| `--m-factor` | 否 | 计算 `M = ceil(m_factor * d / l)` 或等价形式。 |
| `--z` | 是 | Spatial coupling 参数。 |
| `--trials` | 是 | 该配置下重复试验次数。 |
| `--seed` | 是 | 基础随机 seed。 |
| `--mode` | 是 | `spatial` 或 `random`；本实验初期只用 `spatial`。 |
| `--ca` | 否 | Alice 集合大小；大规模实验可默认 `10000000`。 |
| `--cb` | 否 | Bob 集合大小；默认可等于 `ca`。 |
| `--format` | 否 | 推荐 `jsonl`，也可支持 `csv`。 |

第一轮 `d/l/k` 扫描只需要 `--mode spatial`。非 spatial 模式可以留给后续 spatial-coupling 对比实验复用。

## 期望的 C++ 输出

推荐使用 JSONL，因为它容易扩展，不容易破坏解析器。binary 应在聚合所有 trials 后，为每组配置输出一个 JSON 对象。

示例：

```json
{"algorithm":"xyz_v2","mode":"spatial","d":10000,"l":6,"k":2,"M":1917,"z":5,"trials":30,"successes":30,"success_rate":1.0,"encode_avg_s":2.31,"decode_avg_s":0.67,"encode_median_s":2.29,"decode_median_s":0.66,"bits":375732,"C_over_d":1.174,"seed":114514}
```

记录中应包含：

- `algorithm`
- `mode`
- `d`
- `l`
- `k`
- `M`
- `z`
- `trials`
- `successes`
- `success_rate`
- `encode_avg_s`
- `decode_avg_s`
- `encode_median_s`
- `decode_median_s`
- `bits`
- `C_over_d`
- `seed`

Python 脚本应保存这些记录，不改变字段含义。

## Python 脚本职责

`tests/test_dlk.py` 应包含实验编排逻辑。

推荐函数：

```python
def repo_root() -> Path:
    """Return the repository root."""

def ensure_dirs(root: Path) -> dict[str, Path]:
    """Create and return output directories."""

def build_benchmark(root: Path) -> Path:
    """Build or locate the xyz_v2 benchmark binary."""

def default_grid() -> list[dict]:
    """Return the default d/l/k experiment configurations."""

def choose_trials(d: int) -> int:
    """Choose trial count based on problem size."""

def choose_z(d: int, l: int, k: int, m: int) -> int:
    """Choose z for the first sweep."""

def choose_m_factor(d: int, l: int, k: int) -> float:
    """Choose the communication budget for this configuration."""

def run_one(binary: Path, config: dict) -> dict:
    """Invoke the C++ benchmark for one configuration and parse JSONL output."""

def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write raw result records."""

def write_csv(path: Path, rows: list[dict]) -> None:
    """Write a tabular copy for quick inspection."""

def main() -> None:
    """Run the d/l/k sweep."""
```

脚本应使用 `subprocess.run` 和显式参数列表，不要拼 shell 字符串。

## 初始参数网格

第一版应保持网格适中，先验证工作流。

建议 quick grid：

```python
D_VALUES = [100, 300, 1000, 3000, 10000]
L_VALUES = [2, 3, 4, 6, 8, 10]
K_VALUES = [2, 3, 4]
```

脚本稳定后，再使用 extended grid：

```python
D_VALUES = [10, 30, 100, 300, 1000, 3000, 10000, 30000, 100000, 300000, 1000000]
L_VALUES = [2, 3, 4, 6, 8, 10, 16, 20]
K_VALUES = [2, 3, 4]
```

对于很小的 `d`，某些 `l` 可能过大或没有意义。脚本应跳过 `l > d` 或计算出的 `M` 过小的配置。

## `M` 和 `z` 的选择

第一份实验主要变量是 `d/l/k`，不是搜索通信阈值。因此先使用一个简单、确定性的 `M` 和 `z` 策略。

当前脚本对 `k = 2` 继续使用原来的启发式；对更大的 `k`，使用通过 `tests/test_find_best_m.py` 测得的经验 `C/d`。

对于 `k = 3` 和 `k = 4`，这些值来自代表配置 `d = 1000, l = 6, target_success_rate = 0.9`：

```text
k = 3: C/d = 1.668
k = 4: C/d = 1.782
```

脚本按如下方式缩放：

```text
M = ceil((C/d target) * d / l)
```

对于 `k = 2`，脚本保留原有随 `d` 变化的策略：

```text
d <= 100      -> C/d = 1.60
d <= 1000     -> C/d = 1.30
d <= 10000    -> C/d = 1.20
d <= 100000   -> C/d = 1.12
otherwise     -> C/d = 1.10
```

然后：

```text
z = max(0, round(M^(1/3) / 3))
```

Python 脚本应该显式写出这个策略，方便后续读者知道每个结果是如何产生的。

## 输出文件

推荐输出位置：

```text
tests/results/dlk/
```

推荐文件：

```text
tests/results/dlk/raw.jsonl
tests/results/dlk/raw.csv
tests/results/dlk/summary.md
```

`raw.jsonl` 应作为 source of truth。`raw.csv` 用于快速查看。`summary.md` 可以包含一段人类可读的运行摘要。

## 失败处理

Python 脚本应谨慎处理 benchmark 失败：

- 如果 C++ 进程返回非零状态，记录命令、stderr 和配置到错误日志。
- 如果 JSON 输出无法解析，保存原始 stdout 和 stderr。
- 如果某次 trial 解码失败，C++ benchmark 应把它计为失败 trial，而不是直接崩溃。
- 除非构建步骤失败，否则脚本应继续运行下一组配置。

推荐错误日志文件：

```text
tests/results/dlk/errors.log
```

## 可复现性

每组配置应有确定性的基础 seed。一个简单方案是：

```text
seed = base_seed + 1000000 * d_index + 10000 * l_index + 100 * k_index
```

在 C++ benchmark 内部，第 `t` 次 trial 可使用：

```text
trial_seed = seed + t
```

seed 必须包含在输出记录中。

## 实现顺序

真正开始实现时，建议按这个顺序：

1. 创建或改造一个 C++ benchmark binary，使它接受单组配置并输出 JSONL。
2. 用一个很小的 grid 实现 `tests/test_dlk.py`。
3. 验证能正确产出并解析一条记录。
4. 加入 CSV/JSONL 写入。
5. 扩展到 quick grid。
6. 加入失败日志和 summary 输出。
7. quick grid 稳定后，再运行 extended grid。

## 本脚本不负责的内容

该脚本不应该：

- 详细比较 spatial vs non-spatial coupling。
- 扫描 `z` 敏感性。
- 加入外部 baseline。
- 生成最终论文图。
- 用 Python 重新实现 XYZ-v2。

这些是后续任务。本脚本应专注于更详细的 `d/l/k` 参数扫描。

## 编译和使用指南

当前实验由两个文件组成：

- `tests/benchmarks/xyz_v2_bench.cpp`：C++ benchmark 可执行文件源码。
- `tests/test_dlk.py`：Python 实验驱动脚本。

### 手动编译 Benchmark

从仓库根目录运行：

```bash
mkdir -p build
g++ -std=c++17 -O2 tests/benchmarks/xyz_v2_bench.cpp -o build/xyz_v2_bench
```

在 Windows PowerShell 中可以运行：

```powershell
New-Item -ItemType Directory -Force build
g++ -std=c++17 -O2 tests\benchmarks\xyz_v2_bench.cpp -o build\xyz_v2_bench.exe
```

### 运行单组 Benchmark 配置

示例：

```bash
./build/xyz_v2_bench \
  --d 1000 \
  --l 6 \
  --k 2 \
  --m 217 \
  --z 2 \
  --trials 5 \
  --seed 114514 \
  --mode spatial \
  --ca 10000 \
  --cb 10000 \
  --format jsonl
```

benchmark 会向 stdout 输出一个 JSON 对象。

### 运行 Python 扫描脚本

从仓库根目录运行：

```bash
python tests/test_dlk.py
```

默认情况下，脚本会：

1. 编译 `build/xyz_v2_bench` 或 `build/xyz_v2_bench.exe`。
2. 运行 quick `d/l/k` 参数网格。
3. 把结果写入 `tests/results/dlk/`。

预期输出文件：

```text
tests/results/dlk/raw.jsonl
tests/results/dlk/raw.csv
tests/results/dlk/summary.md
tests/results/dlk/errors.log   # 只有失败时才会出现
```

### 常用脚本选项

只打印命令，不实际运行：

```bash
python tests/test_dlk.py --dry-run
```

只跑前几个配置，用于 smoke test：

```bash
python tests/test_dlk.py --limit 2
```

复用已经编译好的 benchmark：

```bash
python tests/test_dlk.py --skip-build
```

运行更大的 extended grid：

```bash
python tests/test_dlk.py --extended
```

使用其他输出目录：

```bash
python tests/test_dlk.py --output-dir tests/results/dlk_run_001
```

调整生成集合大小：

```bash
python tests/test_dlk.py --max-set-size 1000000 --set-size-scale 20
```

### 当前限制

`xyz_v2_bench.cpp` 当前只支持 `--mode spatial`，因为现有 `XYZ-v2/XYZSketch.cpp` 在编译期固定选择 `SpatialCoupling`。后续做 spatial-coupling 对比实验时，应该重构或复制 hash 选择路径，使 `--mode random` 能被干净地 benchmark。

