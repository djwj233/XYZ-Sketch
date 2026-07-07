#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

#include "../../XYZ-v2/XYZSketch.cpp"

using namespace std;

namespace {

struct Options {
    int D = -1;
    int L = -1;
    int K = -1;
    int exact_m = -1;
    double m_factor = 1.2;
    int Z = -1;
    int trials = -1;
    uint32_t seed = 114514;
    string mode = "spatial";
    double circular_a = 1.0 / 3.0;
    bool dedup_hashes = false;
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
    cerr << "usage: xyz_v2_bench --d D --l L --k K --z Z --trials N --seed S "
            "[--m M | --m-factor F] [--mode spatial|random|circular|naive] [--ca N] [--cb N] "
            "[--circular-a A] [--dedup-hashes true|false] "
            "[--dataset PATH] "
            "[--format jsonl]\n";
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

bool parse_bool(const string &value, const string &name) {
    if(value == "true" || value == "1" || value == "yes") return true;
    if(value == "false" || value == "0" || value == "no") return false;
    usage_error("invalid boolean for " + name + ": " + value);
    return false;
}

Options parse_args(int argc, char **argv) {
    Options opt;
    for(int i = 1; i < argc; i++) {
        string key = argv[i];
        if(key == "--help" || key == "-h") {
            usage_error("help requested");
        }
        if(i + 1 >= argc) usage_error("missing value for " + key);
        string value = argv[++i];
        if(key == "--d") opt.D = parse_int(value, key);
        else if(key == "--l") opt.L = parse_int(value, key);
        else if(key == "--k") opt.K = parse_int(value, key);
        else if(key == "--m") opt.exact_m = parse_int(value, key);
        else if(key == "--m-factor") opt.m_factor = parse_double(value, key);
        else if(key == "--z") opt.Z = parse_int(value, key);
        else if(key == "--trials") opt.trials = parse_int(value, key);
        else if(key == "--seed") opt.seed = parse_uint32(value, key);
        else if(key == "--mode") opt.mode = value;
        else if(key == "--circular-a") opt.circular_a = parse_double(value, key);
        else if(key == "--dedup-hashes") opt.dedup_hashes = parse_bool(value, key);
        else if(key == "--ca") opt.cA = parse_int(value, key);
        else if(key == "--cb") opt.cB = parse_int(value, key);
        else if(key == "--dataset") opt.dataset_path = value;
        else if(key == "--format") opt.format = value;
        else usage_error("unknown argument: " + key);
    }

    if(opt.D <= 0) usage_error("--d must be positive");
    if(opt.L <= 0) usage_error("--l must be positive");
    if(opt.K <= 0) usage_error("--k must be positive");
    if(opt.Z < 0) usage_error("--z must be non-negative");
    if(opt.trials <= 0) usage_error("--trials must be positive");
    if(opt.cA <= 0 || opt.cB <= 0) usage_error("--ca and --cb must be positive");
    if(opt.mode != "spatial" && opt.mode != "random" &&
       opt.mode != "circular" && opt.mode != "naive")
        usage_error("--mode must be spatial, random, circular, or naive");
    if(!(0.0 <= opt.circular_a && opt.circular_a < 1.0))
        usage_error("--circular-a must be in [0, 1)");
    if(opt.format != "jsonl")
        usage_error("this benchmark currently supports only --format jsonl");
    if(opt.exact_m <= 0 && opt.m_factor <= 0)
        usage_error("either --m must be positive or --m-factor must be positive");
    if(opt.D < abs(opt.cA - opt.cB))
        usage_error("--d must be at least abs(ca - cb)");
    if(((opt.D - abs(opt.cA - opt.cB)) & 1) != 0)
        usage_error("--d and abs(ca - cb) must have the same parity");
    if((opt.D - abs(opt.cA - opt.cB)) / 2 > min(opt.cA, opt.cB))
        usage_error("requested difference is too large for ca/cb");
    return opt;
}

int next_value(unordered_set<int> &used) {
    int x = static_cast<int>(rng() % (P - 1)) + 1;
    while(used.find(x) != used.end()) {
        x = static_cast<int>(rng() % (P - 1)) + 1;
    }
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

    vector<int> base(max_size);
    unordered_set<int> used;
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

        int new_value = next_value(used);
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
            if(expected < 0) usage_error("negative dataset section length: " + path);
            current = token == "A" ? &data.alice : &data.bob;
            current->clear();
            current->reserve(static_cast<size_t>(expected));
            seen = 0;
            continue;
        }
        if(current == nullptr) usage_error("dataset value before section header: " + path);
        int value = parse_int(token, "dataset value");
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

TrialResult run_trial_on_data(const TrialData &data) {
    TrialResult result;

    auto encode_begin = chrono::steady_clock::now();
    XYZSketch alice = Encode(data.alice);
    auto encode_end = chrono::steady_clock::now();

    XYZSketch bob = Encode(data.bob);
    auto decode_begin = chrono::steady_clock::now();
    auto diff_res = (alice - bob).Decode();
    auto decode_end = chrono::steady_clock::now();

    result.encode_s = seconds_since(encode_begin, encode_end);
    result.decode_s = seconds_since(decode_begin, decode_end);
    result.bits = static_cast<int>(alice.to_bitstring().size());

    if(diff_res.index() == 1) {
        result.success = false;
        return result;
    }

    auto diff = get<pair<vector<int>, vector<int>>>(diff_res);
    result.success = (diff.first == data.a_diff && diff.second == data.b_diff);
    return result;
}

TrialResult run_trial(const Options &opt, uint32_t trial_seed) {
    return run_trial_on_data(generate_data(opt, trial_seed));
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

void print_json_bool_field(const string &key, bool value, bool comma = true) {
    cout << "\"" << key << "\":" << (value ? "true" : "false");
    if(comma) cout << ",";
}

} // namespace

int main(int argc, char **argv) {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    Options opt = parse_args(argc, argv);

    k = opt.K;
    l = opt.L;
    d = opt.D;
    M = opt.exact_m > 0 ? opt.exact_m
                        : static_cast<int>(ceil(opt.m_factor * opt.D / opt.L));
    if(M <= 0) usage_error("computed M must be positive");
    if(opt.mode == "spatial") SpatialCoupling::SetHashMode(SpatialCoupling::AUTO);
    else if(opt.mode == "random") SpatialCoupling::SetHashMode(SpatialCoupling::RANDOM);
    else if(opt.mode == "circular") SpatialCoupling::SetHashMode(SpatialCoupling::CIRCULAR);
    else if(opt.mode == "naive") SpatialCoupling::SetHashMode(SpatialCoupling::NAIVE);
    SpatialCoupling::SetCircularA(opt.circular_a);
    SpatialCoupling::SetDedupHashes(opt.dedup_hashes);
    HashingInit(opt.Z);

    const int max_len = 1 << 19;
    tool::init(max_len);
    tool::Pinit(max_len);

    vector<double> encode_times;
    vector<double> decode_times;
    int successes = 0;
    int bits = 0;
    vector<TrialData> loaded_data;
    if(!opt.dataset_path.empty()) {
        loaded_data.push_back(load_dataset(opt.dataset_path));
    }

    for(int t = 0; t < opt.trials; t++) {
        TrialResult result = opt.dataset_path.empty()
                                 ? run_trial(opt, opt.seed + static_cast<uint32_t>(t))
                                 : run_trial_on_data(loaded_data[0]);
        encode_times.push_back(result.encode_s);
        decode_times.push_back(result.decode_s);
        bits = result.bits;
        if(result.success) successes++;
    }

    double success_rate = static_cast<double>(successes) / static_cast<double>(opt.trials);
    double c_over_d = static_cast<double>(bits) / (static_cast<double>(opt.D) * 32.0);

    cout << fixed << setprecision(9);
    cout << "{";
    print_json_string_field("algorithm", "xyz_v2");
    print_json_string_field("mode", opt.mode);
    print_json_int_field("d", opt.D);
    print_json_int_field("l", opt.L);
    print_json_int_field("k", opt.K);
    print_json_int_field("M", M);
    print_json_int_field("z", opt.Z);
    print_json_number_field("circular_a", SpatialCoupling::GetCircularA());
    print_json_bool_field("dedup_hashes", SpatialCoupling::GetDedupHashes());
    print_json_int_field("range_length", RangeLength);
    print_json_int_field("circular_base_range", SpatialCoupling::CircularBaseRange());
    print_json_int_field("trials", opt.trials);
    print_json_int_field("successes", successes);
    print_json_number_field("success_rate", success_rate);
    print_json_number_field("encode_avg_s", average(encode_times));
    print_json_number_field("decode_avg_s", average(decode_times));
    print_json_number_field("encode_median_s", median(encode_times));
    print_json_number_field("decode_median_s", median(decode_times));
    print_json_int_field("bits", bits);
    print_json_number_field("C_over_d", c_over_d);
    print_json_int_field("seed", opt.seed);
    print_json_int_field("ca", opt.cA);
    print_json_int_field("cb", opt.cB, false);
    cout << "}\n";

    return 0;
}
