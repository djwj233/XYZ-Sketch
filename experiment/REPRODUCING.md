# Building and inspecting the paper experiments

## What is included

Git contains the experiment source, existing tests, protocol and audit reports,
threshold table, selected result snapshots, and the paper figures. The core
`XYZ-Sketch/` and `IBLT/` implementations are the `99bbe7a` baseline.

`artifact-index.json` lists every selected file under the experiment `results/`
directories, its original repository-relative path, size, and SHA-256. Original
run IDs, statuses and hashes are preserved. Intermediate and failed-run
metadata are retained for provenance; an old `fine_running` marker is a saved
historical state, not evidence of a currently active process.

The approximately 70 GB full local archive is not in Git. Omitted files include
large trial logs, calibration matrices, dataset caches, per-point checkpoints,
stdout/stderr logs and duplicate renderings. A clone therefore supports code
inspection, builds, tests and inspection of compact results; it does not contain
all inputs needed to resume or independently audit every historical trial.
Run manifests may reference omitted files or original `/root/...` paths.

Saved implementation audit reports describe the historical runs and their
recorded hashes. A new formal run still needs its own build/environment
manifests and the protocol's gates. Do not overwrite archived frozen parameters
or reuse old audit approval for changed binaries.

## Selected runs

| Output | Result directory under `experiment/` |
| --- | --- |
| Frozen parameters | `figure-1bc/results/calibration/figure1bc-calibration-20260716T095512Z-99bbe7a-b4444f9c40f4` |
| Sealed holdout | `figure-1bc/results/holdout/figure1bc-holdout-20260716T110856Z-99bbe7a-35901f553b9f` |
| Figure 1(a) | `figure-1a/results/dense/figure1a-dense-20260717T072537Z-99bbe7a-6a6c112cc6fc` |
| Final Figure 1(b)(c) and Appendix Figure 3 renderings | `figure-1bc/results/figure3-wide/figure3-wide-r4-20260716T140249Z-99bbe7a-5418d4c3ceae` |
| Final Figure 2 | `figure-2/results/final/figure2-final-20260721T085150Z` |

The final Figure 2 aggregate has 54 algorithm/size entries, including the
extended Project IBLT baseline; the selected paper figures show five algorithms.
MiniSketch has five completed timing points and four larger sizes not run after
a resource limit. CPISync has three completed timing points, one timeout and five
larger sizes not run. These statuses must not be interpreted as measured zeros.

## Dependencies and submodules

The reference environment is Linux/x86-64 with a C++17 compiler, CMake 3.16+,
Python 3.8+, OpenSSL development headers, NTL, GMP, pthreads and Go 1.21.
PDF/PNG rendering additionally uses `rsvg-convert` (package `librsvg2-bin`).
On Debian/Ubuntu the C++/plot dependencies are:

```bash
sudo apt-get install build-essential cmake python3 libssl-dev libntl-dev libgmp-dev librsvg2-bin
```

From the repository root, initialize the pinned submodules and apply the
experiment's wire-format adapter to the external IBLT:

```bash
git submodule update --init --recursive
git -C external/IBLT_Cplusplus apply --check ../../patches/iblt-canonical-wire.patch
git -C external/IBLT_Cplusplus apply ../../patches/iblt-canonical-wire.patch
```

Apply the patch once to a clean submodule checkout. An experiment checkout that
already has it applied needs no second application. The patch adds cell-count
and canonical serialization interfaces; it does not change the upstream hash,
update or peeling algorithm. Its base revision is recorded in `patches/README.md`.

## Build

Run from the repository root:

```bash
cmake -S experiment/figure-1bc -B experiment/figure-1bc/build -DCMAKE_BUILD_TYPE=Release
cmake --build experiment/figure-1bc/build -j2
cmake -S experiment/figure-1a -B experiment/figure-1a/build -DCMAKE_BUILD_TYPE=Release
cmake --build experiment/figure-1a/build -j2
cmake -S experiment/figure-2 -B experiment/figure-2/build -DCMAKE_BUILD_TYPE=Release
cmake --build experiment/figure-2/build -j2
(cd experiment/figure-2/go/figure2_riblt_engine && go build -o ../../build/figure2_riblt_engine .)
```

Use Go 1.21 for the last command. The historical Figure 2 manifest-generation
command in `figure2/cli.py` also expects `/usr/local/go1.21/bin/go`; generating
new implementation manifests requires that installation path or a reviewed
portability update. This restriction does not affect the C++ core sample.

## Existing validation suites

After building, run from the repository root:

```bash
(cd experiment/threshold && python3 -m unittest discover -s . -p 'test_*.py' -v)
(cd experiment/figure-1bc && python3 -m unittest discover -s tests -v)
(cd experiment/figure-1a && python3 -m unittest discover -s tests -v)
(cd experiment/figure-2 && python3 -m unittest discover -s tests -v)
```

These include engine golden vectors and small shared-dataset smoke checks.
They do not rerun the full paper measurements. See each module's README and CLI
help for formal execution, frozen inputs and resource settings.
