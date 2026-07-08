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
- 比较 `random` 和 `naive` 两种模式。
- 使用代表性参数 `(k,l) = (2,3), (2,6), (3,4)`。

运行：

```bash
python3 tests/test_xyz_sharp_threshold.py \
  --d-values 10000 \
  --l-values 3,6,4 \
  --k-values 2,3 \
  --modes random,naive \
  --trials 100 \
  --center-trials 30 \
  --points 41 \
  --target-success-rate 0.9 \
  --circular-a 0 \
  --output-dir tests/results/paper_fig1_sharp_threshold
```

重要输出文件：

```text
tests/results/paper_fig1_sharp_threshold/raw.jsonl
tests/results/paper_fig1_sharp_threshold/raw.csv
tests/results/paper_fig1_sharp_threshold/summary.jsonl
tests/results/paper_fig1_sharp_threshold/summary.csv
tests/results/paper_fig1_sharp_threshold/summary.md
tests/results/paper_fig1_sharp_threshold/run_config.json
```

注意：上面的命令会运行列出的 `k` 和 `l` 的笛卡尔积。如果论文实验只想严格使用
`(2,3), (2,6), (3,4)` 这三个 tuple，需要分别运行命令，或者新增一个 tuple wrapper。

### Figure 1(b)：Communication Frontier

目标：

- 对每个 `d`，搜索达到 90% 成功率所需的最小通信量。
- 比较 iid hashing 和 spatial coupling。
- 在当前代码中，`random = iid`，`naive = spatial coupling`。

运行：

```bash
python3 tests/test_frontier_xyz.py \
  --d-values 100,300,1000,3000,10000 \
  --tuple-values 2:3,2:6,3:4 \
  --modes random,naive \
  --probe-trials 50 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --circular-a 0 \
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
Figure 1 绘图脚本尚未实现。
建议脚本名：tests/plot_figure1.py
```

绘图脚本应读取：

```text
tests/results/paper_fig1_sharp_threshold/raw.csv
tests/results/paper_fig1_frontier/summary.csv
```

预期最终图像输出：

```text
tests/results/paper_figures/figure1a_sharp_threshold.png
tests/results/paper_figures/figure1a_sharp_threshold.pdf
tests/results/paper_figures/figure1b_frontier.png
tests/results/paper_figures/figure1b_frontier.pdf
```

## 2. Figure 2

Figure 2 应该在 Figure 3 之前生成，因为 Figure 3 会使用 Figure 2 提取出的
tuned `(a,z)` 参数。

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
  --d-values 100,300,1000,3000,10000 \
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

Figure 3 用 tuned XYZ-Sketch 与实用 baseline 做对比。

Figure 3 依赖 Figure 2 生成的这个文件：

```text
tests/results/paper_fig2_z_star/summary.jsonl
```

### Figure 3(a)、3(b)、3(c)：共享实验

同一个实验会生成 Figure 3 三个 panel 所需的数据：

- Figure 3(a)：communication frontier，使用 `best_R_w30`
- Figure 3(b)：update cost，使用 `update_avg_s_per_element`
- Figure 3(c)：decode cost，使用 `decode_avg_s_per_difference`

运行：

```bash
python3 tests/test_compare_frontier.py \
  --d-values 100,300,1000,3000,10000 \
  --algorithms xyz_v2,iblt,minisketch \
  --probe-trials 30 \
  --final-trials 100 \
  --target-success-rate 0.9 \
  --xyz-tuning tests/results/paper_fig2_z_star/summary.jsonl \
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
  --input tests/results/paper_fig3_compare_frontier/summary.csv \
  --output-dir tests/results/paper_figures
```

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
test_compare_frontier.py 尚未接入 optional baselines。
当前支持的 baseline：xyz_v2, iblt, minisketch。
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
  --algorithms xyz_v2,iblt,minisketch \
  --probe-trials 5 \
  --final-trials 10 \
  --target-success-rate 0.9 \
  --xyz-tuning tests/results/paper_fig2_z_star/summary.jsonl \
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
1. 新增 tests/plot_figure1.py。
2. 新增 tests/plot_figure2.py。
3. 为 tests/plot_figure3.py 增加 PNG/PDF 导出。
4. 可选：扩展 tests/test_compare_frontier.py，加入更多 baseline：
   xyz_v1, iblt_cpp, cpisync, riblt, negentropy。
```

