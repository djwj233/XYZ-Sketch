#include "common.hpp"
#include "iblt.h"
#include <iostream>
#include <set>

namespace {
void update(IBLT& table, const std::vector<std::uint32_t>& values) {
    for (auto value : values) table.insert(value, {});
}
figure2::EngineResult run(const figure2::Dataset& data, size_t cells, size_t k,
                         size_t z, std::uint64_t seed) {
    figure2::EngineResult result;
    result.algorithm = "iblt_sc";
    IBLT alice(cells, k, z, seed), bob(cells, k, z, seed);
    double begin = figure2::ThreadCpuSeconds();
    update(alice, data.alice);
    result.update_alice_cpu = figure2::ThreadCpuSeconds()-begin;
    begin = figure2::ThreadCpuSeconds();
    update(bob, data.bob);
    result.update_bob_cpu = figure2::ThreadCpuSeconds()-begin;
    begin = figure2::ThreadCpuSeconds();
    auto message = alice.serialize_canonical();
    result.sender_cpu = figure2::ThreadCpuSeconds()-begin;
    begin = figure2::ThreadCpuSeconds();
    auto transmitted = message;
    result.transfer_cpu = figure2::ThreadCpuSeconds()-begin;
    begin = figure2::ThreadCpuSeconds();
    figure2::ValidatePackedState(transmitted, std::uint64_t(cells)*87);
    IBLT received(cells, k, z, seed);
    received.deserialize_canonical(transmitted);
    auto residual = received-bob;
    std::set<std::pair<std::uint64_t, std::vector<std::uint8_t>>> positive, negative;
    const bool decoded = residual.listEntries(positive, negative);
    std::vector<std::uint32_t> a, b;
    for (const auto& entry : positive) a.push_back(entry.first);
    for (const auto& entry : negative) b.push_back(entry.first);
    const bool shape = figure2::CanonicalizeDirected(a,b);
    result.failure = decoded && shape ? "pending_ground_truth" : (decoded ? "wrong_output" : "decode_failed");
    result.receiver_cpu = figure2::ThreadCpuSeconds()-begin;
    result.payload_sha256 = figure2::Sha256(message);
    result.residual_sha256 = figure2::Sha256(residual.serialize_canonical());
    if (result.failure == "pending_ground_truth") {
        result.success = figure2::CompareGroundTruthAfterTimer(a,b,data,true);
        result.failure = result.success ? "success" : "wrong_output";
    }
    result.alice_output_sha256 = figure2::VectorSha256(a);
    result.bob_output_sha256 = figure2::VectorSha256(b);
    result.logical_state_bits = std::uint64_t(cells)*87;
    result.state_bits = message.size()*8;
    result.total_payload_bits = result.state_bits;
    return result;
}
}
int main(int argc, char** argv) {
    try {
        if (argc != 7 || std::string(argv[1])!="--run")
            throw std::invalid_argument("usage: --run DATASET M k z seed");
        figure2::PrintResult(run(figure2::ReadDataset(argv[2]),std::stoull(argv[3]),
                            std::stoull(argv[4]),std::stoull(argv[5]),std::stoull(argv[6])));
        return 0;
    } catch (const std::exception& e) {
        std::cerr << typeid(e).name() << ": " << e.what() << '\n';
        return 1;
    }
}
