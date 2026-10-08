#include "common.hpp"
#include "iblt.h"
#include <iostream>
#include <set>
#include <string>

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: engine DATASET");
        const auto data = figure2::ReadDataset(argv[1]);
        if (!data.full || data.d != 100000 || data.alice.size() != 10000000 ||
            data.bob.size() != 10000000) throw std::runtime_error("unexpected cohort");
        IBLT alice(87000, 0), bob(87000, 0);
        for (auto x : data.alice) alice.insert(x, {});
        for (auto x : data.bob) bob.insert(x, {});
        if (alice.cell_count() != 130500) throw std::runtime_error("cell count changed");
        const auto residual32 = alice - bob;
        const auto reference_state = alice.serialize_canonical();
        const auto reference_residual = residual32.serialize_canonical();
        const std::vector<unsigned> widths = {
            0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,28,32
        };
        for (unsigned bits : widths) {
            auto sender = alice, local = bob;
            sender.set_fingerprint_bits(bits);
            local.set_fingerprint_bits(bits);
            const auto message = sender.serialize_canonical();
            IBLT received(87000, 0);
            received.set_fingerprint_bits(bits);
            received.deserialize_canonical(message);
            if (received.serialize_canonical() != message)
                throw std::runtime_error("wire roundtrip failed");
            auto residual = received - local;
            auto masked = residual32;
            masked.set_fingerprint_bits(bits);
            if (masked.serialize_canonical() != residual.serialize_canonical())
                throw std::runtime_error("masking/subtraction disagreement");
            bool original_identity = bits != 32 ||
                (message == reference_state && residual.serialize_canonical() == reference_residual);
            if (!original_identity) throw std::runtime_error("32-bit identity failed");
            IBLT::DecodeStats stats;
            stats.max_peels = 1000000;
            stats.max_inspections = 13050000;
            std::set<std::pair<uint64_t,std::vector<uint8_t>>> pos, neg;
            const double begin = figure2::ThreadCpuSeconds();
            const bool decoded = residual.listEntries(pos, neg, &stats);
            const double decode_seconds = figure2::ThreadCpuSeconds() - begin;
            std::vector<uint32_t> a, b;
            for (const auto& x : pos) a.push_back(static_cast<uint32_t>(x.first));
            for (const auto& x : neg) b.push_back(static_cast<uint32_t>(x.first));
            const bool shape = figure2::CanonicalizeDirected(a, b);
            const bool exact = shape && figure2::CompareGroundTruthAfterTimer(a, b, data, true);
            const bool success = decoded && exact && !stats.limit_hit;
            const char* status = stats.limit_hit ? "decode_budget_exceeded" :
                (success ? "success" : (decoded ? "wrong_output" : "decode_failed"));
            const uint64_t logical = 130500ULL * (55 + bits);
            if (message.size() != (logical+7)/8) throw std::runtime_error("wire accounting failed");
            std::cout << "{\"fingerprint_bits\":" << bits
                << ",\"status\":\"" << status << "\",\"success\":" << (success?"true":"false")
                << ",\"decoder_reported_success\":" << (decoded?"true":"false")
                << ",\"ground_truth_exact\":" << (exact?"true":"false")
                << ",\"shape_valid\":" << (shape?"true":"false")
                << ",\"decoded_positive\":" << a.size() << ",\"decoded_negative\":" << b.size()
                << ",\"peel_operations\":" << stats.peels
                << ",\"cell_inspections\":" << stats.inspections
                << ",\"limit_hit\":" << (stats.limit_hit?"true":"false")
                << ",\"remaining_cells\":" << stats.remaining_cells
                << ",\"decode_cpu_seconds\":" << std::setprecision(17) << decode_seconds
                << ",\"logical_bits\":" << logical << ",\"payload_bytes\":" << message.size()
                << ",\"payload_sha256\":\"" << figure2::Sha256(message)
                << "\",\"initial_residual_sha256\":\"" << figure2::Sha256(residual.serialize_canonical())
                << "\",\"alice_hash\":\"" << figure2::VectorSha256(a)
                << "\",\"bob_hash\":\"" << figure2::VectorSha256(b)
                << "\",\"wire_roundtrip\":true,\"masking_subtraction_identity\":true"
                << ",\"original_32bit_identity\":" << (original_identity?"true":"false") << "}" << std::endl;
        }
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
