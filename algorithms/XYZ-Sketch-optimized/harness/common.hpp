#ifndef FIGURE2_COMMON_HPP
#define FIGURE2_COMMON_HPP

#include <openssl/sha.h>
#include <time.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <sched.h>
namespace figure2 {
inline std::string ActualAffinity() {
    cpu_set_t mask; CPU_ZERO(&mask);
    if (sched_getaffinity(0, sizeof(mask), &mask)) throw std::runtime_error("affinity read failed");
    std::string value;
    for (int i=0;i<CPU_SETSIZE;++i) if (CPU_ISSET(i,&mask)) {
        if (!value.empty()) value += ",";
        value += std::to_string(i);
    }
    return value;
}

constexpr std::uint32_t kFieldModulus = 1073741824U;

inline void AppendU32(std::vector<unsigned char>& output, std::uint32_t value) {
    output.push_back(static_cast<unsigned char>(value >> 24U));
    output.push_back(static_cast<unsigned char>(value >> 16U));
    output.push_back(static_cast<unsigned char>(value >> 8U));
    output.push_back(static_cast<unsigned char>(value));
}

inline void AppendU64(std::vector<unsigned char>& output, std::uint64_t value) {
    for(int shift = 56; shift >= 0; shift -= 8) {
        output.push_back(static_cast<unsigned char>(value >> shift));
    }
}

inline std::uint32_t ReadU32(const std::vector<unsigned char>& input, std::size_t& offset) {
    if(offset + 4U > input.size()) throw std::runtime_error("truncated u32");
    std::uint32_t value = 0;
    for(int index = 0; index < 4; ++index) value = (value << 8U) | input[offset++];
    return value;
}

inline std::uint64_t ReadU64(const std::vector<unsigned char>& input, std::size_t& offset) {
    if(offset + 8U > input.size()) throw std::runtime_error("truncated u64");
    std::uint64_t value = 0;
    for(int index = 0; index < 8; ++index) value = (value << 8U) | input[offset++];
    return value;
}

inline std::string Hex(const unsigned char* data, std::size_t size) {
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for(std::size_t index = 0; index < size; ++index) {
        output << std::setw(2) << static_cast<unsigned int>(data[index]);
    }
    return output.str();
}

inline std::string Sha256(const std::vector<unsigned char>& bytes) {
    std::array<unsigned char, SHA256_DIGEST_LENGTH> digest{};
    SHA256(bytes.data(), bytes.size(), digest.data());
    return Hex(digest.data(), digest.size());
}

inline std::string VectorSha256(const std::vector<std::uint32_t>& values) {
    SHA256_CTX context;
    SHA256_Init(&context);
    for(std::uint32_t value : values) {
        const unsigned char encoded[] = {
            static_cast<unsigned char>(value >> 24U),
            static_cast<unsigned char>(value >> 16U),
            static_cast<unsigned char>(value >> 8U),
            static_cast<unsigned char>(value),
        };
        SHA256_Update(&context, encoded, sizeof(encoded));
    }
    std::array<unsigned char, SHA256_DIGEST_LENGTH> digest{};
    SHA256_Final(digest.data(), &context);
    return Hex(digest.data(), digest.size());
}

inline double ThreadCpuSeconds() {
    struct timespec value {};
    if(clock_gettime(CLOCK_THREAD_CPUTIME_ID, &value) != 0) {
        throw std::runtime_error("clock_gettime failed");
    }
    return static_cast<double>(value.tv_sec) + static_cast<double>(value.tv_nsec) * 1e-9;
}

struct Dataset {
    bool full = false;
    std::uint32_t d = 0;
    std::uint64_t identity_seed = 0;
    std::uint64_t alice_order_seed = 0;
    std::uint64_t bob_order_seed = 0;
    std::vector<std::uint32_t> alice;
    std::vector<std::uint32_t> bob;
    std::vector<std::uint32_t> alice_only;
    std::vector<std::uint32_t> bob_only;
    std::array<std::string, 4> hashes;
};

inline void WriteBytes(std::ofstream& output, const std::vector<unsigned char>& bytes) {
    output.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    if(!output) throw std::runtime_error("dataset write failed");
}

inline void WriteDataset(const std::string& path, const Dataset& dataset) {
    std::vector<unsigned char> header;
    header.insert(header.end(), {'F', '2', 'D', 'S'});
    AppendU32(header, 1U);
    AppendU32(header, dataset.full ? 1U : 0U);
    AppendU32(header, dataset.d);
    AppendU64(header, dataset.alice.size());
    AppendU64(header, dataset.bob.size());
    AppendU64(header, dataset.alice_only.size());
    AppendU64(header, dataset.bob_only.size());
    AppendU64(header, dataset.identity_seed);
    AppendU64(header, dataset.alice_order_seed);
    AppendU64(header, dataset.bob_order_seed);
    for(const std::string& hash : dataset.hashes) {
        if(hash.size() != 64U) throw std::runtime_error("invalid dataset hash");
        for(std::size_t index = 0; index < hash.size(); index += 2) {
            header.push_back(static_cast<unsigned char>(std::stoul(hash.substr(index, 2), nullptr, 16)));
        }
    }
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if(!output) throw std::runtime_error("cannot create dataset file");
    WriteBytes(output, header);
    for(const auto* values : {&dataset.alice, &dataset.bob, &dataset.alice_only, &dataset.bob_only}) {
        std::vector<unsigned char> encoded;
        encoded.reserve(values->size() * 4U);
        for(std::uint32_t value : *values) AppendU32(encoded, value);
        WriteBytes(output, encoded);
    }
}

inline Dataset ReadDataset(const std::string& path) {
    std::ifstream stream(path, std::ios::binary);
    if(!stream) throw std::runtime_error("cannot open dataset");
    std::vector<unsigned char> bytes(
        (std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>()
    );
    if(bytes.size() < 200U || std::string(bytes.begin(), bytes.begin() + 4) != "F2DS") {
        throw std::runtime_error("invalid dataset magic/size");
    }
    std::size_t offset = 4U;
    if(ReadU32(bytes, offset) != 1U) throw std::runtime_error("unsupported dataset version");
    Dataset dataset;
    dataset.full = ReadU32(bytes, offset) == 1U;
    dataset.d = ReadU32(bytes, offset);
    const std::array<std::uint64_t, 4> sizes = {
        ReadU64(bytes, offset), ReadU64(bytes, offset), ReadU64(bytes, offset), ReadU64(bytes, offset)
    };
    dataset.identity_seed = ReadU64(bytes, offset);
    dataset.alice_order_seed = ReadU64(bytes, offset);
    dataset.bob_order_seed = ReadU64(bytes, offset);
    for(std::string& hash : dataset.hashes) {
        if(offset + 32U > bytes.size()) throw std::runtime_error("truncated dataset hashes");
        hash = Hex(bytes.data() + offset, 32U);
        offset += 32U;
    }
    std::array<std::vector<std::uint32_t>*, 4> outputs = {
        &dataset.alice, &dataset.bob, &dataset.alice_only, &dataset.bob_only
    };
    for(std::size_t array_index = 0; array_index < outputs.size(); ++array_index) {
        if(sizes[array_index] > (bytes.size() - offset) / 4U) throw std::runtime_error("dataset size overflow");
        outputs[array_index]->reserve(static_cast<std::size_t>(sizes[array_index]));
        for(std::uint64_t index = 0; index < sizes[array_index]; ++index) {
            outputs[array_index]->push_back(ReadU32(bytes, offset));
        }
    }
    if(offset != bytes.size()) throw std::runtime_error("dataset has trailing bytes");
    for(std::size_t index = 0; index < outputs.size(); ++index) {
        if(VectorSha256(*outputs[index]) != dataset.hashes[index]) {
            throw std::runtime_error("dataset array hash mismatch");
        }
    }
    if(dataset.alice_only.size() + dataset.bob_only.size() != dataset.d) {
        throw std::runtime_error("dataset difference cardinality mismatch");
    }
    return dataset;
}

inline void ValidatePackedState(
    const std::vector<unsigned char>& state,
    std::uint64_t logical_state_bits
) {
    const std::uint64_t state_bytes_u64 = (logical_state_bits + 7U) / 8U;
    if(state_bytes_u64 != state.size()) {
        throw std::runtime_error("algorithm state length mismatch");
    }
    if(logical_state_bits % 8U && state_bytes_u64) {
        const unsigned int unused = 8U - static_cast<unsigned int>(logical_state_bits % 8U);
        const unsigned char mask = static_cast<unsigned char>((1U << unused) - 1U);
        if(state[static_cast<std::size_t>(state_bytes_u64) - 1U] & mask) {
            throw std::runtime_error("algorithm state padding bits are nonzero");
        }
    }
}

inline bool CanonicalizeDirected(
    std::vector<std::uint32_t>& alice,
    std::vector<std::uint32_t>& bob
) {
    std::sort(alice.begin(), alice.end());
    std::sort(bob.begin(), bob.end());
    const auto valid = [](const std::vector<std::uint32_t>& values) {
        return std::all_of(values.begin(), values.end(), [](std::uint32_t value) {
            return value > 0U && value < kFieldModulus;
        }) && std::adjacent_find(values.begin(), values.end()) == values.end();
    };
    if(!valid(alice) || !valid(bob)) return false;
    std::vector<std::uint32_t> overlap;
    std::set_intersection(
        alice.begin(), alice.end(), bob.begin(), bob.end(), std::back_inserter(overlap)
    );
    return overlap.empty();
}

inline bool CompareGroundTruthAfterTimer(
    const std::vector<std::uint32_t>& alice,
    const std::vector<std::uint32_t>& bob,
    const Dataset& dataset,
    bool receiver_timer_stopped
) {
    if(!receiver_timer_stopped) throw std::runtime_error("ground truth comparison is inside receiver timer");
    return alice == dataset.alice_only && bob == dataset.bob_only;
}

inline bool ExactDirected(
    std::vector<std::uint32_t> alice,
    std::vector<std::uint32_t> bob,
    const Dataset& dataset
) {
    return CanonicalizeDirected(alice, bob) &&
        alice == dataset.alice_only && bob == dataset.bob_only;
}

struct EngineResult {
    std::string algorithm;
    bool success = false;
    std::string failure = "process_error";
    std::uint64_t logical_state_bits = 0;
    std::uint64_t state_bits = 0;
    std::uint64_t control_bits = 0;
    std::uint64_t total_payload_bits = 0;
    double update_alice_cpu = 0.0;
    double update_bob_cpu = 0.0;
    double sender_cpu = 0.0;
    double transfer_cpu = 0.0;
    double receiver_cpu = 0.0;
    std::string alice_output_sha256;
    std::string bob_output_sha256;
    std::string residual_sha256;
    std::int64_t required_symbols = -1;
    std::string payload_sha256;
};

inline void PrintResult(const EngineResult& result) {
    std::cout << "figure2-engine-v2\t" << result.algorithm << '\t'
              << (result.success ? 1 : 0) << '\t' << result.failure << '\t'
              << result.logical_state_bits << '\t' << result.state_bits << '\t'
              << result.control_bits << '\t' << result.total_payload_bits << '\t'
              << std::setprecision(17) << result.update_alice_cpu << '\t'
              << result.update_bob_cpu << '\t' << result.sender_cpu << '\t'
              << result.transfer_cpu << '\t' << result.receiver_cpu << '\t'
              << result.alice_output_sha256 << '\t' << result.bob_output_sha256 << '\t'
              << result.residual_sha256 << '\t' << result.required_symbols << '\t'
              << result.payload_sha256 << '\t' << ActualAffinity() << '\n';
}

}  // namespace figure2

#endif
