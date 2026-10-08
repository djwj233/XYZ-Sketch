#include <cstddef>
#include <string>
#include "iblt.h"
#include <iostream>
#include <random>
#include <stdexcept>
#include <functional>
struct W{std::vector<uint8_t>b;size_t n=0;void put(uint64_t v,unsigned w){for(unsigned i=w;i>0;--i){if(n%8==0)b.push_back(0);b.back()|=((v>>(i-1))&1)<<(7-n%8);++n;}}};
void check(bool b){if(!b)throw std::runtime_error("test failed");}
int main(){try{
 std::mt19937_64 rng(20261006);size_t cases=0;
 for(size_t cells:{size_t(4),size_t(127),size_t(128),size_t(129),size_t(257),size_t(1000)}){
  for(unsigned trial=0;trial<80;++trial){
   W w;for(size_t i=0;i<cells;++i){
    int32_t count=trial==0?0:trial==1?-1:trial==2?(1<<24)-1:trial==3?-(1<<24):int32_t(rng()%(1<<25))-(1<<24);
    w.put(uint32_t(count)&((1U<<25)-1),25);w.put(rng()%998244353,30);w.put(uint32_t(rng()),32);
   }
   IBLT a(cells,3,1,17),b(cells,3,1,17);a.deserialize_canonical(w.b);uint64_t bits;
   auto compact=a.serialize_compact(&bits);check(compact.size()==(bits+7)/8);
   b.deserialize_compact(compact);check(b.serialize_canonical()==w.b);check(b.serialize_compact()==compact);
   for(int malformed=0;malformed<2;++malformed){auto bad=compact;if(malformed==0)bad.pop_back();else bad.push_back(0);bool caught=false;
    try{b.deserialize_compact(bad);}catch(const std::exception&){caught=true;}check(caught);}
   if(bits%8){auto bad=compact;bad.back()|=1;bool caught=false;try{b.deserialize_compact(bad);}catch(const std::exception&){caught=true;}check(caught);}
   ++cases;
  }
 }
 // Counts spanning all of int32_t, including 32-bit offset width.
 for(int mode=0;mode<2;++mode){
   W w;for(int i=0;i<4;++i){w.put(0,30);w.put(0,32);}w.put(0x80000000U,32);w.put(32,6);
   for(uint64_t x:{0ULL,0xffffffffULL,0x80000000ULL,0x7fffffffULL})w.put(x,32);
   IBLT a(4,3,1,17),b(4,3,1,17);a.deserialize_compact(w.b);auto compact=a.serialize_compact();b.deserialize_compact(compact);check(b.serialize_compact()==compact);
 }
 // Real signed set reconciliation, both placements.
 for(int sc=0;sc<2;++sc){IBLT a=sc?IBLT(400,3,4,123):IBLT(300,0),b=a;
  for(uint64_t x=1;x<=120;++x)a.insert(x,{});for(uint64_t x=51;x<=150;++x)b.insert(x,{});
  IBLT c=a;c.deserialize_compact(a.serialize_compact());auto old=a-b,now=c-b;
  check(old.serialize_canonical()==now.serialize_canonical());
  std::set<std::pair<uint64_t,std::vector<uint8_t>>> ap,an,bp,bn;
  check(old.listEntries(ap,an)==now.listEntries(bp,bn));check(ap==bp&&an==bn);check(ap.size()==50&&an.size()==30);
 }
 std::cout<<"PASS "<<cases<<" random/boundary snapshots, malformed inputs, full int32 range, signed peeling for both placements\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
