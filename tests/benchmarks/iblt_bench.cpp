#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

#include "../../IBLT/iblt.cpp"

using namespace std;

namespace {

const uint32_t ALL = (1u << 30) - 1u;

struct Options {
    int D = -1;
    int trials = -1;
    uint32_t seed = 114514;
    int cA = 10000000;
    int cB = 10000000;
    double capacity_factor = -1.0;
    string dataset_path;
    string format = "jsonl";
};

struct TrialData {
    vector<uint32_t> alice;
    vector<uint32_t> bob;
    vector<uint32_t> a_diff;
    vector<uint32_t> b_diff;
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
    cerr << "usage: iblt_bench --d D --trials N --seed S [--ca N] [--cb N] "
            "[--capacity-factor F] [--dataset PATH] [--format jsonl]\n";
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
        else if(key == "--dataset") opt.dataset_path = value;
        else if(key == "--format") opt.format = value;
        else usage_error("unknown argument: " + key);
    }

    if(opt.D <= 0) usage_error("--d must be positive");
    if(opt.trials <= 0) usage_error("--trials must be positive");
    if(opt.cA <= 0 || opt.cB <= 0) usage_error("--ca and --cb must be positive");
    if(opt.capacity_factor <= 0) usage_error("--capacity-factor must be positive");
    if(opt.format != "jsonl") usage_error("this benchmark currently supports only --format jsonl");
    if(opt.D < abs(opt.cA - opt.cB)) usage_error("--d must be at least abs(ca - cb)");
    if(((opt.D - abs(opt.cA - opt.cB)) & 1) != 0)
        usage_error("--d and abs(ca - cb) must have the same parity");
    if((opt.D - abs(opt.cA - opt.cB)) / 2 > min(opt.cA, opt.cB))
        usage_error("requested difference is too large for ca/cb");
    return opt;
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

TrialResult run_trial_on_data(const Options &opt, const TrialData &data, int &cells, int &hash_count) {
    IBLT iblt(opt.D, opt.capacity_factor);
    cells = iblt.cell_count();
    hash_count = iblt.hash_count_value();

    TrialResult result;
    auto encode_begin = chrono::steady_clock::now();
    auto alice = iblt.Encode(data.alice);
    auto encode_end = chrono::steady_clock::now();

    auto bob = iblt.Encode(data.bob);
    auto decode_begin = chrono::steady_clock::now();
    auto diff = iblt.Decode(alice, bob);
    auto decode_end = chrono::steady_clock::now();

    result.encode_s = seconds_since(encode_begin, encode_end);
    result.decode_s = seconds_since(decode_begin, decode_end);
    result.bits = static_cast<int>(alice.size() * sizeof(tuple<int, uint32_t, uint32_t>) * 8);
    result.success = (diff.first == data.a_diff && diff.second == data.b_diff);
    return result;
}

TrialResult run_trial(const Options &opt, uint32_t trial_seed, int &cells, int &hash_count) {
    return run_trial_on_data(opt, generate_data(opt, trial_seed), cells, hash_count);
}

double average(const vector<double> &values) {
    if(values.empty()) return 0.0;
    return accumulate(values.begin(), values.end(), 0.0) / static_cast<double>(values.size());
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
    vector<double> encode_times;
    vector<double> decode_times;
    int successes = 0;
    int bits = 0;
    int cells = 0;
    int hash_count = 0;
    vector<TrialData> loaded_data;
    if(!opt.dataset_path.empty()) {
        loaded_data.push_back(load_dataset(opt.dataset_path));
    }

    for(int t = 0; t < opt.trials; t++) {
        TrialResult result = opt.dataset_path.empty()
                                 ? run_trial(opt, opt.seed + static_cast<uint32_t>(t), cells, hash_count)
                                 : run_trial_on_data(opt, loaded_data[0], cells, hash_count);
        encode_times.push_back(result.encode_s);
        decode_times.push_back(result.decode_s);
        bits = result.bits;
        if(result.success) successes++;
    }

    const int cell_bits = static_cast<int>(sizeof(tuple<int, uint32_t, uint32_t>) * 8);
    double success_rate = static_cast<double>(successes) / static_cast<double>(opt.trials);
    double bit_c_over_d = static_cast<double>(bits) / (static_cast<double>(opt.D) * 32.0);

    cout << fixed << setprecision(9);
    cout << "{";
    print_json_string_field("algorithm", "iblt");
    print_json_string_field("variant", "local");
    print_json_string_field("implementation", "local");
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
    print_json_number_field("capacity_factor", opt.capacity_factor);
    print_json_int_field("seed", opt.seed);
    print_json_int_field("ca", opt.cA);
    print_json_int_field("cb", opt.cB, false);
    cout << "}\n";
    return 0;
}
