#include "common.hpp"

#include <cmath>
#include <iostream>
#include <random>
#include <variant>

#include "XYZSketch.h"

namespace {

std::vector<unsigned char> PackBits(const std::vector<bool>& bits) {
    std::vector<unsigned char> output((bits.size() + 7U) / 8U, 0U);
    for(std::size_t index = 0; index < bits.size(); ++index) {
        if(bits[index]) output[index / 8U] |= static_cast<unsigned char>(1U << (7U - index % 8U));
    }
    return output;
}

std::vector<bool> UnpackBits(
    const std::vector<unsigned char>& bytes, std::size_t offset, std::size_t bit_count
) {
    if(offset + (bit_count + 7U) / 8U != bytes.size()) throw std::runtime_error("XYZ wire size mismatch");
    std::vector<bool> bits(bit_count);
    for(std::size_t index = 0; index < bit_count; ++index) {
        bits[index] = (bytes[offset + index / 8U] >> (7U - index % 8U)) & 1U;
    }
    return bits;
}

void Configure(int cells, double a, int z) {
    k = 2;
    l = 6;
    M = cells;
    Hashing::SetHashMode(Hashing::CIRCULAR);
    Hashing::SetCircularA(a);
    Hashing::SetDedupHashes(true);
    Hashing::HashingInit(z);
}

void Update(XYZSketch& sketch, const std::vector<std::uint32_t>& values) {
    for(std::uint32_t value : values) sketch.Update(static_cast<int>(value));
}

void SeedDecoder(std::uint64_t seed) {
    const std::uint32_t high = static_cast<std::uint32_t>(seed >> 32U);
    const std::uint32_t low = static_cast<std::uint32_t>(seed);
    std::seed_seq sequence{high, low};
    rng.seed(sequence);
}

struct ParsedXYZ {
    std::vector<bool> bits;
};

ParsedXYZ ParseState(const std::vector<unsigned char>& state, int cells) {
    if(cells <= 0) throw std::runtime_error("XYZ cell count is invalid");
    const std::uint64_t logical_bits = static_cast<std::uint64_t>(cells) * 184U;
    figure2::ValidatePackedState(state, logical_bits);
    return ParsedXYZ{UnpackBits(state, 0U, static_cast<std::size_t>(logical_bits))};
}

figure2::EngineResult Run(
    const figure2::Dataset& dataset, int cells, double a, int z, std::uint64_t decoder_seed
) {
    figure2::EngineResult result;
    result.algorithm = "xyz";
    tool::init(64);
    tool::Pinit(64);
    Configure(cells, a, z);
    XYZSketch alice;
    alice.init();
    double begin = figure2::ThreadCpuSeconds();
    Update(alice, dataset.alice);
    result.update_alice_cpu = figure2::ThreadCpuSeconds() - begin;
    Configure(cells, a, z);
    XYZSketch bob;
    bob.init();
    begin = figure2::ThreadCpuSeconds();
    Update(bob, dataset.bob);
    result.update_bob_cpu = figure2::ThreadCpuSeconds() - begin;

    begin = figure2::ThreadCpuSeconds();
    std::vector<bool> logical = alice.to_bitstring();
    std::vector<unsigned char> state = PackBits(logical);
    result.sender_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    std::vector<unsigned char> received_state = state;
    result.transfer_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    ParsedXYZ parsed = ParseState(received_state, cells);
    Configure(cells, a, z);
    XYZSketch received = to_sketch(parsed.bits);
    XYZSketch residual = received - bob;
    SeedDecoder(decoder_seed);
    auto decoded = residual.Decode();
    std::vector<std::uint32_t> alice_only, bob_only;
    if(decoded.index() == 0) {
        const auto& output = std::get<std::pair<std::vector<int>, std::vector<int>>>(decoded);
        alice_only.assign(output.first.begin(), output.first.end());
        bob_only.assign(output.second.begin(), output.second.end());
        const bool shape_valid = figure2::CanonicalizeDirected(alice_only, bob_only);
        result.failure = shape_valid ? "pending_ground_truth" : "wrong_output";
    } else {
        result.failure = "decode_failed";
    }
    result.receiver_cpu = figure2::ThreadCpuSeconds() - begin;
    Configure(cells, a, z);
    XYZSketch audit_residual = to_sketch(parsed.bits) - bob;
    result.residual_sha256 = figure2::Sha256(PackBits(audit_residual.to_bitstring()));
    const bool timer_stopped = true;
    if(decoded.index() == 0 && result.failure == "pending_ground_truth") {
        result.success = figure2::CompareGroundTruthAfterTimer(
            alice_only, bob_only, dataset, timer_stopped
        );
        result.failure = result.success ? "success" : "wrong_output";
    }
    result.alice_output_sha256 = figure2::VectorSha256(alice_only);
    result.bob_output_sha256 = figure2::VectorSha256(bob_only);
    result.logical_state_bits = logical.size();
    result.state_bits = state.size() * 8U;
    result.control_bits = 0U;
    result.total_payload_bits = result.state_bits;
    if(result.logical_state_bits != static_cast<std::uint64_t>(cells) * 184U ||
       result.total_payload_bits != result.state_bits) {
        throw std::runtime_error("XYZ accounting mismatch");
    }
    return result;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if(argc == 2 && std::string(argv[1]) == "--self-test") {
            tool::init(64);
            tool::Pinit(64);
            Configure(2, 0.2, 1);
            XYZSketch sketch;
            sketch.init();
            const std::vector<bool> bits = sketch.to_bitstring();
            const std::vector<unsigned char> state = PackBits(bits);
            bool malformed_rejected = false;
            try {
                ParseState(std::vector<unsigned char>(state.begin(), state.end() - 1), 2);
            } catch(const std::exception&) {
                malformed_rejected = true;
            }
            const bool passed = bits.size() == 368U && state.size() * 8U == 368U &&
                ParseState(state, 2).bits == bits && malformed_rejected;
            std::cout << "{\"protocol\":\"figure2-engine-v2\",\"algorithm\":\"xyz\","
                      << "\"golden_total_bits\":" << state.size() * 8U
                      << ",\"malformed_state_rejected\":" << (malformed_rejected ? "true" : "false")
                      << ",\"passed\":" << (passed ? "true" : "false") << "}\n";
            return passed ? 0 : 2;
        }
        if(argc != 7 || std::string(argv[1]) != "--run") {
            throw std::invalid_argument("usage: figure2_xyz_engine --run DATASET M a z decoder_seed");
        }
        figure2::PrintResult(Run(
            figure2::ReadDataset(argv[2]), std::stoi(argv[3]), std::stod(argv[4]),
            std::stoi(argv[5]), std::stoull(argv[6])
        ));
        return 0;
    } catch(const std::exception& error) {
        std::cerr << typeid(error).name() << ": " << error.what() << '\n';
        return 1;
    }
}
