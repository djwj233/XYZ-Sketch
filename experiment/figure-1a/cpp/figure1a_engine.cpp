#include <openssl/sha.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

#include "XYZSketch.h"

namespace {

constexpr const char* kProtocol = "figure1a-engine-v1";
constexpr std::uint32_t kResultMagic = 0x46314152U;
using Clock = std::chrono::steady_clock;

struct Config {
    std::string id;
    std::string label;
    int cell_count;
    double a;
    int coupling_z;
};

enum FailureCode : std::uint32_t {
    kSuccess = 0,
    kDecodeFailed = 1,
    kWrongAliceOnly = 2,
    kWrongBobOnly = 3,
    kWrongBoth = 4,
    kDuplicateOutput = 5,
    kSerializationMismatch = 6,
    kProcessError = 7,
};

struct JobResult {
    std::uint32_t magic = kResultMagic;
    std::uint32_t index = 0;
    std::uint32_t success = 0;
    std::uint32_t failure = kProcessError;
    std::uint64_t logical_state_bits = 0;
    std::uint64_t state_bits = 0;
    std::uint64_t control_bits = 0;
    std::uint64_t total_payload_bits = 0;
    double alice_encode_seconds = 0.0;
    double serialization_seconds = 0.0;
    double bob_encode_seconds = 0.0;
    double decode_seconds = 0.0;
    double total_seconds = 0.0;
};

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
            if(!chosen.insert(fallback).second) throw std::runtime_error("Floyd fallback duplicate");
            values.push_back(static_cast<int>(fallback + 1U));
        }
    }
    if(values.size() != count || chosen.size() != count) {
        throw std::runtime_error("Floyd cardinality mismatch");
    }
    for(int value : values) {
        if(value <= 0 || value >= P) throw std::runtime_error("sample outside nonzero field");
    }
    std::shuffle(values.begin(), values.end(), generator);
    return values;
}

std::string SampleSha256(const std::vector<int>& values) {
    SHA256_CTX context;
    SHA256_Init(&context);
    for(int value : values) {
        const unsigned char encoded[] = {
            static_cast<unsigned char>((static_cast<std::uint32_t>(value) >> 24U) & 0xffU),
            static_cast<unsigned char>((static_cast<std::uint32_t>(value) >> 16U) & 0xffU),
            static_cast<unsigned char>((static_cast<std::uint32_t>(value) >> 8U) & 0xffU),
            static_cast<unsigned char>(static_cast<std::uint32_t>(value) & 0xffU),
        };
        SHA256_Update(&context, encoded, sizeof(encoded));
    }
    std::array<unsigned char, SHA256_DIGEST_LENGTH> digest{};
    SHA256_Final(digest.data(), &context);
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for(unsigned char value : digest) output << std::setw(2) << static_cast<unsigned int>(value);
    return output.str();
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

void AppendU32(std::vector<unsigned char>& output, std::uint32_t value) {
    output.push_back(static_cast<unsigned char>((value >> 24U) & 0xffU));
    output.push_back(static_cast<unsigned char>((value >> 16U) & 0xffU));
    output.push_back(static_cast<unsigned char>((value >> 8U) & 0xffU));
    output.push_back(static_cast<unsigned char>(value & 0xffU));
}

void AppendU64(std::vector<unsigned char>& output, std::uint64_t value) {
    for(int shift = 56; shift >= 0; shift -= 8) {
        output.push_back(static_cast<unsigned char>((value >> shift) & 0xffU));
    }
}

std::uint32_t ReadU32(const std::vector<unsigned char>& input, std::size_t offset) {
    if(offset + 4U > input.size()) throw std::runtime_error("truncated u32");
    std::uint32_t value = 0;
    for(std::size_t index = 0; index < 4; ++index) value = (value << 8U) | input[offset + index];
    return value;
}

std::uint64_t ReadU64(const std::vector<unsigned char>& input, std::size_t offset) {
    if(offset + 8U > input.size()) throw std::runtime_error("truncated u64");
    std::uint64_t value = 0;
    for(std::size_t index = 0; index < 8; ++index) value = (value << 8U) | input[offset + index];
    return value;
}

std::vector<unsigned char> PackBits(const std::vector<bool>& bits) {
    std::vector<unsigned char> output((bits.size() + 7U) / 8U, 0U);
    for(std::size_t index = 0; index < bits.size(); ++index) {
        if(bits[index]) output[index / 8U] |= static_cast<unsigned char>(1U << (7U - index % 8U));
    }
    return output;
}

std::vector<bool> UnpackBits(
    const std::vector<unsigned char>& bytes,
    std::size_t offset,
    std::size_t bit_count
) {
    if(offset + (bit_count + 7U) / 8U > bytes.size()) throw std::runtime_error("truncated state");
    std::vector<bool> output(bit_count);
    for(std::size_t index = 0; index < bit_count; ++index) {
        output[index] = (bytes[offset + index / 8U] >> (7U - index % 8U)) & 1U;
    }
    return output;
}

std::uint16_t PlacementFlag(const std::string& label) {
    if(label == "iid") return 0;
    if(label == "naive") return 1;
    if(label == "circular") return 2;
    throw std::invalid_argument("unknown placement label");
}

std::vector<unsigned char> BuildWire(
    const Config& config,
    int kval,
    int ell,
    const std::vector<bool>& logical_bits
) {
    std::vector<unsigned char> state = PackBits(logical_bits);
    std::vector<unsigned char> output;
    output.reserve(44U + state.size());
    output.insert(output.end(), {'X', 'S', 'R', '1'});
    output.push_back(1U);
    output.push_back(1U);
    const std::uint16_t flags = PlacementFlag(config.label);
    output.push_back(static_cast<unsigned char>(flags >> 8U));
    output.push_back(static_cast<unsigned char>(flags & 0xffU));
    output.push_back(30U);
    output.insert(output.end(), 3U, 0U);
    AppendU32(output, 20U);
    AppendU64(output, logical_bits.size());
    output.push_back(static_cast<unsigned char>(kval));
    output.push_back(static_cast<unsigned char>(ell));
    output.push_back(config.label == "circular" ? 0U : 1U);
    output.push_back(1U);
    AppendU32(output, static_cast<std::uint32_t>(config.cell_count));
    AppendU32(output, static_cast<std::uint32_t>(config.coupling_z));
    std::uint64_t a_bits = 0;
    static_assert(sizeof(a_bits) == sizeof(config.a));
    std::memcpy(&a_bits, &config.a, sizeof(a_bits));
    AppendU64(output, a_bits);
    output.insert(output.end(), state.begin(), state.end());
    return output;
}

Config ParseAndConfigure(
    const std::vector<unsigned char>& wire,
    int expected_k,
    int expected_ell,
    std::size_t* logical_bits
) {
    if(wire.size() < 44U || std::string(wire.begin(), wire.begin() + 4) != "XSR1") {
        throw std::runtime_error("invalid wire envelope");
    }
    if(wire[4] != 1U || wire[5] != 1U || wire[8] != 30U || ReadU32(wire, 12) != 20U) {
        throw std::runtime_error("invalid wire protocol fields");
    }
    if(wire[9] != 0U || wire[10] != 0U || wire[11] != 0U) {
        throw std::runtime_error("nonzero wire reserved bytes");
    }
    const std::uint16_t flags = (static_cast<std::uint16_t>(wire[6]) << 8U) | wire[7];
    std::string label;
    if(flags == 0) label = "iid";
    else if(flags == 1) label = "naive";
    else if(flags == 2) label = "circular";
    else throw std::runtime_error("invalid placement flags");
    const int parsed_k = wire[24];
    const int parsed_ell = wire[25];
    const int core_mode = wire[26];
    const int dedup = wire[27];
    if(parsed_k != expected_k || parsed_ell != expected_ell || dedup != 1) {
        throw std::runtime_error("parameter header mismatch");
    }
    if((label == "circular") != (core_mode == 0)) {
        throw std::runtime_error("label/core mode mismatch");
    }
    Config config;
    config.label = label;
    config.cell_count = static_cast<int>(ReadU32(wire, 28));
    config.coupling_z = static_cast<int>(ReadU32(wire, 32));
    const std::uint64_t a_bits = ReadU64(wire, 36);
    std::memcpy(&config.a, &a_bits, sizeof(config.a));
    *logical_bits = static_cast<std::size_t>(ReadU64(wire, 16));
    const std::size_t expected_size = 44U + (*logical_bits + 7U) / 8U;
    if(wire.size() != expected_size) throw std::runtime_error("wire state length mismatch");

    k = parsed_k;
    l = parsed_ell;
    M = config.cell_count;
    Hashing::SetHashMode(core_mode == 0 ? Hashing::CIRCULAR : Hashing::NAIVE);
    Hashing::SetCircularA(config.a);
    Hashing::SetDedupHashes(true);
    Hashing::HashingInit(config.coupling_z);
    return config;
}

bool HasDuplicates(const std::vector<int>& values) {
    return std::adjacent_find(values.begin(), values.end()) != values.end();
}

JobResult RunJob(
    std::uint32_t index,
    const Config& config,
    int kval,
    int ell,
    std::uint64_t decoder_seed,
    const std::vector<int>& alice,
    const std::vector<int>& bob,
    const std::vector<int>& expected_alice,
    const std::vector<int>& expected_bob
) {
    JobResult result;
    result.index = index;
    const auto total_begin = Clock::now();
    try {
        k = kval;
        l = ell;
        M = config.cell_count;
        Hashing::SetHashMode(config.label == "circular" ? Hashing::CIRCULAR : Hashing::NAIVE);
        Hashing::SetCircularA(config.a);
        Hashing::SetDedupHashes(true);
        Hashing::HashingInit(config.coupling_z);

        const auto alice_begin = Clock::now();
        XYZSketch alice_sketch = EncodeReference(alice);
        const auto alice_end = Clock::now();
        const auto serialization_begin = Clock::now();
        std::vector<bool> logical = alice_sketch.to_bitstring();
        const std::size_t bits_per_cell = 30U * static_cast<std::size_t>(ell) +
            static_cast<std::size_t>(std::ceil(std::log2(2.0 * ell + 1.0)));
        if(logical.size() != static_cast<std::size_t>(config.cell_count) * bits_per_cell) {
            throw std::runtime_error("logical state bit assertion failed");
        }
        std::vector<unsigned char> wire = BuildWire(config, kval, ell, logical);
        std::size_t parsed_logical_bits = 0;
        Config parsed = ParseAndConfigure(wire, kval, ell, &parsed_logical_bits);
        if(parsed.cell_count != config.cell_count || parsed.coupling_z != config.coupling_z ||
           parsed.a != config.a || parsed.label != config.label) {
            throw std::runtime_error("parsed configuration differs");
        }
        std::vector<bool> received_bits = UnpackBits(wire, 44U, parsed_logical_bits);
        XYZSketch received = to_sketch(received_bits);
        if(received.to_bitstring() != logical) {
            result.failure = kSerializationMismatch;
            return result;
        }
        const auto serialization_end = Clock::now();
        const auto bob_begin = Clock::now();
        XYZSketch bob_sketch = EncodeReference(bob);
        const auto bob_end = Clock::now();
        const auto decode_begin = Clock::now();
        SeedDecoder(decoder_seed);
        auto decoded = (received - bob_sketch).Decode();
        const auto decode_end = Clock::now();

        result.logical_state_bits = logical.size();
        result.state_bits = ((logical.size() + 7U) / 8U) * 8U;
        result.control_bits = 352U;
        result.total_payload_bits = wire.size() * 8U;
        if(result.total_payload_bits != result.state_bits + result.control_bits) {
            throw std::runtime_error("wire accounting mismatch");
        }
        result.alice_encode_seconds = Seconds(alice_begin, alice_end);
        result.serialization_seconds = Seconds(serialization_begin, serialization_end);
        result.bob_encode_seconds = Seconds(bob_begin, bob_end);
        result.decode_seconds = Seconds(decode_begin, decode_end);
        if(decoded.index() == 1) {
            result.failure = kDecodeFailed;
        } else {
            const auto& value = std::get<std::pair<std::vector<int>, std::vector<int>>>(decoded);
            if(HasDuplicates(value.first) || HasDuplicates(value.second)) {
                result.failure = kDuplicateOutput;
            } else {
                const bool alice_correct = value.first == expected_alice;
                const bool bob_correct = value.second == expected_bob;
                if(alice_correct && bob_correct) {
                    result.success = 1;
                    result.failure = kSuccess;
                } else if(!alice_correct && !bob_correct) {
                    result.failure = kWrongBoth;
                } else if(!alice_correct) {
                    result.failure = kWrongAliceOnly;
                } else {
                    result.failure = kWrongBobOnly;
                }
            }
        }
    } catch(...) {
        result.failure = kProcessError;
    }
    result.total_seconds = Seconds(total_begin, Clock::now());
    return result;
}

bool WriteAll(int fd, const void* data, std::size_t size) {
    const unsigned char* current = static_cast<const unsigned char*>(data);
    while(size > 0) {
        const ssize_t written = write(fd, current, size);
        if(written <= 0) return false;
        current += written;
        size -= static_cast<std::size_t>(written);
    }
    return true;
}

bool ReadAll(int fd, void* data, std::size_t size) {
    unsigned char* current = static_cast<unsigned char*>(data);
    while(size > 0) {
        const ssize_t count = read(fd, current, size);
        if(count <= 0) return false;
        current += count;
        size -= static_cast<std::size_t>(count);
    }
    return true;
}

const char* FailureName(std::uint32_t code) {
    switch(code) {
        case kSuccess: return "success";
        case kDecodeFailed: return "decode_failed";
        case kWrongAliceOnly: return "wrong_alice_only";
        case kWrongBobOnly: return "wrong_bob_only";
        case kWrongBoth: return "wrong_alice_and_bob";
        case kDuplicateOutput: return "duplicate_output";
        case kSerializationMismatch: return "serialization_mismatch";
        default: return "process_error";
    }
}

void RunBatch() {
    std::string protocol;
    if(!(std::cin >> protocol) || protocol != kProtocol) throw std::invalid_argument("invalid protocol");
    std::size_t set_size = 0;
    int difference = 0, kval = 0, ell = 0, trial_index = 0, config_count = 0, workers = 0;
    if(!(std::cin >> set_size >> difference >> kval >> ell >> trial_index >> config_count >> workers)) {
        throw std::invalid_argument("invalid batch header");
    }
    std::uint64_t dataset_seed = 0, alice_seed = 0, bob_seed = 0, decoder_seed = 0, hash_seed = 0;
    if(!(std::cin >> dataset_seed >> alice_seed >> bob_seed >> decoder_seed >> hash_seed)) {
        throw std::invalid_argument("invalid seed row");
    }
    if(set_size < static_cast<std::size_t>(difference / 2) || difference <= 0 || difference % 2 ||
       kval <= 0 || ell <= 0 || config_count <= 0 || workers <= 0) {
        throw std::invalid_argument("invalid batch dimensions");
    }
    std::vector<Config> configs(static_cast<std::size_t>(config_count));
    for(Config& config : configs) {
        if(!(std::cin >> config.id >> config.label >> config.cell_count >> config.a >> config.coupling_z)) {
            throw std::invalid_argument("invalid config row");
        }
        if(config.id.find_first_of(" \t\r\n") != std::string::npos) {
            throw std::invalid_argument("config id contains whitespace");
        }
    }

    tool::init(64);
    tool::Pinit(64);
    const auto dataset_begin = Clock::now();
    std::mt19937_64 dataset_generator(dataset_seed);
    const std::size_t one_direction = static_cast<std::size_t>(difference / 2);
    const std::size_t common_size = set_size - one_direction;
    std::vector<int> sample = FloydSample(set_size + one_direction, dataset_generator);
    const std::string sample_sha256 = SampleSha256(sample);
    std::vector<int> alice(sample.begin(), sample.begin() + common_size);
    alice.insert(alice.end(), sample.begin() + common_size, sample.begin() + set_size);
    std::vector<int> bob(sample.begin(), sample.begin() + common_size);
    bob.insert(bob.end(), sample.begin() + set_size, sample.end());
    std::vector<int> expected_alice(sample.begin() + common_size, sample.begin() + set_size);
    std::vector<int> expected_bob(sample.begin() + set_size, sample.end());
    std::sort(expected_alice.begin(), expected_alice.end());
    std::sort(expected_bob.begin(), expected_bob.end());
    std::mt19937_64 alice_generator(alice_seed), bob_generator(bob_seed);
    std::shuffle(alice.begin(), alice.end(), alice_generator);
    std::shuffle(bob.begin(), bob.end(), bob_generator);
    std::vector<int>().swap(sample);
    const double dataset_seconds = Seconds(dataset_begin, Clock::now());

    std::vector<JobResult> results(configs.size());
    const std::size_t worker_count = std::min<std::size_t>(workers, configs.size());
    for(std::size_t start = 0; start < configs.size(); start += worker_count) {
        const std::size_t stop = std::min(configs.size(), start + worker_count);
        struct Child { pid_t pid; int fd; std::size_t index; };
        std::vector<Child> children;
        children.reserve(stop - start);
        for(std::size_t index = start; index < stop; ++index) {
            int descriptors[2];
            if(pipe(descriptors) != 0) throw std::runtime_error("pipe failed");
            const pid_t pid = fork();
            if(pid < 0) throw std::runtime_error("fork failed");
            if(pid == 0) {
                close(descriptors[0]);
                JobResult result = RunJob(
                    static_cast<std::uint32_t>(index), configs[index], kval, ell, decoder_seed,
                    alice, bob, expected_alice, expected_bob
                );
                const bool written = WriteAll(descriptors[1], &result, sizeof(result));
                close(descriptors[1]);
                _exit(written ? 0 : 4);
            }
            close(descriptors[1]);
            children.push_back({pid, descriptors[0], index});
        }
        for(const Child& child : children) {
            JobResult result;
            const bool read_ok = ReadAll(child.fd, &result, sizeof(result));
            close(child.fd);
            int status = 0;
            const pid_t waited = waitpid(child.pid, &status, 0);
            if(!read_ok || waited != child.pid || !WIFEXITED(status) || WEXITSTATUS(status) != 0 ||
               result.magic != kResultMagic || result.index != child.index) {
                result = JobResult{};
                result.index = static_cast<std::uint32_t>(child.index);
                result.failure = kProcessError;
            }
            results[child.index] = result;
        }
    }

    std::cout << kProtocol << '\n';
    std::cout << std::setprecision(17);
    std::cout << "D\t" << trial_index << '\t' << dataset_seconds << '\t' << sample_sha256 << '\t'
              << dataset_seed << '\t' << alice_seed << '\t' << bob_seed << '\t' << decoder_seed << '\t'
              << hash_seed << '\n';
    for(std::size_t index = 0; index < configs.size(); ++index) {
        const JobResult& result = results[index];
        std::cout << "R\t" << configs[index].id << '\t' << result.success << '\t'
                  << FailureName(result.failure) << '\t' << result.logical_state_bits << '\t'
                  << result.state_bits << '\t' << result.control_bits << '\t'
                  << result.total_payload_bits << '\t' << result.alice_encode_seconds << '\t'
                  << result.serialization_seconds << '\t' << result.bob_encode_seconds << '\t'
                  << result.decode_seconds << '\t' << result.total_seconds << '\n';
    }
}

bool ResidualEquivalent(
    const std::vector<int>& common,
    const std::vector<int>& alice_only,
    const std::vector<int>& bob_only,
    const Config& config,
    int kval,
    int ell
) {
    k = kval;
    l = ell;
    M = config.cell_count;
    Hashing::SetHashMode(config.label == "circular" ? Hashing::CIRCULAR : Hashing::NAIVE);
    Hashing::SetCircularA(config.a);
    Hashing::SetDedupHashes(true);
    Hashing::HashingInit(config.coupling_z);
    std::vector<int> alice = common;
    alice.insert(alice.end(), alice_only.begin(), alice_only.end());
    std::vector<int> bob = common;
    bob.insert(bob.end(), bob_only.begin(), bob_only.end());
    XYZSketch a = EncodeReference(alice);
    XYZSketch b = EncodeReference(bob);
    XYZSketch residual = a - b;
    const std::vector<bool> state = residual.to_bitstring();

    XYZSketch da = EncodeReference(alice_only);
    XYZSketch db = EncodeReference(bob_only);
    XYZSketch difference_only = da - db;
    if(state != difference_only.to_bitstring()) return false;
    SeedDecoder(123456789U);
    auto decoded = residual.Decode();
    if(decoded.index() == 1) return false;
    auto expected_a = alice_only, expected_b = bob_only;
    std::sort(expected_a.begin(), expected_a.end());
    std::sort(expected_b.begin(), expected_b.end());
    const auto& value = std::get<std::pair<std::vector<int>, std::vector<int>>>(decoded);
    return value.first == expected_a && value.second == expected_b;
}

void SelfTest() {
    tool::init(64);
    tool::Pinit(64);
    const std::vector<int> alice_only = {1, 2, 3};
    const std::vector<int> bob_only = {4, 5, 6};
    const std::vector<int> common_small = {10, 11};
    std::vector<int> common_large = common_small;
    for(int value = 100; value < 300; ++value) common_large.push_back(value);
    const std::vector<std::tuple<Config, int, int>> cases = {
        {Config{"iid", "iid", 80, 0.0, 0}, 2, 3},
        {Config{"naive", "naive", 80, 0.0, 2}, 2, 6},
        {Config{"circular", "circular", 80, 0.5, 2}, 3, 4},
    };
    bool equivalence = true;
    for(const auto& item : cases) {
        const Config& config = std::get<0>(item);
        const int kval = std::get<1>(item), ell = std::get<2>(item);
        equivalence = equivalence && ResidualEquivalent(
            common_small, alice_only, bob_only, config, kval, ell
        );
        equivalence = equivalence && ResidualEquivalent(
            common_large, alice_only, bob_only, config, kval, ell
        );
    }
    const std::array<std::tuple<int, int, std::size_t, std::size_t>, 3> golden = {{
        {2, 3, 186, 544}, {2, 6, 368, 720}, {3, 4, 248, 600}
    }};
    bool accounting = true;
    for(const auto& item : golden) {
        k = std::get<0>(item);
        l = std::get<1>(item);
        M = 2;
        Hashing::SetHashMode(Hashing::NAIVE);
        Hashing::SetCircularA(0.0);
        Hashing::SetDedupHashes(true);
        Hashing::HashingInit(0);
        XYZSketch sketch;
        sketch.init();
        Config config{"golden", "iid", 2, 0.0, 0};
        const std::vector<bool> bits = sketch.to_bitstring();
        const std::vector<unsigned char> wire = BuildWire(config, k, l, bits);
        accounting = accounting && bits.size() == std::get<2>(item);
        accounting = accounting && wire.size() * 8U == std::get<3>(item);
    }
    std::cout << "{\"protocol\":\"" << kProtocol << "\",\"residual_equivalence\":"
              << (equivalence ? "true" : "false") << ",\"golden_accounting\":"
              << (accounting ? "true" : "false") << "}\n";
    if(!equivalence || !accounting) throw std::runtime_error("self-test failed");
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if(argc == 2 && std::string(argv[1]) == "--self-test") {
            SelfTest();
        } else if(argc == 1) {
            RunBatch();
        } else {
            throw std::invalid_argument("usage: figure1a_engine [--self-test]");
        }
        return 0;
    } catch(const std::exception& error) {
        std::cerr << typeid(error).name() << ": " << error.what() << '\n';
        return 1;
    }
}
