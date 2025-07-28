#include <bits/stdc++.h>
#include "XYZSketch.cpp"

using namespace std;
#define fo(v, a, b) for(int v = a; v <= b; v++)
#define fr(v, a, b) for(int v = a; v >= b; v--)
#define cl(a, v) memset(a, v, sizeof(a))

const int MAXLEN = (1 << 19);

vector<int> AliceData, BobData; vector<int> Adiff, Bdiff;

int D;
void genereteData(int cA, int cB) {
    AliceData.clear(), BobData.clear();
    Adiff.clear(), Bdiff.clear();
    assert(D >= abs(cA - cB));
    AliceData.resize(max(cA, cB));
    set<int> S, Sp;
    for(int i = 0; i < max(cA, cB); i++) {
        int x = rng() % (P - 1) + 1;
        while(S.find(x) != S.end()) x = rng() % (P - 1) + 1;
        AliceData[i] = x, S.insert(x);
    }
    BobData = AliceData;
    AliceData.resize(cA), BobData.resize(cB);
    for(int i = 1; i <= (D - abs(cA - cB)) / 2; i++) {
        int p = rng() % min(cA, cB), v = rng() % (P - 1) + 1;
        while(Sp.find(p) != Sp.end()) p = rng() % min(cA, cB);
        while(S.find(v) != S.end()) v = rng() % (P - 1) + 1;
        BobData[p] = v, S.insert(v), Sp.insert(p);
        Adiff.push_back(AliceData[p]), Bdiff.push_back(BobData[p]);
    }
    for(int i = cB; i < cA; i++) Adiff.push_back(AliceData[i]);
    for(int i = cA; i < cB; i++) Bdiff.push_back(BobData[i]);
    sort(Adiff.begin(), Adiff.end()), sort(Bdiff.begin(), Bdiff.end());
    shuffle(AliceData.begin(), AliceData.end(), rng);
    shuffle(BobData.begin(), BobData.end(), rng);
}

int cA, cB;
void Test() {
    genereteData(cA, cB);
    int Znow;
    // switch (D) {
    //     case 10: M = 3 * D, Znow = 0; break;
    //     case 100: M = 1.6 * D, Znow = 1; break;
    //     case 1000: M = 1.3 * D, Znow = 2; break;
    //     case 10000: M = 1.15 * D, Znow = 5; break;
    //     case 100000: M = 1.082 * D, Znow = 10; break;
    //     case 1000000: M = 1.06 * D, Znow = 25; break;
    //     // default: assert(0); break;
    // }
    switch (D) {
        case 10: M = 3 * D, Znow = 0; break;
        case 100: M = 1.6 * D, Znow = 1; break;
        case 1000: M = 1.3 * D, Znow = 2; break;
        case 10000: M = 1.15 * D, Znow = 5; break;
        case 100000: M = 1.082 * D, Znow = 10; break;
        case 1000000: M = 1.045 * D, Znow = 25; break;
        default: assert(0); break;
    }
    M += l - 1, M /= l;
    // Znow = pow(M, 0.3333) / 2;
    HashingInit(Znow);
    printf("cA = %d cB = %d d = %d l = %d k = %d M = %d Cost = %d z = %d\n",
        cA, cB, D, l, k, M, M * l, Znow);
    // for(int x : AliceData) fo(j, 1, k)
    //     printf("+ %d %d : %d\n", j, x, h(j, x));
    // for(int x : BobData) fo(j, 1, k)
    //     printf("- %d %d : %d\n", j, x, h(j, x));
    // auto check = [&](Cell &v) {
    //     return 0 <= v.c && v.c <= 2 * l && v.p.size() <= l;
    // } ;
    double EncodeBegin = clock();
    cerr << "BeginAliceEncoding" << endl;
        auto Alice = Encode(AliceData);
    double EncodeEnd = clock();
    cerr << "BeginBobEncoding" << endl;
        auto Bob = Encode(BobData);
    double DecodeBegin = clock();
    cerr << "BeginDecoding" << endl;
        auto DiffRes = (Alice - Bob).Decode();
    double DecodeEnd = clock();

    if(DiffRes.index() == 1) puts("ERROR"), exit(0);
    auto Diff = get<pair<vector<int>, vector<int> > >(DiffRes);
    auto ansad = Diff.first, ansbd = Diff.second;
    assert(ansad.size() == Adiff.size() && ansbd.size() == Bdiff.size());
    for(int i = 0; i < (int)Adiff.size(); i++) assert(Adiff[i] == ansad[i]);
    for(int i = 0; i < (int)Bdiff.size(); i++) assert(Bdiff[i] == ansbd[i]);
    // // puts("Alice - Bob : ");
    // // for(int x : Diff.first) printf("%d ", x);
    // // puts("");
    // // puts("Bob - Alice : ");
    // // for(int x : Diff.second) printf("%d ", x);
    // // puts("");

    // puts("AC");
    printf("%.3lf %.3lf\n", (EncodeEnd - EncodeBegin) / CLOCKS_PER_SEC, (DecodeEnd - DecodeBegin) / CLOCKS_PER_SEC);
    printf("Com Cost : %d bits\n", Alice.to_bitstring().size());
    //     // printf("Running Time of Encode : %.3lf s\n", );
    //     // printf("Running Time of Decode : %.3lf s\n", );
    //     // puts("AC");
    // printf("Running Time of Encode : %.3lf s\n", (EncodeEnd - EncodeBegin) / CLOCKS_PER_SEC);
    // printf("Running Time of Decode : %.3lf s\n", (DecodeEnd - DecodeBegin) / CLOCKS_PER_SEC);
}

int main() {
    // freopen("data.out", "w", stdout);
    tool::init(MAXLEN), tool::Pinit(MAXLEN);
    l = 6, k = 2;

    cA = cB = 1000;
    for(int d = 10; d <= cA; d *= 10) {
        D = d, Test();
    }

    cA = cB = 1e5;
    for(int d = 10; d <= cA; d *= 10) {
        D = d, Test();
    }

    cA = cB = 1e7;
    for(int d = 10; d <= 1e6; d *= 10) {
        D = d, Test();
    }
    return 0;
}
/*
Sample :
Input:
10 3
1 2 3 4 5 6 7 8 9 10
1 12 3 4 5 6 7 28 39 10
Output:
Alice - Bob :
2 8 9
Bob - Alice :
12 28 39
*/