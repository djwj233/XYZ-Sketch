#include <bits/stdc++.h>
using namespace std;
#define fo(v, a, b) for(int v = a; v <= b; v++)
#define fr(v, a, b) for(int v = a; v >= b; v--)
#define cl(a, v) memset(a, v, sizeof(a))

random_device Rng; mt19937 rng(Rng());

const int N = 2e7 + 10;

int n, m, l; bool fl[N], mark[N];
vector<int> vec[N], pos[N];
queue<int> q;

int main()
{
    // int inpz; scanf("%d", &inpz);
    // int l = 10, k = 2, z = 18;
    // n = 1.038e6 / l, m = 1e6;
    // int l = 6, k = 2, z = 6;
    // n = 1.122e4 / l, m = 1e4;
    // int l = 6, k = 2, z = 10;
    // n = 1.14e5 / l, m = 1e5;
    // int l = 6, k = 2, z = 10;
    // n = 1.071e5 / l, m = 1e5;
    // int l = 6, k = 2, z = 25;
    // n = 1.03e6 / l, m = 1e6;
    // int l = 6, k = 2, z = 25;
    // n = 1.0389e6 / l, m = 1e6;
    // int l = 2, k = 2, z = 32;
    // n = 1.141e6 / l, m = 1e6;
    int l = 4, k = 2, z = 27;
    n = 1.049e6 / l, m = 1e6;
    // int l = 6, k = 2, z = 60;
    // n = 1.022e7 / l, m = 1e7;
    // int l = 100, k = 2, z = inpz;
    // n = 1.10e6 / l, m = 1e6;
    printf("n = %d m = %d l = %d k = %d z = %d\n", n, m, l, k, z);
    int len = n / (z + 1);
    // n = 896000, m = 1000000, lim = 1;
    // n = 100000, m = 116900, lim = 3;
    // m /= lim;

    // int T = 10, cnt = 0;
    int T = 100, cnt = 0;
    fo(id, 1, T) {
        cl(fl, 0), cl(mark, 0);
        fo(i, 1, n) vec[i].clear();
        fo(i, 1, m) pos[i].clear();
        fo(i, 1, m) {
            int now = rng() % (n - len / 3 + 1);
            // int now = rng() % (n - len);
            fo(j, 1, k) {
                int d = rng() % len, x = (now + d) % n + 1;
                vec[x].push_back(i), pos[i].push_back(x);
            }
        }
        int now = 0;
        fo(i, 1, n) if(vec[i].size() <= l)
            mark[i] = true, q.push(i);
        while(q.size()) {
            int x = q.front(); q.pop();
            vector<int> tmp = vec[x];
            for(int y : tmp) if(!fl[y]) {
                fl[y] = true, now++;
                for(int id : pos[y]) {
                    vec[id].erase(remove(vec[id].begin(), vec[id].end(), y),
                        vec[id].end());
                    if(!mark[id] && vec[id].size() <= l)
                        mark[id] = true, q.push(id);
                }
            }
        }
        printf("Case #%d : ", id);
        if(now == m) puts("Success"), cnt++;
        else printf("Fail, Only %d / %d\n", now, m);
    }

    printf("%d / %d\n", cnt, T);   

    return 0;
}