#include "../harness/common.hpp"

#include <cmath>
#include <iostream>
#include <random>
#include <variant>

#include "XYZSketch.h"

namespace {
int configured_k = 2, configured_ell = 6;
std::string configured_mode = "circular";
std::uint64_t CellBits() { return 30U * configured_ell + (64U - __builtin_clzll(2U * configured_ell)); }


std::vector<unsigned char> PackBits(const std::vector<bool>& bits) {
    std::vector<unsigned char> output((bits.size() + 7U) / 8U, 0U);
    for(std::size_t index = 0; index < bits.size(); ++index) {
        if(bits[index]) output[index / 8U] |= static_cast<unsigned char>(1U << (7U - index % 8U));
    }
    return output;
}

std::vector<bool> UnpackBits(
    const std::vector<unsigned char>& bytes, std::size_t offset, std::size_t bit_count
) {
    if(offset + (bit_count + 7U) / 8U != bytes.size()) throw std::runtime_error("XYZ wire size mismatch");
    std::vector<bool> bits(bit_count);
    for(std::size_t index = 0; index < bit_count; ++index) {
        bits[index] = (bytes[offset + index / 8U] >> (7U - index % 8U)) & 1U;
    }
    return bits;
}

// Fields remain least-significant-bit first, packed in MSB-first bytes exactly
// as the original to_bitstring -> PackBits pipeline; all validation is retained.
inline unsigned ReverseByte(unsigned x){
    x=((x&0x55U)<<1)|((x>>1)&0x55U);x=((x&0x33U)<<2)|((x>>2)&0x33U);
    return ((x&0x0fU)<<4)|((x>>4)&0x0fU);
}
void WriteField(std::vector<unsigned char>& bytes,size_t& bit,unsigned x,int width){
    while(width){int offset=bit%8,take=std::min(width,8-offset);
        bytes[bit/8]|=ReverseByte(x&((1U<<take)-1))>>offset;
        x>>=take;bit+=take;width-=take;}
}
unsigned ReadField(const std::vector<unsigned char>& bytes,size_t& bit,int width){
    unsigned result=0;int used=0;
    while(width){int offset=bit%8,take=std::min(width,8-offset);
        unsigned x=(bytes[bit/8]>>(8-offset-take))&((1U<<take)-1);
        result|=(ReverseByte(x)>>(8-take))<<used;bit+=take;used+=take;width-=take;}
    return result;
}
std::vector<unsigned char> PackSketch(const XYZSketch& sketch){
    std::vector<unsigned char> bytes((size_t(sketch.B.size())*CellBits()+7)/8,0);size_t pos=0;
    int counter_bits=CellBits()-30U*configured_ell;
    for(const auto& cell:sketch.B){WriteField(bytes,pos,cell.c,counter_bits);
        for(int j=0;j<configured_ell;++j){int v=cell.p.v(j);WriteField(bytes,pos,v,30);}}
    return bytes;
}
XYZSketch ParseSketch(const std::vector<unsigned char>& bytes,int cells){
    if(cells<=0)throw std::runtime_error("XYZ cell count is invalid");
    figure2::ValidatePackedState(bytes,uint64_t(cells)*CellBits());
    XYZSketch sketch;sketch.init();size_t pos=0;int counter_bits=CellBits()-30U*configured_ell;
    for(auto& cell:sketch.B){unsigned count=ReadField(bytes,pos,counter_bits);
        if(count>=unsigned(2*configured_ell+1))throw std::runtime_error("invalid counter");cell.c=count;
        for(int j=0;j<configured_ell;++j){unsigned v=ReadField(bytes,pos,30);
            if(v>=figure2::kFieldModulus || (j==0 && v==0))throw std::runtime_error("invalid field coefficient");
            cell.p[j]=v;}}
    return sketch;
}

void Configure(int cells, double a, int z) {
    k = configured_k;
    l = configured_ell;
    M = cells;
    Hashing::SetHashMode(configured_mode == "circular" ? Hashing::CIRCULAR : Hashing::NAIVE);
    Hashing::SetCircularA(a);
    Hashing::SetDedupHashes(true);
    Hashing::HashingInit(z);
}

void Update(XYZSketch& sketch, const std::vector<std::uint32_t>& values) {
    for(std::uint32_t value : values) sketch.Update(static_cast<int>(value));
}

void SeedDecoder(std::uint64_t seed) {
    const std::uint32_t high = static_cast<std::uint32_t>(seed >> 32U);
    const std::uint32_t low = static_cast<std::uint32_t>(seed);
    std::seed_seq sequence{high, low};
    rng.seed(sequence);
}

struct ParsedXYZ {
    std::vector<bool> bits;
};

ParsedXYZ ParseState(const std::vector<unsigned char>& state, int cells) {
    if(cells <= 0) throw std::runtime_error("XYZ cell count is invalid");
    const std::uint64_t logical_bits = static_cast<std::uint64_t>(cells) * CellBits();
    figure2::ValidatePackedState(state, logical_bits);
    auto bits = UnpackBits(state, 0U, static_cast<std::size_t>(logical_bits));
    std::size_t offset = 0;
    const int cb = CellBits() - 30U * configured_ell;
    for(int i=0; i<cells; ++i) {
        unsigned count=0;
        for(int j=0;j<cb;++j) count |= unsigned(bits[offset++]) << j;
        if(count >= unsigned(2*configured_ell+1)) throw std::runtime_error("invalid counter");
        for(int t=0;t<configured_ell;++t) {
            unsigned coefficient=0;
            for(int j=0;j<30;++j) coefficient |= unsigned(bits[offset++]) << j;
            if(coefficient >= figure2::kFieldModulus || (t==0 && coefficient==0))
                throw std::runtime_error("invalid field coefficient");
        }
    }
    return ParsedXYZ{std::move(bits)};
}

figure2::EngineResult Run(
    const figure2::Dataset& dataset, int cells, double a, int z, std::uint64_t decoder_seed
) {
    figure2::EngineResult result;
    result.algorithm = "xyz-gf230";
    tool::init(std::max(64,16*configured_ell));
    tool::Pinit(std::max(64,16*configured_ell));
    Configure(cells, a, z);
    XYZSketch alice;
    alice.init();
    double begin = figure2::ThreadCpuSeconds();
    Update(alice, dataset.alice);
    result.update_alice_cpu = figure2::ThreadCpuSeconds() - begin;
    Configure(cells, a, z);
    XYZSketch bob;
    bob.init();
    begin = figure2::ThreadCpuSeconds();
    Update(bob, dataset.bob);
    result.update_bob_cpu = figure2::ThreadCpuSeconds() - begin;

    begin = figure2::ThreadCpuSeconds();
    #if 1
    const size_t logical_bits=size_t(cells)*CellBits();
    std::vector<unsigned char> state=PackSketch(alice);
#else
    std::vector<bool> logical = alice.to_bitstring();
    const size_t logical_bits=logical.size();
    std::vector<unsigned char> state = PackBits(logical);
#endif
    result.sender_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    std::vector<unsigned char> received_state = state;
    result.transfer_cpu = figure2::ThreadCpuSeconds() - begin;
    begin = figure2::ThreadCpuSeconds();
    Configure(cells,a,z);
#if 1
    XYZSketch received=ParseSketch(received_state,cells);
#else
    ParsedXYZ parsed=ParseState(received_state,cells);
    XYZSketch received=to_sketch(parsed.bits);
#endif
    XYZSketch residual = received - bob;
    SeedDecoder(decoder_seed);
    auto decoded = residual.Decode(false);
    std::vector<std::uint32_t> alice_only, bob_only;
    if(decoded.index() == 0) {
        const auto& output = std::get<std::pair<std::vector<int>, std::vector<int>>>(decoded);
        alice_only.assign(output.first.begin(), output.first.end());
        bob_only.assign(output.second.begin(), output.second.end());
        const bool shape_valid = figure2::CanonicalizeDirected(alice_only, bob_only);
        result.failure = shape_valid ? "pending_ground_truth" : "wrong_output";
    } else {
        result.failure = "decode_failed";
    }
    result.receiver_cpu = figure2::ThreadCpuSeconds() - begin;
    Configure(cells, a, z);
    XYZSketch audit_residual = received - bob;
    result.residual_sha256 = figure2::Sha256(PackBits(audit_residual.to_bitstring()));
    const bool timer_stopped = true;
    if(decoded.index() == 0 && result.failure == "pending_ground_truth") {
        result.success = figure2::CompareGroundTruthAfterTimer(
            alice_only, bob_only, dataset, timer_stopped
        );
        result.failure = result.success ? "success" : "wrong_output";
    }
    result.alice_output_sha256 = figure2::VectorSha256(alice_only);
    result.bob_output_sha256 = figure2::VectorSha256(bob_only);
    result.logical_state_bits = logical_bits;
    result.state_bits = state.size() * 8U;
    result.control_bits = 0U;
    result.total_payload_bits = result.state_bits;
    if(result.logical_state_bits != static_cast<std::uint64_t>(cells) * CellBits() ||
       result.total_payload_bits != result.state_bits) {
        throw std::runtime_error("XYZ accounting mismatch");
    }
    result.payload_sha256 = figure2::Sha256(state); // Outside all timing windows.
    return result;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if(argc == 2 && std::string(argv[1]) == "--self-test") {
            tool::init(std::max(64,16*configured_ell));
            tool::Pinit(std::max(64,16*configured_ell));
            Configure(2, 0.2, 1);
            XYZSketch sketch;
            sketch.init();
            const std::vector<bool> bits = sketch.to_bitstring();
            const std::vector<unsigned char> state = PackBits(bits);
            bool malformed_rejected = false;
            try {
                ParseState(std::vector<unsigned char>(state.begin(), state.end() - 1), 2);
            } catch(const std::exception&) {
                malformed_rejected = true;
            }
            const bool passed = bits.size() == 368U && state.size() * 8U == 368U &&
                ParseState(state, 2).bits == bits && malformed_rejected;
            std::cout << "{\"protocol\":\"figure2-engine-v2\",\"algorithm\":\"xyz-gf230\","
                      << "\"golden_total_bits\":" << state.size() * 8U
                      << ",\"malformed_state_rejected\":" << (malformed_rejected ? "true" : "false")
                      << ",\"passed\":" << (passed ? "true" : "false") << "}\n";
            return passed ? 0 : 2;
        }
        if(argc != 10 || std::string(argv[1]) != "--run") {
            throw std::invalid_argument("usage: tradeoff_xyz_engine --run DATASET k ell MODE M a z SEED");
        }
        configured_k = std::stoi(argv[3]); configured_ell = std::stoi(argv[4]);
        configured_mode = argv[5];
        if(configured_k<2 || configured_k>4 ||
           !(configured_ell==2 || configured_ell==3 || configured_ell==4 || configured_ell==6 || configured_ell==8 || configured_ell==10))
            throw std::invalid_argument("configuration outside validated grid");
        if(configured_mode!="circular" && configured_mode!="naive" && configured_mode!="iid")
            throw std::invalid_argument("invalid placement mode");
        if(configured_mode=="iid" && (std::stoi(argv[8])!=0 || std::stod(argv[7])!=0))
            throw std::invalid_argument("iid requires a=z=0");
        figure2::PrintResult(Run(figure2::ReadDataset(argv[2]),std::stoi(argv[6]),
                                std::stod(argv[7]),std::stoi(argv[8]),std::stoull(argv[9])));
        return 0;
    } catch(const std::exception& error) {
        std::cerr << typeid(error).name() << ": " << error.what() << '\n';
        return 1;
    }
}
