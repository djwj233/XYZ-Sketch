#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

#include "../../XYZ-v1/XYZ-v1.cpp"

using namespace std;

namespace {

struct Options {
    int D = -1;
    int trials = -1;
    uint32_t seed = 114514;
    int cA = 10000000;
    int cB = 10000000;
    string dataset_path;
    string format = "jsonl";
};

struct TrialData {
    vector<int> alice;
    vector<int> bob;
    vector<int> a_diff;
    vector<int> b_diff;
};

struct TrialResult {
    bool success = false;
    double encode_s = 0.0;
    double decode_s = 0.0;
    int bits = 0;
};

[[noreturn]] void usage_error(const string &message) {
    cerr << "error: " << message << "\n";
    cerr << "usage: xyz_v1_bench --d D --trials N --seed S --dataset PATH "
            "[--ca N] [--cb N] [--format jsonl]\n";
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
        else if(key == "--dataset") opt.dataset_path = value;
        else if(key == "--format") opt.format = value;
        else usage_error("unknown argument: " + key);
    }
    if(opt.D <= 0) usage_error("--d must be positive");
    if(opt.trials <= 0) usage_error("--trials must be positive");
    if(opt.cA <= 0 || opt.cB <= 0) usage_error("--ca and --cb must be positive");
    if(opt.dataset_path.empty()) usage_error("xyz_v1_bench currently requires --dataset");
    if(opt.format != "jsonl") usage_error("this benchmark currently supports only --format jsonl");
    return opt;
}

int parse_value(const string &value) {
    uint32_t parsed = parse_uint32(value, "dataset value");
    if(parsed >= static_cast<uint32_t>(P)) usage_error("dataset value must be inside XYZ field");
    return static_cast<int>(parsed);
}

void compute_diffs(TrialData &data) {
    unordered_set<int> alice(data.alice.begin(), data.alice.end());
    unordered_set<int> bob(data.bob.begin(), data.bob.end());
    data.a_diff.clear();
    data.b_diff.clear();
    for(int value : data.alice) {
        if(bob.find(value) == bob.end()) data.a_diff.push_back(value);
    }
    for(int value : data.bob) {
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
    vector<int> *current = nullptr;
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
        current->push_back(parse_value(token));
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

TrialResult run_trial_on_data(const TrialData &data) {
    TrialResult result;
    auto encode_begin = chrono::steady_clock::now();
    info alice = Encode(const_cast<vector<int>&>(data.alice));
    auto encode_mid = chrono::steady_clock::now();
    info bob = Encode(const_cast<vector<int>&>(data.bob));
    auto decode_begin = chrono::steady_clock::now();
    auto diff_res = Decode(alice, bob);
    auto decode_end = chrono::steady_clock::now();

    result.encode_s = seconds_since(encode_begin, encode_mid);
    result.decode_s = seconds_since(decode_begin, decode_end);
    result.bits = static_cast<int>(to_bitstring(alice).size());
    if(diff_res.index() == 0) {
        auto diff = get<pair<vector<int>, vector<int>>>(diff_res);
        sort(diff.first.begin(), diff.first.end());
        sort(diff.second.begin(), diff.second.end());
        result.success = diff.first == data.a_diff && diff.second == data.b_diff;
    }
    (void)bob;
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

    const int max_len = 1 << 21;
    tool::init(max_len);
    tool::Pinit(max_len);

    Options opt = parse_args(argc, argv);
    D = opt.D;
    TrialData data = load_dataset(opt.dataset_path);

    vector<double> encode_times;
    vector<double> decode_times;
    int successes = 0;
    int bits = 0;
    for(int t = 0; t < opt.trials; t++) {
        TrialResult result = run_trial_on_data(data);
        encode_times.push_back(result.encode_s);
        decode_times.push_back(result.decode_s);
        bits = result.bits;
        if(result.success) successes++;
    }

    double success_rate = static_cast<double>(successes) / static_cast<double>(opt.trials);
    double bit_c_over_d = static_cast<double>(bits) / (static_cast<double>(opt.D) * 32.0);
    cout << fixed << setprecision(9);
    cout << "{";
    print_json_string_field("algorithm", "xyz_v1");
    print_json_string_field("variant", "basic");
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
    print_json_int_field("seed", opt.seed);
    print_json_int_field("ca", opt.cA);
    print_json_int_field("cb", opt.cB, false);
    cout << "}\n";
    return 0;
}
