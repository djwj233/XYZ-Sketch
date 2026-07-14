#include <bits/stdc++.h>
#include "tools.cpp"
#include "hash.cpp"
using namespace std;
#define fo(v, a, b) for(int v = a; v <= b; v++)
#define fr(v, a, b) for(int v = a; v >= b; v--)
#define cl(a, v) memset(a, v, sizeof(a))

using namespace Hashing;

int k, l, d;
queue<int> Q; vector<bool> Vis;
constexpr int FIELD_COEFFICIENT_BITS = 30;
static_assert(P >= (1 << (FIELD_COEFFICIENT_BITS - 1)) &&
              P < (1LL << FIELD_COEFFICIENT_BITS));

struct Cell {
    char c; poly p;
    Cell() {  c = 0, p = plv({1});  }
} ;

inline vector<int> HashLocations(int x) {
    vector<int> positions;
    positions.reserve(k);
    fo(i, 1, k) positions.push_back(h(i, x));
    if(GetDedupHashes()) {
        sort(positions.begin(), positions.end());
        positions.erase(unique(positions.begin(), positions.end()), positions.end());
    }
    return positions;
}

poly PolynomialFromRoots(const vector<int>& roots) {
    poly result = plv({1});
    for(int x : roots) result *= plv({P - x, 1});
    result.PopZero();
    return result;
}

bool HasDuplicateRoots(const vector<int>& roots) {
    return adjacent_find(roots.begin(), roots.end()) != roots.end();
}

struct XYZSketch {
    vector<Cell> B;
    // int queryMemory() {  return B.size() * (sizeof(char) + B[0].p.size() * sizeof(int));  }
    int size() {  return B.size();  }
    void init() {  B.resize(M); fo(i, 0, M - 1) B[i].p.rs(l);  }
    Cell & operator [] (int x) { return B[x]; }
    friend XYZSketch operator - (XYZSketch a, XYZSketch b) {
        XYZSketch res; res.init();
        fo(i, 0, M - 1) {
            res[i].c = (a[i].c - b[i].c + (2 * l + 1)) % (2 * l + 1);
            a[i].p.rs(l), b[i].p.rs(l);
            res[i].p = a[i].p * b[i].p.Inv(), res[i].p.rs(l);
        }
        return res;
    }

    inline void InsertToCell(int i, int x) {
        B[i].c = (B[i].c + 1) % (2 * l + 1);
        fr(j, l - 1, 1) B[i].p[j] = ((ll)(P - x) * B[i].p[j] + B[i].p[j - 1]) % P;
        B[i].p[0] = (ll)(P - x) * B[i].p[0] % P;
        // B[i].p = B[i].p * plv({P - x, 1}), B[i].p.rs(l);
    }
    inline void InsertToCell_Fast(int i, int x) {
        // B[i].c = (B[i].c + 1) % (2 * l + 1);
        B[i].c++; if(B[i].c == 2 * l + 1) B[i].c = 0;
        fr(j, l - 1, 1) B[i].p[j] = tool::fastMod::calcmod((ll)(P - x) * B[i].p[j] + B[i].p[j - 1]);
        B[i].p[0] = tool::fastMod::calcmod((ll)(P - x) * B[i].p[0]);
    }
    inline void Update(int x) {
        for(int i : HashLocations(x)) InsertToCell_Fast(i, x);
    }

    // pair<vector<int>, vector<int> > PureCellDecode(int i) {
    //     int m = B[i].c; if(m > l) m -= 2 * l + 1;
    //     auto ChiRes = tool :: RFuncReconstruct(B[i].p, l, m);
    //     if(ChiRes.index() == 1) assert(0);
    //     auto Chi = get<pair<poly, poly> >(ChiRes);
    //     auto DeltaA = tool :: findRoots(Chi.first), DeltaB = tool :: findRoots(Chi.second);
    //     sort(DeltaA.begin(), DeltaA.end()), sort(DeltaB.begin(), DeltaB.end());
    //     return make_pair(DeltaA, DeltaB);
    // }
    variant<bool, pair<vector<int>, vector<int> > > PureCellVerify(int i) {
        int m = B[i].c; if(m > l) m -= 2 * l + 1;
        auto ChiRes = tool :: RFuncReconstruct(B[i].p, l, m);
        if(ChiRes.index() == 1) return false;
        auto Chi = get<pair<poly, poly> >(ChiRes);
        Chi.first.PopZero(), Chi.second.PopZero();
        if(Chi.first.a.empty() || Chi.second.a.empty()) return false;
        if(Chi.first.a.back() != Chi.second.a.back()) return false;
        Chi.first.monic(), Chi.second.monic();
        auto DA = tool :: findAllRoots(Chi.first), DB = tool :: findAllRoots(Chi.second);
        if(DA.index() == 1 || DB.index() == 1) return false;
        auto DeltaA = get<vi>(DA), DeltaB = get<vi>(DB);

        sort(DeltaA.begin(), DeltaA.end());
        sort(DeltaB.begin(), DeltaB.end());
        if(HasDuplicateRoots(DeltaA) || HasDuplicateRoots(DeltaB)) return false;
        if((int)DeltaA.size() + (int)DeltaB.size() > l) return false;
        if((int)DeltaA.size() - (int)DeltaB.size() != m) return false;
        if(!(PolynomialFromRoots(DeltaA) == Chi.first)) return false;
        if(!(PolynomialFromRoots(DeltaB) == Chi.second)) return false;

        for(auto t : {DeltaA, DeltaB}) for(int x : t) {
            bool fl = false;
            for(int pos : HashLocations(x)) if(pos == i) {  fl = true; break;  }
            if(!fl) return false;
        }
        return make_pair(DeltaA, DeltaB);
    }
    void Extract(int x, int type) {
        poly now = plv({P - x, 1});
        if(type == 0) now.rs(l), now = now.Inv();
        for(int i : HashLocations(x)) {
            if(type == 0)
                B[i].c = (B[i].c + 2 * l) % (2 * l + 1);
            else
                B[i].c = (B[i].c + 1) % (2 * l + 1);
            B[i].p = B[i].p * now, B[i].p.rs(l);
            if(!Vis[i]) Vis[i] = true, Q.push(i);
        }
    }

    variant<pair<vi, vi>, bool> Decode() {
        while(Q.size()) Q.pop();
        Vis.clear(), Vis.resize(M, false);
        vector<int> SA, SB;
        fo(i, 0, M - 1) Vis[i] = true, Q.push(i);
        while(Q.size()) {
            int i = Q.front(); Q.pop();
            auto res = PureCellVerify(i);
            if(res.index() == 0) {  Vis[i] = false; continue; }
            auto [da, db] = get<pair<vi, vi>>(res);
            // printf("i = %d\n", i);
            // print(da), print(db);
            // if(da.empty() && db.empty()) continue;
            for(int x : da) Extract(x, 0), SA.push_back(x);
            for(int x : db) Extract(x, 1), SB.push_back(x);
        }
        fo(i, 0, M - 1) {
            B[i].p.PopZero();
            if(B[i].c != 0 || !(B[i].p == plv({1}))) return false;
        }
        sort(SA.begin(), SA.end()), sort(SB.begin(), SB.end());
        return make_pair(SA, SB);
    }
    vector<bool> to_bitstring() {
        vector<bool> res;
        fo(id, 0, M - 1) {
            B[id].p.rs(l);
            fo(j, 0, __lg(2 * l + 1))
                res.push_back(B[id].c >> j & 1);
            fo(i, 0, l - 1) {
                int coefficient = B[id].p[i] % P;
                if(coefficient < 0) coefficient += P;
                fo(j, 0, FIELD_COEFFICIENT_BITS - 1)
                    res.push_back(coefficient >> j & 1);
            }
        }
        return res;
    }
} ;

XYZSketch Encode(vector<int> v) {
    XYZSketch res; res.init();
    for(int x : v) res.Update(x);
    return res;
}
XYZSketch to_sketch(vector<bool> S) {
    XYZSketch res; int pos = 0;
    res.B.resize(M); fo(i, 0, M - 1) res.B[i].p = vector<int>(l, 0);
    fo(id, 0, M - 1) {
        fo(j, 0, __lg(2 * l + 1))
            res.B[id].c |= ((int)S[pos + j]) << j;
        pos += __lg(2 * l + 1) + 1;
        fo(i, 0, l - 1) {
            fo(j, 0, FIELD_COEFFICIENT_BITS - 1)
                res.B[id].p[i] |= ((int)S[pos + j]) << j;
            pos += FIELD_COEFFICIENT_BITS;
        }
    }
    return res;
}
