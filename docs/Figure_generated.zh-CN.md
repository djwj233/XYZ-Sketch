# Figure 生成指南

本文档说明如何生成 Figure 1、Figure 2 和 Figure 3 所需的实验数据与图像。

所有命令都从仓库根目录运行：

```bash
cd /root/XYZ-Sketch
```

## 0. 准备外部子模块

Figure 3 会用到 minisketch 等外部 baseline。先初始化 submodule：

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

如果这一步因为无法访问 GitHub 失败，需要先修复网络，或者把 `.gitmodules`
里的 URL 改成 SSH URL，然后再次运行上面的命令。

## 1. Figure 1

Figure 1 与 Figure 2、Figure 3 相互独立，可以单独生成。

### Figure 1(a)：Sharp Threshold

目标：

- 展示通信量 `R_w30` 增加时，解码成功率如何变化。
- 比较 `random`、`naive` 和 `circular` 三种模式。
- 使用代表性参数 `(k,l) = (2,3), (2,6), (3,4)`。

运行：

```bash
python3 tests/test_xyz_sharp_threshold.py \
  --d-values 10000 \
  --tuple-values 2:3,2:6,3:4 \
  --modes random,naive,circular \
  --trials 100 \
  --center-trials 10 \
  --window-fraction 0.06 \
  --min-window 20 \
  --max-window 120 \
  --step 3 \
  --target-success-rate 0.9 \
  --a-constant 0.3333333333 \
  --z-constant 1.3333333333 \
  --output-dir tests/results/paper_fig1_sharp_threshold
```

这里先用 10 次 `center-trials` 快速搜索经验中心 `M0`，再只扫描
`M0 +/- min(max(0.06*M0, 20), 120)` 的较窄区间，并以 `step = 3`
密集测试候选 `M`。如果曲线两端没有同时覆盖明显失败点和成功点，再适当增大
`--max-window` 或 `--window-fraction`。

重要输出文件：

```text
tests/results/paper_fig1_sharp_threshold/raw.jsonl
tests/results/paper_fig1_sharp_threshold/raw.csv
tests/results/paper_fig1_sharp_threshold/summary.jsonl
tests/results/paper_fig1_sharp_threshold/summary.csv
tests/results/paper_fig1_sharp_threshold/summary.md
tests/results/paper_fig1_sharp_threshold/run_config.json
```

上面的命令使用 `--tuple-values`，因此只会运行 `(2,3)`、`(2,6)` 和 `(3,4)`。

### Figure 1(b)：Communication Frontier

目标：

- 对每个 `d`，搜索达到 90% 成功率所需的最小通信量。
- 比较 iid hashing 和 spatial coupling。
- 在当前代码中，`random = iid`；`naive` 和 `circular` 是两种 spatial-coupling 变体。

运行：

```bash
python3 tests/test_frontier_xyz.py \
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 \
  --tuple-values 2:3,2:6,3:4 \
  --modes random,naive,circular \
  --probe-trials 50 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --a-constant 0.3333333333 \
  --z-constant 1.3333333333 \
  --output-dir tests/results/paper_fig1_frontier
```

重要输出文件：

```text
tests/results/paper_fig1_frontier/probes.jsonl
tests/results/paper_fig1_frontier/summary.jsonl
tests/results/paper_fig1_frontier/summary.csv
tests/results/paper_fig1_frontier/summary.md
tests/results/paper_fig1_frontier/run_config.json
```

验证 Figure 1 数据：

```bash
python3 tests/json_verifier.py tests/results/paper_fig1_sharp_threshold/raw.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_sharp_threshold/summary.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig1_frontier/summary.jsonl --strict
```

当前绘图状态：

```text
Figure 1 数据生成脚本已经存在。
Figure 1 SVG 绘图脚本已实现：tests/plot_figure1.py。
如果论文提交需要 PNG/PDF，可以从 SVG 通过 Inkscape、rsvg-convert 或浏览器打印/导出流程转换。
```

运行：

```bash
python3 tests/plot_figure1.py \
  --sharp-input tests/results/paper_fig1_sharp_threshold/raw.csv \
  --frontier-input tests/results/paper_fig1_frontier/summary.csv \
  --output-dir tests/results/paper_figures
```

当前图像输出：

```text
tests/results/paper_figures/figure1a_sharp_threshold.svg
tests/results/paper_figures/figure1b_frontier.svg
tests/results/paper_figures/figure1_source_summary.md
```

## 2. Figure 2

Figure 2 可以独立生成。当前 Figure 3 主实验默认不使用 Figure 2 提取出的 tuned `(a,z)`，而是按启发式公式计算 `a,z`；`paper_fig2_z_star/summary.jsonl` 作为可选输入保留，方便以后切回实验调参版本。

### Figure 2(a)：Circular `(a,z)` Heatmap

目标：

- 扫描 circular spatial coupling 的参数 `a` 和 `z`。
- 对每个 `(a,z)` cell，搜索达到 90% 成功率所需的最小 `M`。
- 使用 `best_R_w30` 作为 heatmap 的颜色值。

如果只需要一个代表性 heatmap，运行：

```bash
python3 tests/test_az_grid.py \
  --d-values 3000 \
  --k-values 2 \
  --l-values 6 \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --z-values 0,1,2,3,4,5,6,8,10,12,16 \
  --probe-trials 30 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --shared-datasets \
  --output-dir tests/results/paper_fig2_az_grid
```

如果还需要有意义的 Figure 2(b) 曲线，应使用多个 `d`：

```bash
python3 tests/test_az_grid.py \
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 \
  --k-values 2 \
  --l-values 6 \
  --a-values 0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9 \
  --z-values 0,1,2,3,4,5,6,8,10,12,16 \
  --probe-trials 30 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --shared-datasets \
  --output-dir tests/results/paper_fig2_az_grid
```

重要输出文件：

```text
tests/results/paper_fig2_az_grid/probes.jsonl
tests/results/paper_fig2_az_grid/summary.jsonl
tests/results/paper_fig2_az_grid/summary.csv
tests/results/paper_fig2_az_grid/summary.md
tests/results/paper_fig2_az_grid/run_config.json
tests/results/paper_fig2_az_grid/errors.log
```

### Figure 2(b)：提取 `z_star(d)`

目标：

- 为每个 `d` 选择最优 `(a,z)`。
- 比较实验得到的 `z_star` 和启发式/理论值 `z_theory`。
- 生成 Figure 3 使用的调参文件。

运行：

```bash
python3 tests/extract_fig2_z_star.py \
  --input tests/results/paper_fig2_az_grid/summary.jsonl \
  --z-constant 1.3333333333 \
  --output-dir tests/results/paper_fig2_z_star
```

重要输出文件：

```text
tests/results/paper_fig2_z_star/summary.jsonl
tests/results/paper_fig2_z_star/summary.csv
tests/results/paper_fig2_z_star/summary.md
tests/results/paper_fig2_z_star/run_config.json
```

验证 Figure 2 数据：

```bash
python3 tests/json_verifier.py tests/results/paper_fig2_az_grid/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig2_az_grid/summary.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig2_z_star/summary.jsonl --strict
```

当前绘图状态：

```text
Figure 2 数据生成脚本已经存在。
Figure 2 z_star 提取脚本已经存在。
Figure 2 绘图脚本尚未实现。
建议脚本名：tests/plot_figure2.py
```

绘图脚本应读取：

```text
tests/results/paper_fig2_az_grid/summary.csv
tests/results/paper_fig2_z_star/summary.csv
```

预期最终图像输出：

```text
tests/results/paper_figures/figure2a_az_heatmap.png
tests/results/paper_figures/figure2a_az_heatmap.pdf
tests/results/paper_figures/figure2b_z_star.png
tests/results/paper_figures/figure2b_z_star.pdf
```

## 3. Figure 3

Figure 3 用启发式公式计算 `(a,z)` 的 XYZ-Sketch 与实用 baseline 做对比。

默认设置为 `C=1/3`、`D=4/3`：

```text
a = C * c_orient / c_peel
z = D * (1-a)^(2/3) * (M/log(1/delta))^(1/3)
```

如果以后要改回 Figure 2 实验选出的 tuned `(a,z)`，可以额外传入：

```text
--xyz-tuning tests/results/paper_fig2_z_star/summary.jsonl
```

### Figure 3(a)、3(b)、3(c)：共享实验

同一个实验会生成 Figure 3 三个 panel 所需的数据：

- Figure 3(a)：communication frontier，使用 `best_R_w30`
- Figure 3(b)：update cost，使用 `update_avg_s_per_element`
- Figure 3(c)：decode cost，使用 `decode_avg_s_per_difference`

运行：

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000 \
  --algorithms xyz_v1,xyz_v2,iblt,minisketch,cpisync,riblt,negentropy \
  --probe-trials 30 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --job-timeout-s 1800 \
  --a-constant 0.3333333333 \
  --z-constant 1.3333333333 \
  --output-dir tests/results/paper_fig3_compare_frontier
```

重要输出文件：

```text
tests/results/paper_fig3_compare_frontier/probes.jsonl
tests/results/paper_fig3_compare_frontier/summary.jsonl
tests/results/paper_fig3_compare_frontier/summary.csv
tests/results/paper_fig3_compare_frontier/summary.md
tests/results/paper_fig3_compare_frontier/run_config.json
tests/results/paper_fig3_compare_frontier/errors.log
```

验证 Figure 3 数据：

```bash
python3 tests/json_verifier.py tests/results/paper_fig3_compare_frontier/probes.jsonl --strict
python3 tests/json_verifier.py tests/results/paper_fig3_compare_frontier/summary.jsonl --strict
```

生成 Figure 3 SVG 图像：

```bash
python3 tests/plot_figure3.py \
  --input tests/results/paper_fig3_compare_frontier/summary.jsonl \
  --output-dir tests/results/paper_figures
```

绘图脚本也支持 CSV。默认会用空心叉号保留 `unresolved` 候选点，但不把它们
连接进通过 90% final validation 的实线；正式图可用 `--hide-unresolved`
只保留通过复验的数据。三个 panel 使用对数横轴和对数纵轴，未提供的零计时值
不会再被画成零成本。

生成文件：

```text
tests/results/paper_figures/figure3a_communication.svg
tests/results/paper_figures/figure3b_update_cost.svg
tests/results/paper_figures/figure3c_decode_cost.svg
tests/results/paper_figures/figure3_source_summary.md
```

当前绘图状态：

```text
Figure 3 SVG 绘图脚本已经存在。
PNG/PDF 导出尚未实现。
test_compare_frontier.py 已接入 xyz_v1、xyz_v2、iblt、minisketch、cpisync、riblt 和 negentropy。xyz_v1 是固定参数 baseline；riblt 使用 max_symbols 做 frontier 搜索。iblt_cpp 仍未接入 frontier 脚本。
```

补上 PNG/PDF 导出后，预期论文图像输出为：

```text
tests/results/paper_figures/figure3a_communication.png
tests/results/paper_figures/figure3a_communication.pdf
tests/results/paper_figures/figure3b_update_cost.png
tests/results/paper_figures/figure3b_update_cost.pdf
tests/results/paper_figures/figure3c_decode_cost.png
tests/results/paper_figures/figure3c_decode_cost.pdf
```

## 4. 论文规模实验前的 Smoke Test

在启动耗时较长的论文规模实验前，建议先跑小规模 smoke test。

Figure 2 smoke：

```bash
python3 tests/test_az_grid.py \
  --d-values 300 \
  --k-values 2 \
  --l-values 6 \
  --a-values 0,0.3333333333,0.6 \
  --z-values 0,1,2,3 \
  --probe-trials 5 \
  --final-trials 10 \
  --target-success-rate 0.9 \
  --shared-datasets \
  --output-dir tests/results/paper_fig2_az_grid_smoke
```

Figure 3 smoke：

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100,300 \
  --algorithms xyz_v1,xyz_v2,iblt,minisketch,cpisync,riblt,negentropy \
  --probe-trials 5 \
  --final-trials 10 \
  --target-success-rate 0.9 \
  --job-timeout-s 1800 \
  --a-constant 0.3333333333 \
  --z-constant 1.3333333333 \
  --output-dir tests/results/paper_fig3_compare_frontier_smoke
```

## 5. 最终结果目录结构

全部成功运行后，预期结果目录为：

```text
tests/results/
  paper_fig1_sharp_threshold/
  paper_fig1_frontier/
  paper_fig2_az_grid/
  paper_fig2_z_star/
  paper_fig3_compare_frontier/
  paper_figures/
```

用于绘图的核心文件是：

```text
Figure 1(a): tests/results/paper_fig1_sharp_threshold/raw.csv
Figure 1(b): tests/results/paper_fig1_frontier/summary.csv
Figure 2(a): tests/results/paper_fig2_az_grid/summary.csv
Figure 2(b): tests/results/paper_fig2_z_star/summary.csv
Figure 3:    tests/results/paper_fig3_compare_frontier/summary.csv
```

## 6. 仍需补齐的工作

要完整生成可用于论文的 Figure 1、Figure 2 和 Figure 3 图像，还需要补以下代码：

```text
1. 新增 tests/plot_figure2.py。
2. 如果论文提交需要 PNG/PDF，为 tests/plot_figure1.py 和 tests/plot_figure3.py 增加转换/导出流程。
3. 可选剩余扩展：把 iblt_cpp 接入 tests/test_compare_frontier.py。xyz_v1 和 riblt 已接入。
```
