# Figure 2 大规模 d 标准流程

本文档定义 `d >= 10^5` 时 Figure 2 固定 M peeling simulation 的统一生成流程。

## 1. 统一入口

脚本：

```text
tests/run_figure2_large_d.py
```

默认运行 `d=10^6,10^7`：

```bash
python3 tests/run_figure2_large_d.py
```

中断后继续：

```bash
python3 tests/run_figure2_large_d.py --resume --skip-build
```

只运行指定阶段：

```bash
python3 tests/run_figure2_large_d.py --stages search
python3 tests/run_figure2_large_d.py --stages prepare \
  --search-source-template 'tests/results/paper_fig2_d{d}_m_search'
python3 tests/run_figure2_large_d.py --stages grid --resume --skip-build
python3 tests/run_figure2_large_d.py --stages plot
```

`--stages` 可选值为 `search,prepare,grid,plot`，默认依次运行全部阶段。
`prepare` 只生成每个 M 的居中 `grid_spec.json`，不运行模拟器。

### 1.1 复用已有 1e6/1e7 阈值

当前服务器已经存在：

```text
tests/results/paper_fig2_d1000000_m_search
tests/results/paper_fig2_d10000000_m_search
```

只生成并检查居中网格，不运行实验：

```bash
python3 tests/run_figure2_large_d.py \
  --d-values 1000000,10000000 \
  --stages prepare \
  --search-source-template 'tests/results/paper_fig2_d{d}_m_search' \
  --skip-build
```

使用已有阈值，运行 heatmap 数据并绘图：

```bash
python3 tests/run_figure2_large_d.py \
  --d-values 1000000,10000000 \
  --stages prepare,grid,plot \
  --search-source-template 'tests/results/paper_fig2_d{d}_m_search' \
  --skip-build
```

中断后使用完全相同的参数并增加 `--resume`。

## 2. M 阈值搜索

每个 `d` 固定：

```text
k = 2
l = 6
trials = 20
target_success_rate = 0.9
shared trial seeds = true
```

启发式点为：

```text
c_orient/c_peel = 1.2081
C = (1/3) / 1.2081
a = C * c_orient/c_peel = 1/3
D = 0.5
delta = 0.1
z(M) = round(D * (1-a)^(2/3) * (M/log(1/delta))^(1/3))
```

默认搜索区间：

```text
lower M = 0.1d
upper M = 0.4d
maximum M = 2d
```

如果上界未达到目标，搜索脚本会自动扩大上界，直到达到 `maximum M`。

### 2.1 搜索分辨率

大规模实验不报告个位数精度的 M。默认分辨率为：

```text
M resolution = nice_round(0.0001d)
```

因此：

```text
d=10^5  -> resolution=10
d=10^6  -> resolution=100
d=10^7  -> resolution=1000
```

二分搜索只探测该分辨率网格上的 M。

### 2.2 稳定通过规则

默认要求连续两个预算点均达到 `success_rate >= 0.9`：

```text
M0       passes
M0 + resolution passes
```

第一个满足该规则的 `M0` 作为稳定经验阈值。该规则减少 20 trials 导致的单点随机误判，但不能替代更大 trials 的最终确认。

## 3. M 序列

候选 M 不再使用固定 `+100,+200,+300`，而是按 d 缩放：

```text
M candidates = M0 + nice_round({0.005d, 0.01d, 0.02d})
```

默认间距为：

| d | offsets |
| ---: | --- |
| `10^5` | `+500,+1000,+2000` |
| `10^6` | `+5000,+10000,+20000` |
| `10^7` | `+50000,+100000,+200000` |

这些间距约等于阈值 M 的 `2.8%`、`5.6%` 和 `11%`，比固定加 100 更容易在三张 heatmap 中展示成功区域的变化。

可通过以下参数覆盖：

```text
--offset-fractions 0.005,0.01,0.02
```

## 4. 公式居中的网格

每个固定 M panel 独立计算公式点：

```text
a_center = a* = 1/3
z_float = D * (1-a*)^(2/3) * (M/log(1/delta))^(1/3)
z_center = round(z_float)
```

默认 a 轴在公式值两侧各取 3 格：

```text
a_values = a_center + {-3,-2,-1,0,1,2,3} * 0.1
```

因此 `a*=1/3` 始终是 7 列中的正中央。

默认 z 轴在 `z_center` 两侧各取 4 格：

```text
z_step = nice_round(z_center * 0.125)
z_values = z_center + {-4,-3,-2,-1,0,1,2,3,4} * z_step
```

因此取整后的公式 z 始终是 9 行中的正中央。panel 标题仍显示未取整的连续
`z_float`。不同 M 可以使用不同的 z 标签，plotter 会按 panel-specific 坐标绘制。

可调参数：

```text
--a-step 0.1
--a-radius 3
--z-step 0                 # 0 表示自动选择
--z-step-fraction 0.125
--z-radius 4
```

## 5. 公平比较和并行

所有候选 M 和 `(a,z)` 格子共用同一组 trial seeds，以 common random numbers 方式降低格子之间的输入随机波动。

默认：

```text
jobs = 6
```

服务器有 8 个 CPU 核和约 6.2 GiB 可用内存。`d=10^7` 单进程约占 520 MiB，因此 6 jobs 将峰值控制在约 3.2 GiB。

C++ 模拟器使用扁平 CSR 邻接结构。与旧 `vector<vector<int>>` 实现比较：

| d | old time/trial | CSR time/trial | old memory | CSR memory |
| ---: | ---: | ---: | ---: | ---: |
| `10^6` | `1.05s` | `0.52s` | `82 MiB` | `56 MiB` |
| `10^7` | `15.9s` | `8.3s` | `786 MiB` | `520 MiB` |

多个参数和 seeds 的新旧二进制成功次数已逐项比对一致。

## 6. 输出结构

数据目录：

```text
tests/results/paper_fig2_large_d/
  d<D>/
    m_candidates.csv
    grid_spec.json
    m_search/
      threshold_probes.jsonl
      threshold_probes.csv
      threshold_summary.json
      m_candidates.csv
      m_candidates.jsonl
      m_candidates.md
    fixed_m_sim/
      raw.jsonl
      summary.jsonl
      summary.csv
      summary.md
      run_config.json
    workflow_summary.json
    workflow_summary.md
  workflow_summary.json
```

图片目录：

```text
tests/results/paper_figures/figure2_large_d/
  d<D>/
    figure2a_fixed_m_d<D>.svg
    figure2a_fixed_m_index.md
    figure2b_fixed_m_z_star.svg
    figure2b_fixed_m_z_star_source.csv
```

每个 fixed-M 网格结束后自动运行：

```bash
python3 tests/json_verifier.py <summary.jsonl> --strict
```

校验失败时统一脚本立即停止，不继续绘图。

## 7. 恢复语义

搜索阶段每完成一个 probe 就写入 `threshold_probes.jsonl`。网格阶段每完成一个 `(M,a,z)` 就更新 summary。中断后使用：

```bash
python3 tests/run_figure2_large_d.py --resume --skip-build
```

已完成的搜索 probe 和网格配置会被跳过。

## 8. 统计限制

20 trials 下：

```text
0.9 = 18/20
```

Wilson 95% 置信区间仍然较宽。该流程产生的是粗粒度、可复现、适合定位 heatmap 区域的经验 M 序列，不应把 M0 表述成精确的 90% 成功率阈值。论文最终确认可对选中的少量黄框点额外运行 100 或更多 trials。

此外，该实验仍是结构层面的 hypergraph peeling simulation，不是完整 XYZ 端到端解码。
