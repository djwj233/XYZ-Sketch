# Final Figure 2 paper images

The paper-main outputs are `figure2a`, `figure2b`, `figure2c`, and
`figure2-combined`, each in SVG, PDF, and PNG format. They contain exactly:

```text
XYZ-Sketch, minisketch, IBLT, Rateless IBLT, CPISync
```

Project IBLT is excluded from the paper-main figures. The three individual PNG
files are 1400 x 1400. The combined PNG is 3000 x 1200 and uses one shared
legend.

The source aggregate is:

```text
/root/XYZ-Sketch-experiment/experiment/figure-2/results/final/
figure2-final-20260721T085150Z/aggregate.json
```

`final-plot-manifest.json` binds every final image to that aggregate. MiniSketch
at `d=10,000` uses the deterministic exact-capacity point and newly measured
timing from the serial 5-dataset, 3-repetition extension.
