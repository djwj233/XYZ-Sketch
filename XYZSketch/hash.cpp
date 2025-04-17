#include <random>
#include <iostream>

#include <limits.h>
#include <stdint.h>
#include "murmur3.cc"
// #include "hash.h"
using namespace std;
#define fo(v, a, b) for(int v = a; v <= b; v++)
#define fr(v, a, b) for(int v = a; v >= b; v--)
#define cl(a, v) memset(a, v, sizeof(a))

int M, z, RangeLength;

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
    inline int base_h0(int x) {
        // return MurmurHash::Hash(x, 114514) % (M - RangeLength + 1);
        return MurmurHash::Hash(x, 114514) % (M - RangeLength / 3 + 1);
    }
    inline int h(int i, int x) {
        int cur = MurmurHash::Hash(x, i) % RangeLength;
        // return base_h0(x) + cur;
        return (base_h0(x) + cur) % M;
    }
    void HashingInit(int znow) {
        z = znow, RangeLength = M / (z + 1);
    }
}