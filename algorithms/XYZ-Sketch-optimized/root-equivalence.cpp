#include <bits/stdc++.h>
#include "src/XYZSketch.h"
int main(){
 std::mt19937 rr(8828923);int cases=0,trace_cases=0;
 for(int d=3;d<=12;++d)for(int t=0;t<250;++t){
  std::vector<XYZBinaryField::Elem> p(d+1);for(auto& x:p)x=rr()&XYZ_FIELD_MASK;p[d]=1;
  unsigned param=1+rr()%XYZ_FIELD_MASK;std::vector<XYZBinaryField::Elem> old,now;
  TraceMod(p,old,param,xyz_field);XYZTraceMod(p,now,param,xyz_field);
  if(old!=now){std::cerr<<"trace mismatch degree="<<d<<" case="<<t<<"\n";return 1;}++trace_cases;
 }
 for(int degree=0;degree<=8;++degree)for(int t=0;t<600;++t){
  poly input(degree+1);for(int&x:input.a)x=rr()&XYZ_FIELD_MASK;input[degree]=1+rr()%XYZ_FIELD_MASK;
  if(t%3!=0){input=plv({1});for(int i=0;i<degree;++i){int root=1+rr()%XYZ_FIELD_MASK;if(t%7==0 && i<2)root=151;input=input*plv({root,1});}input=(1+rr()%XYZ_FIELD_MASK)*input;}
  unsigned seed=rr();rng.seed(seed);auto old=tool::findAllRootsReference(input);auto old_rng=rng;
  rng.seed(seed);auto now=tool::findAllRoots(input);
  if(old!=now || old_rng!=rng){std::cerr<<"root mismatch degree="<<degree<<" case="<<t<<"\n";return 1;}++cases;
 }
 std::cout<<"{\"passed\":true,\"root_and_rng_equivalence_cases\":"<<cases<<",\"trace_equivalence_cases\":"<<trace_cases<<"}\n";
}
