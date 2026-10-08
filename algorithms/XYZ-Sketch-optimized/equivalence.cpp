#include <bits/stdc++.h>
#include "src/XYZSketch.h"
using Result=std::variant<std::pair<poly,poly>,bool>;
std::optional<std::pair<poly,poly>> accepted(Result x,int n,int m){
 if(x.index())return {};
 auto p=std::get<0>(std::move(x));p.first.PopZero();p.second.PopZero();
 if(p.first.a.empty()||p.second.a.empty())return {};
 if(p.first.a.back()!=p.second.a.back())return {};
 if(p.first.deg()+p.second.deg()>n || p.first.deg()-p.second.deg()!=m)return {};
 p.first.monic();p.second.monic();return p;
}
int main(){
 std::mt19937 rr(3276523);int cases=0;
 for(int n:{2,3,4,6,8})for(int t=0;t<12000;++t){
  poly A(n);for(int&x:A.a)x=rr()&XYZ_FIELD_MASK;A[0]=1+rr()%XYZ_FIELD_MASK;
  int m=int(rr()%(2*n+1))-n;
  auto a=accepted(tool::RFuncReconstructSmall(A,n,m),n,m);
  auto b=accepted(tool::RFuncReconstructReference(A,n,m),n,m);
  if(bool(a)!=bool(b)|| (a && !(a->first==b->first && a->second==b->second))) {
   std::cerr<<"different accepted reconstruction n="<<n<<" m="<<m<<" case="<<t<<" new="<<bool(a)<<" old="<<bool(b)<<"\n";return 1;
  }
  ++cases;
 }
 std::cout<<"{\"passed\":true,\"arbitrary_series_equivalence_cases\":"<<cases<<"}\n";
}
