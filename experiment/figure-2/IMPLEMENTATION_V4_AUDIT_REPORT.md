# Figure 2 v4 implementation audit report

## Result

Status: `pass_for_v4_trials`.

The v4 implementation summary SHA-256 is
`c7bbee1ea203f0e8d3d72c963a25fea1b83ede9d2844f3c5412480fe4b475907`.
Every child artifact hash recorded by that summary was independently recomputed and matched.

## Findings

- `XYZ-Sketch/` and project `IBLT/` have no diff. Core algorithms are unchanged.
- The external conventional-IBLT patch is limited to read-only cell count and canonical
  serialization/deserialization. Its golden table has four cells, 348 logical bits, and 352 serialized bits.
- Rateless IBLT uses 30 Symbol bits, 49 truncated SipHash bits, and 25 Count bits. The maximum-`d`
  collision union bound is `0.000888178 < 0.001`. Encoder and fixed-cap Sketch agree in all 18 golden cases.
- All six shared-dataset smoke outputs match the exact directed ground truth.
- All 120 existing full-vs-difference equivalence configurations match residual state, status, and output.
- The v4 runner migrates unchanged v3 algorithms by parent aggregate hash, migrates conventional-IBLT
  probability only, and reruns every probability or timing path affected by the v4 profiles. A RIBLT
  confirmation below 90/100 advances through independent q95, q99, q100, and at most `3d` blocks.
- Probability execution is pinned across physical CPUs 0-7. Timing execution is serial on CPU 0 with
  five successful datasets, three repetitions per dataset, and no warm-up.

No formal v4 discovery, confirmation, or timing trial was executed before this report.
