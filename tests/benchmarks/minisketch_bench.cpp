#include <algorithm>
#include <cmath>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <set>
#include <string>
#include <vector>

#ifdef ENABLE_REAL_MINISKETCH
#include "../../external/minisketch/include/minisketch.h"
#endif

using namespace std;

namespace {

struct Options {
    int D = -1;
    int trials = -1;
    uint32_t seed = 114514;
    int cA = 10000000;
    int cB = 10000000;
    double capacity_factor = 1.0;
    int field_bits = 30;
    string dataset_path;
    string format = "jsonl";
};

[[noreturn]] void usage_error(const string &message) {
    cerr << "error: " << message << "\n";
    exit(2);
}

int parse_int(const string &value, const string &name) {
    try {
        size_t pos = 0;
        int result = stoi(value, &pos);
        if(pos != value.size()) usage_error("invalid integer for " + name);
        return result;
    } catch(const exception &) {
        usage_error("invalid integer for " + name);
    }
}

uint32_t parse_uint32(const string &value, const string &name) {
    try {
        size_t pos = 0;
        unsigned long result = stoul(value, &pos);
        if(pos != value.size() || result > numeric_limits<uint32_t>::max()) usage_error("invalid uint32 for " + name);
        return static_cast<uint32_t>(result);
    } catch(const exception &) {
        usage_error("invalid uint32 for " + name);
    }
}

double parse_double(const string &value, const string &name) {
    try {
        size_t pos = 0;
        double result = stod(value, &pos);
        if(pos != value.size()) usage_error("invalid number for " + name);
        return result;
    } catch(const exception &) {
        usage_error("invalid number for " + name);
    }
}

Options parse_args(int argc, char **argv) {
    Options opt;
    for(int i = 1; i < argc; i++) {
        string key = argv[i];
        if(i + 1 >= argc) usage_error("missing value for " + key);
        string value = argv[++i];
        if(key == "--d") opt.D = parse_int(value, key);
        else if(key == "--trials") opt.trials = parse_int(value, key);
        else if(key == "--seed") opt.seed = parse_uint32(value, key);
        else if(key == "--ca") opt.cA = parse_int(value, key);
        else if(key == "--cb") opt.cB = parse_int(value, key);
        else if(key == "--capacity-factor") opt.capacity_factor = parse_double(value, key);
        else if(key == "--field-bits") opt.field_bits = parse_int(value, key);
        else if(key == "--dataset") opt.dataset_path = value;
        else if(key == "--format") opt.format = value;
        else usage_error("unknown argument: " + key);
    }
    if(opt.D <= 0 || opt.trials <= 0 || opt.capacity_factor <= 0.0) usage_error("invalid required parameter");
    if(opt.dataset_path.empty()) usage_error("--dataset is required");
    return opt;
}

struct Dataset {
    vector<uint64_t> alice;
    vector<uint64_t> bob;
};

Dataset load_dataset(const string &path) {
    ifstream input(path);
    if(!input) usage_error("failed to open dataset");
    Dataset data;
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
            if(current != nullptr && expected >= 0 && seen != expected) usage_error("dataset section length mismatch");
            input >> expected;
            current = token == "A" ? &data.alice : &data.bob;
            current->clear();
            seen = 0;
            continue;
        }
        if(current == nullptr) usage_error("dataset value before section");
        current->push_back(parse_uint32(token, "dataset value"));
        seen++;
    }
    return data;
}

set<uint64_t> symmetric_difference(const Dataset &data) {
    set<uint64_t> alice(data.alice.begin(), data.alice.end());
    set<uint64_t> bob(data.bob.begin(), data.bob.end());
    set<uint64_t> diff;
    for(uint64_t value : alice) {
        if(!bob.count(value)) diff.insert(value);
    }
    for(uint64_t value : bob) {
        if(!alice.count(value)) diff.insert(value);
    }
    return diff;
}

int capacity(const Options &opt) {
    return max(1, static_cast<int>(ceil(opt.capacity_factor * static_cast<double>(opt.D))));
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

void print_unavailable(const Options &opt, const string &reason) {
    int cap = capacity(opt);
    cout << fixed << setprecision(9);
    cout << "{";
    print_json_string_field("algorithm", "minisketch");
    print_json_string_field("variant", "capacity_factor=" + to_string(opt.capacity_factor));
    print_json_string_field("implementation", "external/minisketch");
    print_json_int_field("d", opt.D);
    print_json_int_field("trials", opt.trials);
    print_json_int_field("successes", 0);
    print_json_number_field("success_rate", 0.0);
    print_json_number_field("encode_avg_s", 0.0);
    print_json_number_field("decode_avg_s", 0.0);
    print_json_number_field("encode_median_s", 0.0);
    print_json_number_field("decode_median_s", 0.0);
    print_json_int_field("bits", 0);
    print_json_number_field("C_over_d", 0.0);
    print_json_int_field("field_bits", opt.field_bits);
    print_json_int_field("capacity", cap);
    print_json_number_field("capacity_factor", opt.capacity_factor);
    print_json_int_field("seed", opt.seed);
    print_json_int_field("ca", opt.cA);
    print_json_int_field("cb", opt.cB);
    print_json_string_field("status", "unavailable");
    print_json_string_field("unavailable_reason", reason, false);
    cout << "}\n";
}

#ifdef ENABLE_REAL_MINISKETCH
struct TrialResult {
    bool success = false;
    long long bits = 0;
    long long bytes = 0;
    double encode_s = 0.0;
    double decode_s = 0.0;
    int decoded_count = 0;
    string status = "ok";
    string error;
};

TrialResult run_minisketch(const Options &opt, const Dataset &data) {
    using clock = chrono::steady_clock;
    TrialResult result;
    const int cap = capacity(opt);
    const set<uint64_t> expected = symmetric_difference(data);
    result.bytes = static_cast<long long>((static_cast<long long>(cap) * opt.field_bits + 7) / 8);
    result.bits = result.bytes * 8;

    auto encode_begin = clock::now();

    if(!minisketch_bits_supported(static_cast<uint32_t>(opt.field_bits))) {
        result.status = "unavailable";
        result.error = "field_bits not supported by linked minisketch";
        return result;
    }

    minisketch *alice = minisketch_create(static_cast<uint32_t>(opt.field_bits), 0, static_cast<size_t>(cap));
    minisketch *bob = minisketch_create(static_cast<uint32_t>(opt.field_bits), 0, static_cast<size_t>(cap));
    if(alice == nullptr || bob == nullptr) {
        if(alice) minisketch_destroy(alice);
        if(bob) minisketch_destroy(bob);
        result.status = "benchmark_error";
        result.error = "minisketch_create failed";
        return result;
    }
    minisketch_set_seed(alice, opt.seed);
    minisketch_set_seed(bob, opt.seed);

    for(uint64_t value : data.alice) minisketch_add_uint64(alice, value);
    for(uint64_t value : data.bob) minisketch_add_uint64(bob, value);
    auto encode_end = clock::now();

    auto decode_begin = clock::now();
    size_t merged_capacity = minisketch_merge(alice, bob);
    vector<uint64_t> decoded(static_cast<size_t>(cap));
    ssize_t decoded_count = -1;
    if(merged_capacity != 0) {
        decoded_count = minisketch_decode(alice, decoded.size(), decoded.data());
    }
    auto decode_end = clock::now();

    result.encode_s = chrono::duration<double>(encode_end - encode_begin).count();
    result.decode_s = chrono::duration<double>(decode_end - decode_begin).count();
    result.bytes = static_cast<long long>(minisketch_serialized_size(alice));
    result.bits = result.bytes * 8;
    result.decoded_count = decoded_count < 0 ? -1 : static_cast<int>(decoded_count);

    if(merged_capacity == 0) {
        result.status = "failed_decode";
        result.error = "minisketch_merge failed";
    } else if(decoded_count < 0) {
        result.status = "failed_decode";
        result.error = "minisketch_decode failed";
    } else {
        decoded.resize(static_cast<size_t>(decoded_count));
        set<uint64_t> actual(decoded.begin(), decoded.end());
        result.success = actual == expected;
        if(!result.success) {
            result.status = "failed_decode";
            result.error = "decoded symmetric difference mismatch";
        }
    }

    minisketch_destroy(alice);
    minisketch_destroy(bob);
    return result;
}

void print_result(const Options &opt, const TrialResult &result) {
    int cap = capacity(opt);
    cout << fixed << setprecision(9);
    cout << "{";
    print_json_string_field("algorithm", "minisketch");
    print_json_string_field("variant", "capacity_factor=" + to_string(opt.capacity_factor));
    print_json_string_field("implementation", "external/minisketch");
    print_json_int_field("d", opt.D);
    print_json_int_field("trials", opt.trials);
    print_json_int_field("successes", result.success ? 1 : 0);
    print_json_number_field("success_rate", result.success ? 1.0 : 0.0);
    print_json_number_field("encode_avg_s", result.encode_s);
    print_json_number_field("decode_avg_s", result.decode_s);
    print_json_number_field("encode_median_s", result.encode_s);
    print_json_number_field("decode_median_s", result.decode_s);
    print_json_int_field("bits", result.bits);
    print_json_int_field("bytes", result.bytes);
    print_json_number_field("C_over_d", static_cast<double>(result.bits) / (32.0 * static_cast<double>(opt.D)));
    print_json_int_field("field_bits", opt.field_bits);
    print_json_int_field("capacity", cap);
    print_json_number_field("capacity_factor", opt.capacity_factor);
    print_json_int_field("decoded_count", result.decoded_count);
    print_json_string_field("communication_model", "fixed_sketch");
    print_json_int_field("seed", opt.seed);
    print_json_int_field("ca", opt.cA);
    print_json_int_field("cb", opt.cB);
    print_json_string_field("status", result.status);
    print_json_string_field(result.status == "unavailable" ? "unavailable_reason" : "error", result.error, false);
    cout << "}\n";
}
#endif

} // namespace

int main(int argc, char **argv) {
    Options opt = parse_args(argc, argv);
    Dataset data = load_dataset(opt.dataset_path);
#ifndef ENABLE_REAL_MINISKETCH
    print_unavailable(opt, "minisketch_bench was built without ENABLE_REAL_MINISKETCH");
    return 0;
#else
    print_result(opt, run_minisketch(opt, data));
    return 0;
#endif
}
