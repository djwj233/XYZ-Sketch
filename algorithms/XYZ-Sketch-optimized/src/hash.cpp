#include <algorithm>
#include <cmath>
#include <stdexcept>

#include "hash.h"
#include "murmur3.cc"

int M, z, RangeLength;

namespace MurmurHash {
    // An element is always one native 32-bit word. Share the Murmur block
    // mixing across seeds, while retaining the original finalization exactly.
    struct PreparedInt {
        std::uint32_t block;
        explicit PreparedInt(int value){block=ROTL32(std::uint32_t(value)*0xcc9e2d51U,15)*0x1b873593U;}
        std::uint32_t Hash(std::uint32_t seed)const{return fmix32((ROTL32(seed^block,13)*5U+0xe6546b64U)^4U);}
    };
    std::uint32_t Hash(const int& data, std::uint32_t seed){
        std::uint32_t output;
        MurmurHash3_x86_32(&data, sizeof(int), seed, &output);
        return output;
    }
}

namespace Hashing {
    HashMode CurrentHashMode = CIRCULAR;
    double CircularA = 0.0;
    bool DedupHashes = false;

    // Exact unsigned remainder: ceil(2^32/divisor) estimates the quotient
    // with at most one excess; a signed correction restores the true remainder.
    struct ExactU32Remainder {
        std::uint32_t divisor=1;std::uint64_t reciprocal=1ULL<<32;
        void Reset(std::uint32_t d){if(!d)throw std::invalid_argument("zero placement divisor");divisor=d;reciprocal=((1ULL<<32)+d-1)/d;}
        std::uint32_t operator()(std::uint32_t value)const{
            std::uint64_t quotient=(std::uint64_t(value)*reciprocal)>>32;
            std::int64_t remainder=std::int64_t(value)-std::int64_t(quotient)*divisor;
            std::uint64_t correction=0-(std::uint64_t(remainder)>>63);
            remainder+=std::int64_t(correction&divisor);return std::uint32_t(remainder);
        }
    };
    ExactU32Remainder offset_remainder,naive_anchor_remainder,circular_anchor_remainder;
    int cached_circular_base_range=1;
    void RefreshPlacementCache(){
        if(M<=0 || RangeLength<=0 || RangeLength>M)return;
        int naive=M-RangeLength+1;
        cached_circular_base_range=std::min(M,naive+int(std::floor(CircularA*double(RangeLength))));
        offset_remainder.Reset(RangeLength);naive_anchor_remainder.Reset(naive);circular_anchor_remainder.Reset(cached_circular_base_range);
    }
    std::uint32_t PlacementOffset(int x,int index){return offset_remainder(MurmurHash::Hash(x,index));}
    std::uint32_t PlacementOffset(const MurmurHash::PreparedInt& x,int index){return offset_remainder(x.Hash(index));}
    int base_h0(const MurmurHash::PreparedInt& x){return CurrentHashMode==CIRCULAR?circular_anchor_remainder(x.Hash(114514)):naive_anchor_remainder(x.Hash(114514));}
    int JoinLocation(int anchor,std::uint32_t offset){
        std::uint32_t value=std::uint32_t(anchor)+offset;
        if(CurrentHashMode==CIRCULAR && value>=std::uint32_t(M))value-=M;return int(value);
    }

    void SetHashMode(HashMode mode) {
        CurrentHashMode = mode;
    }

    HashMode GetHashMode() {
        return CurrentHashMode;
    }

    void SetCircularA(double value) {
        if(!std::isfinite(value) || value < 0.0 || value >= 1.0)
            throw std::invalid_argument("circular parameter a must be in [0, 1)");
        CircularA = value;
        RefreshPlacementCache();
    }

    double GetCircularA() {
        return CircularA;
    }

    void SetDedupHashes(bool enabled) {
        DedupHashes = enabled;
    }

    bool GetDedupHashes() {
        return DedupHashes;
    }

    int NaiveBaseRange() {
        return M - RangeLength + 1;
    }

    int CircularBaseRange() {
        // Discretizes the paper's anchor support [0, z + a).
        return cached_circular_base_range;
    }

    static int circular_base_h0(int x) {
        return circular_anchor_remainder(MurmurHash::Hash(x,114514));
    }
    static int naive_base_h0(int x) {
        return naive_anchor_remainder(MurmurHash::Hash(x,114514));
    }
    int base_h0(int x) {
        return CurrentHashMode == CIRCULAR ? circular_base_h0(x) : naive_base_h0(x);
    }
    int h(int i, int x) {
        return JoinLocation(base_h0(x),PlacementOffset(x,i));
    }
    void HashingInit(int znow) {
        if(M <= 0) throw std::invalid_argument("M must be positive before HashingInit");
        if(znow < 0) throw std::invalid_argument("coupling parameter z must be nonnegative");
        if(znow >= M) throw std::invalid_argument("coupling parameter z must be smaller than M");
        z = znow;
        RangeLength = M / (z + 1);
        RefreshPlacementCache();
    }
}
