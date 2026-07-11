#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <queue>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

#include "../../XYZ-v2/murmur3.cc"

using namespace std;

namespace {

const int FIELD_P = 998244353;

struct Options {
    int d = -1;
    int l = -1;
    int k = -1;
    int M = -1;
    double circular_a = 1.0 / 3.0;
    int z = -1;
    int trials = -1;
    uint32_t seed = 114514;
    bool dedup_hashes = false;
    string format = "jsonl";
};

[[noreturn]] void usage_error(const string &message) {
    cerr << "error: " << message << "\n";
    cerr << "usage: fig2_peeling_sim --d D --l L --k K --M M --a A --z Z "
            "--trials N --seed S [--dedup-hashes true|false] [--format jsonl]\n";
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
        if(key == "--help" || key == "-h") usage_error("help requested");
        if(i + 1 >= argc) usage_error("missing value for " + key);
        string value = argv[++i];
        if(key == "--d") opt.d = parse_int(value, key);
        else if(key == "--l") opt.l = parse_int(value, key);
        else if(key == "--k") opt.k = parse_int(value, key);
        else if(key == "--M" || key == "--m") opt.M = parse_int(value, key);
        else if(key == "--a" || key == "--circular-a") opt.circular_a = parse_double(value, key);
        else if(key == "--z") opt.z = parse_int(value, key);
        else if(key == "--trials") opt.trials = parse_int(value, key);
        else if(key == "--seed") opt.seed = parse_uint32(value, key);
        else if(key == "--dedup-hashes") opt.dedup_hashes = parse_bool(value, key);
        else if(key == "--format") opt.format = value;
        else usage_error("unknown argument: " + key);
    }
    if(opt.d <= 0) usage_error("--d must be positive");
    if(opt.l <= 0) usage_error("--l must be positive");
    if(opt.k <= 0) usage_error("--k must be positive");
    if(opt.M <= 0) usage_error("--M must be positive");
    if(opt.z < 0) usage_error("--z must be non-negative");
    if(opt.trials <= 0) usage_error("--trials must be positive");
    if(!(0.0 <= opt.circular_a && opt.circular_a < 1.0))
        usage_error("--a/--circular-a must be in [0, 1)");
    if(opt.format != "jsonl") usage_error("this benchmark currently supports only --format jsonl");
    return opt;
}

uint32_t murmur_int(int value, uint32_t seed) {
    uint32_t output = 0;
    MurmurHash3_x86_32(&value, sizeof(int), seed, &output);
    return output;
}

int range_length(const Options &opt) {
    return opt.M / (opt.z + 1);
}

int circular_base_range(const Options &opt) {
    int len = range_length(opt);
    int shrink = static_cast<int>(floor(opt.circular_a * static_cast<double>(len)));
    int base_range = opt.M - shrink + 1;
    return max(1, min(opt.M, base_range));
}

vector<int> hash_locations(const Options &opt, int value) {
    int len = range_length(opt);
    int base_range = circular_base_range(opt);
    int base = static_cast<int>(murmur_int(value, 114514) % static_cast<uint32_t>(base_range));
    vector<int> positions;
    positions.reserve(static_cast<size_t>(opt.k));
    for(int i = 1; i <= opt.k; i++) {
        int offset = static_cast<int>(murmur_int(value, static_cast<uint32_t>(i)) % static_cast<uint32_t>(len));
        positions.push_back((base + offset) % opt.M);
    }
    if(opt.dedup_hashes) {
        sort(positions.begin(), positions.end());
        positions.erase(unique(positions.begin(), positions.end()), positions.end());
    }
    return positions;
}

vector<int> generate_values(int count, uint32_t seed) {
    mt19937 rng(seed);
    unordered_set<int> used;
    used.reserve(static_cast<size_t>(count * 2 + 16));
    vector<int> values;
    values.reserve(static_cast<size_t>(count));
    for(int i = 0; i < count; i++) {
        int value = static_cast<int>(rng() % (FIELD_P - 1)) + 1;
        while(used.find(value) != used.end()) {
            value = static_cast<int>(rng() % (FIELD_P - 1)) + 1;
        }
        used.insert(value);
        values.push_back(value);
    }
    return values;
}

bool run_trial(const Options &opt, uint32_t trial_seed) {
    vector<int> values = generate_values(opt.d, trial_seed);
    vector<int> edge_offsets(static_cast<size_t>(opt.d) + 1, 0);
    vector<int> edge_buckets;
    edge_buckets.reserve(static_cast<size_t>(opt.d) * static_cast<size_t>(opt.k));
    vector<int> degree(static_cast<size_t>(opt.M), 0);

    for(int edge = 0; edge < opt.d; edge++) {
        vector<int> positions = hash_locations(opt, values[edge]);
        edge_offsets[edge] = static_cast<int>(edge_buckets.size());
        for(int bucket : positions) {
            edge_buckets.push_back(bucket);
            degree[bucket]++;
        }
    }
    edge_offsets[opt.d] = static_cast<int>(edge_buckets.size());

    vector<int> bucket_offsets(static_cast<size_t>(opt.M) + 1, 0);
    for(int bucket = 0; bucket < opt.M; bucket++) {
        bucket_offsets[bucket + 1] = bucket_offsets[bucket] + degree[bucket];
    }
    vector<int> bucket_cursor(bucket_offsets.begin(), bucket_offsets.end() - 1);
    vector<int> bucket_edges(edge_buckets.size(), 0);
    for(int edge = 0; edge < opt.d; edge++) {
        for(int index = edge_offsets[edge]; index < edge_offsets[edge + 1]; index++) {
            int bucket = edge_buckets[index];
            bucket_edges[bucket_cursor[bucket]++] = edge;
        }
    }

    queue<int> q;
    vector<bool> queued(static_cast<size_t>(opt.M), false);
    for(int bucket = 0; bucket < opt.M; bucket++) {
        if(degree[bucket] > 0 && degree[bucket] <= opt.l) {
            queued[bucket] = true;
            q.push(bucket);
        }
    }

    vector<bool> edge_alive(static_cast<size_t>(opt.d), true);
    int peeled = 0;
    while(!q.empty()) {
        int bucket = q.front();
        q.pop();
        if(degree[bucket] <= 0 || degree[bucket] > opt.l) continue;

        for(int index = bucket_offsets[bucket]; index < bucket_offsets[bucket + 1]; index++) {
            int edge = bucket_edges[index];
            if(!edge_alive[edge]) continue;
            edge_alive[edge] = false;
            peeled++;
            for(int edge_index = edge_offsets[edge]; edge_index < edge_offsets[edge + 1]; edge_index++) {
                int other_bucket = edge_buckets[edge_index];
                degree[other_bucket]--;
                if(degree[other_bucket] > 0 && degree[other_bucket] <= opt.l && !queued[other_bucket]) {
                    queued[other_bucket] = true;
                    q.push(other_bucket);
                }
            }
        }
    }
    return peeled == opt.d;
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
    int len = range_length(opt);
    int successes = 0;
    string status = "ok";
    string invalid_reason;

    if(len <= 0) {
        status = "invalid";
        invalid_reason = "range_length <= 0";
    } else {
        for(int trial = 0; trial < opt.trials; trial++) {
            uint32_t trial_seed = opt.seed + static_cast<uint32_t>(trial);
            if(run_trial(opt, trial_seed)) successes++;
        }
    }

    double success_rate = opt.trials > 0 ? static_cast<double>(successes) / static_cast<double>(opt.trials) : 0.0;

    cout << fixed << setprecision(9);
    cout << "{";
    print_json_string_field("algorithm", "peeling_sim");
    print_json_string_field("mode", "circular");
    print_json_string_field("status", status);
    print_json_int_field("d", opt.d);
    print_json_int_field("l", opt.l);
    print_json_int_field("k", opt.k);
    print_json_int_field("M", opt.M);
    print_json_int_field("m", opt.M);
    print_json_int_field("z", opt.z);
    print_json_number_field("circular_a", opt.circular_a);
    print_json_bool_field("dedup_hashes", opt.dedup_hashes);
    print_json_int_field("range_length", len);
    print_json_int_field("circular_base_range", len > 0 ? circular_base_range(opt) : 0);
    print_json_int_field("trials", opt.trials);
    print_json_int_field("successes", successes);
    print_json_number_field("success_rate", success_rate);
    print_json_number_field("peeling_success_rate", success_rate);
    print_json_int_field("seed", opt.seed);
    print_json_number_field("field_C_over_d", static_cast<double>(opt.M) * opt.l / static_cast<double>(opt.d));
    print_json_number_field("bits", 0.0);
    if(status == "invalid") {
        print_json_string_field("invalid_reason", invalid_reason, false);
    } else {
        print_json_string_field("invalid_reason", "", false);
    }
    cout << "}\n";
    return status == "ok" ? 0 : 0;
}
