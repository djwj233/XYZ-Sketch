#include "common.hpp"
#include "iblt.h"
#include <set>
#include <random>

int main() {
    std::mt19937_64 rng(202610071337ULL);
    size_t snapshots=0, known_recoveries=0;
    for (unsigned bits=0; bits<=32; ++bits) {
        for (unsigned trial=0; trial<10; ++trial) {
            std::set<uint32_t> keys;
            while (keys.size()<100) keys.insert(1 + rng()%998244352);
            IBLT a32(200,0), b32(200,0), a(200,0), b(200,0);
            a.set_fingerprint_bits(bits); b.set_fingerprint_bits(bits);
            unsigned j=0;
            std::set<std::pair<uint64_t,std::vector<uint8_t>>> pos_expected, neg_expected;
            for (auto k:keys) {
                if (j<70) { a.insert(k,{}); a32.insert(k,{}); }
                if (j>=30) { b.insert(k,{}); b32.insert(k,{}); }
                if (j<30) pos_expected.insert({k,{}});
                if (j>=70) neg_expected.insert({k,{}});
                if (a.placement(k)!=a32.placement(k)) throw std::runtime_error("placement changed");
                ++j;
            }
            auto am=a32, bm=b32;
            am.set_fingerprint_bits(bits); bm.set_fingerprint_bits(bits);
            if (a.serialize_canonical()!=am.serialize_canonical() ||
                b.serialize_canonical()!=bm.serialize_canonical())
                throw std::runtime_error("direct build vs masked state mismatch");
            auto residual=a-b, reference=a32-b32;
            reference.set_fingerprint_bits(bits);
            if (residual.serialize_canonical()!=reference.serialize_canonical())
                throw std::runtime_error("subtraction mismatch");
            IBLT parsed(200,0); parsed.set_fingerprint_bits(bits);
            parsed.deserialize_canonical(residual.serialize_canonical());
            if (parsed.serialize_canonical()!=residual.serialize_canonical())
                throw std::runtime_error("roundtrip mismatch");
            std::set<std::pair<uint64_t,std::vector<uint8_t>>> pos,neg;
            IBLT::DecodeStats stats; stats.max_peels=10000; stats.max_inspections=30000;
            bool ok=parsed.listEntries(pos,neg,&stats);
            if (bits==32 && (!ok || pos!=pos_expected || neg!=neg_expected))
                throw std::runtime_error("32bit known signed recovery failed");
            ++snapshots;
        }
        IBLT singleton(2,0); singleton.set_fingerprint_bits(bits); singleton.insert(12345,{});
        std::set<std::pair<uint64_t,std::vector<uint8_t>>> pos,neg;
        IBLT::DecodeStats stats; stats.max_peels=10; stats.max_inspections=100;
        if (!singleton.listEntries(pos,neg,&stats) || pos.size()!=1 || !neg.empty() || pos.begin()->first!=12345)
            throw std::runtime_error("singleton failed");
        IBLT empty(2,0); empty.set_fingerprint_bits(bits);pos.clear();neg.clear();
        if (!empty.listEntries(pos,neg,&stats) || !pos.empty() || !neg.empty())
            throw std::runtime_error("empty failed");
        known_recoveries+=2;
    }
    // A deliberately tiny measurement budget must be identified separately.
    IBLT t(2,0); t.insert(1,{});std::set<std::pair<uint64_t,std::vector<uint8_t>>> p,n;
    IBLT::DecodeStats s;s.max_peels=1;s.max_inspections=1;
    if (t.listEntries(p,n,&s) || !s.limit_hit) throw std::runtime_error("budget detection failed");
    std::cout << "{\"snapshots\":"<<snapshots<<",\"empty_singleton_recoveries\":"
              <<known_recoveries<<",\"placement_unchanged\":true,\"mask_build_equivalence\":true,"
              <<"\"wire_roundtrip\":true,\"passed\":true}" <<std::endl;
}
