# Figure 2 v4 wire correction

## Scope

Protocol v4 corrects the conventional IBLT and Rateless IBLT wire profiles and reruns every affected
timing or probability path. The completed v3 aggregate is immutable and is used only as a hash-bound
parent artifact.

## Conventional IBLT

The IBLT algorithm, selected expected-entry count, actual cell count, MurmurHash settings, updates,
subtraction, purity test, and peeling are unchanged. Each cell is serialized as a contiguous 87-bit
record:

```text
Count:    25-bit two's-complement signed integer
KeySum:   30 unsigned bits
KeyCheck: 32 unsigned bits
```

The count width exactly covers `[-10^7,10^7]`. XOR of 30-bit elements remains 30-bit. Records are
MSB-first and bit-packed without per-cell alignment; only the final byte may contain zero padding.
Probability and operating-point evidence migrate from v3 because canonical serialization does not
affect the table state. All conventional-IBLT timing points are rerun because serialization and
deserialization are inside the decode timer.

## Rateless IBLT

The item hash is `SipHash-2-4(item) mod 2^49`. For `d_max=10^6`, the union bound for a collision
among difference items is

```text
d_max * (d_max - 1) / (2 * 2^49) < 0.001.
```

Each coded symbol contains 30 Symbol bits, 49 Hash bits, and a 25-bit signed Count, for 104 logical
bits. Because the hash seeds both the upstream mapping generator and the purity checksum, v3
Rateless-IBLT probability evidence is not migrated. Resource discovery, sealed confirmation, and
timing are all rerun under the v4 profile.

If the independent RIBLT q90 confirmation block has fewer than 90 successes, the runner advances
through q95, q99, and q100 caps from the frozen discovery order statistics, each with a new independent
100-trial full-set block. If needed, the final registered cap is `3d`. Only the first block reaching
90/100 becomes the operating point; all failed blocks remain in the raw artifacts.

## Migration and execution

XYZ-Sketch, MiniSketch, CPISync, and Project IBLT migrate probability, payload, and timing rows from
v3. Conventional IBLT migrates only probability and the selected table size. Rateless IBLT uses fresh
probability evidence. Conventional IBLT and Rateless IBLT use fresh timing data. The
migration manifest binds the parent aggregate, profiles, executables, source
tree, and all migrated algorithm names.
