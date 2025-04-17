#include <bits/stdc++.h>
#include "PolyFast.cpp"
using namespace std;
#define fo(v, a, b) for(int v = a; v <= b; v++)
#define fr(v, a, b) for(int v = a; v >= b; v--)
#define cl(a, v) memset(a, v, sizeof(a))

const int MAXLEN = (1 << 21);

vector<int> AliceData, BobData; vector<int> Adiff, Bdiff;

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
    printf("cA = %d cB = %d d = %d\n", cA, cB, D), genereteData(cA, cB);

    double EncodeBegin = clock();
        info Alice = Encode(AliceData);
    double EncodeEnd = clock();
    cerr << "AliceEncodingEnded" << endl;
        info Bob = Encode(BobData);
    cerr << "BobEncodingEnded" << endl;
    double DecodeBegin = clock();
        auto DiffRes = Decode(Alice, Bob);
    double DecodeEnd = clock();
    cerr << "DecodingEnded" << endl;

    if(DiffRes.index() == 1) puts("ERROR"), exit(0);
    auto Diff = get<pair<vector<int>, vector<int> > >(DiffRes);
    auto ansad = Diff.first, ansbd = Diff.second;
    assert(ansad.size() == Adiff.size() && ansbd.size() == Bdiff.size());
    for(int i = 0; i < (int)Adiff.size(); i++) assert(Adiff[i] == ansad[i]);
    for(int i = 0; i < (int)Bdiff.size(); i++) assert(Bdiff[i] == ansbd[i]);
    // puts("AC");
    // puts("Alice - Bob : ");
    // for(int x : Diff.first) printf("%d ", x);
    // puts("");
    // puts("Bob - Alice : ");
    // for(int x : Diff.second) printf("%d ", x);
    // puts("");

    printf("%.3lf %.3lf\n", (EncodeEnd - EncodeBegin) / CLOCKS_PER_SEC, (DecodeEnd - DecodeBegin) / CLOCKS_PER_SEC);
        // printf("Running Time of Encode : %.3lf s\n", );
        // printf("Running Time of Decode : %.3lf s\n", );
        // puts("AC");
    printf("Com Cost : %d bits\n", to_bitstring(Alice).size());
    cerr << "AC" << endl;
}
int main() {
    // freopen("data.out", "w", stdout);
    tool::init(MAXLEN), tool::Pinit(MAXLEN);

    // cA = cB = 1000;
    // for(int d = 10; d <= cA; d *= 10) {
    //     D = d, Test();
    // }

    // cA = cB = 1e5;
    // for(int d = 10; d <= cA; d *= 10) {
    //     D = d, Test();
    // }

    cA = cB = 1e7;
    for(int d = 10; d <= 1e5; d *= 10) {
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