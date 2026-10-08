#include <cstddef>
#include <string>
#include "iblt.h"
#include <algorithm>
#include <limits>
#include <stdexcept>

namespace compact_wire {
struct Writer {
    std::vector<uint8_t> bytes;
    uint64_t bits=0;
    void put(uint64_t value, unsigned width) {
        for (unsigned i=width; i>0; --i) {
            if (!(bits%8)) bytes.push_back(0);
            bytes.back() |= uint8_t(((value>>(i-1))&1)<<(7-bits%8));
            ++bits;
        }
    }
};
struct Reader {
    const std::vector<uint8_t>& bytes;
    uint64_t bits=0;
    uint64_t get(unsigned width) {
        if (bits+width>uint64_t(bytes.size())*8) throw std::runtime_error("truncated compact count wire");
        uint64_t value=0;
        for (unsigned i=0;i<width;++i,++bits)
            value=(value<<1)|((bytes[bits/8]>>(7-bits%8))&1);
        return value;
    }
    void finish() {
        if ((bits+7)/8!=bytes.size()) throw std::runtime_error("trailing compact count bytes");
        if (bits%8 && (bytes.back()&((1U<<(8-bits%8))-1))) throw std::runtime_error("nonzero compact padding");
    }
};
}

// Compact-count-v1: each 128-cell block stores its signed minimum (32 bits),
// offset width (6 bits), then count offsets. Key/checksum widths stay 30/32.
// M, placement and block size are shared protocol parameters, as in baseline.
std::vector<uint8_t> IBLT::serialize_compact(uint64_t* logical_bits) const {
    if (valueSize!=0) throw std::runtime_error("compact set-only wire");
    compact_wire::Writer w;
    w.bytes.reserve((hashTable.size()*87+7)/8);
    for (const auto& e:hashTable) {
        if (e.keySum>=(uint64_t(1)<<30)) throw std::runtime_error("key exceeds 30 bits");
        w.put(e.keySum,30); w.put(e.keyCheck,32);
    }
    for (size_t first=0;first<hashTable.size();first+=128) {
        const size_t end=std::min(first+128,hashTable.size());
        int32_t low=hashTable[first].count, high=low;
        for (size_t i=first+1;i<end;++i) {
            low=std::min(low,hashTable[i].count); high=std::max(high,hashTable[i].count);
        }
        uint64_t span=uint64_t(int64_t(high)-int64_t(low));
        unsigned width=0;
        for (uint64_t s=span;s;s>>=1) ++width;
        w.put(uint32_t(low),32); w.put(width,6);
        for (size_t i=first;i<end;++i) w.put(uint64_t(int64_t(hashTable[i].count)-low),width);
    }
    if (logical_bits) *logical_bits=w.bits;
    return w.bytes;
}

void IBLT::deserialize_compact(const std::vector<uint8_t>& bytes) {
    if (valueSize!=0) throw std::runtime_error("compact set-only wire");
    compact_wire::Reader r{bytes};
    for (auto& e:hashTable) {
        e.keySum=r.get(30); e.keyCheck=uint32_t(r.get(32)); e.valueSum.clear();
    }
    for (size_t first=0;first<hashTable.size();first+=128) {
        uint64_t encoded=r.get(32);
        int64_t low=encoded>=(uint64_t(1)<<31)?int64_t(encoded)-(int64_t(1)<<32):int64_t(encoded);
        unsigned width=unsigned(r.get(6));
        if (width>32) throw std::runtime_error("invalid count width");
        for (size_t i=first;i<std::min(first+128,hashTable.size());++i) {
            int64_t value=low+int64_t(r.get(width));
            if (value<std::numeric_limits<int32_t>::min() || value>std::numeric_limits<int32_t>::max())
                throw std::runtime_error("decoded count overflow");
            hashTable[i].count=int32_t(value);
        }
    }
    r.finish();
}
