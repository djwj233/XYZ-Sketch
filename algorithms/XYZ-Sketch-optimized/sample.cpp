#include <algorithm>
#include <iostream>
#include <variant>
#include <vector>
#include "src/XYZSketch.h"

int main() {
    const std::vector<int> alice_set{1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
    const std::vector<int> bob_set{1, 12, 3, 4, 5, 6, 7, 28, 39, 10};

    // Both parties use the same cell layout and hash functions.
    tool::init(64);
    tool::Pinit(64);
    k = 2;
    l = 3;
    M = 6;
    Hashing::SetHashMode(Hashing::CIRCULAR);
    Hashing::SetCircularA(0.5);
    Hashing::SetDedupHashes(true);
    Hashing::HashingInit(1);

    auto alice = Encode(alice_set);
    const auto message = alice.to_bitstring();
    auto received = to_sketch(message);
    auto bob = Encode(bob_set);
    auto difference = (received - bob).Decode(false);
    if (difference.index() != 0) {
        std::cerr << "Decoding failed\n";
        return 1;
    }

    auto recovered = std::get<0>(difference);
    std::sort(recovered.first.begin(), recovered.first.end());
    std::sort(recovered.second.begin(), recovered.second.end());
    if (recovered.first != std::vector<int>{2, 8, 9} ||
        recovered.second != std::vector<int>{12, 28, 39}) {
        std::cerr << "Incorrect recovered difference\n";
        return 1;
    }

    std::cout << "Alice only:";
    for (int x : recovered.first) std::cout << ' ' << x;
    std::cout << "\nBob only:";
    for (int x : recovered.second) std::cout << ' ' << x;
    std::cout << '\n';
}
