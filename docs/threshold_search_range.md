# Threshold Search Confidence Interval Plan

This document plans how to add binomial confidence intervals to the existing threshold-search scripts. No code is implemented here.

Target scripts:

```text
tests/test_find_best_m.py
tests/test_spatial.py
```

Both scripts search for the smallest `M` that reaches a target decoding success rate. They already record:

```text
trials
successes
success_rate
target_success_rate
best_M
best_C_over_d
```

The missing piece is uncertainty: a result like `99/100 = 0.99` is not the same as knowing the true success probability is at least `0.99`.

## Goals

1. Add confidence intervals to every probe row.
2. Add confidence intervals to every final threshold row.
3. Report several threshold interpretations:

```text
point_estimate threshold
lower_confidence_bound threshold
uncertain threshold range
```

4. Keep the existing scripts usable with their current defaults.
5. Keep JSON output compatible with `benchmark.v1`.

## Statistical Model

Each decode attempt is treated as a Bernoulli trial:

```text
success = 1 if reconciliation succeeds
success = 0 otherwise
```

For a probe with:

```text
s = successes
n = trials
p_hat = s / n
```

compute a confidence interval:

```text
ci_low <= p <= ci_high
```

The first implementation should use the Wilson score interval because it is accurate for small and large samples, has a closed-form formula, and does not require external Python dependencies.

Default:

```text
ci_method = "wilson"
ci_confidence = 0.95
z = 1.959963984540054
```

Later, if exact intervals are needed, add Clopper-Pearson behind an optional mode.

## Wilson Interval Formula

For confidence level `1 - alpha` and normal quantile `z`:

```text
denom = 1 + z^2 / n
center = (p_hat + z^2 / (2n)) / denom
half = z * sqrt((p_hat * (1 - p_hat) / n + z^2 / (4n^2))) / denom
ci_low = max(0, center - half)
ci_high = min(1, center + half)
```

If `n = 0`, use:

```text
ci_low = 0
ci_high = 1
```

and mark the row as unusable for threshold decisions.

## New Shared Helper

Create a small dependency-free helper:

```text
tests/statistics.py
```

Recommended API:

```python
def normal_z(confidence: float) -> float:
    ...

def wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    ...

def add_binomial_ci(row: dict[str, Any], confidence: float, method: str = "wilson") -> dict[str, Any]:
    ...
```

`normal_z()` can support common confidence levels without SciPy:

```text
0.90 -> 1.6448536269514722
0.95 -> 1.959963984540054
0.99 -> 2.5758293035489004
```

If a user passes an unsupported value, fail with a clear error in the first implementation.

## JSON Fields

Add these fields to probe rows and threshold rows:

```text
ci_method
ci_confidence
ci_low
ci_high
```

For threshold summaries, also add:

```text
threshold_policy
point_estimate_reaches_target
ci_low_reaches_target
ci_high_reaches_target
```

Meanings:

```text
point_estimate_reaches_target = success_rate >= target_success_rate
ci_low_reaches_target = ci_low >= target_success_rate
ci_high_reaches_target = ci_high >= target_success_rate
```

Interpretation:

- If `ci_low_reaches_target` is true, the evidence is strong that this `M` reaches the target.
- If only `point_estimate_reaches_target` is true, the estimate reaches the target but uncertainty remains.
- If `ci_high_reaches_target` is false, this `M` is very likely below target.
- If `ci_low < target <= ci_high`, the result is uncertain.

## Threshold Policies

The existing scripts use point-estimate logic:

```text
successes >= ceil(target_success_rate * trials)
```

This should remain the default for backward compatibility:

```text
--threshold-policy point
```

Add a stricter option:

```text
--threshold-policy ci-low
```

Policy behavior:

```text
point:
    works if success_rate >= target_success_rate

ci-low:
    works if ci_low >= target_success_rate
```

The `ci-low` policy requires many more trials when target success is high. For example, proving a lower bound near `0.99` with 95% confidence may require hundreds or thousands of successes. Therefore the default should not silently switch to `ci-low`.

## Search Procedure Changes

### Probe Phase

Every `run_probe()` should:

1. run the C++ benchmark;
2. parse JSON;
3. attach search metadata;
4. attach confidence interval fields;
5. normalize through `benchmark.v1`.

The `works()` function should use `args.threshold_policy`.

### Final Validation Phase

The final validation row should usually use more trials than probe rows. It should record:

```text
final_successes
final_success_rate
final_ci_low
final_ci_high
final_ci_method
final_ci_confidence
```

To avoid duplicated meaning, the row can also keep the generic fields:

```text
successes
success_rate
ci_low
ci_high
```

where generic fields refer to the final validation measurement.

## Threshold Uncertainty Output

Binary search only tests a logarithmic number of `M` values, so it does not fully map the threshold curve. Still, the scripts can summarize uncertainty from the tested probes.

For all probes in one search:

```text
point_best_M = smallest tested M with success_rate >= target
ci_low_best_M = smallest tested M with ci_low >= target
uncertain_M_min = smallest tested M with ci_high >= target and ci_low < target
uncertain_M_max = largest tested M with ci_high >= target and ci_low < target
```

Add these fields to summary rows when available:

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

For the first implementation, it is acceptable to fill these from the tested probe list, not from an exhaustive scan.

## Script-Specific Plan

### `tests/test_find_best_m.py`

Add CLI arguments:

```text
--ci-confidence 0.95
--ci-method wilson
--threshold-policy point|ci-low
```

Update:

```text
SUMMARY_FIELDS
run_probe()
works()
summary_from_final()
main loop summary construction
```

The final summary should include both:

```text
best_M
best_C_over_d
```

for the policy-selected threshold, and the point/CI alternatives listed above.

### `tests/test_spatial.py`

Apply the same changes. Because this script compares modes, keep `mode` in every CI-bearing row and summary.

The summary table should make it easy to compare:

```text
mode
best_M under selected policy
point_best_M
ci_low_best_M
final_success_rate
final_ci_low
final_ci_high
```

## CSV Updates

Add to `SUMMARY_FIELDS`:

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

Keep old fields so existing notebooks and summaries do not immediately break.

## Verifier Updates

`tests/json_verifier.py` should allow these optional fields:

```text
ci_method
ci_confidence
ci_low
ci_high
```

It should check, when present:

```text
0 <= ci_low <= ci_high <= 1
0 < ci_confidence < 1
```

This can be a small extension, not a new schema version.

## Testing Plan

### Unit-Style CI Checks

Add a few direct checks for `wilson_interval()`:

```text
0/10 has ci_low = 0 and ci_high > 0
10/10 has ci_high = 1 and ci_low < 1
5/10 is centered near 0.5
larger n narrows the interval
```

These can be simple assertions in a smoke path or a small script invocation.

### Smoke Run

Run a tiny threshold search:

```powershell
python tests\test_find_best_m.py --d-values 100 --l-values 6 --k-values 2 --probe-trials 3 --final-trials 5 --limit 1 --ci-confidence 0.95 --threshold-policy point --output-dir tests\results\ci_best_m_smoke --skip-build
```

Verify:

```powershell
python tests\json_verifier.py tests\results\ci_best_m_smoke\probes.jsonl tests\results\ci_best_m_smoke\summary.jsonl --strict
```

Run spatial smoke:

```powershell
python tests\test_spatial.py --d-values 100 --l-values 6 --k-values 2 --modes spatial --probe-trials 3 --final-trials 5 --limit 1 --ci-confidence 0.95 --threshold-policy point --output-dir tests\results\ci_spatial_smoke --skip-build
```

### Policy Comparison Smoke

Run the same tiny case with:

```text
--threshold-policy ci-low
```

Expected behavior:

```text
ci-low may require a larger M or become unresolved
point policy should match old behavior
```

## Recommended Defaults

Use:

```text
ci_method = wilson
ci_confidence = 0.95
threshold_policy = point
```

For publishable or high-confidence threshold claims, use:

```text
target_success_rate = 0.99
ci_confidence = 0.95
threshold_policy = ci-low
final_trials >= 300
```

This is much more expensive, so it should be an explicit choice.

## Completion Criteria

This task is complete when:

```text
tests/statistics.py exists
test_find_best_m.py records CI fields in probes and summaries
test_spatial.py records CI fields in probes and summaries
both scripts expose --ci-confidence, --ci-method, and --threshold-policy
point policy reproduces old threshold behavior
ci-low policy is available for stricter claims
json_verifier.py validates CI fields when present
smoke runs pass strict JSON verification
```

