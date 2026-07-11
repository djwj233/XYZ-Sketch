# Figure 3 Plot Source Summary

- Input: `tests/results/emergency_figure2/source.csv`
- Rows read: 23
- Algorithms: xyz_v2=6, minisketch=5, iblt=6, PolyFast=6
- Statuses: ok=23
- Unresolved candidate markers shown: yes
- Filled markers and connecting lines: rows passing the 90% final validation.
- Open crossed markers: measured candidates whose final validation did not reach 90%; they are not connected.
- Figure 3(a): log-log axes; R_w30 = transmitted bits / (30*d).
- Figure 3(b,c): log-log axes. Zero timing values are treated as unavailable, not as zero cost.
- final_ci_low/final_ci_high are success-rate intervals, not communication-threshold error bars, so they are not drawn on the R axis.
- Output format: dependency-free SVG.
