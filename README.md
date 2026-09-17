# XYZ-Sketch

XYZ-Sketch reconciles two sets by exchanging a compact sketch and recovering
both directed differences. The C++17 implementation combines truncated
characteristic polynomials over `F_998244353` with spatially coupled hashing.

## Project status

This repository includes the core implementation, the paper experiment suite,
and the selected figures. The status below was checked on 2026-09-16 against
the saved run artifacts; it does not imply that every baseline completed every
requested problem size.

| Component | Saved result |
| --- | --- |
| Threshold formulas | 48 validated entries; validation report in `experiment/threshold/` |
| Figure 1(b)(c) calibration and holdout | Parameters selected and frozen; holdout complete |
| Figure 1(a) | Final dense run complete: 627 points, 62,700 trials, nine curves; reduced-cardinality revision (`|A|=|B|=20,000`) |
| Figure 2 | Final v4 aggregate and five-baseline plots complete; large MiniSketch/CPISync points retain resource-limit statuses |
| Appendix Figure 3 | Final 12-panel diagnostic generated |

Start with [the experiment guide](experiment/README.md),
[build and archive instructions](experiment/REPRODUCING.md), and
[the figure index](figures/README.md). Raw trials and checkpoints total about
70 GB on the experiment machine and are **not included in Git**. The repository
contains compact result snapshots with checksums in
[`experiment/artifact-index.json`](experiment/artifact-index.json).

## Repository Structure

```text
XYZ-Sketch/          XYZ-Sketch implementation and end-to-end sample
IBLT/                Conventional IBLT implementation and sample
docs/                Complete usage guides for XYZ-Sketch and IBLT
external/            Third-party reconciliation implementations (submodules)
experiment/          Experiment sources, tests, protocols and compact result snapshots
figures/             Selected paper figures (SVG, PDF and PNG)
patches/             Reproducible changes required by experiment baselines
```

External submodules:

- [MiniSketch](https://github.com/bitcoin-core/minisketch)
- [Rateless IBLT](https://github.com/yangl1996/riblt)
- [IBLT C++](https://github.com/gavinandresen/IBLT_Cplusplus)
- [CPISync](https://github.com/Bowenislandsong/cpisync)

## XYZ-Sketch Sample

Run from the repository root:

```bash
g++ -std=c++17 -O2 XYZ-Sketch/sample.cpp -o /tmp/xyz_sketch_sample \
  && /tmp/xyz_sketch_sample
```

## IBLT Sample

Run from the repository root:

```bash
g++ -std=c++17 -O2 IBLT/iblttest.cpp -o /tmp/iblt_sample \
  && /tmp/iblt_sample
```

Read [the XYZ-Sketch usage guide](docs/XYZ-Sketch.md) for the API, input
constraints, shared parameters and serialization format.
