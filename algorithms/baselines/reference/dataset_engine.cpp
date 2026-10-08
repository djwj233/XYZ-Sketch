#include "common.hpp"

#include <iostream>
#include <random>
#include <unordered_set>

namespace {

std::vector<std::uint32_t> FloydSample(std::size_t count, std::mt19937_64& generator) {
    constexpr std::uint64_t universe = figure2::kFieldModulus - 1U;
    if(count > universe) throw std::invalid_argument("sample exceeds field universe");
    std::unordered_set<std::uint32_t> chosen;
    chosen.max_load_factor(0.70F);
    chosen.reserve(count * 10U / 7U + 1U);
    std::vector<std::uint32_t> values;
    values.reserve(count);
    for(std::uint64_t j = universe - count; j < universe; ++j) {
        std::uniform_int_distribution<std::uint64_t> distribution(0, j);
        const std::uint32_t candidate = static_cast<std::uint32_t>(distribution(generator));
        if(chosen.insert(candidate).second) values.push_back(candidate + 1U);
        else {
            const std::uint32_t fallback = static_cast<std::uint32_t>(j);
            if(!chosen.insert(fallback).second) throw std::runtime_error("Floyd fallback duplicate");
            values.push_back(fallback + 1U);
        }
    }
    std::shuffle(values.begin(), values.end(), generator);
    return values;
}

figure2::Dataset Generate(
    bool full,
    std::uint32_t d,
    std::size_t set_size,
    std::uint64_t identity_seed,
    std::uint64_t alice_seed,
    std::uint64_t bob_seed
) {
    if(d == 0 || d % 2U != 0U) throw std::invalid_argument("d must be positive and even");
    const std::size_t half = d / 2U;
    if(full && set_size < half) throw std::invalid_argument("full set size is below d/2");
    std::mt19937_64 identity_generator(identity_seed);
    std::vector<std::uint32_t> sample = FloydSample(full ? set_size + half : d, identity_generator);
    figure2::Dataset dataset;
    dataset.full = full;
    dataset.d = d;
    dataset.identity_seed = identity_seed;
    dataset.alice_order_seed = alice_seed;
    dataset.bob_order_seed = bob_seed;
    if(full) {
        const std::size_t common = set_size - half;
        dataset.alice.assign(sample.begin(), sample.begin() + common);
        dataset.alice.insert(dataset.alice.end(), sample.begin() + common, sample.begin() + set_size);
        dataset.bob.assign(sample.begin(), sample.begin() + common);
        dataset.bob.insert(dataset.bob.end(), sample.begin() + set_size, sample.end());
        dataset.alice_only.assign(sample.begin() + common, sample.begin() + set_size);
        dataset.bob_only.assign(sample.begin() + set_size, sample.end());
    } else {
        dataset.alice.assign(sample.begin(), sample.begin() + half);
        dataset.bob.assign(sample.begin() + half, sample.end());
        dataset.alice_only = dataset.alice;
        dataset.bob_only = dataset.bob;
    }
    std::sort(dataset.alice_only.begin(), dataset.alice_only.end());
    std::sort(dataset.bob_only.begin(), dataset.bob_only.end());
    std::mt19937_64 alice_generator(alice_seed), bob_generator(bob_seed);
    std::shuffle(dataset.alice.begin(), dataset.alice.end(), alice_generator);
    std::shuffle(dataset.bob.begin(), dataset.bob.end(), bob_generator);
    dataset.hashes = {
        figure2::VectorSha256(dataset.alice), figure2::VectorSha256(dataset.bob),
        figure2::VectorSha256(dataset.alice_only), figure2::VectorSha256(dataset.bob_only),
    };
    return dataset;
}

std::pair<figure2::Dataset, figure2::Dataset> GenerateEquivalence(
    std::uint32_t d,
    std::size_t set_size,
    std::uint64_t identity_seed,
    std::uint64_t alice_seed,
    std::uint64_t bob_seed
) {
    figure2::Dataset full = Generate(true, d, set_size, identity_seed, alice_seed, bob_seed);
    figure2::Dataset difference;
    difference.full = false;
    difference.d = d;
    difference.identity_seed = identity_seed;
    difference.alice_order_seed = alice_seed;
    difference.bob_order_seed = bob_seed;
    difference.alice = full.alice_only;
    difference.bob = full.bob_only;
    difference.alice_only = full.alice_only;
    difference.bob_only = full.bob_only;
    std::mt19937_64 alice_generator(alice_seed), bob_generator(bob_seed);
    std::shuffle(difference.alice.begin(), difference.alice.end(), alice_generator);
    std::shuffle(difference.bob.begin(), difference.bob.end(), bob_generator);
    difference.hashes = {
        figure2::VectorSha256(difference.alice), figure2::VectorSha256(difference.bob),
        figure2::VectorSha256(difference.alice_only), figure2::VectorSha256(difference.bob_only),
    };
    return {std::move(full), std::move(difference)};
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if(argc == 2 && std::string(argv[1]) == "--self-test") {
            figure2::Dataset dataset = Generate(true, 4, 8, 1, 2, 3);
            const bool valid = dataset.alice.size() == 8U && dataset.bob.size() == 8U &&
                dataset.alice_only.size() == 2U && dataset.bob_only.size() == 2U;
            std::cout << "{\"protocol\":\"figure2-dataset-v1\",\"passed\":"
                      << (valid ? "true" : "false") << "}\n";
            return valid ? 0 : 2;
        }
        if(argc == 10 && std::string(argv[1]) == "--equivalence") {
            auto datasets = GenerateEquivalence(
                static_cast<std::uint32_t>(std::stoul(argv[4])),
                static_cast<std::size_t>(std::stoull(argv[5])), std::stoull(argv[6]),
                std::stoull(argv[7]), std::stoull(argv[8])
            );
            if(std::string(argv[9]) != "figure2-equivalence-v1") {
                throw std::invalid_argument("invalid equivalence protocol literal");
            }
            figure2::WriteDataset(argv[2], datasets.first);
            figure2::WriteDataset(argv[3], datasets.second);
            std::cout << "{\"protocol\":\"figure2-equivalence-v1\",\"d\":"
                      << datasets.first.d << ",\"full_set_size\":" << datasets.first.alice.size()
                      << ",\"alice_only_sha256\":\"" << datasets.first.hashes[2]
                      << "\",\"bob_only_sha256\":\"" << datasets.first.hashes[3] << "\"}\n";
            return 0;
        }
        if(argc != 8) {
            throw std::invalid_argument(
                "usage: figure2_dataset_engine OUTPUT full|difference d set_size identity_seed alice_seed bob_seed"
            );
        }
        const bool full = std::string(argv[2]) == "full";
        if(!full && std::string(argv[2]) != "difference") throw std::invalid_argument("invalid mode");
        figure2::Dataset dataset = Generate(
            full, static_cast<std::uint32_t>(std::stoul(argv[3])),
            static_cast<std::size_t>(std::stoull(argv[4])), std::stoull(argv[5]),
            std::stoull(argv[6]), std::stoull(argv[7])
        );
        figure2::WriteDataset(argv[1], dataset);
        std::cout << "{\"protocol\":\"figure2-dataset-v1\",\"full\":"
                  << (full ? "true" : "false") << ",\"d\":" << dataset.d
                  << ",\"set_size_A\":" << dataset.alice.size()
                  << ",\"set_size_B\":" << dataset.bob.size()
                  << ",\"alice_sha256\":\"" << dataset.hashes[0]
                  << "\",\"bob_sha256\":\"" << dataset.hashes[1]
                  << "\",\"alice_only_sha256\":\"" << dataset.hashes[2]
                  << "\",\"bob_only_sha256\":\"" << dataset.hashes[3] << "\"}\n";
        return 0;
    } catch(const std::exception& error) {
        std::cerr << typeid(error).name() << ": " << error.what() << '\n';
        return 1;
    }
}
