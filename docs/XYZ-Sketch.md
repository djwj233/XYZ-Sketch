# XYZ-Sketch Usage Guide

XYZ-Sketch reconciles two sets by encoding each set into a compact sketch,
transmitting one sketch, subtracting the sketches, and peeling the signed set
difference. The implementation uses truncated characteristic polynomials over
the finite field `F_998244353` and spatially coupled hashing.

## Requirements

- A C++17 compiler
- A standard C++ library

The XYZ-Sketch implementation has no external runtime dependency.

## Files

| File | Purpose |
| --- | --- |
| `XYZ-Sketch/XYZSketch.h` | Public single-translation-unit include |
| `XYZ-Sketch/XYZSketch.cpp` | Sketch, serialization, subtraction, and decoder |
| `XYZ-Sketch/hash.h` | Hashing declarations |
| `XYZ-Sketch/hash.cpp` | Naive and circular spatially coupled placement |
| `XYZ-Sketch/tools.cpp` | Finite-field and polynomial operations |
| `XYZ-Sketch/murmur3.h`, `XYZ-Sketch/murmur3.cc` | MurmurHash3 implementation |
| `XYZ-Sketch/sample.cpp` | End-to-end example |

## Run the Sample

From the repository root:

```bash
g++ -std=c++17 -O2 XYZ-Sketch/sample.cpp -o /tmp/xyz_sketch_sample \
  && /tmp/xyz_sketch_sample
```

Expected output:

```text
A \ B :
2 8 9
B \ A :
12 28 39
```

The sample initializes the implementation, encodes both sets, serializes and
deserializes Alice's sketch, subtracts Bob's sketch, and decodes both directed
differences.

## Initialization

Initialize the polynomial utilities and configure the shared sketch parameters
before encoding either set:

```cpp
#include "XYZ-Sketch/XYZSketch.h"

const int max_polynomial_length = 1 << 10;
tool::init(max_polynomial_length);
tool::Pinit(max_polynomial_length);

k = 2;  // hash locations requested for each element
l = 3;  // maximum total difference decoded from one pure cell
M = 6;  // number of sketch cells

Hashing::SetHashMode(Hashing::CIRCULAR);
Hashing::SetCircularA(0.5);
Hashing::SetDedupHashes(true);
Hashing::HashingInit(1);  // z = 1
```

Both parties must use identical values of `k`, `l`, `M`, `a`, `z`, hash mode,
and hash deduplication. `M` must be positive, and `z` must satisfy
`0 <= z < M`.

`SetDedupHashes(true)` makes each element update a cell at most once when two
of its requested hash locations coincide. The same setting must be used during
encoding and decoding.

## Reconciliation Flow

```cpp
std::vector<int> alice_values = {1, 2, 3, 4};
std::vector<int> bob_values = {1, 2, 5, 6};

XYZSketch alice = Encode(alice_values);
std::vector<bool> payload = alice.to_bitstring();

XYZSketch received_alice = to_sketch(payload);
XYZSketch bob = Encode(bob_values);
auto decoded = (received_alice - bob).Decode();

if (decoded.index() == 1) {
    // Decoding failed for the selected parameters and sketch size.
    return 1;
}

auto [alice_only, bob_only] =
    std::get<std::pair<std::vector<int>, std::vector<int>>>(decoded);
```

The successful result is ordered as `(Alice \ Bob, Bob \ Alice)`. A failure
result indicates that the residual sketch could not be completely peeled.

`XYZSketch::Update(x)` may be used to insert individual elements instead of
calling `Encode(values)`. The implementation accepts distinct field elements
in the range `1 <= x < 998244353`.

## Hashing Parameters

`Hashing::HashingInit(z)` defines the coupled window length as

```text
RangeLength = floor(M / (z + 1)).
```

`Hashing::NAIVE` uses non-wrapping placement. `Hashing::CIRCULAR` uses circular
placement controlled by `a`, where `0 <= a < 1`. In the paper's convention,
`a = 0` is the non-wrapping placement, while increasing `a` introduces more
circular anchors and approaches fully circular placement. The implementation
uses

```text
base_range = min(M, M - RangeLength + 1 + floor(a * RangeLength)).
```

For threshold-based parameter selection, the paper's heuristic is

```text
a = C * c_peel / c_orient
z = round(D * (1 - a)^(2/3) * (M / log(1 / delta))^(1/3)).
```

The caller supplies the calibration constants and passes the resulting values
to `Hashing::SetCircularA(a)` and `Hashing::HashingInit(z)`.

## Serialization

`XYZSketch::to_bitstring()` serializes all cells into a `std::vector<bool>`, and
`to_sketch(bits)` reconstructs a sketch using the current global `M` and `l`.
Each polynomial coefficient is serialized in 30 bits, the bit width required
for `F_998244353`. Configuration is not embedded in the payload, so it must be
agreed separately by both parties.

## Integration

`XYZSketch.h` exposes the implementation as a single translation unit. Include
it in exactly one application source file and compile that source file alone;
do not separately compile `XYZSketch.cpp`, `hash.cpp`, or `murmur3.cc` into the
same executable.
