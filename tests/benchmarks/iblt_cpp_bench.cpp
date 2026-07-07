#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

#include "../../external/IBLT_Cplusplus/iblt.h"

using namespace std;

namespace {

struct Options {
    int D = -1;
    int trials = -1;
    uint32_t seed = 114514;
    int cA = 10000000;
    int cB = 10000000;
    double capacity_factor = -1.0;
    int value_size = 4;
    string dataset_path;
    string format = "jsonl";
};

struct TrialData {
    vector<uint64_t> alice;
    vector<uint64_t> bob;
    vector<uint64_t> a_diff;
    vector<uint64_t> b_diff;
};

struct TrialResult {
    bool success = false;
    double encode_s = 0.0;
    double decode_s = 0.0;
    int bits = 0;
};

[[noreturn]] void usage_error(const string &message) {
    cerr << "error: " << message << "\n";
    cerr << "usage: iblt_cpp_bench --d D --trials N --seed S --dataset PATH "
            "[--ca N] [--cb N] [--capacity-factor F] [--value-size N] [--format jsonl]\n";
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
        else if(key == "--value-size") opt.value_size = parse_int(value, key);
        else if(key == "--dataset") opt.dataset_path = value;
        else if(key == "--format") opt.format = value;
        else usage_error("unknown argument: " + key);
    }
    if(opt.D <= 0) usage_error("--d must be positive");
    if(opt.trials <= 0) usage_error("--trials must be positive");
    if(opt.capacity_factor <= 0.0) usage_error("--capacity-factor must be positive");
    if(opt.value_size < 0) usage_error("--value-size must be non-negative");
    if(opt.dataset_path.empty()) usage_error("iblt_cpp_bench currently requires --dataset");
    if(opt.format != "jsonl") usage_error("this benchmark currently supports only --format jsonl");
    return opt;
}

vector<uint8_t> value_bytes(uint64_t value, int value_size) {
    vector<uint8_t> result(static_cast<size_t>(value_size));
    for(int i = 0; i < value_size; i++) result[static_cast<size_t>(i)] = static_cast<uint8_t>((value >> (8 * i)) & 0xff);
    return result;
}

void compute_diffs(TrialData &data) {
    unordered_set<uint64_t> alice(data.alice.begin(), data.alice.end());
    unordered_set<uint64_t> bob(data.bob.begin(), data.bob.end());
    data.a_diff.clear();
    data.b_diff.clear();
    for(uint64_t value : data.alice) {
        if(bob.find(value) == bob.end()) data.a_diff.push_back(value);
    }
    for(uint64_t value : data.bob) {
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
    vector<uint64_t> *current = nullptr;
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
            current = token == "A" ? &data.alice : &data.bob;
            current->clear();
            current->reserve(static_cast<size_t>(expected));
            seen = 0;
            continue;
        }
        if(current == nullptr) usage_error("dataset value before section header: " + path);
        current->push_back(parse_uint32(token, "dataset value"));
        seen++;
    }
    if(current != nullptr && expected >= 0 && seen != expected)
        usage_error("dataset section length mismatch: " + path);
    if(data.alice.empty() || data.bob.empty()) usage_error("dataset missing Alice or Bob section: " + path);
    compute_diffs(data);
    return data;
}

double seconds_since(chrono::steady_clock::time_point start, chrono::steady_clock::time_point finish) {
    return chrono::duration<double>(finish - start).count();
}

int expected_entries(const Options &opt) {
    return max(1, static_cast<int>(ceil(opt.capacity_factor * static_cast<double>(opt.D))));
}

int cell_count_from_expected(int expected) {
    int n_entries = expected + expected / 2;
    while(n_entries % 4 != 0) ++n_entries;
    return n_entries;
}

TrialResult run_trial_on_data(const Options &opt, const TrialData &data, int &cells) {
    int expected = expected_entries(opt);
    cells = cell_count_from_expected(expected);
    IBLT alice(static_cast<size_t>(expected), static_cast<size_t>(opt.value_size));
    IBLT bob(static_cast<size_t>(expected), static_cast<size_t>(opt.value_size));

    auto encode_begin = chrono::steady_clock::now();
    for(uint64_t value : data.alice) alice.insert(value, value_bytes(value, opt.value_size));
    auto encode_mid = chrono::steady_clock::now();
    for(uint64_t value : data.bob) bob.insert(value, value_bytes(value, opt.value_size));
    auto decode_begin = chrono::steady_clock::now();
    IBLT diff = alice - bob;
    set<pair<uint64_t, vector<uint8_t>>> positive;
    set<pair<uint64_t, vector<uint8_t>>> negative;
    bool decoded = diff.listEntries(positive, negative);
    auto decode_end = chrono::steady_clock::now();

    vector<uint64_t> pos_values;
    vector<uint64_t> neg_values;
    for(const auto &entry : positive) pos_values.push_back(entry.first);
    for(const auto &entry : negative) neg_values.push_back(entry.first);
    sort(pos_values.begin(), pos_values.end());
    sort(neg_values.begin(), neg_values.end());

    TrialResult result;
    result.encode_s = seconds_since(encode_begin, encode_mid);
    result.decode_s = seconds_since(decode_begin, decode_end);
    result.bits = cells * (32 + 64 + 32 + opt.value_size * 8);
    result.success = decoded && pos_values == data.a_diff && neg_values == data.b_diff;
    return result;
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
    TrialData data = load_dataset(opt.dataset_path);
    vector<double> encode_times;
    vector<double> decode_times;
    int successes = 0;
    int bits = 0;
    int cells = 0;
    for(int t = 0; t < opt.trials; t++) {
        TrialResult result = run_trial_on_data(opt, data, cells);
        encode_times.push_back(result.encode_s);
        decode_times.push_back(result.decode_s);
        bits = result.bits;
        if(result.success) successes++;
    }

    double success_rate = static_cast<double>(successes) / static_cast<double>(opt.trials);
    double bit_c_over_d = static_cast<double>(bits) / (static_cast<double>(opt.D) * 32.0);
    cout << fixed << setprecision(9);
    cout << "{";
    print_json_string_field("algorithm", "iblt_cpp");
    print_json_string_field("variant", "capacity_factor=" + to_string(opt.capacity_factor));
    print_json_string_field("implementation", "external/IBLT_Cplusplus");
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
    print_json_int_field("hash_count", 4);
    print_json_int_field("cell_bits", 32 + 64 + 32 + opt.value_size * 8);
    print_json_number_field("capacity_factor", opt.capacity_factor);
    print_json_int_field("expected_entries", expected_entries(opt));
    print_json_int_field("value_size", opt.value_size);
    print_json_int_field("seed", opt.seed);
    print_json_int_field("ca", opt.cA);
    print_json_int_field("cb", opt.cB, false);
    cout << "}\n";
    return 0;
}
