#include <bits/stdc++.h>
#include <openssl/sha.h>
#include "src/XYZSketch.h"
using Vec=std::vector<int>;
std::mt19937 tests_rng(739220);
int slowmul(unsigned a,unsigned b){unsigned result=0;while(b){if(b&1)result^=a;b>>=1;bool carry=a&(1U<<29);a=(a<<1)&XYZ_FIELD_MASK;if(carry)a^=3;}return result;}
int slowpow(int a,unsigned e){int r=1;while(e){if(e&1)r=slowmul(r,a);a=slowmul(a,a);e>>=1;}return r;}
Vec norm(Vec v){while(!v.empty()&&!v.back())v.pop_back();return v;}
Vec coeff(const poly& p){return norm(Vec(p.a.begin(),p.a.end()));}
Vec multiply(const Vec& a,const Vec& b,int n=10000){
    if(a.empty()||b.empty())return {};Vec out(std::min(n,int(a.size()+b.size()-1)));
    for(int i=0;i<int(a.size());++i)for(int j=0;j<int(b.size())&&i+j<int(out.size());++j)out[i+j]^=slowmul(a[i],b[j]);return norm(out);
}
void require(bool yes,const char* what){if(!yes)throw std::runtime_error(what);}
Vec randomvec(int n){Vec r(n);for(int&v:r)v=tests_rng()&XYZ_FIELD_MASK;return r;}
std::string hexhash(const std::vector<unsigned char>& data){unsigned char h[32];SHA256(data.data(),data.size(),h);std::ostringstream s;for(unsigned c:h)s<<std::hex<<std::setfill('0')<<std::setw(2)<<c;return s.str();}
int main(){
    int arithmetic=0,reconstructions=0,rootcases=0,sketchcases=0,placement_checks=0;
    for(int t=0;t<200000;++t){std::uint32_t divisor=tests_rng()|1,value=tests_rng();Hashing::ExactU32Remainder mod;mod.Reset(divisor);require(mod(value)==value%divisor,"exact hash remainder/reference");++placement_checks;}
    for(std::uint32_t divisor:{1U,2U,3U,4U,7U,23U,137U,18000U,176000U,1U<<16,(1U<<31)-1,(1U<<31),UINT32_MAX}){
        Hashing::ExactU32Remainder mod;mod.Reset(divisor);
        for(std::uint32_t value:{0U,1U,divisor-1,divisor,divisor+1,UINT32_MAX}){require(mod(value)==value%divisor,"hash remainder boundaries");++placement_checks;}
    }
    // Check placement independently against the original '%' expressions.
    for(int cells:{23,137,18000,176000})for(int mode:{0,1}){
        M=cells;Hashing::SetHashMode(mode?Hashing::NAIVE:Hashing::CIRCULAR);Hashing::SetCircularA(.2);Hashing::HashingInit(3);
        for(double fraction:{0.,.2,.7243668166820519,.99}){
            Hashing::SetCircularA(fraction);
            int support=mode?M-RangeLength+1:std::min(M,M-RangeLength+1+int(std::floor(fraction*RangeLength)));
            for(int t=0;t<1000;++t){int x=1+tests_rng()%XYZ_FIELD_MASK;int anchor=MurmurHash::Hash(x,114514)%support;
                require(base_h0(x)==anchor,"cached anchor/reference");++placement_checks;
                for(int index=1;index<=9;++index){int expected=anchor+MurmurHash::Hash(x,index)%RangeLength;if(!mode)expected%=M;require(Hashing::h(index,x)==expected,"cached placement/reference");++placement_checks;}
            }
        }
    }
    for(int t=0;t<200000;++t){int value=int(tests_rng());std::uint32_t seed=tests_rng();MurmurHash::PreparedInt prepared(value);
        require(prepared.Hash(seed)==MurmurHash::Hash(value,seed),"shared Murmur block/native reference");++placement_checks;
    }
    // Restore the original test RNG state so v2/v3 state transcripts stay comparable.
    tests_rng.seed(739220);
    for(int t=0;t<20000;++t){int a=tests_rng()&XYZ_FIELD_MASK,b=tests_rng()&XYZ_FIELD_MASK;
        require(FieldMultiply(a,b)==slowmul(a,b),"field multiply/reference");
        require(xyz_field.Sqr(a)==slowmul(a,a),"field square/reference");
        if(a){require(FieldMultiply(a,FieldInverse(a))==1,"field inverse");require(FieldInverse(a)==slowpow(a,XYZ_FIELD_SIZE-2),"inverse/reference");}
        arithmetic+=4;
    }
    for(unsigned a:{0U,1U,2U,3U,1U<<29,XYZ_FIELD_MASK})for(unsigned b:{0U,1U,2U,3U,1U<<29,XYZ_FIELD_MASK}){require(FieldMultiply(a,b)==slowmul(a,b),"field boundary");++arithmetic;}
    for(int t=0;t<2500;++t){Vec a=randomvec(t%3==0?25:tests_rng()%10),b=randomvec(1+tests_rng()%13);poly pa(a),pb(b);
        require(coeff(pa*pb)==multiply(a,b),"polynomial product/reference");int n=1+tests_rng()%20;
        require(coeff(tool::TruncatedProduct(pa,pb,n))==multiply(a,b,n),"truncated product");
        auto qr=div(pa,pb);Vec restored=multiply(coeff(qr.first),norm(b));auto rem=coeff(qr.second);restored.resize(std::max(restored.size(),rem.size()));for(int i=0;i<int(rem.size());++i)restored[i]^=rem[i];
        require(norm(restored)==norm(a)&&rem.size()<norm(b).size(),"division identity");
        if(!a.empty()&&a[0])require(multiply(a,coeff(pa.Inv()),a.size())==Vec{1},"series inverse");arithmetic+=4;
    }
    for(int ell:{2,3,4,6,8,12,20})for(int t=0;t<350;++t){
        int na=tests_rng()%(ell+1),nb=tests_rng()%(ell-na+1);std::set<int> used;Vec ra,rb;
        auto fill=[&](Vec& v,int n){while(int(v.size())<n){int x=1+(tests_rng()%XYZ_FIELD_MASK);if(used.insert(x).second)v.push_back(x);}};fill(ra,na);fill(rb,nb);
        Vec f{1},g{1};for(int x:ra)f=multiply(f,Vec{x,1});for(int x:rb)g=multiply(g,Vec{x,1});
        auto truncated=tool::TruncatedProduct(poly(f),poly(g).Rs(ell).Inv(),ell);
        auto reconstruction=tool::RFuncReconstruct(truncated,ell,na-nb);
        require(reconstruction.index()==0,"D-RFR returned failure");auto result=std::get<0>(reconstruction);result.first.monic();result.second.monic();
        require(coeff(result.first)==f&&coeff(result.second)==g,"D-RFR exact signed polynomials");++reconstructions;
    }
    for(int degree:{0,1,2,3,4,6,12})for(int t=0;t<100;++t){
        std::set<int> unique;while(int(unique.size())<degree)unique.insert(1+tests_rng()%XYZ_FIELD_MASK);Vec roots(unique.begin(),unique.end()),f{1};for(int x:roots)f=multiply(f,Vec{x,1});
        auto found=tool::findAllRoots(poly(f));require(found.index()==0&&std::get<0>(found)==roots,"MiniSketch roots");
        // Nonmonic inputs must normalize to the same roots.
        auto scaled=tool::findAllRoots((1+tests_rng()%XYZ_FIELD_MASK)*poly(f));require(scaled.index()==0&&std::get<0>(scaled)==roots,"nonmonic roots");++rootcases;
    }
    require(tool::findAllRoots(plv({0})).index()==1,"zero root input rejected");
    auto repeated=tool::findAllRoots(poly(multiply(Vec{9,1},Vec{9,1})));require(repeated.index()==1,"repeated roots rejected before native solver");
    for(int degree:{3,4,6,12}){Vec f{1};for(int i=0;i<degree;++i)f=multiply(f,Vec{i==degree-1?7:7+13*i,1});
        require(tool::findAllRoots(poly(f)).index()==1,"higher-degree repeated roots rejected");}
    // A derivative that vanishes identically is also outside the native solver's domain.
    require(tool::findAllRoots(plv({9,0,1,0,1})).index()==1,"zero derivative rejected");
    int bad=1U<<29; // This basis element has absolute trace 1 in the native field.
    require(bad!=0&&tool::findAllRoots(plv({bad,1,1})).index()==1,"irreducible quadratic rejected");
    require(tool::findAllRoots(poly(multiply(Vec{bad,1,1},Vec{13,1}))).index()==1,"partially split rejected");
    std::vector<unsigned char> transcript;
    for(int ell:{2,3,4,6,8,12,20})for(int count:{2,3,4,9})for(int mode:{0,1}){
        l=ell;k=count;M=137;Hashing::SetHashMode(mode?Hashing::NAIVE:Hashing::CIRCULAR);Hashing::SetCircularA(.7243668166820519);Hashing::SetDedupHashes(true);Hashing::HashingInit(3);
        XYZSketch a,b;a.init();b.init();std::vector<poly> ref_a(M,plv({1}).Rs(ell)),ref_b=ref_a;
        Vec da,db;
        for(int i=0;i<110;++i){int x=1+tests_rng()%XYZ_FIELD_MASK;bool on_a=i%4!=0,on_b=i%4!=1;
            if(on_a){a.Update(x);for(int cell:HashLocations(x)){Vec expected=multiply(Vec(ref_a[cell].a.begin(),ref_a[cell].a.end()),Vec{x,1},ell);ref_a[cell]=poly(expected).Rs(ell);}}
            if(on_b){b.Update(x);for(int cell:HashLocations(x)){Vec expected=multiply(Vec(ref_b[cell].a.begin(),ref_b[cell].a.end()),Vec{x,1},ell);ref_b[cell]=poly(expected).Rs(ell);}}
            if(on_a&&!on_b)da.push_back(x);if(on_b&&!on_a)db.push_back(x);
        }
        for(int i=0;i<M;++i){require(a[i].p==ref_a[i]&&b[i].p==ref_b[i],"full update states/reference");}
        auto bytes=a.to_bitstring();require(to_sketch(bytes).to_bitstring()==bytes,"wire roundtrip");
        auto residual=a-b;
        for(int i=0;i<M;++i)require(residual[i].p==tool::TruncatedProduct(ref_a[i],ref_b[i].Inv(),ell),"sketch subtraction");
        for(auto& cell:residual.B){transcript.push_back(cell.c);for(int c:cell.p.a)for(int j=0;j<4;++j)transcript.push_back(unsigned(c)>>(8*j));}
        Vis.assign(M,false);Q={};for(int x:da)residual.Extract(x,0);for(int x:db)residual.Extract(x,1);
        for(auto& cell:residual.B)require(!cell.c&&cell.p==plv({1}),"both signed Extract directions");
        if(count<=4&&ell<=8){auto diff=a-b;rng.seed(1138);auto decoded=diff.Decode();require(decoded.index()==0,"full decoding");
            auto answer=std::get<0>(decoded);std::sort(da.begin(),da.end());std::sort(db.begin(),db.end());require(answer.first==da&&answer.second==db,"signed ground truth");}
        ++sketchcases;
    }
    // Equal sets decode successfully to an empty signed difference.
    auto empty=XYZSketch();empty.init();auto decoded=empty.Decode();require(decoded.index()==0&&std::get<0>(decoded).first.empty()&&std::get<0>(decoded).second.empty(),"empty difference");
    std::cout<<"{\"passed\":true,\"backend\":"<<XYZ_GF230_BACKEND<<",\"arithmetic_checks\":"<<arithmetic<<",\"reconstruction_cases\":"<<reconstructions<<",\"root_cases\":"<<rootcases<<",\"placement_checks\":"<<placement_checks<<",\"sketch_cases\":"<<sketchcases<<",\"state_transcript_sha256\":\""<<hexhash(transcript)<<"\"}"<<std::endl;
}
