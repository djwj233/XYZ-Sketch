#include <openssl/sha.h>
#include <sys/resource.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

#include "XYZSketch.h"

namespace {

using Clock = std::chrono::steady_clock;

std::uint64_t DeriveSeed(int kval, int ell, const std::string& role) {
    const std::string material =
        "figure1a|114514|benchmark|" + std::to_string(kval) + "|" +
        std::to_string(ell) + "|0|" + role;
    unsigned char digest[SHA256_DIGEST_LENGTH];
    SHA256(reinterpret_cast<const unsigned char*>(material.data()), material.size(), digest);
    std::uint64_t value = 0;
    for(int index = 0; index < 8; ++index) value = (value << 8U) | digest[index];
    return value;
}

double Seconds(Clock::time_point begin, Clock::time_point end) {
    return std::chrono::duration<double>(end - begin).count();
}

std::vector<int> FloydSample(std::size_t count, std::mt19937_64& generator) {
    constexpr std::uint64_t universe = static_cast<std::uint64_t>(P) - 1U;
    if(count > universe) throw std::invalid_argument("sample exceeds universe");
    std::unordered_set<std::uint32_t> chosen;
    chosen.max_load_factor(0.70F);
    chosen.reserve(count * 10U / 7U + 1U);
    std::vector<int> values;
    values.reserve(count);
    for(std::uint64_t j = universe - count; j < universe; ++j) {
        std::uniform_int_distribution<std::uint64_t> distribution(0, j);
        const std::uint32_t candidate = static_cast<std::uint32_t>(distribution(generator));
        if(chosen.insert(candidate).second) {
            values.push_back(static_cast<int>(candidate + 1U));
        } else {
            const std::uint32_t fallback = static_cast<std::uint32_t>(j);
            if(!chosen.insert(fallback).second) throw std::runtime_error("Floyd duplicate fallback");
            values.push_back(static_cast<int>(fallback + 1U));
        }
    }
    if(values.size() != count || chosen.size() != count) {
        throw std::runtime_error("Floyd sample cardinality mismatch");
    }
    for(int value : values) {
        if(value <= 0 || value >= P) throw std::runtime_error("sample outside nonzero field");
    }
    std::shuffle(values.begin(), values.end(), generator);
    return values;
}

XYZSketch EncodeReference(const std::vector<int>& values) {
    XYZSketch sketch;
    sketch.init();
    for(int value : values) sketch.Update(value);
    return sketch;
}

void SeedDecoder(std::uint64_t seed) {
    const std::uint32_t high = static_cast<std::uint32_t>(seed >> 32U);
    const std::uint32_t low = static_cast<std::uint32_t>(seed);
    std::seed_seq sequence{high, low};
    rng.seed(sequence);
}

long MaximumRssKiB() {
    struct rusage usage {};
    if(getrusage(RUSAGE_SELF, &usage) != 0) return -1;
    return usage.ru_maxrss;
}

}  // namespace

int main(int argc, char** argv) {
    if(argc != 9) {
        std::cerr << "usage: figure1a_probe set_size d k ell M mode a z\n";
        return 2;
    }
    try {
        const std::size_t set_size = std::stoull(argv[1]);
        const int difference = std::stoi(argv[2]);
        k = std::stoi(argv[3]);
        l = std::stoi(argv[4]);
        M = std::stoi(argv[5]);
        const std::string mode = argv[6];
        const double circular_a = std::stod(argv[7]);
        const int z_value = std::stoi(argv[8]);
        if(difference <= 0 || difference % 2 != 0 || set_size < static_cast<std::size_t>(difference / 2)) {
            throw std::invalid_argument("invalid set size or difference");
        }

        tool::init(64);
        tool::Pinit(64);
        Hashing::SetHashMode(mode == "circular" ? Hashing::CIRCULAR : Hashing::NAIVE);
        Hashing::SetCircularA(circular_a);
        Hashing::SetDedupHashes(true);
        Hashing::HashingInit(z_value);

        const auto total_begin = Clock::now();
        std::mt19937_64 dataset_generator(DeriveSeed(k, l, "dataset_identity"));
        const std::size_t one_direction = static_cast<std::size_t>(difference / 2);
        const std::size_t common_size = set_size - one_direction;
        std::vector<int> sample = FloydSample(set_size + one_direction, dataset_generator);
        std::vector<int> alice(sample.begin(), sample.begin() + common_size);
        alice.insert(alice.end(), sample.begin() + common_size, sample.begin() + set_size);
        std::vector<int> bob(sample.begin(), sample.begin() + common_size);
        bob.insert(bob.end(), sample.begin() + set_size, sample.end());
        std::vector<int> expected_alice(sample.begin() + common_size, sample.begin() + set_size);
        std::vector<int> expected_bob(sample.begin() + set_size, sample.end());
        std::sort(expected_alice.begin(), expected_alice.end());
        std::sort(expected_bob.begin(), expected_bob.end());
        std::mt19937_64 alice_generator(DeriveSeed(k, l, "alice_insertion_order"));
        std::mt19937_64 bob_generator(DeriveSeed(k, l, "bob_insertion_order"));
        std::shuffle(alice.begin(), alice.end(), alice_generator);
        std::shuffle(bob.begin(), bob.end(), bob_generator);
        const auto dataset_end = Clock::now();

        const auto alice_begin = Clock::now();
        XYZSketch alice_sketch = EncodeReference(alice);
        const auto alice_end = Clock::now();
        const auto serialize_begin = Clock::now();
        std::vector<bool> logical_bits = alice_sketch.to_bitstring();
        XYZSketch received = to_sketch(logical_bits);
        if(received.to_bitstring() != logical_bits) throw std::runtime_error("serialization mismatch");
        const auto serialize_end = Clock::now();
        const auto bob_begin = Clock::now();
        XYZSketch bob_sketch = EncodeReference(bob);
        const auto bob_end = Clock::now();
        const auto decode_begin = Clock::now();
        SeedDecoder(DeriveSeed(k, l, "decoder_root_finding"));
        auto decoded = (received - bob_sketch).Decode();
        bool success = false;
        if(decoded.index() == 0) {
            const auto& value = std::get<std::pair<std::vector<int>, std::vector<int>>>(decoded);
            success = value.first == expected_alice && value.second == expected_bob;
        }
        const auto decode_end = Clock::now();

        const std::size_t wire_state_bytes = (logical_bits.size() + 7U) / 8U;
        const auto total_end = Clock::now();
        std::cout << "{"
                  << "\"set_size\":" << set_size << ','
                  << "\"d\":" << difference << ','
                  << "\"k\":" << k << ','
                  << "\"ell\":" << l << ','
                  << "\"M\":" << M << ','
                  << "\"mode\":\"" << mode << "\","
                  << "\"a\":" << circular_a << ','
                  << "\"z\":" << z_value << ','
                  << "\"dataset_seconds\":" << Seconds(total_begin, dataset_end) << ','
                  << "\"alice_encode_seconds\":" << Seconds(alice_begin, alice_end) << ','
                  << "\"serialization_seconds\":" << Seconds(serialize_begin, serialize_end) << ','
                  << "\"bob_encode_seconds\":" << Seconds(bob_begin, bob_end) << ','
                  << "\"decode_seconds\":" << Seconds(decode_begin, decode_end) << ','
                  << "\"total_seconds\":" << Seconds(total_begin, total_end) << ','
                  << "\"logical_state_bits\":" << logical_bits.size() << ','
                  << "\"wire_state_bytes\":" << wire_state_bytes << ','
                  << "\"success\":" << (success ? "true" : "false") << ','
                  << "\"max_rss_kib\":" << MaximumRssKiB()
                  << "}\n";
        return success ? 0 : 1;
    } catch(const std::exception& error) {
        std::cerr << typeid(error).name() << ": " << error.what() << '\n';
        return 3;
    }
}
