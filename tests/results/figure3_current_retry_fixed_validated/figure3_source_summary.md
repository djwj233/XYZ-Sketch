# Figure 3 Plot Source Summary

- Input: `tests/results/figure3_current_retry_fixed.jsonl`
- Rows read: 45
- Algorithms: xyz_v2=9, minisketch=9, iblt=9, riblt=9, cpisync=9
- Statuses: job_timeout=9, ok=36
- Unresolved candidate markers shown: no
- Filled markers and connecting lines: rows passing the 90% final validation.
- Rows below the 90% final validation are hidden and still break connecting lines.
- Figure 3(a): log-log axes; R_w30 = transmitted bits / (30*d).
- Figure 3(b,c): log-log axes. Zero timing values are treated as unavailable, not as zero cost.
- final_ci_low/final_ci_high are success-rate intervals, not communication-threshold error bars, so they are not drawn on the R axis.
- Output format: dependency-free SVG.
