#include "common.hpp"

#include <iostream>
#include <tuple>
#include <utility>

#include "iblt.cpp"

namespace {

using Cell = std::tuple<int, std::uint32_t, std::uint32_t>;

std::vector<unsigned char> Serialize(const std::vector<Cell>& cells) {
    std::vector<unsigned char> output;
    output.reserve(cells.size() * 12U);
    for(const Cell& cell : cells) {
        figure2::AppendU32(output, static_cast<std::uint32_t>(std::get<0>(cell)));
        figure2::AppendU32(output, std::get<1>(cell));
        figure2::AppendU32(output, std::get<2>(cell));
    }
    return output;
}

std::vector<Cell> Parse(const std::vector<unsigned char>& bytes, std::size_t cells) {
    if(bytes.size() != cells * 12U) throw std::runtime_error("project IBLT state size mismatch");
    std::size_t offset = 0;
    std::vector<Cell> output;
    output.reserve(cells);
    for(std::size_t index = 0; index < cells; ++index) {
        const std::int32_t count = static_cast<std::int32_t>(figure2::ReadU32(bytes, offset));
        const std::uint32_t key_sum = figure2::ReadU32(bytes, offset);
        const std::uint32_t fingerprint = figure2::ReadU32(bytes, offset);
        output.emplace_back(count, key_sum, fingerprint);
    }
    return output;
}

std::vector<Cell> Residual(const std::vector<Cell>& alice, const std::vector<Cell>& bob) {
    if(alice.size() != bob.size()) throw std::runtime_error("project IBLT residual size mismatch");
    std::vector<Cell> result(alice.size());
    for(std::size_t index = 0; index < alice.size(); ++index) {
        result[index] = Cell{
            std::get<0>(alice[index]) - std::get<0>(bob[index]),
            std::get<1>(alice[index]) - std::get<1>(bob[index]),
            std::get<2>(alice[index]) ^ std::get<2>(bob[index]),
        };
    }
    return result;
}

struct ParsedProjectIBLT {
    std::vector<Cell> state;
};

ParsedProjectIBLT ParseState(
    const std::vector<unsigned char>& state, std::uint32_t cells
) {
    figure2::ValidatePackedState(state, static_cast<std::uint64_t>(cells) * 96U);
    return ParsedProjectIBLT{Parse(state, cells)};
}

figure2::EngineResult Run(const figure2::Dataset& dataset, int cells) {
    figure2::EngineResult result;
    result.algorithm = "project_iblt";
    const double factor = (static_cast<double>(cells) - 0.5) / dataset.d;
    IBLT algorithm(dataset.d, factor);
    if(algorithm.cell_count() != cells) throw std::runtime_error("project IBLT exact M assertion failed");
    std::vector<std::uint32_t> alice_input(dataset.alice);
    std::vector<std::uint32_t> bob_input(dataset.bob);
    double begin = figure2::ThreadCpuSeconds();
    std::vector<Cell> alice = algorithm.Encode(std::move(alice_input));
    result.update_alice_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    std::vector<Cell> bob = algorithm.Encode(std::move(bob_input));
    result.update_bob_cpu = figure2::ThreadCpuSeconds() - begin;

    begin = figure2::ThreadCpuSeconds();
    std::vector<unsigned char> state = Serialize(alice);
    result.sender_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    std::vector<unsigned char> received_state = state;
    result.transfer_cpu = figure2::ThreadCpuSeconds() - begin;
    result.residual_sha256 = figure2::Sha256(Serialize(Residual(alice, bob)));
    begin = figure2::ThreadCpuSeconds();
    ParsedProjectIBLT parsed = ParseState(received_state, static_cast<std::uint32_t>(cells));
    IBLT receiver_algorithm(dataset.d, factor);
    if(receiver_algorithm.cell_count() != cells ||
       receiver_algorithm.hash_count_value() != algorithm.hash_count_value()) {
        throw std::runtime_error("project IBLT receiver configuration mismatch");
    }
    auto decoded = receiver_algorithm.Decode(std::move(parsed.state), std::move(bob));
    std::vector<std::uint32_t> alice_only = decoded.first;
    std::vector<std::uint32_t> bob_only = decoded.second;
    result.failure = figure2::CanonicalizeDirected(alice_only, bob_only) ?
        "pending_ground_truth" : "wrong_output";
    result.receiver_cpu = figure2::ThreadCpuSeconds() - begin;
    if(result.failure == "pending_ground_truth") {
        result.success = figure2::CompareGroundTruthAfterTimer(
            alice_only, bob_only, dataset, true
        );
        result.failure = result.success ? "success" : "wrong_output";
    }
    result.alice_output_sha256 = figure2::VectorSha256(alice_only);
    result.bob_output_sha256 = figure2::VectorSha256(bob_only);
    result.logical_state_bits = state.size() * 8U;
    result.state_bits = state.size() * 8U;
    result.control_bits = 0U;
    result.total_payload_bits = result.state_bits;
    if(state.size() != static_cast<std::size_t>(cells) * 12U ||
       result.total_payload_bits != result.state_bits) {
        throw std::runtime_error("project IBLT accounting mismatch");
    }
    return result;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if(argc == 2 && std::string(argv[1]) == "--self-test") {
            IBLT algorithm(2, 1.25);
            std::vector<Cell> state = algorithm.Encode({});
            const std::vector<unsigned char> bytes = Serialize(state);
            bool malformed_rejected = false;
            try {
                ParseState(std::vector<unsigned char>(bytes.begin(), bytes.end() - 1), 3);
            } catch(const std::exception&) {
                malformed_rejected = true;
            }
            const bool passed = algorithm.cell_count() == 3 && algorithm.hash_count_value() == 4 &&
                bytes.size() == 36U && bytes.size() * 8U == 288U &&
                Parse(bytes, 3) == state && malformed_rejected;
            std::cout << "{\"protocol\":\"figure2-engine-v2\",\"algorithm\":\"project_iblt\","
                      << "\"golden_total_bits\":" << bytes.size() * 8U
                      << ",\"malformed_state_rejected\":" << (malformed_rejected ? "true" : "false")
                      << ",\"passed\":" << (passed ? "true" : "false") << "}\n";
            return passed ? 0 : 2;
        }
        if(argc != 4 || std::string(argv[1]) != "--run") {
            throw std::invalid_argument("usage: figure2_project_iblt_engine --run DATASET M");
        }
        figure2::PrintResult(Run(figure2::ReadDataset(argv[2]), std::stoi(argv[3])));
        return 0;
    } catch(const std::exception& error) {
        std::cerr << typeid(error).name() << ": " << error.what() << '\n';
        return 1;
    }
}
