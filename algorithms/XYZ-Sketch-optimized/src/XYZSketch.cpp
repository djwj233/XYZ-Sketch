#include <bits/stdc++.h>
#include "gf230_poly.hpp"
#include "hash.cpp"
using namespace std;
#define fo(v, a, b) for(int v = a; v <= b; v++)
#define fr(v, a, b) for(int v = a; v >= b; v--)
#define cl(a, v) memset(a, v, sizeof(a))

using namespace Hashing;
#define XYZ_OPT_LOCATIONS 1
#define XYZ_OPT_VERIFY 1
#ifndef XYZ_BATCH_INVERSE
#define XYZ_BATCH_INVERSE 1
#endif
#ifndef XYZ_SHORT_CELLS
#define XYZ_SHORT_CELLS 1
#endif

int k, l, d;
queue<int> Q; vector<bool> Vis;
constexpr int FIELD_COEFFICIENT_BITS = 30;
static_assert(XYZ_FIELD_SIZE==(1U<<FIELD_COEFFICIENT_BITS));

struct Cell {
    char c; poly p;
    Cell() {  c = 0, p = plv({1});  }
} ;

#if XYZ_OPT_LOCATIONS
struct SmallLocations {
    std::array<int,8> small{};std::vector<int> large;int count=0;
    int* begin(){return count>8?large.data():small.data();}
    int* end(){return begin()+count;}
};
inline SmallLocations HashLocations(int x) {
    SmallLocations positions;positions.count=k;if(k>8)positions.large.resize(k);
    int* values=positions.begin();MurmurHash::PreparedInt prepared(x);int anchor=base_h0(prepared);
    for(int i=1;i<=k;++i){int cur=PlacementOffset(prepared,i);
        values[i-1]=JoinLocation(anchor,cur);}
    if(GetDedupHashes()){
        if(k==2){if(values[1]<values[0])std::swap(values[0],values[1]);if(values[0]==values[1])positions.count=1;}
        else {std::sort(values,values+k);positions.count=std::unique(values,values+k)-values;
            // A >8 input may deduplicate below 8; move the result back to its inline buffer.
            if(k>8 && positions.count<=8)std::copy(values,values+positions.count,positions.small.begin());}
    }return positions;
}
#else
inline vector<int> HashLocations(int x) {
    vector<int> positions;
    positions.reserve(k);
    fo(i, 1, k) positions.push_back(h(i, x));
    if(GetDedupHashes()) {
        sort(positions.begin(), positions.end());
        positions.erase(unique(positions.begin(), positions.end()), positions.end());
    }
    return positions;
}

#endif

poly PolynomialFromRoots(const vector<int>& roots) {
    poly result=plv({1});
    for(int x:roots){int n=result.size();result.rs(n+1);result[n]=result[n-1];
        XYZMultiplier m(xyz_field,x);for(int j=n-1;j>=1;--j)result[j]=m(result[j])^result[j-1];result[0]=m(result[0]);}
    result.PopZero();return result;
}

bool HasDuplicateRoots(const vector<int>& roots) {
    return adjacent_find(roots.begin(), roots.end()) != roots.end();
}

struct XYZSketch {
    vector<Cell> B;
    // int queryMemory() {  return B.size() * (sizeof(char) + B[0].p.size() * sizeof(int));  }
    int size() {  return B.size();  }
    void init() {  B.resize(M); fo(i, 0, M - 1) B[i].p.rs(l);  }
    Cell & operator [] (int x) { return B[x]; }
    friend XYZSketch operator-(const XYZSketch& a,const XYZSketch& b){
        XYZSketch result;result.init();
#if XYZ_BATCH_INVERSE
        // Montgomery batch inversion. Zero inputs retain FieldInverse(0)==0;
        // all nonzero inverses are exactly the same as independent inversion.
        std::vector<int> inverses(M);int product=1;
        for(int i=0;i<M;++i){inverses[i]=product;int x=b.B[i].p[0];if(x)product=FieldMultiply(product,x);}
        int inverse_product=FieldInverse(product);
        for(int i=M-1;i>=0;--i){int x=b.B[i].p[0];
            if(x){int prefix=inverses[i];inverses[i]=FieldMultiply(prefix,inverse_product);inverse_product=FieldMultiply(inverse_product,x);}
            else inverses[i]=0;
        }
#endif
        for(int i=0;i<M;++i){result[i].c=(a.B[i].c-b.B[i].c+2*l+1)%(2*l+1);
            const poly& numerator=a.B[i].p;const poly& denominator=b.B[i].p;
#if XYZ_BATCH_INVERSE
            int inverse=inverses[i];
#else
            int inverse=FieldInverse(denominator[0]);
#endif
            for(int j=0;j<l;++j){int sum=0;for(int t=1;t<=j&&t<denominator.size();++t)sum^=FieldMultiply(denominator[t],result[i].p[j-t]);
                result[i].p[j]=FieldMultiply(numerator.v(j)^sum,inverse);}}
        return result;
    }

#if XYZ_GF230_BACKEND != 0
    struct PairedUpdateMultiplier {
        __m128i value;
        explicit PairedUpdateMultiplier(int x):value(_mm_cvtsi32_si128(x)){}
        inline __m128i Pair(__m128i coefficients)const {
            // Two native-basis carryless products; reduce both 64-bit lanes
            // together using x^30 = x+1. This changes scheduling, not the field.
            const __m128i mask=_mm_set1_epi64x(XYZ_FIELD_MASK);
            __m128i lanes=_mm_unpacklo_epi32(coefficients,_mm_setzero_si128());
            __m128i first=_mm_clmulepi64_si128(value,lanes,0);
            __m128i second=_mm_clmulepi64_si128(value,lanes,0x10);
            __m128i products=_mm_unpacklo_epi64(first,second);
            __m128i high=_mm_srli_epi64(products,30);
            __m128i reduced=_mm_and_si128(_mm_xor_si128(products,_mm_xor_si128(high,_mm_slli_epi64(high,1))),mask);
            return _mm_shuffle_epi32(reduced,_MM_SHUFFLE(2,0,2,0));
        }
    };
    template<int Capacity>inline void InsertPaired(int i,const PairedUpdateMultiplier& multiply,int x){
        B[i].c++;if(B[i].c==2*l+1)B[i].c=0;int* coefficients=B[i].p.a.data();
        if constexpr(Capacity%2)coefficients[Capacity-1]=FieldMultiply(x,coefficients[Capacity-1])^coefficients[Capacity-2];
        for(int begin=(Capacity/2-1)*2;begin>=0;begin-=2){
            __m128i old=_mm_loadl_epi64(reinterpret_cast<const __m128i*>(coefficients+begin));
            __m128i previous=begin?_mm_loadl_epi64(reinterpret_cast<const __m128i*>(coefficients+begin-1)):_mm_slli_si128(old,4);
            _mm_storel_epi64(reinterpret_cast<__m128i*>(coefficients+begin),_mm_xor_si128(multiply.Pair(old),previous));
        }
    }
#endif
    template<int Capacity>inline void InsertSized(int i,const XYZMultiplier& multiply){
        B[i].c++;if(B[i].c==2*l+1)B[i].c=0;
        for(int j=Capacity-1;j>=1;--j)B[i].p[j]=multiply(B[i].p[j])^B[i].p[j-1];B[i].p[0]=multiply(B[i].p[0]);
    }
    template<int Capacity>inline void InsertTwoCells(int first,int second,int x){
#if XYZ_GF230_BACKEND != 0
        PairedUpdateMultiplier multiply(x);InsertPaired<Capacity>(first,multiply,x);
        if(second>=0)InsertPaired<Capacity>(second,multiply,x);
#else
        XYZMultiplier multiply(xyz_field,x);InsertSized<Capacity>(first,multiply);
        if(second>=0)InsertSized<Capacity>(second,multiply);
#endif
    }
    inline void Update(int x){
        // The common two-hash case needs no temporary location container.
        // Keep the same sorting and duplicate suppression as HashLocations.
        if(k==2){
            MurmurHash::PreparedInt prepared(x);int anchor=base_h0(prepared);int first=JoinLocation(anchor,PlacementOffset(prepared,1));
            int second=JoinLocation(anchor,PlacementOffset(prepared,2));
            if(GetDedupHashes()){if(second<first)std::swap(first,second);if(second==first)second=-1;}
            switch(l){
                case 2:InsertTwoCells<2>(first,second,x);return;case 3:InsertTwoCells<3>(first,second,x);return;
                case 4:InsertTwoCells<4>(first,second,x);return;case 6:InsertTwoCells<6>(first,second,x);return;
                case 8:InsertTwoCells<8>(first,second,x);return;
            }
        }
        XYZMultiplier multiply(xyz_field,x);
#if XYZ_GF230_BACKEND != 0
        PairedUpdateMultiplier paired(x);
#endif
        for(int i:HashLocations(x))switch(l){
#if XYZ_GF230_BACKEND != 0
            case 2:InsertPaired<2>(i,paired,x);break;case 3:InsertPaired<3>(i,paired,x);break;
            case 4:InsertPaired<4>(i,paired,x);break;case 6:InsertPaired<6>(i,paired,x);break;case 8:InsertPaired<8>(i,paired,x);break;
#else
            case 2:InsertSized<2>(i,multiply);break;case 3:InsertSized<3>(i,multiply);break;
            case 4:InsertSized<4>(i,multiply);break;case 6:InsertSized<6>(i,multiply);break;
#endif
            default:B[i].c++;if(B[i].c==2*l+1)B[i].c=0;
                for(int j=l-1;j>=1;--j)B[i].p[j]=multiply(B[i].p[j])^B[i].p[j-1];B[i].p[0]=multiply(B[i].p[0]);
        }
    }

    // pair<vector<int>, vector<int> > PureCellDecode(int i) {
    //     int m = B[i].c; if(m > l) m -= 2 * l + 1;
    //     auto ChiRes = tool :: RFuncReconstruct(B[i].p, l, m);
    //     if(ChiRes.index() == 1) assert(0);
    //     auto Chi = std::move(get<pair<poly, poly> >(ChiRes));
    //     auto DeltaA = tool :: findRoots(Chi.first), DeltaB = tool :: findRoots(Chi.second);
    //     sort(DeltaA.begin(), DeltaA.end()), sort(DeltaB.begin(), DeltaB.end());
    //     return make_pair(DeltaA, DeltaB);
    // }
    variant<bool, pair<vector<int>, vector<int> > > PureCellVerifyReference(int i) {
        int m = B[i].c; if(m > l) m -= 2 * l + 1;
        auto ChiRes = tool :: RFuncReconstruct(B[i].p, l, m);
        if(ChiRes.index() == 1) return false;
        auto Chi = std::move(get<pair<poly, poly> >(ChiRes));
        Chi.first.PopZero(), Chi.second.PopZero();
        if(Chi.first.a.empty() || Chi.second.a.empty()) return false;
        if(Chi.first.a.back() != Chi.second.a.back()) return false;
        Chi.first.monic(), Chi.second.monic();
        auto DA = tool :: findAllRoots(Chi.first), DB = tool :: findAllRoots(Chi.second);
        if(DA.index() == 1 || DB.index() == 1) return false;
        auto DeltaA = std::move(get<vi>(DA)), DeltaB = std::move(get<vi>(DB));

        sort(DeltaA.begin(), DeltaA.end());
        sort(DeltaB.begin(), DeltaB.end());
        if(HasDuplicateRoots(DeltaA) || HasDuplicateRoots(DeltaB)) return false;
        if((int)DeltaA.size() + (int)DeltaB.size() > l) return false;
        if((int)DeltaA.size() - (int)DeltaB.size() != m) return false;
        if(!(PolynomialFromRoots(DeltaA) == Chi.first)) return false;
        if(!(PolynomialFromRoots(DeltaB) == Chi.second)) return false;

        for(const auto* t : {&DeltaA, &DeltaB}) for(int x : *t) {
            bool fl = false;
#if XYZ_OPT_VERIFY
            // Membership is unchanged by sorting or deduplicating locations.
            MurmurHash::PreparedInt prepared(x);int anchor=base_h0(prepared);
            for(int index=1;index<=k;++index){
                int offset=PlacementOffset(prepared,index);
                int pos=JoinLocation(anchor,offset);
                if(pos==i){fl=true;break;}
            }
#else
            for(int pos : HashLocations(x)) if(pos == i) { fl = true; break; }
#endif
            if(!fl) return false;
        }
        return make_pair(DeltaA, DeltaB);
    }
    variant<bool, pair<vector<int>, vector<int> > > PureCellVerifyV10(int i) {
        int m=B[i].c;if(m>l)m-=2*l+1;
        auto reconstruction=tool::RFuncReconstruct(B[i].p,l,m);
        if(reconstruction.index()==1)return false;
        auto Chi=std::move(get<pair<poly,poly>>(reconstruction));
        Chi.first.PopZero();Chi.second.PopZero();
        if(Chi.first.a.empty()||Chi.second.a.empty())return false;
        if(Chi.first.a.back()!=Chi.second.a.back())return false;
        // Complete root recovery has exactly the polynomial's degree. Reject
        // degree/count violations before spending time on either root search.
        int degree_a=Chi.first.size()-1,degree_b=Chi.second.size()-1;
        if(degree_a+degree_b>l||degree_a-degree_b!=m)return false;
        Chi.first.monic();Chi.second.monic();
        auto recover_and_validate=[&](const poly& target,vector<int>& output){
            auto found=tool::findAllRoots(target);
            if(found.index()==1)return false;
            output=std::move(get<vi>(found));
            // findAllRoots returns sorted roots on every successful path.
            if(HasDuplicateRoots(output))return false;
            if(!(PolynomialFromRoots(output)==target))return false;
            for(int x:output){
                bool found_location=false;
                MurmurHash::PreparedInt prepared(x);int anchor=base_h0(prepared);
                for(int index=1;index<=k;++index){
                    int pos=JoinLocation(anchor,PlacementOffset(prepared,index));
                    if(pos==i){found_location=true;break;}
                }
                if(!found_location)return false;
            }
            return true;
        };
        vector<int> DeltaA,DeltaB;
        // All original polynomial and membership checks remain. Finish one
        // side before attempting the other; rejected cells need no more roots.
        if(!recover_and_validate(Chi.first,DeltaA))return false;
        if(!recover_and_validate(Chi.second,DeltaB))return false;
        return make_pair(std::move(DeltaA),std::move(DeltaB));
    }
    using CellCandidate=variant<bool,pair<vi,vi>>;
    bool PermittedCell(int i,int x) const {
        MurmurHash::PreparedInt prepared(x);int anchor=base_h0(prepared);
        for(int index=1;index<=k;++index)if(JoinLocation(anchor,PlacementOffset(prepared,index))==i)return true;
        return false;
    }
    // Recognize complete truncated-series signatures, not merely the count.
    // A hit solves the same normalized rational function as D-RFR; a miss
    // falls back to the unchanged v10 verifier. All membership checks remain.
    bool TryShortCell(int i,int m,CellCandidate& candidate) {
        const poly& a=B[i].p;
        if(l<2||l>8||!a.v(0))return false;
        if(m==0&&a.v(0)==1){
            bool empty=true;for(int j=1;j<l;++j)if(a.v(j)){empty=false;break;}
            if(empty){candidate=make_pair(vi{},vi{});return true;}
        }
        if(m==1&&a.v(1)==1){
            bool linear=true;for(int j=2;j<l;++j)if(a.v(j)){linear=false;break;}
            if(linear){int x=a.v(0);(void)rng();(void)rng();
                if(PermittedCell(i,x))candidate=make_pair(vi{x},vi{});else candidate=false;
                return true;
            }
        }
        if(m==-1&&a.v(1)==xyz_field.Sqr(a.v(0))){
            int previous=a.v(1);XYZMultiplier multiply(xyz_field,a.v(0));bool geometric=true;
            for(int j=2;j<l;++j){previous=multiply(previous);if(a.v(j)!=previous){geometric=false;break;}}
            if(geometric){int x=FieldInverse(a.v(0));(void)rng();(void)rng();
                if(PermittedCell(i,x))candidate=make_pair(vi{},vi{x});else candidate=false;
                return true;
            }
        }
        if(m==0&&a.v(0)!=1&&a.v(1)){
            // (Z+x)/(Z+y): a1=(a0+1)/y and later coefficients
            // form a geometric progression with ratio 1/y.
            int delta=a.v(0)^1;
            XYZMultiplier left(xyz_field,delta),right(xyz_field,a.v(1));bool geometric=true;
            for(int j=2;j<l;++j)if(left(a.v(j))!=right(a.v(j-1))){geometric=false;break;}
            if(geometric){int y=FieldMultiply(delta,FieldInverse(a.v(1))),x=FieldMultiply(a.v(0),y);
                (void)rng();(void)rng();
                if(!PermittedCell(i,x)){candidate=false;return true;}
                (void)rng();(void)rng();
                if(!PermittedCell(i,y)){candidate=false;return true;}
                candidate=make_pair(vi{x},vi{y});return true;
            }
        }
        return false;
    }
    CellCandidate PureCellVerify(int i) {
#if XYZ_SHORT_CELLS
        int m=B[i].c;if(m>l)m-=2*l+1;CellCandidate short_result;
        if(TryShortCell(i,m,short_result))return short_result;
#endif
        return PureCellVerifyV10(i);
    }
    void Extract(int x,int type){
        XYZMultiplier multiply(xyz_field,type==0?FieldInverse(x):x);
        for(int i:HashLocations(x)){
            if(type==0){B[i].c=B[i].c?B[i].c-1:2*l;int previous=0;
                for(int j=0;j<l;++j){previous=B[i].p[j]=multiply(previous^B[i].p[j]);}}
            else{if(++B[i].c==2*l+1)B[i].c=0;
                for(int j=l-1;j>=1;--j)B[i].p[j]=multiply(B[i].p[j])^B[i].p[j-1];B[i].p[0]=multiply(B[i].p[0]);}
            if(!Vis[i])Vis[i]=true,Q.push(i);
        }
    }

    variant<pair<vi, vi>, bool> Decode(bool sorted_output=true) {
        while(Q.size()) Q.pop();
        Vis.clear(), Vis.resize(M, false);
        vector<int> SA, SB;
        fo(i, 0, M - 1) Vis[i] = true, Q.push(i);
        while(Q.size()) {
            int i = Q.front(); Q.pop();
            auto res = PureCellVerify(i);
            if(res.index() == 0) {  Vis[i] = false; continue; }
            auto [da, db] = std::move(get<pair<vi, vi>>(res));
            // printf("i = %d\n", i);
            // print(da), print(db);
            // if(da.empty() && db.empty()) continue;
            for(int x : da) Extract(x, 0), SA.push_back(x);
            for(int x : db) Extract(x, 1), SB.push_back(x);
        }
        fo(i, 0, M - 1) {
            B[i].p.PopZero();
            if(B[i].c != 0 || !(B[i].p == plv({1}))) return false;
        }
        if(sorted_output){sort(SA.begin(), SA.end());sort(SB.begin(), SB.end());}
        return make_pair(SA, SB);
    }
    vector<bool> to_bitstring() {
        vector<bool> res;
        fo(id, 0, M - 1) {
            B[id].p.rs(l);
            fo(j, 0, __lg(2 * l + 1))
                res.push_back(B[id].c >> j & 1);
            fo(i, 0, l - 1) {
                int coefficient=B[id].p[i];
                fo(j, 0, FIELD_COEFFICIENT_BITS - 1)
                    res.push_back(coefficient >> j & 1);
            }
        }
        return res;
    }
} ;

XYZSketch Encode(vector<int> v) {
    XYZSketch res; res.init();
    for(int x : v) res.Update(x);
    return res;
}
XYZSketch to_sketch(vector<bool> S) {
    XYZSketch res; int pos = 0;
    res.B.resize(M); fo(i, 0, M - 1) res.B[i].p = vector<int>(l, 0);
    fo(id, 0, M - 1) {
        fo(j, 0, __lg(2 * l + 1))
            res.B[id].c |= ((int)S[pos + j]) << j;
        pos += __lg(2 * l + 1) + 1;
        fo(i, 0, l - 1) {
            fo(j, 0, FIELD_COEFFICIENT_BITS - 1)
                res.B[id].p[i] |= ((int)S[pos + j]) << j;
            pos += FIELD_COEFFICIENT_BITS;
        }
    }
    return res;
}
