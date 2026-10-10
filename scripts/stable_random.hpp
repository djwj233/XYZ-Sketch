#pragma once

#include <cstdint>
#include <limits>
#include <random>
#include <utility>
#include <vector>

// Fixed sampling rules for the archived experiment inputs. Do not substitute
// std::uniform_int_distribution or std::shuffle: their sequences can change
// between standard-library versions even when mt19937_64 has the same seed.
namespace xyz_inputs {

template <typename Generator>
std::uint64_t UniformInclusive(Generator& generator, std::uint64_t upper) {
    constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
    static_assert(Generator::min() == 0 && Generator::max() == maximum,
                  "input sampling requires a full-width 64-bit generator");
    if (upper == maximum) return generator();
    const std::uint64_t range = upper + 1;
    const std::uint64_t bucket = maximum / range;
    const std::uint64_t limit = range * bucket;
    std::uint64_t draw;
    do { draw = generator(); } while (draw >= limit);
    return draw / bucket;
}

template <typename T>
void Shuffle(std::vector<T>& values, std::mt19937_64& generator) {
    const std::uint64_t size = values.size();
    if (size < 2) return;
    constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
    if (maximum / size >= size) {
        std::uint64_t index = 1;
        if (size % 2 == 0) {
            std::swap(values[index], values[UniformInclusive(generator, 1)]);
            ++index;
        }
        for (; index < size; index += 2) {
            const std::uint64_t first_range = index + 1;
            const std::uint64_t second_range = index + 2;
            const auto pair = UniformInclusive(generator, first_range * second_range - 1);
            std::swap(values[index], values[pair / second_range]);
            std::swap(values[index + 1], values[pair % second_range]);
        }
    } else {
        for (std::uint64_t index = 1; index < size; ++index)
            std::swap(values[index], values[UniformInclusive(generator, index)]);
    }
}

}  // namespace xyz_inputs
