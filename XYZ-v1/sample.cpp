#include <bits/stdc++.h>
#include "XYZ-v1.cpp"
using namespace std;
#define fo(v, a, b) for(int v = a; v <= b; v++)
#define fr(v, a, b) for(int v = a; v >= b; v--)
#define cl(a, v) memset(a, v, sizeof(a))

const int MAXLEN = (1 << 21);

vector<int> AliceData, BobData;

int cA, cB;

int main() {
    // freopen("data.out", "w", stdout);
    tool::init(MAXLEN), tool::Pinit(MAXLEN);

    scanf("%d%d%d", &cA, &cB, &D);
    AliceData.resize(cA), BobData.resize(cB);
    for(int i = 0; i < cA; i++)
        scanf("%d", &AliceData[i]);
    for(int i = 0; i < cB; i++)
        scanf("%d", &BobData[i]);
    
    info Alice = Encode(AliceData);
    vector<bool> S = to_bitstring(Alice); // Alice can transmit S to Bob

    Alice = to_sketch(S); // Bob decode Alice's sketch from S
    info Bob = Encode(BobData);
    auto DiffRes = Decode(Alice, Bob);

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
/*
Sample :
Input:
10 10 8
1 2 3 4 5 6 7 8 9 10
1 12 3 4 5 6 7 28 39 10
Output:
A \ B :
2 8 9
B \ A :
12 28 39
*/