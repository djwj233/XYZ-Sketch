#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

#ifdef ENABLE_REAL_CPISYNC
#include <NTL/ZZ.h>
#include "../../external/cpisync/include/DataObject.h"
#include "../../external/cpisync/include/ForkHandle.h"
#include "../../external/cpisync/include/GenSync.h"
#endif

using namespace std;

namespace {

struct Options {
    int D = -1;
    int trials = -1;
    uint32_t seed = 114514;
    int cA = 10000000;
    int cB = 10000000;
    double mbar_factor = -1.0;
    int mbar = -1;
    int bits = 30;
    int epsilon = 64;
    int redundant = 0;
    bool hashes = false;
    int port = 8001;
    string dataset_path;
    string format = "jsonl";
};

struct TrialData {
    vector<uint32_t> alice;
    vector<uint32_t> bob;
};

struct TrialResult {
    bool success = false;
    double reconcile_s = 0.0;
    long long bytes = 0;
};

[[noreturn]] void usage_error(const string &message) {
    cerr << "error: " << message << "\n";
    cerr << "usage: cpisync_bench --d D --trials N --seed S --dataset PATH "
            "[--ca N] [--cb N] [--mbar-factor F | --mbar N] [--bits N] "
            "[--epsilon N] [--redundant N] [--hashes true|false] [--port N] "
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
        else if(key == "--mbar-factor") opt.mbar_factor = parse_double(value, key);
        else if(key == "--mbar") opt.mbar = parse_int(value, key);
        else if(key == "--bits") opt.bits = parse_int(value, key);
        else if(key == "--epsilon") opt.epsilon = parse_int(value, key);
        else if(key == "--redundant") opt.redundant = parse_int(value, key);
        else if(key == "--hashes") opt.hashes = parse_bool(value, key);
        else if(key == "--port") opt.port = parse_int(value, key);
        else if(key == "--dataset") opt.dataset_path = value;
        else if(key == "--format") opt.format = value;
        else usage_error("unknown argument: " + key);
    }

    if(opt.D <= 0) usage_error("--d must be positive");
    if(opt.trials <= 0) usage_error("--trials must be positive");
    if(opt.cA <= 0 || opt.cB <= 0) usage_error("--ca and --cb must be positive");
    if(opt.bits < 2) usage_error("--bits must be at least 2");
    if(opt.epsilon < 0) usage_error("--epsilon must be non-negative");
    if(opt.redundant < 0) usage_error("--redundant must be non-negative");
    if(opt.port <= 0) usage_error("--port must be positive");
    if(opt.format != "jsonl") usage_error("this benchmark currently supports only --format jsonl");
    if(opt.dataset_path.empty()) usage_error("cpisync_bench currently requires --dataset");
    if(opt.mbar <= 0 && opt.mbar_factor <= 0.0) usage_error("either --mbar or --mbar-factor must be positive");
    if(opt.D < abs(opt.cA - opt.cB)) usage_error("--d must be at least abs(ca - cb)");
    if(((opt.D - abs(opt.cA - opt.cB)) & 1) != 0)
        usage_error("--d and abs(ca - cb) must have the same parity");
    return opt;
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
        current->push_back(parse_uint32(token, "dataset value"));
        seen++;
    }
    if(current != nullptr && expected >= 0 && seen != expected)
        usage_error("dataset section length mismatch: " + path);
    if(data.alice.empty() || data.bob.empty()) usage_error("dataset missing Alice or Bob section: " + path);
    return data;
}

int effective_mbar(const Options &opt) {
    if(opt.mbar > 0) return opt.mbar;
    return max(1, static_cast<int>(ceil(opt.mbar_factor * static_cast<double>(opt.D))));
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

void print_unavailable(const Options &opt, int mbar, const string &reason) {
    cout << fixed << setprecision(9);
    cout << "{";
    print_json_string_field("algorithm", "cpisync");
    print_json_string_field("variant", "mbar_factor=" + to_string(opt.mbar_factor));
    print_json_string_field("implementation", "external/cpisync");
    print_json_int_field("d", opt.D);
    print_json_int_field("trials", opt.trials);
    print_json_int_field("successes", 0);
    print_json_number_field("success_rate", 0.0);
    print_json_number_field("encode_avg_s", 0.0);
    print_json_number_field("decode_avg_s", 0.0);
    print_json_number_field("encode_median_s", 0.0);
    print_json_number_field("decode_median_s", 0.0);
    print_json_number_field("reconcile_avg_s", 0.0);
    print_json_number_field("reconcile_median_s", 0.0);
    print_json_int_field("bits", 0);
    print_json_int_field("bytes", 0);
    print_json_int_field("mbar", mbar);
    print_json_number_field("mbar_factor", opt.mbar_factor);
    print_json_int_field("bits_param", opt.bits);
    print_json_int_field("epsilon", opt.epsilon);
    print_json_int_field("redundant", opt.redundant);
    print_json_bool_field("hashes", opt.hashes);
    print_json_int_field("seed", opt.seed);
    print_json_int_field("ca", opt.cA);
    print_json_int_field("cb", opt.cB);
    print_json_string_field("status", "unavailable");
    print_json_string_field("unavailable_reason", reason, false);
    cout << "}\n";
}

#ifdef ENABLE_REAL_CPISYNC
TrialResult run_trial_on_data(const Options &opt, const TrialData &data, int mbar) {
    using NTL::ZZ;

    auto start = chrono::steady_clock::now();
    GenSync alice = GenSync::Builder()
                        .setProtocol(GenSync::SyncProtocol::CPISync)
                        .setComm(GenSync::SyncComm::socket)
                        .setBits(opt.bits)
                        .setErr(opt.epsilon)
                        .setMbar(mbar)
                        .setPort(opt.port)
                        .build();
    for(uint32_t value : data.alice) {
        alice.addElem(new DataObject(ZZ(static_cast<long>(value))));
    }

    GenSync bob = GenSync::Builder()
                      .setProtocol(GenSync::SyncProtocol::CPISync)
                      .setComm(GenSync::SyncComm::socket)
                      .setBits(opt.bits)
                      .setErr(opt.epsilon)
                      .setMbar(mbar)
                      .setPort(opt.port)
                      .build();
    for(uint32_t value : data.bob) {
        bob.addElem(new DataObject(ZZ(static_cast<long>(value))));
    }

    forkHandleReport report = forkHandle(alice, bob, false);
    auto finish = chrono::steady_clock::now();

    TrialResult result;
    result.success = report.success;
    result.reconcile_s = report.totalTime >= 0.0
                             ? report.totalTime
                             : chrono::duration<double>(finish - start).count();
    long long recv_bytes = report.bytesRTot > 0 ? report.bytesRTot : 0;
    long long xmit_bytes = report.bytesXTot > 0 ? report.bytesXTot : 0;
    result.bytes = recv_bytes + xmit_bytes;
    return result;
}
#endif

} // namespace

int main(int argc, char **argv) {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    Options opt = parse_args(argc, argv);
    TrialData data = load_dataset(opt.dataset_path);
    const int mbar = effective_mbar(opt);

#ifndef ENABLE_REAL_CPISYNC
    print_unavailable(opt, mbar, "cpisync_bench was built without ENABLE_REAL_CPISYNC");
    return 0;
#else
    vector<double> reconcile_times;
    vector<long long> byte_values;
    int successes = 0;
    for(int t = 0; t < opt.trials; t++) {
        TrialResult result = run_trial_on_data(opt, data, mbar);
        reconcile_times.push_back(result.reconcile_s);
        byte_values.push_back(result.bytes);
        if(result.success) successes++;
    }

    long long bytes = byte_values.empty() ? 0 : byte_values.front();
    long long bits = bytes * 8;
    double success_rate = static_cast<double>(successes) / static_cast<double>(opt.trials);
    double bit_c_over_d = static_cast<double>(bits) / (static_cast<double>(opt.D) * 32.0);

    cout << fixed << setprecision(9);
    cout << "{";
    print_json_string_field("algorithm", "cpisync");
    print_json_string_field("variant", "mbar_factor=" + to_string(opt.mbar_factor));
    print_json_string_field("implementation", "external/cpisync");
    print_json_int_field("d", opt.D);
    print_json_int_field("trials", opt.trials);
    print_json_int_field("successes", successes);
    print_json_number_field("success_rate", success_rate);
    print_json_number_field("encode_avg_s", 0.0);
    print_json_number_field("decode_avg_s", average(reconcile_times));
    print_json_number_field("encode_median_s", 0.0);
    print_json_number_field("decode_median_s", median(reconcile_times));
    print_json_number_field("reconcile_avg_s", average(reconcile_times));
    print_json_number_field("reconcile_median_s", median(reconcile_times));
    print_json_int_field("bits", bits);
    print_json_int_field("bytes", bytes);
    print_json_number_field("C_over_d", bit_c_over_d);
    print_json_number_field("bit_C_over_d", bit_c_over_d);
    print_json_int_field("mbar", mbar);
    print_json_number_field("mbar_factor", opt.mbar_factor);
    print_json_int_field("bits_param", opt.bits);
    print_json_int_field("epsilon", opt.epsilon);
    print_json_int_field("redundant", opt.redundant);
    print_json_bool_field("hashes", opt.hashes);
    print_json_int_field("seed", opt.seed);
    print_json_int_field("ca", opt.cA);
    print_json_int_field("cb", opt.cB);
    print_json_string_field("status", "ok", false);
    cout << "}\n";
    return 0;
#endif
}
