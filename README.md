# XYZ-Sketch

XYZ-Sketch is a sketch for set reconciliation: two parties exchange a compact sketch
to recover the elements present in only one of their sets.
This repository includes the implementations, baselines, and experiments from the paper.

```
algorithms/   XYZ-Sketch, baselines, and dependencies
scripts/      experiment runners and plotting scripts
results/      measurements, configurations, and figures
```

[XYZ-Sketch-optimized](algorithms/XYZ-Sketch-optimized/) uses GF(2^30).
[XYZ-Sketch-unoptimized](algorithms/XYZ-Sketch-unoptimized/) preserves the original
prime-field implementation. [OPTIMIZATIONS.md](OPTIMIZATIONS.md) summarizes the main
optimization techniques.

## Quick start

Clone the repository:

```bash
git clone --branch paper-artifact https://github.com/djwj233/XYZ-Sketch.git
cd XYZ-Sketch
```

Run from the repository root. Both examples require GCC with C++17; the optimized
example additionally requires an x86 CPU with PCLMUL support.

**XYZ-Sketch (optimized):**

```bash
g++ -std=c++17 -O2 -mpclmul -DXYZ_TABLE_SQUARES -DXYZ_DYNAMIC_RECON \
    algorithms/XYZ-Sketch-optimized/sample.cpp -o /tmp/xyz_sketch_sample \
    && /tmp/xyz_sketch_sample
```

**XYZ-Sketch (unoptimized):**

```bash
g++ -std=c++17 -O2 algorithms/XYZ-Sketch-unoptimized/sample.cpp \
    -o /tmp/xyz_sketch_unoptimized_sample \
    && /tmp/xyz_sketch_unoptimized_sample
```

Both examples encode two sets, serialize Alice's sketch, and recover the directed
differences: Alice-only elements `{2, 8, 9}` and Bob-only elements `{12, 28, 39}`.
The optimized example checks the recovered values and exits with an error on failure.

## Reproduce the experiments

The experiment runners require Linux, Python 3.8+, GCC, OpenSSL development headers,
and Go 1.21+. CPISync also requires NTL and GMP. On Ubuntu, the system packages are
`build-essential libssl-dev libntl-dev libgmp-dev`. Set `GO=/path/to/go` if needed.
Upstream sources and licenses are included in `algorithms/dependencies/`, with
versions in `algorithms/dependencies/versions.json`.

For plotting:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r scripts/requirements.txt
```

Check the included data and run a small example measurement:

```bash
python3 scripts/reproduce.py verify
python3 scripts/reproduce.py optimized-comparison --d 100 --method xyz --smoke
```

The smoke run uses a small input. Each measurement command below automatically builds
its required implementations.

| Result | Command | Data |
|---|---|---|
| Figure 2(a): decoding success threshold | `python3 scripts/reproduce.py optimized-sharp --workers 8` | `results/sharp/` |
| Figure 2(b)--(c): time and space for different k, ell | `python3 scripts/reproduce.py optimized-parameters` | `results/optimized/`, `results/parameters/` |
| Figure 2(d) and Figure 3: spatial-coupling heatmaps | `python3 scripts/reproduce.py paper-heatmaps` | `results/reference/heatmaps.csv` |
| Figure 2(e)--(h): communication and timing comparisons | `python3 scripts/reproduce.py main-comparison` | `results/optimized/`, `results/compact-iblt/`, `results/rateless/`, `results/reference/` |
| Figure 4: IBLT fingerprint sensitivity | `python3 scripts/reproduce.py fingerprint --workers 8` | `results/fingerprint/` |
| Tables 3--4: thresholds and space ratios | `python3 scripts/reproduce.py threshold-tables` | `results/threshold-tables/` |
| C,D parameter calibration | `python3 scripts/reproduce.py heuristic-calibration` | `results/calibration/` |
| Regenerate figures from stored measurements | `python3 scripts/reproduce.py figures` | New directory under `results/runs/` |

Individual comparison methods can be run using `optimized-comparison`,
`compact-baselines`, or `rateless`. `rateless-representative` runs the representative
checks from the Rateless IBLT paper. `extra-points` reproduces the additional timing
points at d=200,000 and 500,000. For the unoptimized implementation, use
`paper-comparison` and `paper-threshold`.

Use `--dry-run` to inspect jobs without running them. `--d`, `--method`,
`--kind timing`, `--kind communication`, and `--limit` select subsets.
For single-core timing, use `--workers 1 --cpu N`; parallel workers are intended for
success-probability experiments.

## Inputs and outputs

Full comparison inputs contain 10^7 elements per party, with 30-bit element values.
Large input binaries are not included. `scripts/inputs.json` records seeds and hashes;
missing inputs are generated deterministically and checked against those records.
Use `--data-root /path/to/input-cache` to reuse existing inputs.

Each run creates a new directory under `results/runs/`, containing raw outputs,
input verification records, configuration, summaries, and validation. `--out` selects
a different new output directory. Full campaigns require substantial disk space and
CPU time; `--dry-run` reports their job counts. The `figures` command only replots
stored measurements.

## Measurement conventions

The reported timings use an Intel Core i9-10980XE, GCC 9.4.0, and Go 1.21.13.
Timing uses three repetitions on each of five successful inputs, averaged within each
input, with 95% bootstrap intervals over the five averages. Full fixed-sketch decoding
includes serialization, an in-memory copy, parsing, subtraction, recovery, and output
normalization. Input generation and ground-truth verification are outside algorithm
timing. Failed trials and timeouts are retained.

Rateless IBLT uses the official 64-bit hash, count deviations encoded as signed variable-length
integers, and incremental decoding until completion. Communication is measured on 100
inputs per scale. Its ingestion time measures the encoder API; its full decoding time
includes symbol generation, receiver processing, and wire encoding/decoding.

IBLT and IBLT+SC use lossless counter compression with 30-bit keys and 32-bit checksums.
Their communication and decoding measurements use the same codec. Fingerprint tests
require exact directed recovery and enforce the 10d peeling and 100M inspection limits.

Source hashes are in `results/source-manifest.json`. Timings vary with hardware and
system load.
