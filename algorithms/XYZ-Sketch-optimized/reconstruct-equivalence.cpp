#include <bits/stdc++.h>
#include "src/XYZSketch.h"
int main(){std::mt19937 generator(9933780);int cases=0;
 for(int n=2;n<=8;++n)for(int t=0;t<1600;++t){
  poly input(n);for(int& x:input.a)x=generator()&XYZ_FIELD_MASK;
  int m=int(generator()%(2*n+1))-n;
  if(t%3==0){
   vi left,right;int count=generator()%(n+1);int a=generator()%(count+1),b=count-a;
   for(int i=0;i<a;++i)left.push_back(1+generator()%XYZ_FIELD_MASK);
   for(int i=0;i<b;++i)right.push_back(1+generator()%XYZ_FIELD_MASK);
   if(t%9==0&&a&&b)left[0]=right[0];
   input=tool::TruncatedProduct(PolynomialFromRoots(left),PolynomialFromRoots(right).Rs(n).Inv(),n);m=a-b;
  }else if(t%19==0){input=plv({1}).Rs(n);m=t%2;}
  auto before=tool::RFuncReconstructSmallV11(input,n,m);
  auto after=tool::RFuncReconstructSmall(input,n,m);
  if(before!=after){std::cerr<<"reconstruction mismatch n="<<n<<" t="<<t<<" m="<<m<<"\n";return 1;}++cases;
 }
 std::cout<<"{\"passed\":true,\"reconstruction_equivalence_cases\":"<<cases<<"}\n";
}
