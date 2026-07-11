# Figure 3 Plot Source Summary

- Input: `tests/results/tmp.jsonl`
- Rows read: 36
- Algorithms: xyz_v2=9, iblt=9, riblt=9, negentropy=9
- Statuses: ok=20, unresolved=16
- Unresolved candidate markers shown: no
- Filled markers and connecting lines: rows passing the 90% final validation.
- Rows below the 90% final validation are hidden and still break connecting lines.
- Figure 3(a): log-log axes; R_w30 = transmitted bits / (30*d).
- Figure 3(b,c): log-log axes. Zero timing values are treated as unavailable, not as zero cost.
- final_ci_low/final_ci_high are success-rate intervals, not communication-threshold error bars, so they are not drawn on the R axis.
- No positive `update_avg_s_per_element` measurements for: Negentropy.
- Output format: dependency-free SVG.
