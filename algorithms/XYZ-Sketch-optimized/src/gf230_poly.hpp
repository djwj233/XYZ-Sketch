#pragma once
#include "gf230.hpp"
#include "small_coefficients.hpp"
using vi=std::vector<int>;
inline int qpow(int x,unsigned exponent=XYZ_FIELD_SIZE-2){
    if(exponent==XYZ_FIELD_SIZE-2)return FieldInverse(x);
    int result=1;while(exponent){if(exponent&1)result=FieldMultiply(result,x);exponent>>=1;if(exponent)x=xyz_field.Sqr(x);}return result;
}
namespace tool {
// No tables or global preallocation are needed by the new dense-polynomial path.
inline void init(int){}inline void Pinit(int){}
struct poly {
    SmallCoefficients a;
    poly(unsigned n=0){a.resize(n);}
    poly(const vi& v){a=v;}
    poly(std::initializer_list<int> v){a.resize(v.size());std::copy(v.begin(),v.end(),a.begin());}
    int size()const{return a.size();}
    void rs(int n=0){if(n<0)throw std::invalid_argument("negative polynomial size");a.resize(n);}
    void clear(){a.clear();}
    void PopZero(){while(!a.empty()&&a.back()==0)a.pop_back();}
    int deg(){PopZero();return size()-1;}
    int& operator[](int i){return a[i];}const int& operator[](int i)const{return a[i];}
    int v(int i)const{return i<0||i>=size()?0:a[i];}
    poly Rs(int n=0)const{poly r=*this;r.rs(n);return r;}
    void monic(){PopZero();if(a.empty())throw std::invalid_argument("zero monic input");if(a.back()==1)return;XYZMultiplier m(xyz_field,FieldInverse(a.back()));for(int&x:a)x=m(x);}
    poly Shift(int n)const{poly r=*this;r.ShiftSelf(n);return r;}
    void ShiftSelf(int n){
        if(n<0){int drop=-n;if(drop>=size()){clear();return;}int end=size()-drop;for(int i=0;i<end;++i)a[i]=a[i+drop];rs(end);}
        else if(n>0){int old=size();rs(old+n);for(int i=old-1;i>=0;--i)a[i+n]=a[i];std::fill(a.begin(),a.begin()+n,0);}
    }
    friend bool operator==(const poly& x,const poly& y){for(int i=0;i<std::max(x.size(),y.size());++i)if(x.v(i)!=y.v(i))return false;return true;}
    friend poly operator+(const poly& x,const poly& y){poly r(std::max(x.size(),y.size()));for(int i=0;i<r.size();++i)r[i]=x.v(i)^y.v(i);return r;}
    friend poly operator-(const poly& x,const poly& y){return x+y;}
    friend poly operator*(const poly& x,const poly& y){
        if(x.a.empty()||y.a.empty())return {};
        poly r(x.size()+y.size()-1);
        for(int i=0;i<x.size();++i){if(!x[i])continue;XYZMultiplier m(xyz_field,x[i]);for(int j=0;j<y.size();++j)r[i+j]^=m(y[j]);}return r;
    }
    friend poly operator*(int x,const poly& y){poly r=y;XYZMultiplier m(xyz_field,x);for(int&v:r.a)v=m(v);return r;}
    poly& operator+=(const poly& p){*this=*this+p;return *this;}
    poly& operator-=(const poly& p){*this=*this-p;return *this;}
    poly& operator*=(const poly& p){*this=*this*p;return *this;}
    poly Inv()const{
        poly r(size());if(a.empty())return r;int iv=FieldInverse(a[0]);r[0]=iv;
        for(int i=1;i<size();++i){int sum=0;for(int j=1;j<=i;++j)sum^=FieldMultiply(a[j],r[i-j]);r[i]=FieldMultiply(sum,iv);}return r;
    }
    friend std::pair<poly,poly> div(poly f,poly g){
        f.PopZero();g.PopZero();if(g.a.empty())throw std::invalid_argument("zero divisor");
        if(f.size()<g.size())return {poly(),std::move(f)};
        poly quotient(f.size()-g.size()+1);int inverse=FieldInverse(g.a.back());
        for(int i=quotient.size()-1;i>=0;--i){int c=FieldMultiply(f[i+g.size()-1],inverse);quotient[i]=c;if(!c)continue;
            XYZMultiplier m(xyz_field,c);for(int j=0;j<g.size();++j)f[i+j]^=m(g[j]);}
        f.rs(g.size()-1);f.PopZero();quotient.PopZero();return {std::move(quotient),std::move(f)};
    }
};
inline poly plv(const vi& v){return poly(v);}
inline poly plv(std::initializer_list<int> v){return poly(v);}
inline poly TruncatedProduct(const poly& x,const poly& y,int n){
    poly r(n);for(int i=0;i<x.size()&&i<n;++i){if(!x[i])continue;XYZMultiplier m(xyz_field,x[i]);for(int j=0;j<y.size()&&i+j<n;++j)r[i+j]^=m(y[j]);}return r;
}
inline void RemainderInPlace(poly& f,const poly& g,int inverse){
    f.PopZero();if(f.size()<g.size())return;
    for(int i=f.size()-g.size();i>=0;--i){int c=FieldMultiply(f[i+g.size()-1],inverse);if(!c)continue;
        XYZMultiplier m(xyz_field,c);for(int j=0;j<g.size();++j)f[i+j]^=m(g[j]);}
    f.rs(g.size()-1);f.PopZero();
}
// Degree-aware reconstruction and its Half-GCD transform are defined in the
// following header, ported structurally from frozen prime-field v7.
} // namespace tool
#include "gf230_reconstruct.hpp"
#include "gf230_roots_fast.hpp"
namespace tool {
inline std::variant<vi,bool> findAllRootsReference(poly p){
    p.PopZero();if(p.a.empty())return false;p.monic();int degree=p.size()-1;
    if(!degree)return vi{};
    std::vector<XYZBinaryField::Elem> input(p.a.begin(),p.a.end());
    // MiniSketch's native solver assumes square-free inputs. XYZ verification
    // also sees arbitrary candidates, so reject repeated roots before calling it.
    if(degree==2 && input[1]==0)return false;
    if(degree>2){
        std::vector<XYZBinaryField::Elem> derivative(degree);
        for(int i=1;i<=degree;i+=2)derivative[i-1]=input[i];
        while(!derivative.empty() && derivative.back()==0)derivative.pop_back();
        if(derivative.empty())return false;
        if(derivative.size()>1){auto copy=input;::GCD(copy,derivative,xyz_field);if(copy.size()!=1)return false;}
    }
    // Field basis generation is isolated from the unchanged Murmur placement.
    uint64_t seed=(uint64_t(rng())<<32)|rng();
    auto roots=FindRoots(input,xyz_field.FromSeed(seed),xyz_field);
    if(int(roots.size())!=degree)return false;
    vi output(roots.begin(),roots.end());std::sort(output.begin(),output.end());return output;
}
// Reuse scratch vectors while calling the unmodified MiniSketch recursion.
// Storage is private to each thread; each invocation resets its live contents.
struct RootWorkspace {
    std::vector<std::vector<XYZBinaryField::Elem>> stack{1};
    std::vector<XYZBinaryField::Elem> derivative,copy,roots;
};
inline std::variant<vi,bool> findAllRootsMonic(const poly& p){
    const int degree=p.size()-1;
    if(!degree)return vi{};
    if(degree==2 && !p[1])return false;
    // Preserve the reference wrapper's random-stream consumption, even for
    // linear/quadratic cases that need no splitting basis.
    if(degree<=2){
        (void)rng();(void)rng();
        if(degree==1)return vi{p[0]};
        auto input=xyz_field.Mul(p[0],xyz_field.Sqr(xyz_field.Inv(p[1])));
        auto root=xyz_field.Qrt(input);
        if((xyz_field.Sqr(root)^root)!=input)return false;
        int a=xyz_field.Mul(root,p[1]),b=a^p[1];
        return a<b?vi{a,b}:vi{b,a};
    }
    static thread_local RootWorkspace workspace;
    workspace.stack[0].assign(p.a.begin(),p.a.end());
    auto& derivative=workspace.derivative;
#ifndef XYZ_FULL_DERIVATIVE
    // P(Z)=Even(Z^2)+Z*Odd(Z^2), so gcd(P,P') is nonconstant
    // iff Even(Y) and Odd(Y) have a common factor. Halve both degrees.
    derivative.clear();workspace.copy.clear();
    for(int i=0;i<=degree;++i){
        if(i&1)derivative.push_back(p[i]);else workspace.copy.push_back(p[i]);
    }
    while(!derivative.empty()&&!derivative.back())derivative.pop_back();
    while(!workspace.copy.empty()&&!workspace.copy.back())workspace.copy.pop_back();
    if(derivative.empty())return false;
    if(derivative.size()>1){
        XYZGCD(workspace.copy,derivative,xyz_field);
        if(workspace.copy.size()!=1)return false;
    }
#else
    derivative.assign(degree,0);
    for(int i=1;i<=degree;i+=2)derivative[i-1]=p[i];
    while(!derivative.empty()&&!derivative.back())derivative.pop_back();
    if(derivative.empty())return false;
    if(derivative.size()>1){
        workspace.copy=workspace.stack[0];
        XYZGCD(workspace.copy,derivative,xyz_field);
        if(workspace.copy.size()!=1)return false;
    }
#endif
    const uint64_t seed=(uint64_t(rng())<<32)|rng();
    const auto basis=xyz_field.FromSeed(seed);
    if(!basis)return false;
    workspace.roots.clear();workspace.roots.reserve(degree);
    if(!XYZRecFindRoots(workspace.stack,0,workspace.roots,false,0,basis,xyz_field))return false;
    if(int(workspace.roots.size())!=degree)return false;
    vi output(workspace.roots.begin(),workspace.roots.end());std::sort(output.begin(),output.end());return output;
}
inline std::variant<vi,bool> findAllRoots(const poly& input){
    if(input.a.empty())return false;
    if(input.a.back()==1)return findAllRootsMonic(input);
    poly normalized=input;normalized.PopZero();if(normalized.a.empty())return false;
    normalized.monic();return findAllRootsMonic(normalized);
}

} // namespace tool
using tool::poly;using tool::plv;
