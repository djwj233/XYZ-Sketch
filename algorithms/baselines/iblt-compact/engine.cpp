#include "common.hpp"
#include "iblt.h"
#include <memory>

std::unique_ptr<IBLT> make_table(const std::string& mode, size_t resource, size_t k, size_t z, uint64_t seed) {
    if (mode=="external_iblt") return std::make_unique<IBLT>(resource,0);
    if (mode=="iblt_sc") return std::make_unique<IBLT>(resource,k,z,seed);
    throw std::runtime_error("unknown mode");
}
int main(int argc,char** argv) {
 try {
    if (argc!=9) throw std::runtime_error("usage: engine DATASET mode resource k z seed repetitions");
    const auto data=figure2::ReadDataset(argv[1]);
    const std::string mode=argv[2];
    size_t resource=std::stoull(argv[3]),k=std::stoull(argv[4]),z=std::stoull(argv[5]);
    uint64_t seed=std::stoull(argv[6]); int reps=std::stoi(argv[7]),order=std::stoi(argv[8]);
    auto alice=make_table(mode,resource,k,z,seed),bob=make_table(mode,resource,k,z,seed);
    double begin=figure2::ThreadCpuSeconds();
    for(auto x:data.alice) alice->insert(x,{});
    double ua=figure2::ThreadCpuSeconds()-begin;
    begin=figure2::ThreadCpuSeconds();
    for(auto x:data.bob) bob->insert(x,{});
    double ub=figure2::ThreadCpuSeconds()-begin;
    // Full cell-state identity is checked independently, outside timing.
    auto canonical=alice->serialize_canonical();
    auto recovered=make_table(mode,resource,k,z,seed);
    recovered->deserialize_compact(alice->serialize_compact());
    if (recovered->serialize_canonical()!=canonical) throw std::runtime_error("full snapshot roundtrip mismatch");
    for(int rep=0;rep<reps;++rep) {
        figure2::EngineResult results[2];
        for(int pass=0;pass<2;++pass) {
            int compact=(rep+pass+order)%2;
            auto& out=results[compact];out.algorithm=compact?"compact_count":"canonical";
            out.update_alice_cpu=ua;out.update_bob_cpu=ub;
            uint64_t logical=alice->cell_count()*87;
            begin=figure2::ThreadCpuSeconds();
            auto msg=compact?alice->serialize_compact(&logical):alice->serialize_canonical();
            out.sender_cpu=figure2::ThreadCpuSeconds()-begin;
            begin=figure2::ThreadCpuSeconds();auto transmitted=msg;
            out.transfer_cpu=figure2::ThreadCpuSeconds()-begin;
            begin=figure2::ThreadCpuSeconds();
            auto received=make_table(mode,resource,k,z,seed);
            if(compact) received->deserialize_compact(transmitted); else received->deserialize_canonical(transmitted);
            auto residual=*received-*bob;
            std::set<std::pair<uint64_t,std::vector<uint8_t>>> pos,neg;
            bool decoded=residual.listEntries(pos,neg);
            std::vector<uint32_t> a,b;
            for(const auto& e:pos) a.push_back(e.first);
            for(const auto& e:neg) b.push_back(e.first);
            bool shape=figure2::CanonicalizeDirected(a,b);
            out.receiver_cpu=figure2::ThreadCpuSeconds()-begin;
            out.success=decoded && shape && figure2::CompareGroundTruthAfterTimer(a,b,data,true);
            out.failure=out.success?"success":(decoded?"wrong_output":"decode_failed");
            out.alice_output_sha256=figure2::VectorSha256(a);out.bob_output_sha256=figure2::VectorSha256(b);
            out.residual_sha256=figure2::Sha256(residual.serialize_canonical());out.payload_sha256=figure2::Sha256(msg);
            out.logical_state_bits=logical;out.state_bits=msg.size()*8;out.total_payload_bits=out.state_bits;
        }
        const auto& a=results[0];const auto& b=results[1];
        if(a.success!=b.success || a.failure!=b.failure || a.alice_output_sha256!=b.alice_output_sha256 ||
           a.bob_output_sha256!=b.bob_output_sha256 || a.residual_sha256!=b.residual_sha256)
            throw std::runtime_error("paired decode mismatch");
        figure2::PrintResult(a);figure2::PrintResult(b);
    }
    return 0;
 } catch(const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
