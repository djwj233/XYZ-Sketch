#include <cmath>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

#ifdef ENABLE_REAL_NEGENTROPY
#include "negentropy.h"
#include "negentropy/storage/Vector.h"
#endif

using namespace std;

namespace {

struct Options {
    int D = -1;
    int trials = -1;
    uint32_t seed = 114514;
    int cA = 10000000;
    int cB = 10000000;
    int frame_size_limit = 0;
    string timestamp_mode = "value";
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
        else if(key == "--frame-size-limit") opt.frame_size_limit = parse_int(value, key);
        else if(key == "--timestamp-mode") opt.timestamp_mode = value;
        else if(key == "--dataset") opt.dataset_path = value;
        else if(key == "--format") opt.format = value;
        else usage_error("unknown argument: " + key);
    }
    if(opt.D <= 0 || opt.trials <= 0) usage_error("invalid required parameter");
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
    if(current != nullptr && expected >= 0 && seen != expected) usage_error("dataset section length mismatch");
    return data;
}

set<uint64_t> difference(const vector<uint64_t> &left, const vector<uint64_t> &right) {
    set<uint64_t> right_set(right.begin(), right.end());
    set<uint64_t> out;
    for(uint64_t value : left) {
        if(!right_set.count(value)) out.insert(value);
    }
    return out;
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

#ifdef ENABLE_REAL_NEGENTROPY
string id_from_value(uint64_t value) {
    string id(negentropy::ID_SIZE, '\0');
    for(size_t i = 0; i < sizeof(value); i++) {
        id[i] = static_cast<char>((value >> (8 * i)) & 0xff);
    }
    return id;
}

uint64_t splitmix64(uint64_t value) {
    value += 0x9e3779b97f4a7c15ULL;
    value = (value ^ (value >> 30)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31);
}

uint64_t timestamp_for(uint64_t value, const Options &opt) {
    if(opt.timestamp_mode == "value") return value;
    if(opt.timestamp_mode == "constant") return 1;
    if(opt.timestamp_mode == "random") return splitmix64(value ^ opt.seed);
    usage_error("unknown timestamp mode");
}

void fill_storage(negentropy::storage::Vector &storage, const vector<uint64_t> &values, const Options &opt) {
    for(uint64_t value : values) {
        storage.insert(timestamp_for(value, opt), id_from_value(value));
    }
    storage.seal();
}

set<uint64_t> values_from_ids(const vector<string> &ids) {
    set<uint64_t> out;
    for(const string &id : ids) {
        if(id.size() < sizeof(uint64_t)) continue;
        uint64_t value = 0;
        for(size_t i = 0; i < sizeof(uint64_t); i++) {
            value |= (static_cast<uint64_t>(static_cast<unsigned char>(id[i])) << (8 * i));
        }
        out.insert(value);
    }
    return out;
}

struct TrialResult {
    bool success = false;
    long long client_bytes = 0;
    long long server_bytes = 0;
    int rounds = 0;
    double reconcile_s = 0.0;
    string status = "ok";
    string error;
};

TrialResult run_negentropy(const Options &opt, const Dataset &data) {
    using clock = chrono::steady_clock;
    TrialResult result;
    set<uint64_t> expected_have = difference(data.alice, data.bob);
    set<uint64_t> expected_need = difference(data.bob, data.alice);

    auto start = clock::now();
    try {
        negentropy::storage::Vector client_storage;
        negentropy::storage::Vector server_storage;
        fill_storage(client_storage, data.alice, opt);
        fill_storage(server_storage, data.bob, opt);
        Negentropy<negentropy::storage::Vector> client(client_storage, static_cast<uint64_t>(opt.frame_size_limit));
        Negentropy<negentropy::storage::Vector> server(server_storage, static_cast<uint64_t>(opt.frame_size_limit));

        vector<string> have_ids;
        vector<string> need_ids;
        string msg = client.initiate();
        result.client_bytes += static_cast<long long>(msg.size());

        for(int round = 0; round < 10000; round++) {
            result.rounds++;
            string response = server.reconcile(msg);
            result.server_bytes += static_cast<long long>(response.size());

            vector<string> have;
            vector<string> need;
            optional<string> next = client.reconcile(response, have, need);
            have_ids.insert(have_ids.end(), have.begin(), have.end());
            need_ids.insert(need_ids.end(), need.begin(), need.end());
            if(!next) {
                break;
            }
            msg = *next;
            result.client_bytes += static_cast<long long>(msg.size());
        }

        set<uint64_t> actual_have = values_from_ids(have_ids);
        set<uint64_t> actual_need = values_from_ids(need_ids);
        result.success = actual_have == expected_have && actual_need == expected_need;
        if(!result.success) {
            result.status = "failed_decode";
            result.error = "have/need mismatch";
        }
    } catch(const exception &exc) {
        result.status = "benchmark_error";
        result.error = exc.what();
    }

    result.reconcile_s = chrono::duration<double>(clock::now() - start).count();
    return result;
}

void print_result(const Options &opt, const TrialResult &result) {
    long long bytes = result.client_bytes + result.server_bytes;
    long long bits = bytes * 8;
    cout << fixed << setprecision(9);
    cout << "{";
    print_json_string_field("algorithm", "negentropy");
    print_json_string_field("variant", "frame_size=" + to_string(opt.frame_size_limit) + ",timestamp=" + opt.timestamp_mode);
    print_json_string_field("implementation", "external/negentropy");
    print_json_int_field("d", opt.D);
    print_json_int_field("trials", opt.trials);
    print_json_int_field("successes", result.success ? 1 : 0);
    print_json_number_field("success_rate", result.success ? 1.0 : 0.0);
    print_json_number_field("encode_avg_s", 0.0);
    print_json_number_field("decode_avg_s", result.reconcile_s);
    print_json_number_field("encode_median_s", 0.0);
    print_json_number_field("decode_median_s", result.reconcile_s);
    print_json_number_field("reconcile_avg_s", result.reconcile_s);
    print_json_number_field("reconcile_median_s", result.reconcile_s);
    print_json_int_field("bits", bits);
    print_json_int_field("bytes", bytes);
    print_json_number_field("C_over_d", static_cast<double>(bits) / (32.0 * static_cast<double>(opt.D)));
    print_json_int_field("frame_size_limit", opt.frame_size_limit);
    print_json_string_field("timestamp_mode", opt.timestamp_mode);
    print_json_int_field("rounds", result.rounds);
    print_json_int_field("client_bytes", result.client_bytes);
    print_json_int_field("server_bytes", result.server_bytes);
    print_json_string_field("communication_model", "interactive");
    print_json_bool_field("ordered_workload", opt.timestamp_mode == "value");
    print_json_int_field("seed", opt.seed);
    print_json_int_field("ca", opt.cA);
    print_json_int_field("cb", opt.cB);
    print_json_string_field("status", result.status);
    print_json_string_field("error", result.error, false);
    cout << "}\n";
}
#endif

} // namespace

int main(int argc, char **argv) {
    Options opt = parse_args(argc, argv);
    Dataset data = load_dataset(opt.dataset_path);
#ifdef ENABLE_REAL_NEGENTROPY
    print_result(opt, run_negentropy(opt, data));
    return 0;
#else
    cout << fixed << setprecision(9);
    cout << "{";
    print_json_string_field("algorithm", "negentropy");
    print_json_string_field("variant", "frame_size=" + to_string(opt.frame_size_limit) + ",timestamp=" + opt.timestamp_mode);
    print_json_string_field("implementation", "external/negentropy");
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
    print_json_int_field("frame_size_limit", opt.frame_size_limit);
    print_json_string_field("timestamp_mode", opt.timestamp_mode);
    print_json_int_field("rounds", 0);
    print_json_int_field("client_bytes", 0);
    print_json_int_field("server_bytes", 0);
    print_json_int_field("seed", opt.seed);
    print_json_int_field("ca", opt.cA);
    print_json_int_field("cb", opt.cB);
    print_json_string_field("status", "unavailable");
    print_json_string_field("unavailable_reason", "negentropy adapter is planned but not linked to the C++ implementation yet", false);
    cout << "}\n";
    return 0;
#endif
}
