#include <bits/stdc++.h>
#include "src/XYZSketch.h"
int main(){
 std::mt19937 rr(28163243);int cases=0,successes=0;
 for(int ell:{2,3,4,6,8,12,20})for(int mode=0;mode<2;++mode){
  l=ell;k=mode?3:2;M=137;Hashing::SetHashMode(mode?Hashing::NAIVE:Hashing::CIRCULAR);Hashing::SetCircularA(.7243668166820519);Hashing::SetDedupHashes(true);Hashing::HashingInit(3);
  XYZSketch sketch;sketch.init();
  for(int t=0;t<600;++t){
   int cell=rr()%M;
   if(t%6==0){sketch[cell].p.rs(l);for(int& x:sketch[cell].p.a)x=rr()&XYZ_FIELD_MASK;sketch[cell].p[0]=1+rr()%XYZ_FIELD_MASK;sketch[cell].c=rr()%(2*l+1);}
   else{
    int category=t%6;int total=category==3?l+1+rr()%4:rr()%(l+1);if(category==4)total=std::max(total,2);int positive=category==4?total:rr()%(total+1);std::set<int> used;vi a,b;
    for(int count=0;count<total;++count){int x;
     do{x=1+rr()%XYZ_FIELD_MASK;if(used.count(x))continue;
      if(category==1||category==4){bool found=false;for(int loc:HashLocations(x))if(loc==cell)found=true;if(!found)continue;}
      break;
     }while(true);
     if(category==4&&count==1)x=a[0];
     used.insert(x);(count<positive?a:b).push_back(x);
    }
    poly f=PolynomialFromRoots(a),g=PolynomialFromRoots(b);
    sketch[cell].p=tool::TruncatedProduct(f,g.Rs(l).Inv(),l);
    sketch[cell].c=(positive-(total-positive)+4*l+2)%(2*l+1);
    if(category==5)sketch[cell].c=(sketch[cell].c+1)%(2*l+1);
   }
   unsigned seed=rr();rng.seed(seed);auto before=sketch.PureCellVerifyReference(cell);
   rng.seed(seed);auto after=sketch.PureCellVerify(cell);
   if(before!=after){std::cerr<<"verification mismatch ell="<<l<<" mode="<<mode<<" case="<<t<<"\n";return 1;}
   ++cases;if(after.index()==1)++successes;
  }
 }
 std::cout<<"{\"passed\":true,\"candidate_verification_equivalence_cases\":"<<cases<<",\"accepted_cases\":"<<successes<<"}\n";
}
