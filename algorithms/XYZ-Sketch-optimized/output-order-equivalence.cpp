#include <bits/stdc++.h>
#include "src/XYZSketch.h"
int main(){std::mt19937 generator(630171);int cases=0;
 for(int capacity:{2,3,4,6,8})for(int t=0;t<20;++t){
  l=capacity;k=2;M=100;Hashing::SetHashMode(Hashing::CIRCULAR);Hashing::SetCircularA(.7);Hashing::SetDedupHashes(true);Hashing::HashingInit(1);
  XYZSketch a,b;a.init();b.init();
  for(int i=0;i<50;++i){int x=1+generator()%XYZ_FIELD_MASK;a.Update(x);b.Update(x);}
  for(int i=0;i<10+t;++i){int x=1+generator()%XYZ_FIELD_MASK;if(i&1)a.Update(x);else b.Update(x);}
  auto first=a-b,second=first;unsigned seed=generator();rng.seed(seed);auto old=first.Decode();auto after_rng=rng;
  rng.seed(seed);auto now=second.Decode(false);
  if(now.index()==0){auto& output=std::get<std::pair<vi,vi>>(now);std::sort(output.first.begin(),output.first.end());std::sort(output.second.begin(),output.second.end());}
  if(old!=now||after_rng!=rng){std::cerr<<"output-order mismatch\n";return 1;}++cases;
 }
 std::cout<<"{\"passed\":true,\"output_order_equivalence_cases\":"<<cases<<"}\n";
}
