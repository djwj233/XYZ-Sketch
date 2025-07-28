#include <bits/stdc++.h>
#include "tools.cpp"
using namespace std;
#define fo(v, a, b) for(int v = a; v <= b; v++)
#define fr(v, a, b) for(int v = a; v >= b; v--)
#define cl(a, v) memset(a, v, sizeof(a))

poly dataToPoly(vector<int> &data, int l, int r, int Size) { // mod x^{Size}
    if(l > r) return plv({1});
    if(l == r) return plv({P - data[l], 1});
    int mid = (l + r) >> 1;
    poly res = dataToPoly(data, l, mid, Size) * dataToPoly(data, mid + 1, r, Size);
    return res.Rs(min(res.size(), Size));
}
inline poly CalcCharPoly(vector<int> &data, int Size) {
    return dataToPoly(data, 0, data.size() - 1, Size);
}

// const int D = 6;
// const vector<int> AliceData = {1, 2, 3, 4}, BobData = {2, 6, 7, 5};
// const int D = 6;
// const vector<int> AliceData = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
//                   BobData = {1, 12, 3, 4, 5, 6, 7, 28, 10};
int D;

// D denotes the number of elements with different occurences in A and B
// e.g. A = {1, 2, 3}, B = {2, 3, 3} gives D = 2, since |{1, 3}| = 2 

struct info {
    int sz; poly p;
    info() {  sz = 0, p = plv({1});  }
} ;

void Update(int x, info &Now, vector<int> &S) {
    assert(x != 0);
    Now.sz = (Now.sz + 1) % (2 * D + 1), S.push_back(x);
    if((int)S.size() == D) {
        Now.p = Now.p * CalcCharPoly(S, D);
        Now.p.rs(D), S = {};
    }
}
inline info Encode(vector<int> Data) {
    info res; vector<int> S;
    for(int x : Data) Update(x, res, S);
    if(!S.empty())
        res.p = res.p * CalcCharPoly(S, D), S = {};
    res.p.rs(D); return res;
}
variant<pair<vector<int>, vector<int> >, bool> Decode(info Alice, info Bob) {
    poly R = Alice.p * Bob.p.Inv(); R.rs(D);
    int m = (Alice.sz - Bob.sz + 2 * D + 1) % (2 * D + 1);
    if(m > D) m -= 2 * D + 1;
    auto ChiRes = tool :: RFuncReconstruct(R, D, m);
    if(ChiRes.index() == 1) return false;
    auto Chi = get<pair<poly, poly> >(ChiRes);
    auto DeltaA = tool :: findRoots(Chi.first),
         DeltaB = tool :: findRoots(Chi.second);
    if((int)DeltaA.size() < Chi.first.deg() || (int)DeltaB.size() < Chi.second.deg())
        return false;
    sort(DeltaA.begin(), DeltaA.end()), sort(DeltaB.begin(), DeltaB.end());
    // auto solve = [&](vi v) {
    //     vector<int> ans;
    //     for(int x : v) ans.push_back((P - qpow(x) % P) % P);
    //     sort(ans.begin(), ans.end());
    //     return ans;
    // };
    return make_pair(DeltaA, DeltaB);
}

vector<bool> to_bitstring(info A) {
    vector<bool> res; A.p.rs(D);
    fo(j, 0, __lg(2 * D + 1))
        res.push_back(A.sz >> j & 1);
    fo(i, 0, D - 1) fo(j, 0, 31)
        res.push_back(A.p[i] >> j & 1);
    return res;
}
info to_sketch(vector<bool> S) {
    info res; res.p = vector<int>(D, 0);
    fo(j, 0, __lg(2 * D + 1))
        res.sz |= ((int)S[j]) << j;
    for(int i = 0, pos = __lg(2 * D + 1) + 1; i < D; i++, pos += 32)
        fo(j, 0, 31)
            res.p[i] |= ((int)S[pos + j]) << j;
    return res;
}
