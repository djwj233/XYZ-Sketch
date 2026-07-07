# Threshold Search 置信区间计划

本文档规划如何给现有 threshold-search 脚本加入二项分布置信区间。这里先不实现代码。

目标脚本：

```text
tests/test_find_best_m.py
tests/test_spatial.py
```

这两个脚本都会搜索达到目标解码成功率所需的最小 `M`。它们目前已经记录：

```text
trials
successes
success_rate
target_success_rate
best_M
best_C_over_d
```

缺少的是不确定性信息：`99/100 = 0.99` 并不等价于我们已经知道真实成功概率至少是 `0.99`。

## 目标

1. 给每个 probe row 加入置信区间。
2. 给每个最终 threshold row 加入置信区间。
3. 报告几种不同的阈值解释：

```text
点估计阈值
置信区间下界阈值
不确定阈值范围
```

4. 保持现有脚本的默认用法可用。
5. 保持 JSON 输出兼容 `benchmark.v1`。

## 统计模型

每次 decode 尝试视为一个 Bernoulli trial：

```text
success = 1 表示 reconciliation 成功
success = 0 表示失败
```

对于一个 probe：

```text
s = successes
n = trials
p_hat = s / n
```

计算置信区间：

```text
ci_low <= p <= ci_high
```

第一版建议使用 Wilson score interval，因为它对小样本和大样本都比简单正态近似稳健，有闭式公式，并且不需要额外 Python 依赖。

默认值：

```text
ci_method = "wilson"
ci_confidence = 0.95
z = 1.959963984540054
```

后续如果需要 exact interval，再把 Clopper-Pearson 作为可选模式加入。

## Wilson 区间公式

对置信水平 `1 - alpha` 和正态分位数 `z`：

```text
denom = 1 + z^2 / n
center = (p_hat + z^2 / (2n)) / denom
half = z * sqrt((p_hat * (1 - p_hat) / n + z^2 / (4n^2))) / denom
ci_low = max(0, center - half)
ci_high = min(1, center + half)
```

如果 `n = 0`，使用：

```text
ci_low = 0
ci_high = 1
```

并且该 row 不应用于阈值判断。

## 新增共享 Helper

创建一个无外部依赖的小 helper：

```text
tests/statistics.py
```

建议 API：

```python
def normal_z(confidence: float) -> float:
    ...

def wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    ...

def add_binomial_ci(row: dict[str, Any], confidence: float, method: str = "wilson") -> dict[str, Any]:
    ...
```

`normal_z()` 可以先支持常用置信水平，不引入 SciPy：

```text
0.90 -> 1.6448536269514722
0.95 -> 1.959963984540054
0.99 -> 2.5758293035489004
```

如果用户传入未支持的值，第一版直接给出清晰错误。

## JSON 字段

给 probe rows 和 threshold rows 加入：

```text
ci_method
ci_confidence
ci_low
ci_high
```

对于 threshold summary，还加入：

```text
threshold_policy
point_estimate_reaches_target
ci_low_reaches_target
ci_high_reaches_target
```

含义：

```text
point_estimate_reaches_target = success_rate >= target_success_rate
ci_low_reaches_target = ci_low >= target_success_rate
ci_high_reaches_target = ci_high >= target_success_rate
```

解释：

- 如果 `ci_low_reaches_target` 为 true，说明有较强证据认为该 `M` 达到目标。
- 如果只有 `point_estimate_reaches_target` 为 true，说明点估计达到目标，但仍有不确定性。
- 如果 `ci_high_reaches_target` 为 false，说明该 `M` 很可能低于目标。
- 如果 `ci_low < target <= ci_high`，说明结果处于不确定区域。

## 阈值策略

现有脚本使用点估计逻辑：

```text
successes >= ceil(target_success_rate * trials)
```

为了向后兼容，这应继续作为默认策略：

```text
--threshold-policy point
```

新增更严格的选项：

```text
--threshold-policy ci-low
```

策略行为：

```text
point:
    success_rate >= target_success_rate 时认为 works

ci-low:
    ci_low >= target_success_rate 时认为 works
```

当目标成功率很高时，`ci-low` 策略需要更多 trials。例如要以 95% 置信度证明下界接近 `0.99`，可能需要数百甚至数千次成功。因此默认不应该悄悄切换到 `ci-low`。

## 搜索流程变化

### Probe 阶段

每个 `run_probe()` 应该：

1. 运行 C++ benchmark；
2. 解析 JSON；
3. 附加 search metadata；
4. 附加置信区间字段；
5. 通过 `benchmark.v1` normalize。

`works()` 函数应该使用 `args.threshold_policy`。

### Final Validation 阶段

final validation row 通常使用比 probe 更多的 trials。它应该记录：

```text
final_successes
final_success_rate
final_ci_low
final_ci_high
final_ci_method
final_ci_confidence
```

为了避免含义重复，也可以保留通用字段：

```text
successes
success_rate
ci_low
ci_high
```

其中通用字段指 final validation 的测量结果。

## 阈值不确定性输出

Binary search 只测试对数数量的 `M`，所以它不会完整描绘 threshold curve。但脚本仍然可以从已测试 probes 中总结不确定性。

对于同一次 search 的所有 probes：

```text
point_best_M = 已测试 M 中 success_rate >= target 的最小值
ci_low_best_M = 已测试 M 中 ci_low >= target 的最小值
uncertain_M_min = 已测试 M 中 ci_high >= target 且 ci_low < target 的最小值
uncertain_M_max = 已测试 M 中 ci_high >= target 且 ci_low < target 的最大值
```

summary rows 增加这些字段：

```text
point_best_M
point_best_C_over_d
ci_low_best_M
ci_low_best_C_over_d
uncertain_M_min
uncertain_M_max
uncertain_C_over_d_min
uncertain_C_over_d_max
```

第一版可以只基于已测试 probe list 填充这些字段，不要求做完整密集扫描。

## 脚本级计划

### `tests/test_find_best_m.py`

新增 CLI 参数：

```text
--ci-confidence 0.95
--ci-method wilson
--threshold-policy point|ci-low
```

更新：

```text
SUMMARY_FIELDS
run_probe()
works()
summary_from_final()
main loop summary construction
```

最终 summary 应同时包含：

```text
best_M
best_C_over_d
```

用于表示所选策略下的阈值，以及上面列出的 point/CI 备选阈值。

### `tests/test_spatial.py`

应用同样修改。因为该脚本比较不同 mode，每个带 CI 的 row 和 summary 都要保留 `mode`。

summary table 应方便比较：

```text
mode
所选策略下的 best_M
point_best_M
ci_low_best_M
final_success_rate
final_ci_low
final_ci_high
```

## CSV 更新

向 `SUMMARY_FIELDS` 加入：

```text
ci_method
ci_confidence
final_ci_low
final_ci_high
threshold_policy
point_estimate_reaches_target
ci_low_reaches_target
ci_high_reaches_target
point_best_M
point_best_C_over_d
ci_low_best_M
ci_low_best_C_over_d
uncertain_M_min
uncertain_M_max
```

保留旧字段，避免已有 notebook 和 summary 立刻失效。

## Verifier 更新

`tests/json_verifier.py` 应允许这些可选字段：

```text
ci_method
ci_confidence
ci_low
ci_high
```

当字段存在时，应检查：

```text
0 <= ci_low <= ci_high <= 1
0 < ci_confidence < 1
```

这是一个小扩展，不需要新的 schema version。

## 测试计划

### Unit-Style CI Checks

给 `wilson_interval()` 加一些直接检查：

```text
0/10 的 ci_low = 0 且 ci_high > 0
10/10 的 ci_high = 1 且 ci_low < 1
5/10 的中心接近 0.5
更大的 n 会让区间变窄
```

这些可以是 smoke path 中的简单 assertions，或者一个小脚本调用。

### Smoke Run

运行一个很小的 threshold search：

```powershell
python tests\test_find_best_m.py --d-values 100 --l-values 6 --k-values 2 --probe-trials 3 --final-trials 5 --limit 1 --ci-confidence 0.95 --threshold-policy point --output-dir tests\results\ci_best_m_smoke --skip-build
```

校验：

```powershell
python tests\json_verifier.py tests\results\ci_best_m_smoke\probes.jsonl tests\results\ci_best_m_smoke\summary.jsonl --strict
```

运行 spatial smoke：

```powershell
python tests\test_spatial.py --d-values 100 --l-values 6 --k-values 2 --modes spatial --probe-trials 3 --final-trials 5 --limit 1 --ci-confidence 0.95 --threshold-policy point --output-dir tests\results\ci_spatial_smoke --skip-build
```

### Policy Comparison Smoke

用同一个小 case 运行：

```text
--threshold-policy ci-low
```

预期行为：

```text
ci-low 可能需要更大的 M，或者变成 unresolved
point policy 应匹配旧行为
```

## 推荐默认值

使用：

```text
ci_method = wilson
ci_confidence = 0.95
threshold_policy = point
```

对于可发表或高置信度阈值结论，使用：

```text
target_success_rate = 0.99
ci_confidence = 0.95
threshold_policy = ci-low
final_trials >= 300
```

这会贵很多，所以应该显式选择。

## 完成标准

这个任务完成时应满足：

```text
tests/statistics.py 存在
test_find_best_m.py 在 probes 和 summaries 中记录 CI 字段
test_spatial.py 在 probes 和 summaries 中记录 CI 字段
两个脚本都暴露 --ci-confidence、--ci-method 和 --threshold-policy
point policy 复现旧阈值行为
ci-low policy 可用于更严格结论
json_verifier.py 在 CI 字段存在时校验它们
smoke runs 通过 strict JSON verification
```

