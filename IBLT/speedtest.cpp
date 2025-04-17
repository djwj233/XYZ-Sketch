#include <bits/stdc++.h>
#include "iblt.cpp"
using namespace std;
#define fo(v, a, b) for(int v = a; v <= b; v++)
#define fr(v, a, b) for(int v = a; v >= b; v--)
#define cl(a, v) memset(a, v, sizeof(a))

void print(auto v) {
    for(auto x : v) printf("%d ", x);
    puts("");
}

const int ALL = (1 << 30) - 1;
vector<uint32_t> AliceData, BobData; vector<uint32_t> Adiff, Bdiff;
int cA, cB, D; random_device Rng; mt19937 rng(Rng());
void genereteData() {
	AliceData.clear(), BobData.clear();
    Adiff.clear(), Bdiff.clear();
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
template<typename T>
typename std::enable_if<std::is_class<T>::value, size_t>::type
getMemoryUsage(const std::vector<T>& vec) {
    size_t total = sizeof(vec) + vec.capacity() * sizeof(T);
    for (const auto &elem : vec) {
        total += getMemoryUsage(elem);
    }
    return total;
}
uint64_t differences[100010];
void Test() {
    printf("cA = %d cB = %d d = %d\n", cA, cB, D);
    fprintf(stderr, "cA = %d cB = %d d = %d\n", cA, cB, D);
    IBLT iblt(D); 
    // 创建 Alice 的草图
    double EncodeBegin = clock();
    
//    minisketch *sketch_a = minisketch_create(30, 0, D); // 字段大小为 12，容量为 4
    auto Ali = iblt.Encode(AliceData);
    double EncodeEnd = clock();
    cerr << "AliceEncodingEnded" << endl;

    // // 序列化 Alice 的草图
    // size_t sersize = minisketch_serialized_size(sketch_a);
    // unsigned char *buffer_a = malloc(sersize);
    // minisketch_serialize(sketch_a, buffer_a);
    // minisketch_destroy(sketch_a);

    // 创建 Bob 的草图
//    minisketch *sketch_b = minisketch_create(30, 0, D); // Bob 的草图
//    for (auto x : BobData) { // Bob 的集合是 [3002, 3011]
//        minisketch_add_uint64(sketch_b, x);
//    }
	auto bob = iblt.Encode(BobData);
    cerr << "BobEncodingEnded" << endl;

    // 合并 Alice 的草图到 Bob 的草图
    // sketch_a = minisketch_create(30, 0, D); // 重新创建 Alice 的草图
    // minisketch_deserialize(sketch_a, buffer_a); // 反序列化 Alice 的草图
    double DecodeBegin = clock();
//    minisketch_merge(sketch_b, sketch_a); // 合并草图
    // 解码差异
    auto Diff = iblt.Decode(Ali, bob);
    
    auto ansad = Diff.first, ansbd = Diff.second; 
    
//    ssize_t num_differences = minisketch_decode(sketch_b, D, differences);
    // free(buffer_a); // 释放缓冲区
//    minisketch_destroy(sketch_a);
//    minisketch_destroy(sketch_b);
    double DecodeEnd = clock();
    cerr << "DecodingEnded" << endl;
    assert(ansad.size() == Adiff.size() && ansbd.size() == Bdiff.size());
    for(int i = 0; i < (int)Adiff.size(); i++) assert(Adiff[i] == ansad[i]);
    for(int i = 0; i < (int)Bdiff.size(); i++) assert(Bdiff[i] == ansbd[i]);
//    puts("AC");

//    if (num_differences < 0) {
//        cerr << "error" << endl;
//    } else {
        // for (int i = 0; i < num_differences; ++i) {
        //     printf("%u is in only one of the two sets\n", (unsigned)differences[i]);
        // }

        printf("%.3lf %.3lf\n", (EncodeEnd - EncodeBegin) / CLOCKS_PER_SEC, (DecodeEnd - DecodeBegin) / CLOCKS_PER_SEC);
        cout << Ali.size() * (sizeof(tuple <int, uint32_t, uint32_t>)) * 8 << '\n'; 
		
		// printf("Running Time of Encode : %.3lf s\n", );
        // printf("Running Time of Decode : %.3lf s\n", );
        // puts("AC");
        cerr << "AC" << endl;
//    }
}

int main(void) {
	cerr << (sizeof(tuple <int, uint32_t, uint32_t>)) << '\n';
    // freopen("data.out", "w", stdout);
    // scanf("%d%d%d", &cA, &cB, &D);
//    cA = cB = 1000;
//    for(int d = 10; d <= cA; d *= 10) {
//        D = d, genereteData(), Test();
//    }
//
//    cA = cB = 1e5;
//    for(int d = 10; d <= cA; d *= 10) {
//        D = d, genereteData(), Test();
//    }
//
//    cA = cB = 1e7;
//    for(int d = 10; d <= 1e6; d *= 10) {
//        D = d, genereteData(), Test();
//    }

    return 0;
}
