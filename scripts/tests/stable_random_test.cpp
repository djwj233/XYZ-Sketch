#include "../stable_random.hpp"
#include <algorithm>
#include <iostream>
#include <numeric>
#include <stdexcept>

int main() {
    std::uint64_t transcript = 14695981039346656037ULL;
    auto record = [&](std::uint64_t value) {
        for (unsigned shift = 0; shift < 64; shift += 8) {
            transcript ^= (value >> shift) & 255;
            transcript *= 1099511628211ULL;
        }
    };
    const std::uint64_t bounds[] = {
        0, 1, 2, 126, 127, 255, 256, 998244352, 0xffffffffULL,
        0x7fffffffffffffffULL, 0x8000000000000000ULL,
        0xfffffffffffffffeULL, 0xffffffffffffffffULL
    };
    std::uint64_t draws = 0, shuffles = 0;
    for (std::uint64_t seed : {0ULL, 1ULL, 114514ULL, 0xffffffffffffffffULL}) {
        for (auto upper : bounds) {
            std::mt19937_64 generator(seed), reference(seed);
            std::uniform_int_distribution<std::uint64_t> distribution(0, upper);
            for (unsigned index = 0; index < 1024; ++index) {
                auto value = xyz_inputs::UniformInclusive(generator, upper);
                if (value > upper) throw std::runtime_error("draw outside range");
#ifdef XYZ_COMPARE_GCC9
                if (value != distribution(reference))
                    throw std::runtime_error("draw differs from archived GCC 9 rule");
#endif
                record(value);
                ++draws;
            }
#ifdef XYZ_COMPARE_GCC9
            if (generator != reference) throw std::runtime_error("draw state differs");
#endif
        }
        for (std::size_t size : {0, 1, 2, 3, 4, 5, 127, 128, 129, 10000}) {
            std::vector<std::uint32_t> values(size);
            std::iota(values.begin(), values.end(), 0);
            auto expected = values;
            std::mt19937_64 generator(seed), reference(seed);
            xyz_inputs::Shuffle(values, generator);
#ifdef XYZ_COMPARE_GCC9
            std::shuffle(expected.begin(), expected.end(), reference);
            if (values != expected || generator != reference)
                throw std::runtime_error("shuffle differs from archived GCC 9 rule");
#endif
            auto sorted = values;
            std::sort(sorted.begin(), sorted.end());
            for (std::size_t index = 0; index < size; ++index)
                if (sorted[index] != index) throw std::runtime_error("invalid permutation");
            for (auto value : values) record(value);
            record(generator());
            ++shuffles;
        }
    }
    std::cout << "{\"draws\":" << draws << ",\"shuffles\":" << shuffles
              << ",\"transcript\":" << transcript << "}\n";
}
