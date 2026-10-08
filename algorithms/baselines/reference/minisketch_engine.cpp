#include "common.hpp"

#include <iostream>
#include <memory>
#include <unordered_set>

#include "minisketch.h"

namespace {

struct SketchDeleter {
    void operator()(minisketch* sketch) const { minisketch_destroy(sketch); }
};
using SketchPtr = std::unique_ptr<minisketch, SketchDeleter>;

int Implementation() {
    return minisketch_implementation_supported(30, 2) ? 2 : 0;
}

SketchPtr Create(std::size_t capacity, std::uint64_t seed) {
    SketchPtr sketch(minisketch_create(30, Implementation(), capacity));
    if(!sketch) throw std::runtime_error("minisketch_create failed");
    minisketch_set_seed(sketch.get(), seed);
    return sketch;
}

std::vector<unsigned char> ParseState(
    const std::vector<unsigned char>& state, std::uint32_t capacity
) {
    figure2::ValidatePackedState(state, static_cast<std::uint64_t>(capacity) * 30U);
    return state;
}

figure2::EngineResult Run(const figure2::Dataset& dataset, std::uint64_t seed) {
    figure2::EngineResult result;
    result.algorithm = "minisketch";
    const std::size_t capacity = dataset.d;
    SketchPtr alice = Create(capacity, seed), bob = Create(capacity, seed);
    std::unordered_set<std::uint32_t> bob_membership(dataset.bob.begin(), dataset.bob.end());
    double begin = figure2::ThreadCpuSeconds();
    for(std::uint32_t value : dataset.alice) minisketch_add_uint64(alice.get(), value);
    result.update_alice_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    for(std::uint32_t value : dataset.bob) minisketch_add_uint64(bob.get(), value);
    result.update_bob_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    const std::size_t state_bytes = minisketch_serialized_size(alice.get());
    std::vector<unsigned char> state(state_bytes);
    minisketch_serialize(alice.get(), state.data());
    result.sender_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    std::vector<unsigned char> received_state = state;
    result.transfer_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    const std::vector<unsigned char> parsed = ParseState(
        received_state, static_cast<std::uint32_t>(capacity)
    );
    SketchPtr remote = Create(capacity, seed);
    minisketch_deserialize(remote.get(), parsed.data());
    if(minisketch_merge(remote.get(), bob.get()) != capacity) {
        throw std::runtime_error("minisketch merge failed");
    }
    std::vector<std::uint64_t> decoded(capacity);
    const ssize_t count = minisketch_decode(remote.get(), capacity, decoded.data());
    std::vector<std::uint32_t> alice_only, bob_only;
    if(count < 0) {
        result.failure = "decode_failed";
    } else {
        decoded.resize(static_cast<std::size_t>(count));
        for(std::uint64_t value : decoded) {
            if(value == 0 || value >= figure2::kFieldModulus) continue;
            if(bob_membership.count(static_cast<std::uint32_t>(value))) {
                bob_only.push_back(static_cast<std::uint32_t>(value));
            } else {
                alice_only.push_back(static_cast<std::uint32_t>(value));
            }
        }
        const bool shape_valid = figure2::CanonicalizeDirected(alice_only, bob_only);
        result.failure = static_cast<std::size_t>(count) == dataset.d && shape_valid ?
            "pending_ground_truth" : "wrong_output";
    }
    result.receiver_cpu = figure2::ThreadCpuSeconds() - begin;
    std::vector<unsigned char> residual(state_bytes);
    minisketch_serialize(remote.get(), residual.data());
    result.residual_sha256 = figure2::Sha256(residual);
    if(result.failure == "pending_ground_truth") {
        result.success = figure2::CompareGroundTruthAfterTimer(
            alice_only, bob_only, dataset, true
        );
        result.failure = result.success ? "success" : "wrong_output";
    }
    result.alice_output_sha256 = figure2::VectorSha256(alice_only);
    result.bob_output_sha256 = figure2::VectorSha256(bob_only);
    result.logical_state_bits = capacity * 30U;
    result.state_bits = state_bytes * 8U;
    result.control_bits = 0U;
    result.total_payload_bits = result.state_bits;
    if(result.total_payload_bits != result.state_bits) {
        throw std::runtime_error("minisketch accounting mismatch");
    }
    result.payload_sha256 = figure2::Sha256(state); // Outside all timing windows.
    return result;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if(argc == 2 && std::string(argv[1]) == "--self-test") {
            SketchPtr sketch = Create(2, 123);
            const std::size_t state = minisketch_serialized_size(sketch.get());
            std::vector<unsigned char> state_bytes(state);
            minisketch_serialize(sketch.get(), state_bytes.data());
            bool malformed_rejected = false;
            try {
                ParseState(std::vector<unsigned char>(state_bytes.begin(), state_bytes.end() - 1), 2);
            } catch(const std::exception&) {
                malformed_rejected = true;
            }
            const bool passed = state == 8U && state * 8U == 64U && malformed_rejected;
            std::cout << "{\"protocol\":\"figure2-engine-v2\",\"algorithm\":\"minisketch\","
                      << "\"implementation\":" << Implementation() << ",\"golden_total_bits\":"
                      << state * 8U << ",\"passed\":" << (passed ? "true" : "false")
                      << ",\"malformed_state_rejected\":"
                      << (malformed_rejected ? "true" : "false") << "}\n";
            return passed ? 0 : 2;
        }
        if(argc != 4 || std::string(argv[1]) != "--run") {
            throw std::invalid_argument("usage: figure2_minisketch_engine --run DATASET seed");
        }
        figure2::PrintResult(Run(figure2::ReadDataset(argv[2]), std::stoull(argv[3])));
        return 0;
    } catch(const std::exception& error) {
        std::cerr << typeid(error).name() << ": " << error.what() << '\n';
        return 1;
    }
}
