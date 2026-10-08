#include "common.hpp"

#include <iostream>
#include <set>

#include "iblt.h"

namespace {

struct ParsedExternalIBLT {
    std::vector<unsigned char> state;
};

ParsedExternalIBLT ParseState(
    const std::vector<unsigned char>& state, std::uint32_t cells
) {
    figure2::ValidatePackedState(state, static_cast<std::uint64_t>(cells) * 87U);
    return ParsedExternalIBLT{state};
}

void Update(IBLT& sketch, const std::vector<std::uint32_t>& values) {
    const std::vector<std::uint8_t> empty;
    for(std::uint32_t value : values) sketch.insert(value, empty);
}

figure2::EngineResult Run(const figure2::Dataset& dataset, std::size_t expected) {
    figure2::EngineResult result;
    result.algorithm = "external_iblt";
    IBLT alice(expected, 0);
    double begin = figure2::ThreadCpuSeconds();
    Update(alice, dataset.alice);
    result.update_alice_cpu = figure2::ThreadCpuSeconds() - begin;
    IBLT bob(expected, 0);
    begin = figure2::ThreadCpuSeconds();
    Update(bob, dataset.bob);
    result.update_bob_cpu = figure2::ThreadCpuSeconds() - begin;
    if(alice.cell_count() != bob.cell_count()) throw std::runtime_error("IBLT cell count mismatch");
    const std::uint32_t cells = static_cast<std::uint32_t>(alice.cell_count());

    begin = figure2::ThreadCpuSeconds();
    std::vector<unsigned char> state = alice.serialize_canonical();
    result.sender_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    std::vector<unsigned char> received_state = state;
    result.transfer_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    const ParsedExternalIBLT parsed = ParseState(received_state, cells);
    IBLT received(expected, 0);
    if(received.cell_count() != cells) throw std::runtime_error("parsed IBLT cell count mismatch");
    received.deserialize_canonical(parsed.state);
    IBLT residual = received - bob;
    std::set<std::pair<std::uint64_t, std::vector<std::uint8_t>>> positive, negative;
    const bool decoded = residual.listEntries(positive, negative);
    std::vector<std::uint32_t> alice_only, bob_only;
    for(const auto& item : positive) alice_only.push_back(static_cast<std::uint32_t>(item.first));
    for(const auto& item : negative) bob_only.push_back(static_cast<std::uint32_t>(item.first));
    const bool shape_valid = figure2::CanonicalizeDirected(alice_only, bob_only);
    result.failure = decoded && shape_valid ? "pending_ground_truth" :
        (decoded ? "wrong_output" : "decode_failed");
    result.receiver_cpu = figure2::ThreadCpuSeconds() - begin;
    result.residual_sha256 = figure2::Sha256(residual.serialize_canonical());
    if(result.failure == "pending_ground_truth") {
        result.success = figure2::CompareGroundTruthAfterTimer(
            alice_only, bob_only, dataset, true
        );
        result.failure = result.success ? "success" : "wrong_output";
    }
    result.alice_output_sha256 = figure2::VectorSha256(alice_only);
    result.bob_output_sha256 = figure2::VectorSha256(bob_only);
    result.logical_state_bits = static_cast<std::uint64_t>(cells) * 87U;
    result.state_bits = state.size() * 8U;
    result.control_bits = 0U;
    result.total_payload_bits = result.state_bits;
    if(state.size() != (static_cast<std::size_t>(cells) * 87U + 7U) / 8U ||
       result.total_payload_bits != result.state_bits) {
        throw std::runtime_error("external IBLT accounting mismatch");
    }
    result.payload_sha256 = figure2::Sha256(state); // Outside all timing windows.
    return result;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if(argc == 2 && std::string(argv[1]) == "--self-test") {
            IBLT sketch(2, 0);
            const std::vector<unsigned char> state = sketch.serialize_canonical();
            IBLT parsed(2, 0);
            parsed.deserialize_canonical(state);
            bool malformed_rejected = false;
            try {
                ParseState(std::vector<unsigned char>(state.begin(), state.end() - 1), 4);
            } catch(const std::exception&) {
                malformed_rejected = true;
            }
            const bool passed = sketch.cell_count() == 4U && state.size() == 44U &&
                state.size() * 8U == 352U && parsed.serialize_canonical() == state &&
                malformed_rejected;
            std::cout << "{\"protocol\":\"figure2-engine-v2\",\"algorithm\":\"external_iblt\","
                      << "\"golden_total_bits\":" << state.size() * 8U
                      << ",\"malformed_state_rejected\":" << (malformed_rejected ? "true" : "false")
                      << ",\"passed\":" << (passed ? "true" : "false") << "}\n";
            return passed ? 0 : 2;
        }
        if(argc != 4 || std::string(argv[1]) != "--run") {
            throw std::invalid_argument("usage: figure2_external_iblt_engine --run DATASET expected");
        }
        figure2::PrintResult(Run(figure2::ReadDataset(argv[2]), std::stoull(argv[3])));
        return 0;
    } catch(const std::exception& error) {
        std::cerr << typeid(error).name() << ": " << error.what() << '\n';
        return 1;
    }
}
