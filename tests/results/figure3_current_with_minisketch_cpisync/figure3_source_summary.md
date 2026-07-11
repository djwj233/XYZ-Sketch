# Figure 3 Plot Source Summary

- Input: `tests/results/figure3_current_with_minisketch_cpisync.jsonl`
- Rows read: 54
- Algorithms: xyz_v2=9, minisketch=9, iblt=9, riblt=9, cpisync=9, negentropy=9
- Statuses: job_timeout=9, ok=29, unresolved=16
- Unresolved candidate markers shown: yes
- Filled markers and connecting lines: rows passing the 90% final validation.
- Open crossed markers: measured candidates whose final validation did not reach 90%; they are not connected.
- Figure 3(a): log-log axes; R_w30 = transmitted bits / (30*d).
- Figure 3(b,c): log-log axes. Zero timing values are treated as unavailable, not as zero cost.
- final_ci_low/final_ci_high are success-rate intervals, not communication-threshold error bars, so they are not drawn on the R axis.
- No positive `update_avg_s_per_element` measurements for: CPISync, Negentropy.
- Output format: dependency-free SVG.
