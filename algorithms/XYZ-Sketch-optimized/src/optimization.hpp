#pragma once
#ifndef XYZ_OPT_POLY
#define XYZ_OPT_POLY 1
#endif
#ifndef XYZ_OPT_ROOTS
#define XYZ_OPT_ROOTS 1
#endif
#ifndef XYZ_OPT_QUADRATIC
#define XYZ_OPT_QUADRATIC 1
#endif
#ifndef XYZ_OPT_SMALL
#define XYZ_OPT_SMALL 1
#endif
#ifndef XYZ_OPT_EXTRACT
#define XYZ_OPT_EXTRACT 1
#endif
#ifndef XYZ_OPT_LOCATIONS
#define XYZ_OPT_LOCATIONS 1
#endif
#ifndef XYZ_OPT_FIXED
#define XYZ_OPT_FIXED 1
#endif
#ifndef XYZ_OPT_WIRE
#define XYZ_OPT_WIRE 1
#endif
#ifndef XYZ_OPT_SIMD
#define XYZ_OPT_SIMD 0
#endif

#ifndef XYZ_OPT_FACTORY
#define XYZ_OPT_FACTORY 1
#endif
#ifndef XYZ_OPT_QUOTIENT
#define XYZ_OPT_QUOTIENT 1
#endif
#ifndef XYZ_OPT_VERIFY
#define XYZ_OPT_VERIFY 1
#endif
#ifndef XYZ_OPT_SPLIT
#define XYZ_OPT_SPLIT 1
#endif
#ifndef XYZ_SMALL_CAPACITY
#define XYZ_SMALL_CAPACITY 16
#endif
// A genuine small buffer with unbounded vector fallback: no polynomial degree
// limit is introduced. Only newly exposed slots are zero-filled, like vector.
class SmallCoefficients {
    static constexpr size_t Capacity=XYZ_SMALL_CAPACITY;
    std::array<int,Capacity> small_;
    std::vector<int> large_;
    size_t n_=0;
public:
    SmallCoefficients()=default;
    explicit SmallCoefficients(size_t n){resize(n);}
    SmallCoefficients(const SmallCoefficients& x){resize(x.n_);std::copy(x.begin(),x.end(),begin());}
    SmallCoefficients(SmallCoefficients&& x) noexcept:n_(x.n_){
        if(n_>Capacity)large_=std::move(x.large_);else std::copy(x.begin(),x.end(),small_.begin());x.n_=0;
    }
    SmallCoefficients& operator=(const SmallCoefficients& x){
        if(this!=&x){resize(x.n_);std::copy(x.begin(),x.end(),begin());}return *this;
    }
    SmallCoefficients& operator=(SmallCoefficients&& x) noexcept {
        if(this!=&x){n_=x.n_;if(n_>Capacity)large_=std::move(x.large_);else std::copy(x.begin(),x.end(),small_.begin());x.n_=0;}return *this;
    }
    SmallCoefficients& operator=(const std::vector<int>& x){resize(x.size());std::copy(x.begin(),x.end(),begin());return *this;}
    operator std::vector<int>()const{return std::vector<int>(begin(),end());}
    size_t size()const{return n_;}bool empty()const{return n_==0;}
    int* data(){return n_>Capacity?large_.data():small_.data();}
    const int* data()const{return n_>Capacity?large_.data():small_.data();}
    int* begin(){return data();}int* end(){return data()+n_;}
    const int* begin()const{return data();}const int* end()const{return data()+n_;}
    int& operator[](size_t i){return data()[i];}const int& operator[](size_t i)const{return data()[i];}
    int& back(){return data()[n_-1];}const int& back()const{return data()[n_-1];}
    void resize(size_t n){
        if(n>Capacity){
            if(n_<=Capacity){large_.resize(n);std::copy(small_.begin(),small_.begin()+n_,large_.begin());std::fill(large_.begin()+n_,large_.end(),0);}
            else large_.resize(n);
        }else{
            if(n_>Capacity)std::copy(large_.begin(),large_.begin()+std::min(n,n_),small_.begin());
            else if(n>n_)std::fill(small_.begin()+n_,small_.begin()+n,0);
        }
        n_=n;
    }
    void pop_back(){resize(n_-1);}void push_back(int x){resize(n_+1);back()=x;}
    void clear(){n_=0;}
};
#ifndef XYZ_OPT_REDUCTION
#define XYZ_OPT_REDUCTION 0
#endif
inline unsigned ModularReduce64(unsigned long long x){
    constexpr unsigned long long modulus=998244353ULL;
    constexpr unsigned long long reciprocal=(__uint128_t(1)<<64)/modulus;
    unsigned long long q=(__uint128_t(x)*reciprocal)>>64;
    unsigned long long r=x-q*modulus;
    return r>=modulus?r-modulus:r;
}
#if XYZ_OPT_SIMD
#include <immintrin.h>
inline void CombineCoefficients(const int* a,int na,const int* b,int nb,int* out,int n,bool subtract){
#if defined(__AVX512F__)
    for(int i=0;i<n;i+=16){
        auto mask=[](int c){return __mmask16(c>=16?65535U:c<=0?0U:(1U<<c)-1);};
        __m512i av=_mm512_maskz_loadu_epi32(mask(na-i),a+std::min(i,na)),bv=_mm512_maskz_loadu_epi32(mask(nb-i),b+std::min(i,nb));
        __m512i v=subtract?_mm512_sub_epi32(av,bv):_mm512_add_epi32(av,bv),p=_mm512_set1_epi32(998244353);
        if(subtract)v=_mm512_mask_add_epi32(v,_mm512_cmplt_epi32_mask(v,_mm512_setzero_si512()),v,p);
        else v=_mm512_mask_sub_epi32(v,_mm512_cmpge_epi32_mask(v,p),v,p);
        _mm512_mask_storeu_epi32(out+i,mask(n-i),v);
    }
#elif defined(__AVX2__)
    for(int i=0;i<n;i+=8){
        __m256i index=_mm256_setr_epi32(0,1,2,3,4,5,6,7);
        __m256i av=_mm256_maskload_epi32(a+std::min(i,na),_mm256_cmpgt_epi32(_mm256_set1_epi32(na-i),index));
        __m256i bv=_mm256_maskload_epi32(b+std::min(i,nb),_mm256_cmpgt_epi32(_mm256_set1_epi32(nb-i),index));
        __m256i v=subtract?_mm256_sub_epi32(av,bv):_mm256_add_epi32(av,bv),p=_mm256_set1_epi32(998244353);
        if(subtract)v=_mm256_add_epi32(v,_mm256_and_si256(p,_mm256_cmpgt_epi32(_mm256_setzero_si256(),v)));
        else v=_mm256_sub_epi32(v,_mm256_and_si256(p,_mm256_cmpgt_epi32(v,_mm256_set1_epi32(998244352))));
        _mm256_maskstore_epi32(out+i,_mm256_cmpgt_epi32(_mm256_set1_epi32(n-i),index),v);
    }
#else
    for(int i=0;i<n;++i){int av=i<na?a[i]:0,bv=i<nb?b[i]:0;
        int v=subtract?av-bv:av+bv;if(subtract){if(v<0)v+=998244353;}else if(v>=998244353)v-=998244353;out[i]=v;}
#endif
}
#endif
