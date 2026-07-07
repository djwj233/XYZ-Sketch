#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <queue>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

#include "../../IBLT/murmur3.cc"

using namespace std;

namespace {

const uint32_t ALL = (1u << 30) - 1u;
const uint32_t FP_SEED = 229;

struct Options {
    int D = -1;
    int trials = -1;
    uint32_t seed = 114514;
    int cA = 10000000;
    int cB = 10000000;
    double capacity_factor = -1.0;
    int cells = -1;
    string mode = "uniform";
    string hash_count_arg = "auto";
    int z = -1;
    string dataset_path;
    string format = "jsonl";
};

struct TrialData {
    vector<uint32_t> alice;
    vector<uint32_t> bob;
    vector<uint32_t> a_diff;
    vector<uint32_t> b_diff;
};

struct Cell {
    int count = 0;
    uint32_t key_sum = 0;
    uint32_t key_check = 0;
};

struct TrialResult {
    bool success = false;
    double encode_s = 0.0;
    double decode_s = 0.0;
    int bits = 0;
};

mt19937 rng(114514);

[[noreturn]] void usage_error(const string &message) {
    cerr << "error: " << message << "\n";
    cerr << "usage: iblt_sc_bench --d D --trials N --seed S [--ca N] [--cb N] "
            "[--capacity-factor F | --cells N] [--mode uniform|spatial] "
            "[--hash-count auto|N] [--z N] [--dataset PATH] [--format jsonl]\n";
    exit(2);
}

int parse_int(const string &value, const string &name) {
    try {
        size_t pos = 0;
        int result = stoi(value, &pos);
        if(pos != value.size()) usage_error("invalid integer for " + name + ": " + value);
        return result;
    } catch(const exception &) {
        usage_error("invalid integer for " + name + ": " + value);
    }
}

uint32_t parse_uint32(const string &value, const string &name) {
    try {
        size_t pos = 0;
        unsigned long result = stoul(value, &pos);
        if(pos != value.size() || result > numeric_limits<uint32_t>::max())
            usage_error("invalid uint32 for " + name + ": " + value);
        return static_cast<uint32_t>(result);
    } catch(const exception &) {
        usage_error("invalid uint32 for " + name + ": " + value);
    }
}

double parse_double(const string &value, const string &name) {
    try {
        size_t pos = 0;
        double result = stod(value, &pos);
        if(pos != value.size()) usage_error("invalid number for " + name + ": " + value);
        return result;
    } catch(const exception &) {
        usage_error("invalid number for " + name + ": " + value);
    }
}

Options parse_args(int argc, char **argv) {
    Options opt;
    for(int i = 1; i < argc; i++) {
        string key = argv[i];
        if(key == "--help" || key == "-h") usage_error("help requested");
        if(i + 1 >= argc) usage_error("missing value for " + key);
        string value = argv[++i];
        if(key == "--d") opt.D = parse_int(value, key);
        else if(key == "--trials") opt.trials = parse_int(value, key);
        else if(key == "--seed") opt.seed = parse_uint32(value, key);
        else if(key == "--ca") opt.cA = parse_int(value, key);
        else if(key == "--cb") opt.cB = parse_int(value, key);
        else if(key == "--capacity-factor") opt.capacity_factor = parse_double(value, key);
        else if(key == "--cells") opt.cells = parse_int(value, key);
        else if(key == "--mode") opt.mode = value;
        else if(key == "--hash-count") opt.hash_count_arg = value;
        else if(key == "--z") opt.z = parse_int(value, key);
        else if(key == "--dataset") opt.dataset_path = value;
        else if(key == "--format") opt.format = value;
        else usage_error("unknown argument: " + key);
    }

    if(opt.D <= 0) usage_error("--d must be positive");
    if(opt.trials <= 0) usage_error("--trials must be positive");
    if(opt.cA <= 0 || opt.cB <= 0) usage_error("--ca and --cb must be positive");
    if(opt.cells <= 0 && opt.capacity_factor <= 0.0)
        usage_error("--capacity-factor or --cells must be positive");
    if(opt.mode != "uniform" && opt.mode != "spatial")
        usage_error("--mode must be uniform or spatial");
    if(opt.format != "jsonl") usage_error("this benchmark currently supports only --format jsonl");
    if(opt.D < abs(opt.cA - opt.cB)) usage_error("--d must be at least abs(ca - cb)");
    if(((opt.D - abs(opt.cA - opt.cB)) & 1) != 0)
        usage_error("--d and abs(ca - cb) must have the same parity");
    if((opt.D - abs(opt.cA - opt.cB)) / 2 > min(opt.cA, opt.cB))
        usage_error("requested difference is too large for ca/cb");
    return opt;
}

uint32_t hash32(uint32_t value, uint32_t seed) {
    uint32_t output;
    MurmurHash3_x86_32(&value, sizeof(uint32_t), seed, &output);
    return output;
}

uint32_t fingerprint(uint32_t value) {
    return hash32(value, FP_SEED);
}

uint32_t next_value(unordered_set<uint32_t> &used) {
    uint32_t x = rng() & ALL;
    while(used.find(x) != used.end()) x = rng() & ALL;
    used.insert(x);
    return x;
}

TrialData generate_data(const Options &opt, uint32_t trial_seed) {
    rng.seed(trial_seed);

    TrialData data;
    int max_size = max(opt.cA, opt.cB);
    int common_size = min(opt.cA, opt.cB);
    int imbalance = abs(opt.cA - opt.cB);
    int replacements = (opt.D - imbalance) / 2;

    vector<uint32_t> base(max_size);
    unordered_set<uint32_t> used;
    used.reserve(static_cast<size_t>(max_size + replacements + 16));
    for(int i = 0; i < max_size; i++) base[i] = next_value(used);

    data.alice.assign(base.begin(), base.begin() + opt.cA);
    data.bob.assign(base.begin(), base.begin() + opt.cB);

    unordered_set<int> used_positions;
    used_positions.reserve(static_cast<size_t>(replacements * 2 + 16));
    for(int i = 0; i < replacements; i++) {
        int pos = static_cast<int>(rng() % common_size);
        while(used_positions.find(pos) != used_positions.end()) {
            pos = static_cast<int>(rng() % common_size);
        }
        used_positions.insert(pos);

        uint32_t new_value = next_value(used);
        data.a_diff.push_back(data.alice[pos]);
        data.b_diff.push_back(new_value);
        data.bob[pos] = new_value;
    }

    if(opt.cA > opt.cB) {
        for(int i = opt.cB; i < opt.cA; i++) data.a_diff.push_back(data.alice[i]);
    } else if(opt.cB > opt.cA) {
        for(int i = opt.cA; i < opt.cB; i++) data.b_diff.push_back(data.bob[i]);
    }

    sort(data.a_diff.begin(), data.a_diff.end());
    sort(data.b_diff.begin(), data.b_diff.end());
    shuffle(data.alice.begin(), data.alice.end(), rng);
    shuffle(data.bob.begin(), data.bob.end(), rng);
    return data;
}

void compute_diffs(TrialData &data) {
    unordered_set<uint32_t> alice(data.alice.begin(), data.alice.end());
    unordered_set<uint32_t> bob(data.bob.begin(), data.bob.end());
    data.a_diff.clear();
    data.b_diff.clear();
    for(uint32_t value : data.alice) {
        if(bob.find(value) == bob.end()) data.a_diff.push_back(value);
    }
    for(uint32_t value : data.bob) {
        if(alice.find(value) == alice.end()) data.b_diff.push_back(value);
    }
    sort(data.a_diff.begin(), data.a_diff.end());
    sort(data.b_diff.begin(), data.b_diff.end());
}

TrialData load_dataset(const string &path) {
    ifstream input(path);
    if(!input) usage_error("failed to open dataset: " + path);

    TrialData data;
    string token;
    vector<uint32_t> *current = nullptr;
    int expected = -1;
    int seen = 0;
    while(input >> token) {
        if(token.size() && token[0] == '#') {
            string rest;
            getline(input, rest);
            continue;
        }
        if(token == "A" || token == "B") {
            if(current != nullptr && expected >= 0 && seen != expected)
                usage_error("dataset section length mismatch: " + path);
            input >> expected;
            if(expected < 0) usage_error("negative dataset section length: " + path);
            current = token == "A" ? &data.alice : &data.bob;
            current->clear();
            current->reserve(static_cast<size_t>(expected));
            seen = 0;
            continue;
        }
        if(current == nullptr) usage_error("dataset value before section header: " + path);
        uint32_t value = parse_uint32(token, "dataset value");
        current->push_back(value);
        seen++;
    }
    if(current != nullptr && expected >= 0 && seen != expected)
        usage_error("dataset section length mismatch: " + path);
    if(data.alice.empty() || data.bob.empty()) usage_error("dataset missing Alice or Bob section: " + path);
    compute_diffs(data);
    return data;
}

double seconds_since(chrono::steady_clock::time_point start,
                     chrono::steady_clock::time_point finish) {
    return chrono::duration<double>(finish - start).count();
}

class TestIBLT {
  public:
    TestIBLT(int cells, int hash_count, string mode, int z)
        : cells_(cells), hash_count_(hash_count), mode_(std::move(mode)), z_(z) {
        if(cells_ <= 0 || hash_count_ <= 0) usage_error("invalid IBLT dimensions");
        if(z_ < 0) z_ = max(0, (int)round(pow((double)cells_, 1.0 / 3.0) / 3.0));
        window_size_ = mode_ == "spatial" ? max(hash_count_, cells_ / (z_ + 1)) : cells_;
        window_size_ = min(window_size_, cells_);
    }

    int cell_count() const { return cells_; }
    int hash_count() const { return hash_count_; }
    int z() const { return mode_ == "uniform" ? 0 : z_; }
    int window_size() const { return window_size_; }

    vector<Cell> encode(const vector<uint32_t> &data) const {
        vector<Cell> table(static_cast<size_t>(cells_));
        for(uint32_t value : data) {
            for(int index = 0; index < hash_count_; index++) {
                int pos = location(value, index);
                add(table[static_cast<size_t>(pos)], 1, value);
            }
        }
        return table;
    }

    pair<vector<uint32_t>, vector<uint32_t>> decode(const vector<Cell> &alice, const vector<Cell> &bob) const {
        vector<Cell> diff(static_cast<size_t>(cells_));
        for(int i = 0; i < cells_; i++) {
            diff[static_cast<size_t>(i)].count = alice[static_cast<size_t>(i)].count - bob[static_cast<size_t>(i)].count;
            diff[static_cast<size_t>(i)].key_sum = alice[static_cast<size_t>(i)].key_sum - bob[static_cast<size_t>(i)].key_sum;
            diff[static_cast<size_t>(i)].key_check = alice[static_cast<size_t>(i)].key_check ^ bob[static_cast<size_t>(i)].key_check;
        }

        queue<int> pure;
        vector<uint32_t> only_alice;
        vector<uint32_t> only_bob;
        vector<char> queued(static_cast<size_t>(cells_), 0);
        auto enqueue_if_pure = [&](int pos) {
            if(pos < 0 || pos >= cells_) return;
            if(is_pure(diff[static_cast<size_t>(pos)]) && !queued[static_cast<size_t>(pos)]) {
                pure.push(pos);
                queued[static_cast<size_t>(pos)] = 1;
            }
        };
        for(int i = 0; i < cells_; i++) enqueue_if_pure(i);

        while(!pure.empty()) {
            int pos = pure.front();
            pure.pop();
            queued[static_cast<size_t>(pos)] = 0;
            Cell cell = diff[static_cast<size_t>(pos)];
            if(!is_pure(cell)) continue;
            int sign = cell.count;
            uint32_t value = sign == 1 ? cell.key_sum : (uint32_t)(0u - cell.key_sum);
            if(sign == 1) only_alice.push_back(value);
            else only_bob.push_back(value);

            for(int i = 0; i < hash_count_; i++) {
                int next = location(value, i);
                add(diff[static_cast<size_t>(next)], -sign, value);
                enqueue_if_pure(next);
            }
        }

        sort(only_alice.begin(), only_alice.end());
        sort(only_bob.begin(), only_bob.end());
        return make_pair(only_alice, only_bob);
    }

  private:
    int cells_;
    int hash_count_;
    string mode_;
    int z_;
    int window_size_;

    int location(uint32_t value, int index) const {
        if(mode_ == "uniform") {
            return (int)(hash32(value, 3u * index * index + index + 2u) % (uint32_t)cells_);
        }
        int base_range = max(1, cells_ - window_size_ + 1);
        int base = (int)(hash32(value, 911u) % (uint32_t)base_range);
        int offset = (int)(hash32(value, 3571u + (uint32_t)index * 101u) % (uint32_t)window_size_);
        return min(cells_ - 1, base + offset);
    }

    static void add(Cell &cell, int sign, uint32_t value) {
        cell.count += sign;
        if(sign == 1) cell.key_sum += value;
        else cell.key_sum -= value;
        cell.key_check ^= fingerprint(value);
    }

    static bool is_pure(const Cell &cell) {
        if(cell.count != 1 && cell.count != -1) return false;
        uint32_t value = cell.count == 1 ? cell.key_sum : (uint32_t)(0u - cell.key_sum);
        return fingerprint(value) == cell.key_check;
    }
};

int hash_count_for(const Options &opt) {
    if(opt.hash_count_arg == "auto") return opt.D < 200 ? 4 : 3;
    int value = parse_int(opt.hash_count_arg, "--hash-count");
    if(value <= 0) usage_error("--hash-count must be positive");
    return value;
}

int cells_for(const Options &opt) {
    if(opt.cells > 0) return opt.cells;
    return max(1, (int)ceil(opt.capacity_factor * (double)opt.D));
}

TrialResult run_trial_on_data(const TestIBLT &iblt, const TrialData &data) {
    TrialResult result;
    auto encode_begin = chrono::steady_clock::now();
    auto alice = iblt.encode(data.alice);
    auto encode_end = chrono::steady_clock::now();

    auto bob = iblt.encode(data.bob);
    auto decode_begin = chrono::steady_clock::now();
    auto diff = iblt.decode(alice, bob);
    auto decode_end = chrono::steady_clock::now();

    result.encode_s = seconds_since(encode_begin, encode_end);
    result.decode_s = seconds_since(decode_begin, decode_end);
    result.bits = (int)(alice.size() * sizeof(Cell) * 8);
    result.success = (diff.first == data.a_diff && diff.second == data.b_diff);
    return result;
}

double average(const vector<double> &values) {
    if(values.empty()) return 0.0;
    return accumulate(values.begin(), values.end(), 0.0) / (double)values.size();
}

double median(vector<double> values) {
    if(values.empty()) return 0.0;
    sort(values.begin(), values.end());
    size_t mid = values.size() / 2;
    if(values.size() % 2 == 1) return values[mid];
    return (values[mid - 1] + values[mid]) / 2.0;
}

void print_json_string_field(const string &key, const string &value, bool comma = true) {
    cout << "\"" << key << "\":\"" << value << "\"";
    if(comma) cout << ",";
}

void print_json_number_field(const string &key, double value, bool comma = true) {
    cout << "\"" << key << "\":" << value;
    if(comma) cout << ",";
}

void print_json_int_field(const string &key, long long value, bool comma = true) {
    cout << "\"" << key << "\":" << value;
    if(comma) cout << ",";
}

} // namespace

int main(int argc, char **argv) {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    Options opt = parse_args(argc, argv);
    int cells = cells_for(opt);
    int hash_count = hash_count_for(opt);
    TestIBLT iblt(cells, hash_count, opt.mode, opt.mode == "uniform" ? 0 : opt.z);

    vector<TrialData> loaded_data;
    if(!opt.dataset_path.empty()) loaded_data.push_back(load_dataset(opt.dataset_path));

    vector<double> encode_times;
    vector<double> decode_times;
    int successes = 0;
    int bits = 0;
    for(int t = 0; t < opt.trials; t++) {
        TrialData data = opt.dataset_path.empty() ? generate_data(opt, opt.seed + (uint32_t)t) : loaded_data[0];
        TrialResult result = run_trial_on_data(iblt, data);
        encode_times.push_back(result.encode_s);
        decode_times.push_back(result.decode_s);
        bits = result.bits;
        if(result.success) successes++;
    }

    const int cell_bits = (int)(sizeof(Cell) * 8);
    double success_rate = (double)successes / (double)opt.trials;
    double bit_c_over_d = (double)bits / ((double)opt.D * 32.0);
    double capacity_factor = (double)cells / (double)opt.D;

    cout << fixed << setprecision(9);
    cout << "{";
    print_json_string_field("algorithm", "iblt");
    print_json_string_field("variant", opt.mode);
    print_json_string_field("implementation", "tests/benchmarks/iblt_sc_bench");
    print_json_string_field("mode", opt.mode);
    print_json_int_field("d", opt.D);
    print_json_int_field("trials", opt.trials);
    print_json_int_field("successes", successes);
    print_json_number_field("success_rate", success_rate);
    print_json_number_field("encode_avg_s", average(encode_times));
    print_json_number_field("decode_avg_s", average(decode_times));
    print_json_number_field("encode_median_s", median(encode_times));
    print_json_number_field("decode_median_s", median(decode_times));
    print_json_int_field("bits", bits);
    print_json_number_field("C_over_d", bit_c_over_d);
    print_json_number_field("bit_C_over_d", bit_c_over_d);
    print_json_int_field("cells", cells);
    print_json_int_field("hash_count", hash_count);
    print_json_int_field("cell_bits", cell_bits);
    print_json_number_field("capacity_factor", capacity_factor);
    print_json_int_field("z", iblt.z());
    print_json_int_field("window_size", iblt.window_size());
    print_json_int_field("seed", opt.seed);
    print_json_int_field("ca", opt.cA);
    print_json_int_field("cb", opt.cB, false);
    cout << "}\n";
    return 0;
}
