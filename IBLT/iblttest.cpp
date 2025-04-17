#include <bits/stdc++.h>
#include "iblt.cpp"
using namespace std;
#define fo(v, a, b) for(int v = a; v <= b; v++)
#define fr(v, a, b) for(int v = a; v >= b; v--)
#define cl(a, v) memset(a, v, sizeof(a))

const int MAXLEN = (1 << 19);

const int ALL = (1 << 30) - 1;
vector<unsigned> AliceData, BobData; vector<unsigned> Adiff, Bdiff;
random_device Rng; mt19937 rng(Rng());
const int P = 998244353;
int D,cA,cB;
void genereteData() {
    assert(D >= abs(cA - cB));
    AliceData.resize(max(cA, cB));
    set<uint32_t> S, Sp;
    for(int i = 0; i < max(cA, cB); i++) {
        uint32_t x = rng() & ALL;
        while(S.find(x) != S.end()) x = rng() & ALL;
        AliceData[i] = x, S.insert(x);
    }
    BobData = AliceData;
    AliceData.resize(cA), BobData.resize(cB);
    for(int i = 1; i <= (D - abs(cA - cB)) / 2; i++) {
        int p = rng() % min(cA, cB), v = rng() & ALL;
        while(Sp.find(p) != Sp.end()) p = rng() % min(cA, cB);
        while(S.find(v) != S.end()) v = rng() & ALL;
        BobData[p] = v, S.insert(v), Sp.insert(p);
        Adiff.push_back(AliceData[p]), Bdiff.push_back(BobData[p]);
    }
    for(int i = cB; i < cA; i++) Adiff.push_back(AliceData[i]);
    for(int i = cA; i < cB; i++) Bdiff.push_back(BobData[i]);
    sort(Adiff.begin(), Adiff.end()), sort(Bdiff.begin(), Bdiff.end());
    shuffle(AliceData.begin(), AliceData.end(), rng);
    shuffle(BobData.begin(), BobData.end(), rng);
    // print(AliceData), print(BobData);
}

void print(vector <uint32_t> vec){
	for(int i=0; i<(int)vec.size(); i++) cerr<<vec[i]<<' ';
	cerr<<'\n';
}
int main() {
//    tool::init(MAXLEN), tool::Pinit(MAXLEN);

//    int cA, cB;
    cA = cB = 1000;
    D = 10;
    IBLT iblt(D);
//    scanf("%d%d%d", &cA, &cB, &D);
    genereteData();
//     AliceData = {233613855, 84053574, 955552696, 443195438};
//     BobData = {955552696, 233613855, 84053574, 356042544, 443195438};
//     print(AliceData), print(BobData);
//	cerr<<Adiff.size()<<' '<<Bdiff.size()<<"\n"; 
//    auto check = [&](info &v) {
//        return 0 <= v.sz && v.sz <= 2 * D && v.p.size() <= D;
//    } ;
    double EncodeBegin = clock();
        auto Alice = iblt.Encode(AliceData);
    double EncodeEnd = clock();
    cerr << "AliceEncodingEnded" << endl;
        auto Bob = iblt.Encode(BobData);
//        assert(check(Alice) && check(Bob));
    cerr << "BobEncodingEnded" << endl;
    double DecodeBegin = clock();
        auto DiffRes = iblt.Decode(Alice, Bob);
    double DecodeEnd = clock();
    cerr << "DecodingEnded" << endl;

//    if(DiffRes.index() == 1) puts("ERROR"), exit(0);
    auto Diff = DiffRes;
    auto ansad = Diff.first, ansbd = Diff.second;
//    print(Adiff);
//    print(ansad);
//    print(Bdiff);
//    print(ansbd);
    assert(ansad.size() == Adiff.size() && ansbd.size() == Bdiff.size());
    for(int i = 0; i < (int)Adiff.size(); i++) assert(Adiff[i] == ansad[i]);
    for(int i = 0; i < (int)Bdiff.size(); i++) assert(Bdiff[i] == ansbd[i]);
    puts("AC");
//     puts("Alice - Bob : ");
//     for(int x : Diff.first) printf("%d ", x);
//     puts("");
//     puts("Bob - Alice : ");
//     for(int x : Diff.second) printf("%d ", x);
//     puts("");

    printf("Running Time of Encode : %.3lf s\n", (EncodeEnd - EncodeBegin) / CLOCKS_PER_SEC);
    printf("Running Time of Decode : %.3lf s\n", (DecodeEnd - DecodeBegin) / CLOCKS_PER_SEC);
//    printf("Communication Costs : %d bytes\n", sizeof(int) + Alice.p.size() * sizeof(int));

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
