# Paper figures

This directory contains the final renderings selected for the paper. The files are byte-for-byte copies of the experiment outputs; `manifest.json` records their source paths and SHA-256 hashes.

## Layout

| Paper figure | Directory | Contents |
| --- | --- | --- |
| Figure 1(a), paper preferred | `figure-1/figure1a-wilson95-clean.{svg,pdf,png}` | Compact grid-free rendering with light Wilson 95% confidence bands |
| Figure 1(a), original | `figure-1/figure1a.{svg,pdf,png}` | Original three-panel sharp-threshold rendering with verified 0%/100% platforms |
| Figure 1(a), Wilson 95% CI | `figure-1/figure1a-wilson95.{svg,pdf,png}` | Additional rendering with light blue/red/green Wilson 95% confidence bands |
| Figure 1(b) | `figure-1/figure1b.{svg,pdf,png}` | Final 7x7 square heatmap, `d=3,000`, `M=596` |
| Figure 1(c) | `figure-1/figure1c.{svg,pdf,png}` | Final 7x7 square heatmap, `d=10,000`, `M=1,948` |
| Figure 2(a) | `figure-2/figure2a.{svg,pdf,png}` | Communication rate for the five paper-main algorithms |
| Figure 2(b) | `figure-2/figure2b.{svg,pdf,png}` | Conditional update CPU time for the five paper-main algorithms |
| Figure 2(c) | `figure-2/figure2c.{svg,pdf,png}` | Conditional decode CPU time for the five paper-main algorithms |
| Combined Figure 2 | `figure-2/figure2-combined.{svg,pdf,png}` | Three horizontal panels with one shared legend and the five paper-main algorithms |
| Appendix Figure 3 | `appendix-figure-3/figure3.{svg,pdf,png}` | Complete 12-panel calibration diagnostic |

Use SVG or PDF for typesetting and PNG for preview. `figure2-combined` is the
paper-main rendering with a shared legend. The unqualified `figure2{a,b,c}`
files are the corresponding individual panels. Figure 2 uses the final v4
aggregate dated 2026-07-21; resource-limited points remain absent from the
affected curves. Historical extended presentations belong to their earlier
experiment runs and are not part of this selected figure directory.

`manifest.json` indexes the files actually present here. The dedicated
`figure-2/final-plot-manifest.json` records the final Figure 2 rendering hashes.
Compact source aggregates are included in Git; full raw-trial archives remain
on the experiment machine. See `../experiment/REPRODUCING.md`.
