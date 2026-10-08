# XYZ-Sketch experiments

Source code, measured results, and one-command experiment runners for XYZ-Sketch.

```
algorithms/   XYZ-Sketch before and after optimization, baselines, dependencies
scripts/      build, measurement, verification, and plotting commands
results/      measured data, configurations, validation, and figures
```

`algorithms/XYZ-Sketch-unoptimized/` is the original prime-field implementation.
`algorithms/XYZ-Sketch-optimized/` is the accepted GF(2^30) implementation (v15).
See [OPTIMIZATIONS.md](OPTIMIZATIONS.md) for a short description of the changes.
The ell=10 entry point only extends the parameter whitelist; ell<=8 uses the specialized routines.

## Paper correspondence

The supplied `finalpaper.pdf` has 37 pages and describes prime-field experiments in Figures 1--3.
Those results are under `results/paper/` and `results/reference/`. The accepted binary-field
evaluation is under `results/optimized/` and the other named experiment folders.
They are separate measurements and must not be combined under one implementation label.

There is one manuscript discrepancy: the supplied PDF prints C~0.276 and D~0.5,
whereas the recorded calibration used C=0.875 and D=1.1884504306083168.
The runners reproduce the recorded configurations. They do not manufacture a calibration
record for the different constants printed in that PDF.

## Requirements

Linux, Python 3.8+, GCC with C++17, OpenSSL development headers, Go 1.21+,
and NTL/GMP development libraries for CPISync. The optimized native backend requires
x86 PCLMUL support. All upstream source dependencies are included, with versions in
`algorithms/dependencies/versions.json` and their license files beside the code.

On Ubuntu, install the system packages `build-essential libssl-dev libntl-dev libgmp-dev`.
For plots, install the Python packages in `scripts/requirements.txt` in a virtual environment.
Set `GO=/path/to/go` if the appropriate Go executable is not on PATH.

From the repository root:

```bash
python3 scripts/reproduce.py verify
python3 scripts/build.py xyz
python3 scripts/reproduce.py optimized-comparison --d 100 --method xyz --smoke
python3 scripts/reproduce.py figures
```

The smoke command measures a small input, not a formal data point. The figures command
regenerates plots from stored measurements and performs no new trials.
Every measurement command below builds the required engines automatically.

## One-command experiment map

| Result | Command | Stored result |
|---|---|---|
| Supplied PDF Figure 1(a), original full-implementation threshold | `python3 scripts/reproduce.py paper-threshold` | `results/reference/threshold/` |
| Supplied PDF Figures 1(b), 1(c), and 3, ideal-cell heatmaps | `python3 scripts/reproduce.py paper-heatmaps` | `results/reference/heatmaps.csv` |
| Supplied PDF Figure 2(a)--(c), original end-to-end comparison | `python3 scripts/reproduce.py paper-comparison` | `results/paper/` |
| Tables 3--5, peeling/orientability thresholds and ratios | `python3 scripts/reproduce.py threshold-tables` | `results/threshold-tables/` |
| Recorded C,D heuristic fit, final fixed grid | `python3 scripts/reproduce.py heuristic-calibration` | `results/calibration/` |
| Accepted GF(2^30) main timing, with paired original IBLT | `python3 scripts/reproduce.py optimized-comparison` | `results/optimized/` |
| GF(2^30) k/ell timing, including ell=8,10 | `python3 scripts/reproduce.py optimized-parameters` | `results/optimized/`, `results/parameters/` |
| GF(2^30) sharp threshold, d=10^4, 10^7 elements per side | `python3 scripts/reproduce.py optimized-sharp --workers 8` | `results/sharp/` |
| Compact-count IBLT and IBLT+SC, communication and decoding | `python3 scripts/reproduce.py compact-baselines` | `results/compact-iblt/` |
| Paper-faithful Rateless IBLT, communication and CPU phases | `python3 scripts/reproduce.py rateless` | `results/rateless/` |
| Rateless paper's representative count and symbol-count checks | `python3 scripts/reproduce.py rateless-representative` | `results/rateless/representative-summary.json` |
| Extra timing points d=200,000 and 500,000 | `python3 scripts/reproduce.py extra-points` | `results/extra-points/` |
| IBLT fingerprint sensitivity, d=10^5 | `python3 scripts/reproduce.py fingerprint-100000 --workers 8` | `results/fingerprint/100000/` |
| IBLT fingerprint sensitivity, d=10^6 | `python3 scripts/reproduce.py fingerprint-1000000 --workers 8` | `results/fingerprint/1000000/` |
| All included plots, from stored data | `python3 scripts/reproduce.py figures` | Fresh `results/runs/*-figures-*/` |

Table 1 summarizes analytical/literature bounds, and Table 2 defines notation; neither is
an empirical experiment. Mathematical theorem proofs are in the paper.

For the accepted GF(2^30) eight-panel presentation: panel (a) uses `optimized-sharp`,
(b)--(c) use `optimized-parameters`, (d) uses `paper-heatmaps`, (e) uses
`compact-baselines` and `rateless`, and (f)--(h) combine the named comparison campaigns.
`figures` also generates the communication-breakdown plot directly from measured
field sizes. It does not mix fixed-prefix Rateless data into the accepted plots.

`reference-comparison` additionally replays the common-input prime-field evaluation
used to select the accepted implementation's configurations. It is distinct from the
earlier supplied-PDF measurement batch.

Use `--dry-run` to inspect a campaign without building or running it. Use `--d`,
`--method`, `--kind timing`, `--kind communication`, or `--limit` to select jobs.
Do not present a limited or smoke run as the full experiment.
Run timings with `--workers 1 --cpu N`; multiple workers are intended for probability
experiments, not for reproducing the reported single-core timing conditions.

## Inputs and outputs

Each full input contains 10^7 elements per side unless the recorded protocol specifies
otherwise. Raw input binaries remain on the experiment server and are not in Git.
`scripts/inputs.json` records the generator seeds, source paths, and available SHA-256
hashes. Earlier paper records contain input-array hashes rather than a file hash;
the runner checks that recorded metadata when regenerating those inputs.

On the original server, reuse the existing files:

```bash
python3 scripts/reproduce.py optimized-comparison --data-root /root/XYZ-Sketch-experiment
```

Elsewhere, omit `--data-root` or point it to a new cache directory. Missing inputs are
generated deterministically and verified. Existing inputs with a recorded file hash
are checked before use. Full campaigns need considerable disk space and CPU time;
`--dry-run` shows the number of jobs before execution.

Runs create a fresh directory under `results/runs/`, containing raw records, input
receipts, protocol, summaries, and validation. `--out` may specify a new directory.
Existing outputs are never overwritten. Build products, generated inputs, and new runs
are excluded from Git. Stored failures and timeouts are retained rather than retried
until success. Ground truth is used for output validation, not as a decoder stop oracle.

## Measurement conventions

Reported timings used an Intel Core i9-10980XE, GCC 9.4.0, and Go 1.21.13.
Use three repetitions on each of five successful datasets, average within each dataset,
then report the mean and a 95% bootstrap interval over the five means.
Full fixed-sketch decoding includes sender serialization, in-memory transfer, and
receiver parsing, subtraction, recovery, and output normalization. Input generation
and the final exact-output comparison are outside algorithm timing.

The accepted Rateless runner keeps the official 64-bit hash, encodes counts as deviations
from their expectation with signed variable-length encoding, and generates coded symbols
until the incremental decoder reports completion. Its communication uses 100 inputs per
scale. Its ingestion time is an encoder API measurement; full decoding includes sender
generation, receiver processing, and wire encoding/decoding. It is not a fixed-sketch
update interface. `results/rateless/` includes representative-paper checks and field-level
byte accounting.

The original paper's Rateless adapter used a fixed prefix and a truncated hash. It is
retained only to reproduce the supplied PDF's data and is explicitly labelled
`paper-rateless`/`rateless-fixed`, not as the faithful current baseline.

Compact IBLT/IBLT+SC restores every counter exactly and retains the 30-bit key and
32-bit checksum. Use its own codec timing with its communication results. Fingerprint
experiments count exact signed recovery as success, retain all failures, and enforce
the recorded 10d peel/100M inspection budgets.

Source hashes are in `results/source-manifest.json`. New machines can reproduce
inputs, configurations, outputs, and accounting; CPU times will vary with hardware
and system load. Packaged verification does not claim that every full campaign was
rerun during repository assembly.
