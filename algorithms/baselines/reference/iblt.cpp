#include <cassert>
#include <algorithm>
#include <limits>
#include <iostream>
#include <list>
#include <sstream>
#include <stdexcept>
#include <utility>
#include "iblt.h"
#include "murmurhash3.h"

static const size_t N_HASH = 4;
static const size_t N_HASHCHECK = 11;
static const size_t WIRE_COUNT_BITS = 25;
static const size_t WIRE_KEY_BITS = 30;
static const size_t WIRE_CHECK_BITS = 32;
static const size_t WIRE_CELL_BITS = WIRE_COUNT_BITS + WIRE_KEY_BITS + WIRE_CHECK_BITS;

template<typename T>
std::vector<uint8_t> ToVec(T number)
{
    std::vector<uint8_t> v(sizeof(T));
    for (size_t i = 0; i < sizeof(T); i++) {
        v.at(i) = (number >> i*8) & 0xff;
    }
    return v;
}


bool IBLT::HashTableEntry::isPure() const
{
    if (count == 1 || count == -1) {
        uint32_t check = MurmurHash3(N_HASHCHECK, ToVec(keySum));
        return (keyCheck == check);
    }
    return false;
}

bool IBLT::HashTableEntry::empty() const
{
    return (count == 0 && keySum == 0 && keyCheck == 0);
}

void IBLT::HashTableEntry::addValue(const std::vector<uint8_t> v)
{
    if (v.empty()) {
        return;
    }
    if (valueSum.size() < v.size()) {
        valueSum.resize(v.size());
    }
    for (size_t i = 0; i < v.size(); i++) {
        valueSum[i] ^= v[i];
    }
}

IBLT::IBLT(size_t _expectedNumEntries, size_t _valueSize) :
    valueSize(_valueSize)
{
    // 1.5x expectedNumEntries gives very low probability of
    // decoding failure
    size_t nEntries = _expectedNumEntries + _expectedNumEntries/2;
    // ... make nEntries exactly divisible by N_HASH
    while (N_HASH * (nEntries/N_HASH) != nEntries) ++nEntries;
    hashTable.resize(nEntries);
}

IBLT::IBLT(const IBLT& other)
{
    standardSC = other.standardSC;
    scK = other.scK;
    scZ = other.scZ;
    scSeed = other.scSeed;
    valueSize = other.valueSize;
    hashTable = other.hashTable;
}


namespace {
uint64_t scNext(uint64_t& state) {
    uint64_t x = (state += UINT64_C(0x9e3779b97f4a7c15));
    x = (x ^ (x >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
    x = (x ^ (x >> 27)) * UINT64_C(0x94d049bb133111eb);
    return x ^ (x >> 31);
}
uint64_t scUniform(uint64_t& state, uint64_t bound) {
    const uint64_t threshold = -bound % bound;
    for (;;) {
        const uint64_t v = scNext(state);
        if (v >= threshold) return v % bound;
    }
}
}

IBLT::IBLT(size_t cells, size_t degree, size_t couplingLength, uint64_t seed)
    : standardSC(true), scK(degree), scZ(couplingLength), scSeed(seed), valueSize(0)
{
    if (!cells || cells > UINT32_MAX || scK < 3 || scK > 7 || !scZ || scZ >= cells)
        throw std::invalid_argument("invalid standard SC configuration");
    hashTable.resize(cells);
}

std::vector<size_t> IBLT::placement(uint64_t key) const
{
    std::vector<size_t> positions;
    if (!standardSC) {
        const auto bytes = ToVec(key);
        const size_t width = hashTable.size() / N_HASH;
        for (size_t i=0; i<N_HASH; ++i)
            positions.push_back(i*width + MurmurHash3(i, bytes)%width);
        return positions;
    }
    // 32-bit fractional coordinates: t in [0,z), u in [0,1).
    // Distinct sorted endpoints preserve the finite XOR-cell convention.
    uint64_t state = scSeed ^ (UINT64_C(0xd6efeb86659fd93) * key);
    const uint64_t scale = UINT64_C(1) << 32;
    const uint64_t anchor = scUniform(state, scZ * scale);
    positions.reserve(scK);
    for (size_t i=0; i<scK; ++i) {
        const uint64_t offset = scUniform(state, scale);
        positions.push_back(static_cast<size_t>(
            (__uint128_t(anchor+offset)*hashTable.size()) / ((scZ+1)*scale)));
    }
    std::sort(positions.begin(), positions.end());
    positions.erase(std::unique(positions.begin(), positions.end()), positions.end());
    return positions;
}

bool IBLT::member(uint64_t key, size_t cell) const
{
    const auto positions = placement(key);
    return std::binary_search(positions.begin(), positions.end(), cell);
}

bool IBLT::same_configuration(const IBLT& other) const
{
    return standardSC == other.standardSC && scK == other.scK && scZ == other.scZ &&
        scSeed == other.scSeed && valueSize == other.valueSize &&
        hashTable.size() == other.hashTable.size();
}

IBLT::~IBLT()
{
}

void IBLT::_insert(int plusOrMinus, uint64_t k, const std::vector<uint8_t> v)
{
    assert(v.size() == valueSize);
    if (standardSC) {
        if (!v.empty()) throw std::invalid_argument("SC requires empty values");
        const uint32_t check = MurmurHash3(N_HASHCHECK, ToVec(k));
        for (const auto index : placement(k)) {
            auto& entry = hashTable.at(index);
            entry.count += plusOrMinus;
            entry.keySum ^= k;
            entry.keyCheck ^= check;
            entry.valueSum.clear();
        }
        return;
    }

    std::vector<uint8_t> kvec = ToVec(k);

    size_t bucketsPerHash = hashTable.size()/N_HASH;
    for (size_t i = 0; i < N_HASH; i++) {
        size_t startEntry = i*bucketsPerHash;

        uint32_t h = MurmurHash3(i, kvec);
        IBLT::HashTableEntry& entry = hashTable.at(startEntry + (h%bucketsPerHash));
        entry.count += plusOrMinus;
        entry.keySum ^= k;
        entry.keyCheck ^= MurmurHash3(N_HASHCHECK, kvec);
        if (entry.empty()) {
            entry.valueSum.clear();
        }
        else {
            entry.addValue(v);
        }
    }
}

void IBLT::insert(uint64_t k, const std::vector<uint8_t> v)
{
    _insert(1, k, v);
}

void IBLT::erase(uint64_t k, const std::vector<uint8_t> v)
{
    _insert(-1, k, v);
}

bool IBLT::get(uint64_t k, std::vector<uint8_t>& result) const
{
    result.clear();
    if (standardSC) {
        std::set<std::pair<uint64_t, std::vector<uint8_t>>> positive, negative;
        return listEntries(positive, negative);
    }

    std::vector<uint8_t> kvec = ToVec(k);

    size_t bucketsPerHash = hashTable.size()/N_HASH;
    for (size_t i = 0; i < N_HASH; i++) {
        size_t startEntry = i*bucketsPerHash;

        uint32_t h = MurmurHash3(i, kvec);
        const IBLT::HashTableEntry& entry = hashTable.at(startEntry + (h%bucketsPerHash));

        if (entry.empty()) {
            // Definitely not in table. Leave
            // result empty, return true.
            return true;
        }
        else if (entry.isPure()) {
            if (entry.keySum == k) {
                // Found!
                result.assign(entry.valueSum.begin(), entry.valueSum.end());
                return true;
            }
            else {
                // Definitely not in table.
                return true;
            }
        }
    }

    // Don't know if k is in table or not; "peel" the IBLT to try to find
    // it:
    IBLT peeled = *this;
    size_t nErased = 0;
    for (size_t i = 0; i < peeled.hashTable.size(); i++) {
        IBLT::HashTableEntry& entry = peeled.hashTable.at(i);
        if (entry.isPure()) {
            if (entry.keySum == k) {
                // Found!
                result.assign(entry.valueSum.begin(), entry.valueSum.end());
                return true;
            }
            ++nErased;
            peeled._insert(-entry.count, entry.keySum, entry.valueSum);
        }
    }
    if (nErased > 0) {
        // Recurse with smaller IBLT
        return peeled.get(k, result);
    }
    return false;
}

bool IBLT::listEntries(std::set<std::pair<uint64_t,std::vector<uint8_t> > >& positive,
                       std::set<std::pair<uint64_t,std::vector<uint8_t> > >& negative) const
{
    IBLT peeled = *this;

    size_t nErased = 0;
    do {
        nErased = 0;
        for (size_t i = 0; i < peeled.hashTable.size(); i++) {
            IBLT::HashTableEntry& entry = peeled.hashTable.at(i);
            if (entry.isPure() && (!peeled.standardSC || peeled.member(entry.keySum, i))) {
                if (entry.count == 1) {
                    positive.insert(std::make_pair(entry.keySum, entry.valueSum));
                }
                else {
                    negative.insert(std::make_pair(entry.keySum, entry.valueSum));
                }
                peeled._insert(-entry.count, entry.keySum, entry.valueSum);
                ++nErased;
            }
        }
    } while (nErased > 0);

    // If any buckets for one of the hash functions is not empty,
    // then we didn't peel them all:
    for (size_t i = 0; i < (peeled.standardSC ? peeled.hashTable.size() : peeled.hashTable.size()/N_HASH); i++) {
        if (peeled.hashTable.at(i).empty() != true) return false;
    }
    return true;
}

IBLT IBLT::operator-(const IBLT& other) const
{
    if ((standardSC || other.standardSC) && !same_configuration(other))
        throw std::invalid_argument("SC subtraction configuration mismatch");
    // IBLT's must be same params/size:
    assert(valueSize == other.valueSize);
    assert(hashTable.size() == other.hashTable.size());

    IBLT result(*this);
    for (size_t i = 0; i < hashTable.size(); i++) {
        IBLT::HashTableEntry& e1 = result.hashTable.at(i);
        const IBLT::HashTableEntry& e2 = other.hashTable.at(i);
        e1.count -= e2.count;
        e1.keySum ^= e2.keySum;
        e1.keyCheck ^= e2.keyCheck;
        if (e1.empty()) {
            e1.valueSum.clear();
        }
        else {
            e1.addValue(e2.valueSum);
        }
    }

    return result;
}

size_t IBLT::cell_count() const
{
    return hashTable.size();
}

std::vector<uint8_t> IBLT::serialize_canonical() const
{
    if (valueSize != 0) throw std::runtime_error("canonical experiment wire requires valueSize=0");
    std::vector<uint8_t> output;
    output.reserve((hashTable.size() * WIRE_CELL_BITS + 7) / 8);
    size_t bitOffset = 0;
    const auto append = [&output, &bitOffset](uint64_t value, size_t width) {
        for (size_t index = 0; index < width; ++index) {
            if (bitOffset % 8 == 0) output.push_back(0);
            const size_t shift = width - index - 1;
            if ((value >> shift) & 1U) {
                output.back() |= static_cast<uint8_t>(1U << (7U - bitOffset % 8U));
            }
            ++bitOffset;
        }
    };
    for (const HashTableEntry& entry : hashTable) {
        if (entry.count < -(1 << 24) || entry.count >= (1 << 24)) {
            throw std::runtime_error("IBLT count exceeds 25-bit wire range");
        }
        if (entry.keySum >= (uint64_t(1) << WIRE_KEY_BITS)) {
            throw std::runtime_error("IBLT key sum exceeds 30-bit wire range");
        }
        append(static_cast<uint32_t>(entry.count) & ((uint32_t(1) << WIRE_COUNT_BITS) - 1U),
               WIRE_COUNT_BITS);
        append(entry.keySum, WIRE_KEY_BITS);
        append(entry.keyCheck, WIRE_CHECK_BITS);
    }
    return output;
}

void IBLT::deserialize_canonical(const std::vector<uint8_t>& bytes)
{
    const size_t logicalBits = hashTable.size() * WIRE_CELL_BITS;
    if (valueSize != 0 || bytes.size() != (logicalBits + 7) / 8) {
        throw std::runtime_error("canonical IBLT wire size/parameter mismatch");
    }
    size_t bitOffset = 0;
    const auto read = [&bytes, &bitOffset](size_t width) {
        uint64_t value = 0;
        for (size_t index = 0; index < width; ++index) {
            value = (value << 1U) |
                ((bytes[bitOffset / 8U] >> (7U - bitOffset % 8U)) & 1U);
            ++bitOffset;
        }
        return value;
    };
    for (size_t index = 0; index < hashTable.size(); ++index) {
        HashTableEntry& entry = hashTable[index];
        uint32_t encodedCount = static_cast<uint32_t>(read(WIRE_COUNT_BITS));
        entry.count = static_cast<int32_t>(encodedCount);
        if (encodedCount & (uint32_t(1) << (WIRE_COUNT_BITS - 1))) {
            entry.count -= static_cast<int32_t>(uint32_t(1) << WIRE_COUNT_BITS);
        }
        entry.keySum = read(WIRE_KEY_BITS);
        entry.keyCheck = static_cast<uint32_t>(read(WIRE_CHECK_BITS));
        entry.valueSum.clear();
    }
    if (logicalBits % 8U && (bytes.back() & ((1U << (8U - logicalBits % 8U)) - 1U))) {
        throw std::runtime_error("canonical IBLT wire has nonzero padding");
    }
}

// For debugging during development:
std::string IBLT::DumpTable() const
{
    std::ostringstream result;

    result << "count keySum keyCheckMatch\n";
    for (size_t i = 0; i < hashTable.size(); i++) {
        const IBLT::HashTableEntry& entry = hashTable.at(i);
        result << entry.count << " " << entry.keySum << " ";
        result << (MurmurHash3(N_HASHCHECK, ToVec(entry.keySum)) == entry.keyCheck ? "true" : "false");
        result << "\n";
    }

    return result.str();
}
