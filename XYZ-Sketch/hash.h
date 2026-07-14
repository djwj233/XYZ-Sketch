#ifndef HASH_H
#define HASH_H

#include <cstdint>
#include "murmur3.h"

extern int M, z, RangeLength;

namespace MurmurHash {
    std::uint32_t Hash(const int& data, std::uint32_t seed);
}

namespace Hashing {
    enum HashMode {
        CIRCULAR = 0,
        NAIVE = 1
    };
    void SetHashMode(HashMode mode);
    HashMode GetHashMode();
    void SetCircularA(double value);
    double GetCircularA();
    void SetDedupHashes(bool enabled);
    bool GetDedupHashes();
    int NaiveBaseRange();
    int CircularBaseRange();
    int base_h0(int x);
    int h(int i, int x);
    void HashingInit(int znow);
}

#endif
