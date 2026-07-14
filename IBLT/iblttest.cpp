#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>

#include "iblt.cpp"

int main() {
    const std::vector<std::uint32_t> alice_values =
        {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
    const std::vector<std::uint32_t> bob_values =
        {1, 12, 3, 4, 5, 6, 7, 28, 39, 10};

    IBLT iblt(6);
    auto alice = iblt.Encode(alice_values);
    auto bob = iblt.Encode(bob_values);
    auto [alice_only, bob_only] = iblt.Decode(alice, bob);

    assert((alice_only == std::vector<std::uint32_t>{2, 8, 9}));
    assert((bob_only == std::vector<std::uint32_t>{12, 28, 39}));

    std::cout << "A \\ B :\n";
    for (std::uint32_t x : alice_only) std::cout << x << ' ';
    std::cout << "\nB \\ A :\n";
    for (std::uint32_t x : bob_only) std::cout << x << ' ';
    std::cout << '\n';

    return 0;
}
