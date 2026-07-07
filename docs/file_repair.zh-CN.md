# 文档分叉修复规划

本文档规划如何修复实验系统中的文档分叉问题。

本文档不改变实现行为。目标是让文档清楚地区分：

- 当前已经实现的行为；
- 计划中的目标行为；
- 可选的未来清理工作。

## 问题

一些文档仍然把较旧的项目状态，或者理想中的未来布局，写得像当前事实。

例子：

- `docs/review_001.md` 和 `docs/review_001.zh-CN.md` 仍然把 `failed_decode` 聚合 bug 描述成当前问题，但代码已经修复。
- 一些文档提到目标输出文件，例如：

```text
raw_trials.jsonl
raw_aggregated.jsonl
thresholds.csv
```

但当前脚本常见输出是：

```text
raw.jsonl
probes.jsonl
summary.jsonl
raw.csv
summary.csv
summary.md
run_config.json
```

- 一些文档把 JSON 工作称为统一 schema，而当前实现更准确地说是轻量 normalization 和 verifier 层。
- 一些已完成工作仍然列在 TODO 中，例如第一阶段 XYZ-v2 hash-location deduplication。

这在快速推进的实验仓库中很常见，但会误导后续工作和代码审核。

## 修复原则

### 1. 不重写历史

review 文档可以保留当时的审核上下文，但应该补充状态更新。

使用这些标签：

```text
状态：已修复
状态：部分实现
状态：仍未完成
状态：目标布局，不是当前输出
```

这比直接删除旧问题更好。

### 2. 区分当前布局和目标布局

如果文档提出理想布局，显式标为：

```text
目标布局
```

如果文档描述实际脚本输出，标为：

```text
当前输出
```

不要混在一起写。

### 3. 优先做小范围状态修复

不要一次性重写所有文档。先更新最容易误导当前工作的文档。

### 4. 英文和 zh-CN 文档保持同步

如果某个英文文档有对应中文版本，那么修复英文文档时应在同一个 patch 中更新中文版本。

## 第一批需要修复的文档

### `docs/review_001.md` 和 `docs/review_001.zh-CN.md`

问题：

- 仍然把 `failed_decode` 聚合 bug 描述为当前最高优先级修复。
- 仍然说 per-item hash-location deduplication 没有实现。
- 仍然笼统说很多 shared-dataset migration 缺失，但没有反映 `test_spatial.py` 和 `test_circular_a.py` 已经支持 shared dataset。

修复：

- 在文档开头附近增加简短的 “Status Update / 状态更新” 章节。
- 标记 `failed_decode` 聚合为已修复。
- 如果适用，标记 `SetCircularA` clamp/reject 清理为已修复。
- 标记 XYZ-v2 hash dedup 第一阶段已实现。
- 标记 shared-dataset migration 为部分实现：

```text
已实现：test_spatial.py, test_circular_a.py
剩余：test_xyz_sharp_threshold.py, test_z.py, test_find_best_m.py，如果 test_dlk.py 要进入论文则也需要
```

- 保留未完成项：

```text
external baseline 环境可用性
plotting/table generation
application-side experiments
完整 schema 语义
如果需要，IBLT-SC hash dedup
```

### `docs/todo-list.md` 和 `docs/todo-list.zh-CN.md`

问题：

- 一些优先级条目现在已经部分或完全完成。
- 输出布局示例包含目标名称，但与很多当前脚本不一致。

修复：

- 给优先级条目增加状态标记：

```text
[done]
[partial]
[open]
```

- 更新优先级摘要，把已完成基础设施和剩余科学实验分开。
- 对输出布局章节，把含糊的 “Expected output” 改成：

```text
Current output
```

或者：

```text
Target output layout
```

- 更新 hash dedup 优先级：

```text
XYZ-v2 第一阶段已完成；IBLT-SC 可选/未完成。
```

### `docs/json_verifier.md` 和 `docs/json_verifier.zh-CN.md`

问题：

- 文档描述的是更完整的 canonical schema 目标。
- 当前实现是 `json_schema.py` normalization 加 `json_verifier.py --strict` 通用字段检查。

修复：

- 增加 “Current Implementation / 当前实现” 章节：

```text
json_schema.py 负责 normalize common rows。
json_verifier.py 检查 common fields、数值一致性、已知 record_type 和置信区间基本合法性。
它还没有完整强制算法特有字段、通信模型 caveat 或所有 unavailable 语义。
```

- 增加 “Next Verifier Enhancements / 下一步 verifier 增强” 章节：

```text
status enum
dataset_mode enum
unavailable 必须有 unavailable_reason
failed_decode 是合法 trial outcome
algorithm/implementation 兼容性检查
可选通信模型字段
```

### `docs/data_generator_review.md` 和 `docs/data_generator_review.zh-CN.md`

问题：

- 该文档已经有一些实现状态更新。
- 它应该继续作为 shared-dataset migration 状态的主要参考。

修复：

- 确认 `test_spatial.py` 和 `test_circular_a.py` 标记为已实现。
- 保持剩余迁移列表明确。
- 增加提醒：shared-dataset mode 是可选模式，internal generation 仍然是默认快速路径。

### `docs/test_compare_basic.md` 和 `docs/test_compare_basic.zh-CN.md`

问题：

- 一些 external baseline 状态文字已过时，尤其是 `minisketch`。

修复：

- 标记 `minisketch` 和 `iblt_cpp` 为真实 wrapper。
- 标记 `riblt`、`negentropy`、`cpisync` 为已实现/可选但受环境依赖限制。
- 确认 `failed_decode` 被描述为合法 trial outcome，而不是基础设施错误。

## 输出布局修复

新增一个小的 canonical reference 文档：

```text
docs/results_layout.md
docs/results_layout.zh-CN.md
```

它应该列出当前输出约定。

### 固定参数扫描

适用于：

```text
tests/test_dlk.py
tests/test_z.py
tests/test_circular_a.py --mode fixed-m
```

当前输出：

```text
raw.jsonl
raw.csv
summary.md
run_config.json when available
errors.log when available
```

### Threshold / Search 实验

适用于：

```text
tests/test_find_best_m.py
tests/test_spatial.py
tests/test_iblt_spatial.py
tests/test_circular_a.py --mode threshold
```

当前输出：

```text
probes.jsonl or raw.jsonl
summary.jsonl
summary.csv when available
summary.md when available
run_config.json when available
errors.log when available
```

### Compare 实验

适用于：

```text
tests/test_compare_basic.py
```

当前输出：

```text
raw.jsonl
raw.csv
summary.md
run_config.json
errors.log when needed
```

### 未来目标布局

如果需要，可以把下面布局保留为未来清理目标：

```text
raw_trials.jsonl
raw_aggregated.jsonl
summary.jsonl
summary.csv
summary.md
run_config.json
errors.log
```

但必须标明这是 target/future，不是当前行为。

## JSON Verifier 修复

这个规划项不应该立刻要求完整 schema 重写。

推荐近期实现：

1. 保留 `tests/json_schema.py` 作为 normalization helper。
2. 保持 `tests/json_verifier.py --strict` 对当前 smoke 输出向后兼容。
3. 逐步增加语义检查：

```text
已知 status values
已知 dataset_mode values
unavailable rows 应包含 unavailable_reason
failed_decode 被接受为合法 trial status
trials > 0 时 success_rate 应等于 successes/trials
record_type=unavailable 应搭配 status=unavailable
record_type=error 应搭配 error-like status
```

4. 在对所有历史输出变成 hard failure 之前，先用 warning 或可选 stricter 模式过渡。

## 建议修复顺序

1. 更新 `review_001` 英文和 zh-CN 状态。
2. 更新 `todo-list` 英文和 zh-CN 状态。
3. 新增 `results_layout.md` 和 `results_layout.zh-CN.md`。
4. 更新 JSON verifier 文档，诚实描述当前轻量实现。
5. 更新 compare/basic 文档中的 external baseline 当前状态。
6. 可选地在代码中增加 verifier 语义检查。
7. 用 `rg` 做文档一致性扫描。

## 一致性扫描

修复后，扫描这些容易过时的短语：

```powershell
rg -n "failed_decode aggregation|not implemented|尚未实现|raw_trials.jsonl|raw_aggregated.jsonl|thresholds.csv|scaffolded" docs
```

不是每个命中都是错的。每个命中都要确认文本明确说明它属于：

```text
历史上下文
当前状态
未来目标
未完成 TODO
```

## 验收标准

修复完成时应满足：

- `review_001` 不再把已修复 bug 描述成当前 blocker。
- `todo-list` 能区分 done、partial 和 open tasks。
- 结果文件名被清楚标注为当前输出或未来目标布局。
- JSON 文档准确描述当前轻量 verifier。
- 英文和 zh-CN 文档对任务状态保持一致。
- 读者不需要重读整个 git history，也能判断下一步该实现什么。

