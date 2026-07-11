#include <bits/stdc++.h>
#include "XYZSketch.cpp"

using namespace std;
#define fo(v, a, b) for(int v = a; v <= b; v++)
#define fr(v, a, b) for(int v = a; v >= b; v--)
#define cl(a, v) memset(a, v, sizeof(a))

const int MAXLEN = (1 << 10);

int main() {
    // freopen("data.out", "w", stdout);
    tool::init(MAXLEN), tool::Pinit(MAXLEN);
    
    int cA, cB, D;
    vector<int> AliceData = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
                BobData = {1, 12, 3, 4, 5, 6, 7, 28, 39, 10};
    cA = 10, cB = 10, D = 6;
    k = 2, l = 3, M = 6;
    HashingInit(0); // set z = 0

    XYZSketch Alice = Encode(AliceData);
    vector<bool> S = Alice.to_bitstring(); // Alice can transmit S to Bob

    Alice = to_sketch(S); // Bob decode Alice's sketch from S
    XYZSketch Bob = Encode(BobData);
    auto DiffRes = (Alice - Bob).Decode();

    if(DiffRes.index() == 1) puts("Fail to decode"), exit(0);
    auto Diff = get<pair<vector<int>, vector<int> > >(DiffRes);
    auto Adiff = Diff.first, Bdiff = Diff.second;
    puts("A \\ B : ");
    for(int x : Adiff) printf("%d ", x);
    puts("");
    puts("B \\ A : ");
    for(int x : Bdiff) printf("%d ", x);
    puts("");

    return 0;
}