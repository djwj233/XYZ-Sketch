#include <bits/stdc++.h>
using namespace std;
#define fo(v, a, b) for(int v = a; v <= b; v++)
#define fr(v, a, b) for(int v = a; v >= b; v--)
#define cl(a, v) memset(a, v, sizeof(a))

const int P = 998244353;
typedef vector<int> vi;
// mt19937 rng(time(0));
mt19937 rng(114514);

void print(vector<int> v) {
    for(int x : v) printf("%d ", x);
    puts("");
}

namespace tool {
    // #define fo(v, a, b) for(int v = a; v <= b; v++)
    // #define fr(v, a, b) for(int v = a; v >= b; v--)
    // #define cl(a, v) memset(a, v, sizeof(a))
    // const int P = 998244353;
    //////////
    const int mod = 998244353, _G = 3, N = (1 << 22), inv2 = (mod + 1) / 2;
    #define sz(a) ((int)a.size())
    #define L(i, j, k) for(int i = (j); i <= (k); i++)
    #define R(i, j, k) for(int i = (j); i >= (k); i--)
    #define ll long long
    #define vi vector<int>
    #define add(a, b) (a + b >= mod ? a + b - mod : a + b)
    #define dec(a, b) (a < b ? a - b + mod : a - b)
    int qpow(int x, int y = mod - 2) {
        int res = 1;
        for(; y; x = (ll) x * x % mod, y >>= 1) if(y & 1) res = (ll) res * x % mod;
        return res;
    }
    int fac[N + 1], ifac[N + 1], inv[N + 1];
    void init(int x) {
        fac[0] = ifac[0] = inv[1] = 1;
        L(i, 2, x) inv[i] = (ll) inv[mod % i] * (mod - mod / i) % mod;
        L(i, 1, x) fac[i] = (ll) fac[i - 1] * i % mod, ifac[i] = (ll) ifac[i - 1] * inv[i] % mod;
    }
    int C(int x, int y) {
        return y < 0 || x < y ? 0 : (ll) fac[x] * ifac[y] % mod * ifac[x - y] % mod;
    }
    inline int sgn(int x) {
        return (x & 1) ? mod - 1 : 1;
    }
    int rt[N], Lim;
    void Pinit(int x) {
        for(Lim = 1; Lim <= x; Lim <<= 1) ;
        for(int i = 1; i < Lim; i <<= 1) {
            int sG = qpow (_G, (mod - 1) / (i << 1));
            rt[i] = 1;
            L(j, i + 1, i * 2 - 1) rt[j] = (ll) rt[j - 1] * sG % mod;
        }
    }
      struct poly {
        vector<int> a;
        void print() {
            for(int i = 0; i < sz(a); i++) printf("%d ", a[i]);
            puts("");
        }
        void read(int n) {
            a.resize(n);
            for(int i = 0; i < n; i++) scanf("%d", &a[i]);
        }
        int size() { return sz(a); }
        void PopZero() {
            while(a.size() && a.back() == 0) a.pop_back();
        }
        int deg() {
            PopZero(); return sz(a) == 1 && a[0] == 0 ? -1e9 : sz(a) - 1;
        }
        int & operator [] (int x) { return a[x]; }
        int v(int x) { return x < 0 || x >= sz(a) ? 0 : a[x]; }
        void clear() { vector<int> ().swap(a); }
        void rs(int x = 0) { a.resize(x); }
        poly (unsigned int n = 0) { rs(n); }
        poly (vector<int> o) { a = o; }
        // poly (const poly &o) { a = o.a; }
        poly Rs(int x = 0) { vi res = a; res.resize(x); return res; }
        inline void dif() {
            int n = sz(a);
            for (int l = n >> 1; l >= 1; l >>= 1) 
                for(int j = 0; j < n; j += l << 1) 
                    for(int k = 0, *w = rt + l; k < l; k++, w++) {
                        int x = a[j + k], y = a[j + k + l];
                        a[j + k] = add(x, y);
                        a[j + k + l] = (ll) * w * dec(x, y) % mod;
                    }
        }
        void dit () {
            int n = sz(a);
            for(int i = 2; i <= n; i <<= 1) 
                for(int j = 0, l = (i >> 1); j < n; j += i) 
                    for(int k = 0, *w = rt + l; k < l; k++, w++) {
                        int pa = a[j + k], pb = (ll) a[j + k + l] * *w % mod;
                        a[j + k] = add(pa, pb), a[j + k + l] = dec(pa, pb);
                    }
            reverse(a.begin() + 1, a.end());
            for(int i = 0, iv = qpow(n); i < n; i++) a[i] = (ll) a[i] * iv % mod;
        }
#define BRUTE_POLY_OP
#ifdef BRUTE_POLY_OP
        friend poly operator * (poly aa, poly bb) {
            if(!sz(aa) || !sz(bb)) return (vi){};
            int lim, all = sz(aa) + sz(bb) - 1; poly res(all);
            L(i, 0, all - 1) L(j, max(0, i - sz(bb) + 1), min(i, sz(aa) - 1))
                res[i] = (res[i] + (ll)aa[j] * bb[i - j]) % P; 
            return res;
        }
        poly Inv() {
            assert(sz(a) && a[0] != 0); int iv = qpow(a[0]);
            poly res(sz(a)), f(sz(a)); int siz = sz(a) - 1;
            res[0] = iv; L(j, 0, siz) f[j] = (ll)a[j] * iv % P;
            L(i, 1, siz) {
                int cur = (ll)(P - f[i]) * iv % P; res[i] = cur;
                L(j, i, siz) f[j] = (f[j] + (ll)a[j - i] * cur) % P;
            }
            return res;
        }
#else
        friend poly operator * (poly aa, poly bb) {
            if(!sz(aa) || !sz(bb)) return (vi){};
            if(sz(aa) + sz(bb) <= 30) {
                int lim, all = sz(aa) + sz(bb) - 1; poly res(all);
                L(i, 0, all - 1) L(j, max(0, i - sz(bb) + 1), min(i, sz(aa) - 1))
                res[i] = (res[i] + (ll)aa[j] * bb[i - j]) % P; 
                return res;
            }
            int lim, all = sz(aa) + sz(bb) - 1;
            for(lim = 1; lim < all; lim <<= 1);
            aa.rs(lim), bb.rs(lim), aa.dif(), bb.dif();
            L(i, 0, lim - 1) aa[i] = (ll) aa[i] * bb[i] % mod;
            aa.dit(), aa.a.resize(all);
            return aa;
        }
        poly Inv() {
            assert(sz(a) && a[0] != 0);
            if(sz(a) <= 30) {
                int iv = qpow(a[0]);
                poly res(sz(a)), f(sz(a)); int siz = sz(a) - 1;
                res[0] = iv; L(j, 0, siz) f[j] = (ll)a[j] * iv % P;
                L(i, 1, siz) {
                    int cur = (ll)(P - f[i]) * iv % P; res[i] = cur;
                    L(j, i, siz) f[j] = (f[j] + (ll)a[j - i] * cur) % P;
                }
                return res;
            }
            poly res, f, g;
            res.rs(1), res[0] = qpow(a[0]);
            for(int m = 1, pn; m < sz(a); m <<= 1) {
                pn = m << 1, f = res, g.rs(pn), f.rs(pn);
                for(int i = 0; i < pn; i++) g[i] = (*this).v(i);
                f.dif(), g.dif();
                for(int i = 0; i < pn; i++) g[i] = (ll) f[i] * g[i] % mod;
                g.dit();
                for(int i = 0; i < m; i++) g[i] = 0;
                g.dif();
                for(int i = 0; i < pn; i++) g[i] = (ll) f[i] * g[i] % mod;
                g.dit(), res.rs(pn);
                for(int i = m; i < min(pn, sz(a)); i++) res[i] = (mod - g[i]) % mod;
            } 
            return res.rs(sz(a)), res;
        }
#endif
        poly Shift (int x) {
            assert(sz(a) + x > 0);
            poly zm (sz(a) + x);
            L(i, max(-x, 0), sz(a) - 1) zm[i + x] = a[i];
            return zm; 
        }
        void ShiftSelf (int x) {
            assert(sz(a) + x > 0); vi zm (sz(a) + x);
            L(i, max(-x, 0), sz(a) - 1) zm[i + x] = a[i];
            a = zm;
        }
        friend poly operator * (poly aa, int bb) {
            poly res(sz(aa));
            L(i, 0, sz(aa) - 1) res[i] = (ll) aa[i] * bb % mod;
            return res;
        }
        friend poly operator * (int bb, poly aa) {
            return aa * bb;
        }
        friend bool operator == (poly aa, poly bb) {
            aa.PopZero(), bb.PopZero();
            if(aa.size() != bb.size()) return false;
            L(i, 0, sz(aa) - 1) if(aa[i] != bb[i]) return false;
            return true;
        }
        friend poly operator + (poly aa, poly bb) {
            vector<int> res(max(sz(aa), sz(bb)));
            L(i, 0, sz(res) - 1) res[i] = add(aa.v(i), bb.v(i));
            return poly(res);
        }
        friend poly operator - (poly aa, poly bb) {
            vector<int> res(max(sz(aa), sz(bb)));
            L(i, 0, sz(res) - 1) res[i] = dec(aa.v(i), bb.v(i));
            return poly(res);
        }
        poly & operator += (poly o) {
            rs(max(sz(a), sz(o)));
            L(i, 0, sz(a) - 1) (a[i] += o.v(i)) %= mod;
            return (*this);
        }
        poly & operator -= (poly o) {
            rs(max(sz(a), sz(o)));
            L(i, 0, sz(a) - 1) (a[i] += mod - o.v(i)) %= mod;
            return (*this);
        }
        poly & operator *= (poly o) {
            return (*this) = (*this) * o;
        }
        poly Integ() {
            if(!sz(a)) return poly();
            poly res(sz(a) + 1);
            L(i, 1, sz(a)) res[i] = (ll) a[i - 1] * inv[i] % mod;
            return res;
        }
        poly Deriv() {
            if(!sz(a)) return poly();
            poly res(sz(a) - 1); 
            L(i, 1, sz(a) - 1) res[i - 1] = (ll) a[i] * i % mod;
            return res;
        }
        poly Ln() {
            poly g = ((*this).Inv() * (*this).Deriv()).Integ();
            return g.rs(sz(a)), g;
        }
        poly Exp() {
            poly res(1), f; 
            res[0] = 1;
            for(int m = 1, pn; m < sz(a); m <<= 1) {
                pn = min(m << 1, sz(a)), f.rs(pn), res.rs(pn);
                for(int i = 0; i < pn; i++) f[i] = (*this).v(i);
                f -= res.Ln(), (f[0] += 1) %= mod, res *= f, res.rs(pn); 
            }
            return res.rs(sz(a)), res;
        }
        poly pow(int x, int rx = -1) { // x : the power % mod; rx : the power % (mod - 1)
            if(rx == -1) rx = x;
            int cnt = 0;
            while (a[cnt] == 0 && cnt < sz(a)) cnt += 1;
            
            poly res = (*this);
            L(i, cnt, sz(a) - 1) res[i - cnt] = res[i];
            L(i, sz(a) - cnt, sz(a) - 1) res[i] = 0;
            int c = res[0], w = qpow (res[0]);
            L(i, 0, sz(res) - 1) res[i] = (ll) res[i] * w % mod;
            res = res.Ln();
            L(i, 0, sz(res) - 1) res[i] = (ll) res[i] * x % mod;
            res = res.Exp();
            c = qpow (c, rx);
            L(i, 0, sz(res) - 1) res[i] = (ll) res[i] * c % mod;
            
            if((ll) cnt * x > sz(a)) L(i, 0, sz(a) - 1) res[i] = 0;
            else if(cnt) {
                R(i, sz(a) - cnt * x - 1, 0) res[i + cnt * x] = res[i];
                L(i, 0, cnt * x - 1) res[i] = 0; 
            }
            return res;
        }
        poly sqrt(int Rt = 1) {
            poly res(1), f; 
            res[0] = Rt;
            for(int m = 1, pn; m < sz(a); m <<= 1) {
                pn = min(m << 1, sz(a)), f.rs(pn);
                for(int i = 0; i < pn; i++) f[i] = (*this).v(i);
                f += res * res, f.rs(pn), res.rs(pn), res = f * res.Inv(), res.rs(pn);
                for(int i = 0; i < pn; i++) res[i] = (ll) res[i] * inv2 % mod;
            } 
            return res;
        }
        friend poly mul (poly aa, poly bb, int k) {
            if(!sz(aa) || !sz(bb)) return {};
            int lim; 
            for(lim = 1; lim < k; lim <<= 1);
            aa.rs(lim), bb.rs(lim), aa.dif(), bb.dif();
            L(i, 0, lim - 1) aa[i] = (ll) aa[i] * bb[i] % mod;
            aa.dit(), aa.a.resize(lim);
            return aa;
        }
        void Rev() {
            reverse(a.begin(), a.end());
        }
        friend pair < poly, poly > div (poly f, poly g) { /* f / g = first, f % g = second */
            f.rs(max(sz(f), sz(g))), f.Rev(), g.Rev();
            int n = sz(f), m = sz(g);
            poly A = g.Rs(n - m + 1).Inv(), t;
            A *= f.Rs(n - m + 1), A.rs(n - m + 1), A.Rev(), g.Rev(), f.Rev(), t = f - A * g, t.rs(m - 1);
            A.PopZero(), t.PopZero(); return make_pair(A, t);
        }
        void monic() {
            assert(a.size() && a.back());
            auto C = qpow(a.back());
            for(int &x : a) x = (ll)x * C % P;
        }
    } ;
    inline poly plv(vi v) {  return poly(v);  }
    struct polyMat {
        poly a00, a01, a10, a11;
        polyMat operator*(const polyMat &t) const {
            polyMat res;
            res.a00 = a00 * t.a00 + a01 * t.a10, res.a01 = a00 * t.a01 + a01 * t.a11;
            res.a10 = a10 * t.a00 + a11 * t.a10, res.a11 = a10 * t.a01 + a11 * t.a11;
            res.a00.PopZero(), res.a01.PopZero(), res.a10.PopZero(), res.a11.PopZero();
            return res;
        }
    } ;
    inline polyMat gen(poly Q) {
        return {plv({0}), plv({1}), plv({1}), (P - 1) * Q};
    }
    inline void Mul(polyMat M, poly &A, poly &B) {
        poly tA = A, tB = B;
        A = M.a00 * tA + M.a01 * tB, B = M.a10 * tA + M.a11 * tB;
        A.PopZero(), B.PopZero(); 
    }
    inline pair<poly, poly> Mul(polyMat M, pair<poly, poly> u) {
        Mul(M, u.first, u.second); return u;
    }
    polyMat HalfGCD(poly A, poly B) {
        if(B.deg() == 0) return {plv({1}), plv({0}), plv({0}), plv({1})};
        if(A.deg() == 0) return {plv({0}), plv({1}), plv({1}), plv({0})};
        int len = A.deg(), m = (len + 1) / 2;
        if(B.deg() < m) return {plv({1}), plv({0}), plv({0}), plv({1})};
        poly A1 = A.Shift(-m), B1 = B.Shift(-m); auto M = HalfGCD(A1, B1);
        Mul(M, A, B); if(B.deg() < m) return M;

        auto tmp = div(A, B); A = B, B = tmp.second;
        M = gen(tmp.first) * M; if(B.deg() < m) return M;

        int k = 2 * m - A.deg(); A1 = A.Shift(-k), B1 = B.Shift(-k);
        return HalfGCD(A1, B1) * M;
    }
    polyMat coGCD(poly A, poly B) {
        auto M = HalfGCD(A, B); Mul(M, A, B);
        if(B.size() == 0) return M;
        auto tmp = div(A, B); A = B, B = tmp.second;
        M = gen(tmp.first) * M; if(B.size() == 0) return M;
        return coGCD(A, B) * M;
    }
    inline poly GCD(poly A, poly B) {
        if(B == plv({0})) return A;
        if(A == plv({0})) return B;
        auto M = coGCD(A, B); auto res = M.a00 * A + M.a01 * B;
        res.PopZero(), res.monic();
        return res;
    }
    // deg A < 2 * n + 1, deg p <= n, deg q <= n
    pair<poly, poly> Recon(poly A, int n) {
        poly M(2 * n + 2); M[2 * n + 1] = 1; A.rs(2 * n + 1);
        auto Mat = HalfGCD(A, M);
        auto X = Mat.a00 * A + Mat.a01 * M;
        X.PopZero(), Mat.a00.PopZero();
        if(X.deg() <= n && Mat.a00.deg() <= n)
            return make_pair(X, Mat.a00);
        auto Y = Mat.a10 * A + Mat.a11 * M;
        Y.PopZero(), Mat.a10.PopZero();
        if(Y.deg() <= n && Mat.a10.deg() <= n)
            return make_pair(Y, Mat.a10);
        assert(0);
    }
    // find (p, q) s.t.
    // p / q mod x^n = A, deg p + deg q < n, deg p - deg q = m <= 0, [x^0]p = [x^0]q = 1
    // false for no solution
    variant<pair<poly, poly>, bool> Reconstruct(poly A, int n, int m) {
        int pdeg = (n - 1 + m) / 2, qdeg = (n - 1 - m) / 2;
        assert(pdeg <= qdeg); int delta = qdeg - pdeg;
        A.ShiftSelf(delta); auto res = Recon(A, qdeg);
        bool fl = (res.first.deg() >= delta);
        for(int i = 0; fl && i < delta; i++)
            fl = (res.first[i] == 0);
        if(!fl) return false;
        return make_pair(res.first.Shift(-delta), res.second);
    }
    // find (p, q) s.t.
    // p / q mod x^n = A; deg p + deg q <= n; deg p - deg q = m; p, q monic
    // A invertible
    variant<pair<poly, poly>, bool> RFuncReconstruct(poly A, int n, int m) {
        if(A == plv({1})) {
            if(m != 0) return false;
            return make_pair(plv({1}), plv({1}));
        }
        A.rs(n); auto rec = A;
        variant<pair<poly, poly>, bool> Res;
        if(m < 0) {
            A = A.Inv(), A = A - plv({1}).Shift(-m);
            Res = Reconstruct(A.Inv(), n, m + 1);
        } else if(m == 0) {
            A = A - plv({1});
            Res = Reconstruct(A, n, -1);
        } else {
            A = A - plv({1}).Shift(m);
            Res = Reconstruct(A.Inv(), n, -m + 1);
        }
        if(Res.index() == 1) return false;
        auto res = get<pair<poly, poly> >(Res); poly P = res.first, Q = res.second;
        if(m < 0) {
            Q = Q + P.Shift(-m);
        } else if(m == 0) {
            P = P + Q;
        } else {
            swap(P, Q), P = P + Q.Shift(m);
        }
        P.rs(n + 1), Q.rs(n + 1);
        auto now = P * Q.Inv(); now.rs(n);
        P.PopZero(), Q.PopZero();
        if(now == rec) return make_pair(P, Q);
        return false;
    }

    inline poly randPoly(int n) { // deg = n - 1
        poly r(n);
        for(int i = 0; i < n; i++) r[i] = rng() % P;
        return r;
    }
    poly power(poly A, int n, poly M) {
        auto res = plv({1}), a = A;
        while(n) {
            if(n & 1) res = div(res * a, M).second;
            a = div(a * a, M).second, n >>= 1;
        }
        return res;
    }
    // vector<int> divide(poly A) {
    //     if(A.deg() == 0) return {};
    //     if(A.deg() == 1) return {P - A[0]};
    //     poly R = power(randPoly(A.size()), (P - 1) >> 1, A);
    //     auto lp = GCD(R - plv({1}), A), rp = div(A, lp).first;
    //     auto lv = divide(lp), rv = divide(rp);
    //     for(int x : rv) lv.push_back(x);
    //     return lv;
    // }
    vector<int> divide2(poly iA) {
        queue<poly> Q; Q.push(iA); vector<int> vec;
        int cnt = 0;
        while(Q.size()) {
            poly A = Q.front(); Q.pop(); cnt++;
            if(A.deg() == 0) continue;
            if(A.deg() == 1) {  vec.push_back(P - A[0]); continue;  }
            poly R = power(randPoly(A.size()), (P - 1) >> 1, A);
            auto lp = GCD(R - plv({1}), A), rp = div(A, lp).first;
            Q.push(lp), Q.push(rp);
        }
        return vec;
    }
    vector<int> findRoots(poly A) {
        A.PopZero(), A.monic();
        // the following codes aims to calculate gcd(X^q - X, A),
        auto UniqueRoot = [&](int q) {
            auto res = power(plv({0, 1}), q, A);
            res = res - plv({0, 1}), A = GCD(A, res);
        } ;
        UniqueRoot(P);
        auto res = divide2(A);
        sort(res.begin(), res.end());
        return res;
    }
    variant<vector<int>, bool> findAllRoots(poly A) {
        A.PopZero(), A.monic(); if(A == plv({1})) return (vi){};
        poly rad, tmp = power(plv({0, 1}), P, A);
        tmp = tmp - plv({0, 1}), rad = GCD(A, tmp);
        tmp = power(rad, A.deg(), A);
        if(tmp == plv({0})) {
            auto res = divide2(A); sort(res.begin(), res.end());
            return res;
        }
        return false;
    }

    namespace eval {
        poly A[N], B[N], a, sav;
        int X[N], Y[N];
        void Divide1(int id, int l, int r) {
            if(l == r) return A[id] = poly(vi{1, (mod - X[l]) % mod}), void();
            int mid = (l + r) >> 1;
            Divide1(id << 1, l, mid), Divide1(id << 1 | 1, mid + 1, r);
            A[id] = A[id << 1] * A[id << 1 | 1];
        }
        void Divide2(int id, int l, int r) {
            if(l == r) return Y[l] = (a[0] + (ll) X[l] * B[id][0] % mod) % mod, void();
            int mid = (l + r) >> 1, len = r - l + 1, la = mid - l + 1, lb = r - mid;
            sav = mul(B[id], A[id << 1 | 1], len), B[id << 1].rs(la);
            L(i, 0, la - 1) B[id << 1][i] = sav[i + len - la];
            sav = mul(B[id], A[id << 1], len), B[id << 1 | 1].rs(lb);
            L(i, 0, lb - 1) B[id << 1 | 1][i] = sav[i + len - lb];
            Divide2(id << 1, l, mid), Divide2(id << 1 | 1, mid + 1, r);
        }
        vector<int> solve (poly F, vector<int> x) {
            a = F; int m = x.size();
            L(i, 1, m) X[i] = x[i - 1];
            if(sz(a) < m + 1) a.rs(m + 1);
            int n = sz(a);
            Divide1(1, 1, m);
            sav = a, sav.Rev(), sav *= A[1].Rs(n).Inv(), B[1].rs(m);
            L(i, 0, m - 1) B[1][i] = sav[i + n - m - 1];
            Divide2(1, 1, m);
            vector<int> y(m); L(i, 1, m) y[i - 1] = Y[i];
            return y;
        }
    }
}
using tool::poly; using tool::qpow; using tool::plv;
using tool::RFuncReconstruct; using tool::findRoots;
