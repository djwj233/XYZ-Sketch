#include <bits/stdc++.h>
#include "src/XYZSketch.h"
int main(){std::mt19937 generator(1344101);int cases=0;
 for(int t=0;t<8000;++t){
  std::vector<unsigned> a(generator()%10),b(generator()%10);
  for(auto& x:a)x=generator()&XYZ_FIELD_MASK;
  for(auto& x:b)x=generator()&XYZ_FIELD_MASK;
  if(t%11==0&&!b.empty())b.back()=1;
  auto olda=a,oldb=b;GCD(olda,oldb,xyz_field);XYZGCD(a,b,xyz_field);
  if(!a.empty())MakeMonic(a,xyz_field);if(!olda.empty())MakeMonic(olda,xyz_field);
  if(a!=olda){std::cerr<<"GCD mismatch case="<<t<<"\n";return 1;}++cases;
 }
 std::cout<<"{\"passed\":true,\"gcd_equivalence_cases\":"<<cases<<"}\n";
}
