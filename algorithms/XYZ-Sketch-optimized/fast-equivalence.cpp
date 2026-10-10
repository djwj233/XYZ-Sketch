#include <bits/stdc++.h>
#include "src/XYZSketch.h"
int main(){
 std::mt19937 rr(99827007);int cases=0,accepted=0,subtraction_cells=0;
 for(int ell:{2,3,4,6,8,12,20})for(int mode=0;mode<2;++mode){
  l=ell;k=mode?3:2;M=137;Hashing::SetHashMode(mode?Hashing::NAIVE:Hashing::CIRCULAR);Hashing::SetCircularA(.7243668166820519);Hashing::SetDedupHashes(true);Hashing::HashingInit(3);
  XYZSketch sketch;sketch.init();
  for(int t=0;t<1600&&ell<=8;++t){
   int cell=rr()%M;int kind=t%16;vi a,b;
   auto next=[&](bool membership){for(;;){int x=1+rr()%XYZ_FIELD_MASK;if(!membership||sketch.PermittedCell(cell,x))return x;}};
   if(kind<10){
    if(kind==1||kind==4||kind==7)a.push_back(next(kind<4));
    if(kind==2||kind==5||kind==8)b.push_back(next(kind<4));
    if(kind==3||kind==6||kind==9){a.push_back(next(kind<4));b.push_back(next(kind<4));if(a[0]==b[0])b[0]^=13;}
    poly f=PolynomialFromRoots(a),g=PolynomialFromRoots(b);
    sketch[cell].p=tool::TruncatedProduct(f,g.Rs(l).Inv(),l);
    sketch[cell].c=(int(a.size())-int(b.size())+2*l+1)%(2*l+1);
    if(kind>=7){int coefficient=rr()%l;sketch[cell].p[coefficient]^=1+rr()%XYZ_FIELD_MASK;}
   }else if(kind==10){sketch[cell].p=plv({1}).Rs(l);sketch[cell].c=0;}
   else if(kind==11){sketch[cell].p=plv({1}).Rs(l);sketch[cell].c=1;}
   else if(kind==12){sketch[cell].p=plv({0,1}).Rs(l);sketch[cell].c=1;}
   else if(kind==13){sketch[cell].p=plv({1,0}).Rs(l);sketch[cell].c=2*l;}
   else{sketch[cell].p.rs(l);for(int&x:sketch[cell].p.a)x=rr()&XYZ_FIELD_MASK;sketch[cell].c=rr()%(2*l+1);}
   // The old Half-GCD fallback explicitly assumes an invertible series.
   // Zero constants are tested against its guarded small-cell path only.
   if(l>8&&!sketch[cell].p.v(0))continue;
   unsigned seed=rr();rng.seed(seed);auto before=sketch.PureCellVerifyV10(cell);auto before_rng=rng();
   rng.seed(seed);auto after=sketch.PureCellVerify(cell);auto after_rng=rng();
   if(before!=after||before_rng!=after_rng){std::cerr<<"short mismatch ell="<<ell<<" kind="<<kind<<" t="<<t<<" rng="<<(before_rng==after_rng)<<"\n";return 1;}
   ++cases;if(after.index()==1)++accepted;
  }
  for(int t=0;t<60;++t){
   XYZSketch a,b,ref;a.init();b.init();ref.init();
   for(int i=0;i<M;++i){a[i].c=rr()%(2*l+1);b[i].c=rr()%(2*l+1);
    for(int j=0;j<l;++j){a[i].p[j]=rr()&XYZ_FIELD_MASK;b[i].p[j]=rr()&XYZ_FIELD_MASK;}
    if(i%7==0)b[i].p[0]=0;if(i%11==0)b[i].p[0]=1;
    ref[i].c=(a[i].c-b[i].c+2*l+1)%(2*l+1);int inverse=FieldInverse(b[i].p[0]);
    for(int j=0;j<l;++j){int sum=0;for(int q=1;q<=j;++q)sum^=FieldMultiply(b[i].p[q],ref[i].p[j-q]);ref[i].p[j]=FieldMultiply(a[i].p[j]^sum,inverse);}
   }
   auto actual=a-b;for(int i=0;i<M;++i){if(actual[i].c!=ref[i].c||!(actual[i].p==ref[i].p)){std::cerr<<"subtraction mismatch\n";return 1;}++subtraction_cells;}
  }
 }
 std::cout<<"{\"passed\":true,\"fast_cell_acceptance_and_rng_cases\":"<<cases<<",\"accepted_cases\":"<<accepted<<",\"subtraction_cells\":"<<subtraction_cells<<"}\n";
}
