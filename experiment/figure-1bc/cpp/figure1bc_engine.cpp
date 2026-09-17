#include <openssl/sha.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <exception>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <tuple>
#include <utility>
#include <vector>

namespace {

constexpr int kEll = 6;
constexpr const char* kProtocol = "figure1bc-engine-v1";

struct WordTriple {
  std::uint32_t anchor;
  std::uint32_t offset1;
  std::uint32_t offset2;
};

struct Group {
  std::string id;
  int circular_base_range;
  int z;
};

struct Support {
  int first;
  int second;
  int size;
};

struct PeelResult {
  int residual_edges;
};

struct TrialResult {
  std::string stream_sha256;
  std::vector<int> residual_by_group;
};

std::array<unsigned char, SHA256_DIGEST_LENGTH> Sha256(const std::string& value) {
  std::array<unsigned char, SHA256_DIGEST_LENGTH> digest{};
  SHA256(reinterpret_cast<const unsigned char*>(value.data()), value.size(), digest.data());
  return digest;
}

std::uint32_t FirstU32BigEndian(
    const std::array<unsigned char, SHA256_DIGEST_LENGTH>& digest) {
  return (static_cast<std::uint32_t>(digest[0]) << 24U) |
         (static_cast<std::uint32_t>(digest[1]) << 16U) |
         (static_cast<std::uint32_t>(digest[2]) << 8U) |
         static_cast<std::uint32_t>(digest[3]);
}

std::string Hex(const unsigned char* data, std::size_t size) {
  std::ostringstream stream;
  stream << std::hex << std::setfill('0');
  for (std::size_t index = 0; index < size; ++index) {
    stream << std::setw(2) << static_cast<unsigned int>(data[index]);
  }
  return stream.str();
}

std::string SeedMaterial(std::uint64_t base_seed, const std::string& domain, int d,
                         int M, int trial_index, int edge_index,
                         const char* role) {
  std::ostringstream stream;
  stream << "figure1bc|" << base_seed << '|' << domain << '|' << d << '|' << M
         << '|' << trial_index << '|' << edge_index << '|' << role;
  return stream.str();
}

WordTriple GenerateWords(std::uint64_t base_seed, const std::string& domain, int d,
                         int M, int trial_index, int edge_index) {
  return {
      FirstU32BigEndian(Sha256(SeedMaterial(base_seed, domain, d, M, trial_index,
                                            edge_index, "anchor_word"))),
      FirstU32BigEndian(Sha256(SeedMaterial(base_seed, domain, d, M, trial_index,
                                            edge_index, "offset_word_1"))),
      FirstU32BigEndian(Sha256(SeedMaterial(base_seed, domain, d, M, trial_index,
                                            edge_index, "offset_word_2"))),
  };
}

void UpdateWordStream(SHA256_CTX* context, const WordTriple& words) {
  const std::uint32_t values[] = {words.anchor, words.offset1, words.offset2};
  for (std::uint32_t value : values) {
    const unsigned char encoded[] = {
        static_cast<unsigned char>((value >> 24U) & 0xffU),
        static_cast<unsigned char>((value >> 16U) & 0xffU),
        static_cast<unsigned char>((value >> 8U) & 0xffU),
        static_cast<unsigned char>(value & 0xffU),
    };
    SHA256_Update(context, encoded, sizeof(encoded));
  }
}

Support Place(const WordTriple& words, int M, int circular_base_range, int z) {
  const int range_length = M / (z + 1);
  if (range_length < 1 || circular_base_range < 1 || circular_base_range > M) {
    throw std::invalid_argument("invalid placement geometry");
  }
  const int anchor = static_cast<int>(words.anchor % circular_base_range);
  int first = (anchor + static_cast<int>(words.offset1 % range_length)) % M;
  int second = (anchor + static_cast<int>(words.offset2 % range_length)) % M;
  if (first == second) {
    return {first, first, 1};
  }
  if (first > second) {
    std::swap(first, second);
  }
  return {first, second, 2};
}

PeelResult Peel(int M, const std::vector<WordTriple>& words, const Group& group) {
  std::vector<Support> supports;
  supports.reserve(words.size());
  std::vector<std::vector<int>> adjacency(static_cast<std::size_t>(M));
  std::vector<int> degrees(static_cast<std::size_t>(M), 0);
  for (std::size_t edge = 0; edge < words.size(); ++edge) {
    const Support support = Place(words[edge], M, group.circular_base_range, group.z);
    supports.push_back(support);
    adjacency[static_cast<std::size_t>(support.first)].push_back(static_cast<int>(edge));
    ++degrees[static_cast<std::size_t>(support.first)];
    if (support.size == 2) {
      adjacency[static_cast<std::size_t>(support.second)].push_back(static_cast<int>(edge));
      ++degrees[static_cast<std::size_t>(support.second)];
    }
  }

  std::priority_queue<int, std::vector<int>, std::greater<int>> queue;
  for (int cell = 0; cell < M; ++cell) {
    if (degrees[static_cast<std::size_t>(cell)] >= 1 &&
        degrees[static_cast<std::size_t>(cell)] <= kEll) {
      queue.push(cell);
    }
  }
  std::vector<unsigned char> active(words.size(), 1U);
  int residual = static_cast<int>(words.size());

  while (!queue.empty()) {
    const int cell = queue.top();
    queue.pop();
    const int degree = degrees[static_cast<std::size_t>(cell)];
    if (degree < 1 || degree > kEll) {
      continue;
    }
    for (int edge : adjacency[static_cast<std::size_t>(cell)]) {
      if (active[static_cast<std::size_t>(edge)] == 0U) {
        continue;
      }
      active[static_cast<std::size_t>(edge)] = 0U;
      --residual;
      const Support& support = supports[static_cast<std::size_t>(edge)];
      const int endpoints[] = {support.first, support.second};
      for (int index = 0; index < support.size; ++index) {
        const int endpoint = endpoints[index];
        int& endpoint_degree = degrees[static_cast<std::size_t>(endpoint)];
        const int previous = endpoint_degree;
        --endpoint_degree;
        if (previous > kEll && endpoint_degree >= 1 && endpoint_degree <= kEll) {
          queue.push(endpoint);
        }
      }
    }
  }
  return {residual};
}

void ValidateDomain(const std::string& domain) {
  const std::array<std::string, 4> allowed = {
      "calibration_coarse", "calibration_fine", "holdout_figure1b",
      "holdout_figure1c"};
  if (std::find(allowed.begin(), allowed.end(), domain) == allowed.end()) {
    throw std::invalid_argument("unknown seed domain");
  }
}

void Run() {
  std::string protocol;
  if (!(std::cin >> protocol) || protocol != kProtocol) {
    throw std::invalid_argument("invalid engine protocol header");
  }
  std::uint64_t base_seed = 0;
  std::string domain;
  int d = 0;
  int M = 0;
  int trials = 0;
  int group_count = 0;
  if (!(std::cin >> base_seed >> domain >> d >> M >> trials >> group_count)) {
    throw std::invalid_argument("invalid engine point header");
  }
  ValidateDomain(domain);
  if (d <= 0 || M <= 0 || trials <= 0 || group_count < 0) {
    throw std::invalid_argument("nonpositive engine dimensions");
  }
  std::vector<Group> groups;
  groups.reserve(static_cast<std::size_t>(group_count));
  for (int index = 0; index < group_count; ++index) {
    Group group;
    if (!(std::cin >> group.id >> group.circular_base_range >> group.z)) {
      throw std::invalid_argument("invalid engine group row");
    }
    if (group.id.find('\t') != std::string::npos || group.id.find('\n') != std::string::npos) {
      throw std::invalid_argument("invalid group id");
    }
    groups.push_back(group);
  }

  std::vector<TrialResult> results(static_cast<std::size_t>(trials));
  std::atomic<int> next_trial{0};
  auto run_trial = [&]() {
    while (true) {
      const int trial = next_trial.fetch_add(1);
      if (trial >= trials) {
        return;
      }
    std::vector<WordTriple> words;
    words.reserve(static_cast<std::size_t>(d));
    SHA256_CTX stream_context;
    SHA256_Init(&stream_context);
    for (int edge = 0; edge < d; ++edge) {
      const WordTriple triple = GenerateWords(base_seed, domain, d, M, trial, edge);
      words.push_back(triple);
      UpdateWordStream(&stream_context, triple);
    }
    std::array<unsigned char, SHA256_DIGEST_LENGTH> stream_digest{};
    SHA256_Final(stream_digest.data(), &stream_context);
      TrialResult& trial_result = results[static_cast<std::size_t>(trial)];
      trial_result.stream_sha256 = Hex(stream_digest.data(), stream_digest.size());
      trial_result.residual_by_group.reserve(groups.size());
    for (const Group& group : groups) {
      const PeelResult result = Peel(M, words, group);
        trial_result.residual_by_group.push_back(result.residual_edges);
      }
    }
  };

  const unsigned int detected_threads = std::max(1U, std::thread::hardware_concurrency());
  const int worker_count = std::min(trials, static_cast<int>(detected_threads));
  std::vector<std::thread> workers;
  workers.reserve(static_cast<std::size_t>(worker_count));
  for (int worker = 0; worker < worker_count; ++worker) {
    workers.emplace_back(run_trial);
  }
  for (std::thread& worker : workers) {
    worker.join();
  }

  std::cout << kProtocol << '\n';
  for (int trial = 0; trial < trials; ++trial) {
    const TrialResult& result = results[static_cast<std::size_t>(trial)];
    std::cout << "T\t" << trial << '\t' << result.stream_sha256 << '\n';
    for (std::size_t group_index = 0; group_index < groups.size(); ++group_index) {
      const int residual = result.residual_by_group[group_index];
      std::cout << "G\t" << groups[group_index].id << '\t' << residual << '\t'
                << (residual == 0 ? 1 : 0) << '\n';
    }
  }
}

void RunPlacementFixture(int argc, char** argv) {
  if (argc != 8) {
    throw std::invalid_argument(
        "place requires M a z anchor_word offset_word_1 offset_word_2");
  }
  const int M = std::stoi(argv[2]);
  const double a = std::stod(argv[3]);
  const int z = std::stoi(argv[4]);
  const auto parse_word = [](const char* value) {
    const unsigned long parsed = std::stoul(value);
    if (parsed > std::numeric_limits<std::uint32_t>::max()) {
      throw std::out_of_range("placement word exceeds uint32") ;
    }
    return static_cast<std::uint32_t>(parsed);
  };
  if (M <= 0 || !std::isfinite(a) || a < 0.0 || a >= 1.0 || z < 0 || z >= M) {
    throw std::invalid_argument("invalid fixture placement parameters");
  }
  const int range_length = M / (z + 1);
  const int naive_base_range = M - range_length + 1;
  const int extra_circular_anchors = static_cast<int>(std::floor(a * range_length));
  const int circular_base_range =
      std::min(M, naive_base_range + extra_circular_anchors);
  const WordTriple words = {
      parse_word(argv[5]), parse_word(argv[6]), parse_word(argv[7])};
  const Support support = Place(words, M, circular_base_range, z);
  std::cout << range_length << '\t' << naive_base_range << '\t'
            << circular_base_range << '\t' << support.first;
  if (support.size == 2) {
    std::cout << '\t' << support.second;
  }
  std::cout << '\n';
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc > 1) {
      if (std::string(argv[1]) != "place") {
        throw std::invalid_argument("unknown command");
      }
      RunPlacementFixture(argc, argv);
    } else {
      Run();
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "figure1bc_engine: " << error.what() << '\n';
    return 2;
  }
}
