#include "common.hpp"

#include <iostream>
#include <list>
#include <memory>

#include "CPISync_HalfRound.h"
#include "CommString.h"

namespace {

std::vector<std::uint32_t> Values(const std::list<DataObject*>& objects) {
    std::vector<std::uint32_t> output;
    output.reserve(objects.size());
    for(DataObject* object : objects) output.push_back(static_cast<std::uint32_t>(to_ulong(object->to_ZZ())));
    return output;
}

void DeleteOutputs(std::list<DataObject*>& values) {
    for(DataObject* value : values) delete value;
    values.clear();
}

figure2::EngineResult Run(const figure2::Dataset& dataset) {
    figure2::EngineResult result;
    result.algorithm = "cpisync";
    CPISync_HalfRound alice(dataset.d, 30, 4, 0);
    CPISync_HalfRound bob(dataset.d, 30, 4, 0);
    std::vector<std::unique_ptr<DataObject>> alice_objects, bob_objects;
    alice_objects.reserve(dataset.alice.size());
    bob_objects.reserve(dataset.bob.size());
    for(std::uint32_t value : dataset.alice) alice_objects.emplace_back(new DataObject(to_ZZ(value)));
    for(std::uint32_t value : dataset.bob) bob_objects.emplace_back(new DataObject(to_ZZ(value)));
    double begin = figure2::ThreadCpuSeconds();
    for(const auto& value : alice_objects) {
        if(!alice.addElem(value.get())) throw std::runtime_error("CPISync Alice add failed");
    }
    result.update_alice_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    for(const auto& value : bob_objects) {
        if(!bob.addElem(value.get())) throw std::runtime_error("CPISync Bob add failed");
    }
    result.update_bob_cpu = figure2::ThreadCpuSeconds() - begin;
    std::list<DataObject*> unused_a, unused_b;
    begin = figure2::ThreadCpuSeconds();
    std::shared_ptr<CommString> client(new CommString("", false));
    const bool client_ok = alice.SyncClient(client, unused_a, unused_b);
    const std::string transcript = client->getString();
    if(client->getXmitBytes() != static_cast<long>(transcript.size())) {
        throw std::runtime_error("CPISync client byte counter mismatch");
    }
    result.sender_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    std::string immutable_transcript = transcript;
    result.transfer_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    std::shared_ptr<CommString> server(new CommString(immutable_transcript, false));
    std::list<DataObject*> bob_minus_alice, alice_minus_bob;
    const bool server_ok = bob.SyncServer(server, bob_minus_alice, alice_minus_bob);
    if(server->getRecvBytes() != static_cast<long>(immutable_transcript.size())) {
        throw std::runtime_error("CPISync server byte counter mismatch");
    }
    std::vector<std::uint32_t> alice_only = Values(alice_minus_bob);
    std::vector<std::uint32_t> bob_only = Values(bob_minus_alice);
    const bool shape_valid = figure2::CanonicalizeDirected(alice_only, bob_only);
    result.failure = client_ok && server_ok && shape_valid ? "pending_ground_truth" :
        ((client_ok && server_ok) ? "wrong_output" : "decode_failed");
    result.receiver_cpu += figure2::ThreadCpuSeconds() - begin;
    if(result.failure == "pending_ground_truth") {
        result.success = figure2::CompareGroundTruthAfterTimer(
            alice_only, bob_only, dataset, true
        );
        result.failure = result.success ? "success" : "wrong_output";
    }
    result.alice_output_sha256 = figure2::VectorSha256(alice_only);
    result.bob_output_sha256 = figure2::VectorSha256(bob_only);
    result.residual_sha256 = figure2::Sha256(
        std::vector<unsigned char>(transcript.begin(), transcript.end())
    );
    if(transcript.size() < 41U) throw std::runtime_error("CPISync transcript shorter than control fields");
    const std::size_t state_bytes = transcript.size() - 41U;
    result.logical_state_bits = state_bytes * 8U;
    result.state_bits = state_bytes * 8U;
    result.control_bits = 41U * 8U;
    result.total_payload_bits = transcript.size() * 8U;
    if(result.total_payload_bits != result.state_bits + result.control_bits) {
        throw std::runtime_error("CPISync accounting mismatch");
    }
    DeleteOutputs(unused_a);
    DeleteOutputs(unused_b);
    DeleteOutputs(bob_minus_alice);
    DeleteOutputs(alice_minus_bob);
    return result;
}

figure2::Dataset GoldenDataset() {
    figure2::Dataset dataset;
    dataset.full = true;
    dataset.d = 2;
    dataset.alice = {1, 2};
    dataset.bob = {2, 3};
    dataset.alice_only = {1};
    dataset.bob_only = {3};
    dataset.hashes = {
        figure2::VectorSha256(dataset.alice), figure2::VectorSha256(dataset.bob),
        figure2::VectorSha256(dataset.alice_only), figure2::VectorSha256(dataset.bob_only),
    };
    return dataset;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if(argc == 2 && std::string(argv[1]) == "--self-test") {
            figure2::EngineResult result = Run(GoldenDataset());
            const bool passed = result.success && result.total_payload_bits == 392U &&
                result.state_bits == 64U && result.control_bits == 328U;
            std::cout << "{\"protocol\":\"figure2-engine-v2\",\"algorithm\":\"cpisync\","
                      << "\"golden_total_bits\":" << result.total_payload_bits
                      << ",\"golden_state_bits\":" << result.state_bits
                      << ",\"golden_control_bits\":" << result.control_bits
                      << ",\"passed\":" << (passed ? "true" : "false") << "}\n";
            return passed ? 0 : 2;
        }
        if(argc != 3 || std::string(argv[1]) != "--run") {
            throw std::invalid_argument("usage: figure2_cpisync_engine --run DATASET");
        }
        figure2::PrintResult(Run(figure2::ReadDataset(argv[2])));
        return 0;
    } catch(const std::exception& error) {
        std::cerr << typeid(error).name() << ": " << error.what() << '\n';
        return 1;
    }
}
