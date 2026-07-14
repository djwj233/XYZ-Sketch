# IBLT Usage Guide

The `IBLT` directory contains a conventional invertible Bloom lookup table for
set reconciliation. Each party encodes a set, and the decoder subtracts the two
tables and peels the directed set differences.

## Requirements

- A C++17 compiler
- A standard C++ library

## Files

| File | Purpose |
| --- | --- |
| `IBLT/iblt.cpp` | IBLT class, encoding, subtraction, and peeling |
| `IBLT/murmur3.h`, `IBLT/murmur3.cc` | MurmurHash3 implementation |
| `IBLT/iblttest.cpp` | End-to-end sample and correctness check |

## Run the Sample

From the repository root:

```bash
g++ -std=c++17 -O2 IBLT/iblttest.cpp -o /tmp/iblt_sample \
  && /tmp/iblt_sample
```

Expected output:

```text
A \ B :
2 8 9
B \ A :
12 28 39
```

## Construct a Table

Construct an `IBLT` using the expected symmetric-difference size `D`:

```cpp
IBLT iblt(D);
```

The default constructor policy selects the table size and number of hashes from
`D`. An explicit capacity factor may be supplied when a fixed sizing policy is
preferred:

```cpp
IBLT iblt(D, capacity_factor);
```

The table then contains `ceil(capacity_factor * D)` cells, with a minimum of one
cell. A positive capacity factor is required for the override.

The selected configuration can be inspected with:

```cpp
int cells = iblt.cell_count();
int hashes = iblt.hash_count_value();
```

Both parties must use the same `IBLT` configuration.

## Encode and Decode

The current implementation is provided as a single translation unit:

```cpp
#include "IBLT/iblt.cpp"

#include <cstdint>
#include <iostream>
#include <vector>

int main() {
    std::vector<std::uint32_t> alice_values = {1, 2, 3, 4};
    std::vector<std::uint32_t> bob_values = {1, 2, 5, 6};

    IBLT iblt(4);  // expected total symmetric difference
    auto alice = iblt.Encode(alice_values);
    auto bob = iblt.Encode(bob_values);

    auto [alice_only, bob_only] = iblt.Decode(alice, bob);

    for (std::uint32_t x : alice_only) std::cout << x << ' ';
    std::cout << '\n';
    for (std::uint32_t x : bob_only) std::cout << x << ' ';
    std::cout << '\n';
}
```

`Encode(values)` returns the encoded table. `Decode(alice, bob)` returns
`(Alice \ Bob, Bob \ Alice)`, with both result vectors sorted in ascending
order.

Inputs represent sets: use unique `std::uint32_t` elements within each input
vector. Choose `D` as an appropriate upper bound for the total symmetric
difference. The current API returns the elements peeled from the table and does
not provide a separate failure flag, so applications that require confirmed
reconciliation should validate the result according to their protocol.

Include `iblt.cpp` in exactly one application source file and do not compile it
or `murmur3.cc` separately into the same executable.
