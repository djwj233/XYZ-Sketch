# Figure 1(b)(c) implementation

本文件只说明已实现代码的结构与执行命令。实验参数、统计规则和启动顺序以 `README.md` 为准。

## 1. 结构

```text
CMakeLists.txt
cpp/figure1bc_engine.cpp       C++17 ideal-cell simulator
figure1bc/
  simulator.py                独立 Python reference placement/peeling
  engine.py                   C++ engine 严格输入输出适配
  model.py                    C/gamma 候选公式与 direct holdout placement
  evaluation.py               paired words、distinct-placement 分组与 point aggregate
  relative.py                 固定 (d,M) 的 paired relative score 与 tie-break
  calibration.py              bracket、dense grid、adaptive C search 与 freeze
  holdout.py                  sealed Figure 1(b)(c) 数据运行
  figure3.py                  post-freeze 12-panel centered-grid runner
  figure3_plotting.py         3×4 composite 与 panel renderer
  artifacts.py                canonical JSON、正规化 raw rows、原子 point checkpoint 与 manifest
  cli.py                      dry-run、smoke、calibration、holdout 命令
tests/                         unit、golden、equivalence 与状态机测试
```

C++ engine 和 Python reference 都独立实现 audited placement 与 peeling。正式 point 使用 C++ engine；测试逐 trial
比较两者的 placement-word stream、residual edge count、success 和 aggregate。代码不导入、链接或调用
`XYZ-Sketch/` core。

## 2. 数值口径

- `C/gamma/rho` 网格使用整数定点单位构造；
- threshold、`a`、`z_raw` 与 `D_cal` 使用 IEEE-754 binary64；
- `z` 使用 `floor(z_raw+0.5)`；
- Wilson 95% interval 使用双精度计算，`0/n` 和 `n/n` 的数学端点固定为 0 和 1。

## 3. 构建与测试

```bash
cd /root/XYZ-Sketch-experiment/experiment/figure-1bc
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 2
python3 -m unittest discover -s tests -v
python3 -m figure1bc smoke
python3 -m figure1bc dry-run
```

`smoke` 使用 `d=12` 的非正式 fixture，只比较 C++/Python 等价性，不写入 formal aggregate。`dry-run` 只输出
候选和 point 数量上界，不生成 placement word 或 trial。

## 4. Calibration

新正式 calibration：

```bash
python3 -m figure1bc calibrate
```

结果目录为 `results/calibration/<calibration_id>/`。每个 `(stage,d,M)` 完成后先原子写入 `_checkpoints/`；进程中断后：

```bash
python3 -m figure1bc calibrate \
  --resume results/calibration/<calibration_id>
```

terminal 状态不可 resume。C 覆盖全部合法范围；只有大范围 gamma search 得到距上界至少 0.050 的内点 winner 时才生成
`frozen_parameters.json`，其状态为 `selected`。

## 5. Sealed holdout

Holdout 命令只接受 `status=selected`、calibration 全部满足 `d<3000`，并且 threshold/source identity
与 calibration 一致的冻结文件：

```bash
python3 -m figure1bc holdout \
  --frozen results/calibration/<calibration_id>/frozen_parameters.json
```

该命令在同一个 holdout run 中运行 Figure 1(b) 的 `(d,M)=(3000,596)` 和 Figure 1(c) 的
`(d,M)=(10000,1948)`，但使用互相隔离的 seed domain。`holdout_summary.json` 明确记录两个 frozen prediction
是否分别达到 0.9，以及下游实验 gate 是否打开。

本阶段只生成实验数据。SVG/PDF/PNG 绘图按用户指定在数据实验完成后单独实现。

## 6. Appendix Figure 3

Figure 3 数据使用冻结参数及与 sealed holdout 完全相同的 simulator executable：

```bash
python3 -m figure1bc figure3-run \
  --frozen results/calibration/<calibration_id>/frozen_parameters.json \
  --reference-holdout results/holdout/<holdout_id>
```

每个 panel 完成后原子写入 `_checkpoints/figure3<panel>/`。进程被中断时使用：

```bash
python3 -m figure1bc figure3-run \
  --frozen results/calibration/<calibration_id>/frozen_parameters.json \
  --reference-holdout results/holdout/<holdout_id> \
  --resume results/figure3/<figure3_id>
```

数据完成后单独绘图：

```bash
python3 -m figure1bc figure3-plot \
  --figure3-run results/figure3/<figure3_id>
```

图形输出位于 `<figure3_id>/plots-centered-v1/`。`figure3.svg/pdf/png` 是 3 列×4 行完整图；
`figure3a..figure3l` 是独立 panel。Renderer 读取且只读取该 run 的 `aggregate.csv` 和 `run_config.json`。

宽轴探索按 README Section 10.2 逐 round 执行：

```bash
python3 -m figure1bc figure3-wide-run \
  --round 1 \
  --frozen results/calibration/<calibration_id>/frozen_parameters.json \
  --reference-holdout results/holdout/<holdout_id>

python3 -m figure1bc figure3-wide-plot \
  --figure3-run results/figure3-wide/<wide_id>
```

读取 `wide_summary.json` 的 `stop_rule_met`。仅当其为 `false` 时执行 `--round 2`；不得添加第三种未定义轴或
为单个 panel 调整范围。

停止规则满足后，如需 11 列展示分辨率，运行只加密不扩范围的 `dense11` profile：

```bash
python3 -m figure1bc figure3-wide-run \
  --round 3 \
  --frozen results/calibration/<calibration_id>/frozen_parameters.json \
  --reference-holdout results/holdout/<holdout_id>

python3 -m figure1bc figure3-wide-plot \
  --figure3-run results/figure3-wide/<dense11_id>
```

`--round 3` 只是 CLI identity；其 `a` 端点和 `z` 轴必须逐值等于 Round 1，`run_config.json` 必须记录
`resolution_profile=dense11`。

最终合法 7×7 展示使用 `square7` profile：

```bash
python3 -m figure1bc figure3-wide-run \
  --round 4 \
  --frozen results/calibration/<calibration_id>/frozen_parameters.json \
  --reference-holdout results/holdout/<holdout_id>

python3 -m figure1bc figure3-wide-plot \
  --figure3-run results/figure3-wide/<square7_id>
```

`run_config.json` 必须记录 `resolution_profile=square7`、`grid_shape=[7,7]`、selected cell `(2,3)` 和
`vertical_center_required=false`。所有 `z` 必须为非负递增整数。
