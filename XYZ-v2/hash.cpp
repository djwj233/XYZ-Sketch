#include <random>
#include <iostream>
#include <algorithm>
#include <cmath>

#include <limits.h>
#include <stdint.h>
#include "murmur3.cc"
// #include "hash.h"
using namespace std;
#define fo(v, a, b) for(int v = a; v <= b; v++)
#define fr(v, a, b) for(int v = a; v >= b; v--)
#define cl(a, v) memset(a, v, sizeof(a))

int M, z, RangeLength;
extern int k;

namespace MurmurHash {
    uint32_t Hash(const int& data, uint32_t seed){
        uint32_t output;
        MurmurHash3_x86_32(&data, sizeof(int), seed, &output);
        return output;
    }
}

namespace RandomHash {
    int h(int i, int x) {
        return MurmurHash::Hash(x, 3 * i * i + i + 2) % (uint32_t)M;
    }
    void HashingInit(int znow) {

    }
}
namespace SpatialCoupling {
    enum HashMode {
        AUTO = 0,
        RANDOM = 1,
        CIRCULAR = 2,
        NAIVE = 3
    };

    HashMode CurrentHashMode = AUTO;
    double CircularA = 1.0 / 3.0;
    bool DedupHashes = false;

    void SetHashMode(HashMode mode) {
        CurrentHashMode = mode;
    }

    HashMode GetHashMode() {
        return CurrentHashMode;
    }

    void SetCircularA(double value) {
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

    int CircularBaseRange() {
        int shrink = (int)floor(CircularA * (double)RangeLength);
        int base_range = M - shrink + 1;
        base_range = max(1, min(M, base_range));
        return base_range;
    }

    inline HashMode EffectiveHashMode() {
        if(CurrentHashMode != AUTO) return CurrentHashMode;
        return k <= 2 ? CIRCULAR : NAIVE;
    }

    inline int circular_base_h0(int x) {
        return MurmurHash::Hash(x, 114514) % (uint32_t)CircularBaseRange();
    }
    inline int naive_base_h0(int x) {
        return MurmurHash::Hash(x, 114514) % (M - RangeLength + 1);
    }
    inline int base_h0(int x) {
        return EffectiveHashMode() == CIRCULAR ? circular_base_h0(x) : naive_base_h0(x);
    }
    inline int h(int i, int x) {
        auto mode = EffectiveHashMode();
        if(mode == RANDOM) return RandomHash::h(i, x);
        int cur = MurmurHash::Hash(x, i) % RangeLength;
        if(mode == CIRCULAR) return (base_h0(x) + cur) % M;
        return base_h0(x) + cur;
    }
    void HashingInit(int znow) {
        z = znow, RangeLength = M / (z + 1);
    }
}
