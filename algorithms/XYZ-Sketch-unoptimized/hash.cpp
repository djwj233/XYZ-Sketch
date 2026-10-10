#include <algorithm>
#include <cmath>
#include <stdexcept>

#include "hash.h"
#include "murmur3.cc"

int M, z, RangeLength;

namespace MurmurHash {
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
        int extra_circular_anchors = (int)std::floor(CircularA * (double)RangeLength);
        return std::min(M, NaiveBaseRange() + extra_circular_anchors);
    }

    static int circular_base_h0(int x) {
        return MurmurHash::Hash(x, 114514) % (std::uint32_t)CircularBaseRange();
    }
    static int naive_base_h0(int x) {
        return MurmurHash::Hash(x, 114514) % (std::uint32_t)NaiveBaseRange();
    }
    int base_h0(int x) {
        return CurrentHashMode == CIRCULAR ? circular_base_h0(x) : naive_base_h0(x);
    }
    int h(int i, int x) {
        int cur = MurmurHash::Hash(x, i) % RangeLength;
        if(CurrentHashMode == CIRCULAR) return (base_h0(x) + cur) % M;
        return base_h0(x) + cur;
    }
    void HashingInit(int znow) {
        if(M <= 0) throw std::invalid_argument("M must be positive before HashingInit");
        if(znow < 0) throw std::invalid_argument("coupling parameter z must be nonnegative");
        if(znow >= M) throw std::invalid_argument("coupling parameter z must be smaller than M");
        z = znow;
        RangeLength = M / (z + 1);
    }
}
