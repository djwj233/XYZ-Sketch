#include <iostream>
#include <cassert>
#include <vector>
#include <cmath>
#include <cstdint>
#include <utility>
#include <functional>
#include <queue>
#include <ctime>
#include <algorithm>
#include "murmur3.cc"

using namespace std;
//int D;
namespace MurmurHash {
    uint32_t Hash(const int& data, uint32_t seed){
        uint32_t output;
        MurmurHash3_x86_32(&data, sizeof(int), seed, &output);
        return output;
    }
}
class IBLT{
#define arr tuple <int, uint32_t, uint32_t>
	private:
		int hash_count;
		const int fp = 229;
		int IBF;
		
		uint32_t fasthash32(uint32_t x, uint32_t i) {
			return MurmurHash::Hash(x, 3 * i * i + i + 2);
		}
		uint32_t fasthash(uint32_t x, uint32_t id) {
			return fasthash32(x, id) % IBF;
		} 
		uint32_t fingerprint(uint32_t x, uint32_t seed) {
			return fasthash32(x, seed);
		}
		void add_array(arr &vec, arr delta) {
			get <0>(vec) += get <0>(delta);
			get <1>(vec) += get <1>(delta);
			get <2>(vec) ^= get <2>(delta);
		}
	public:
		IBLT(int _D = 0) {
			hash_count = (_D < 200) ? 4 : 3;
			if(_D < 100) IBF = max(1, 4 * _D); 
			else if(_D < 1000) IBF = 2 * _D;
			else if(_D < 10000) IBF = 1.5 * _D; 
			else IBF = (int)ceil(1.23 * _D);
			
		}
		vector <arr> Encode(vector <uint32_t> Data){
			vector <arr> code(IBF, make_tuple(0, 0, 0));
			
			for(auto x : Data) {
				for(int i = 0; i < hash_count; i++) {
					arr vec;
					get <0>(vec) = 1;
					get <1>(vec) = x;
					get <2>(vec) = fingerprint(x, fp);
					auto pos = fasthash(x, i);
					add_array(code[pos], vec); 
				}
			}
			return code;
		} 
		pair <vector <uint32_t>, vector <uint32_t> > Decode(vector <arr> Alice, vector <arr> Bob) {
			vector <arr> Diff(IBF);
			
			for(int i = 0; i < IBF; i++) {
				get <0>(Diff[i]) = get <0>(Alice[i]) - get <0>(Bob[i]);
				get <1>(Diff[i]) = get <1>(Alice[i]) - get <1>(Bob[i]);
				get <2>(Diff[i]) = get <2>(Alice[i]) ^ get <2>(Bob[i]);
//				cerr<<get <0>(Alice[i])<<' '<<get <1>(Alice[i])<<' '<<get <2>(Alice[i])<<'\n';
//				cerr<<get <0>(Bob[i])<<' '<<get <1>(Bob[i])<<' '<<get <2>(Bob[i])<<'\n';
//				cerr<<get <0>(Diff[i])<<' '<<get <1>(Diff[i])<<' '<<get <2>(Diff[i])<<'\n';
			}
			queue <uint32_t> pure;
			vector <uint32_t> decode_Alice, decode_Bob;
			auto ispure = [&](uint32_t pos) {
				arr vec = Diff[pos];
				if(get <0>(vec) != 1 && get <0>(vec) != -1) return false;
				
				uint32_t cur = get <1>(vec) * get <0>(vec);
//				cerr<<"###########"<<cur<<'\n';
				if(fingerprint(cur, fp) == get <2>(vec)) return true ;
				return false;
			};
			auto solve = [&](uint32_t pos) {
				auto kind = ispure(pos);
				if(kind == false) return;
				auto typ = get <0>(Diff[pos]);
				auto cur = get <1>(Diff[pos]) * typ;
//				cerr<<cur<<'\n';
				if(typ == 1){
					decode_Alice.push_back(cur);
					
					for(int j = 0; j < hash_count; j++){
						arr vec;
						get <0>(vec) = -1;
						get <1>(vec) = -cur;
						get <2>(vec) = fingerprint(cur, fp);
						auto newpos = fasthash(cur, j);
						add_array(Diff[newpos], vec);
						
						if(ispure(newpos)){
							pure.emplace(newpos);
						}
					}
				}
				else {
					decode_Bob.push_back(cur);
					for(int j = 0; j < hash_count; j++){
						arr vec;
						get <0>(vec) = 1;
						get <1>(vec) = cur;
						get <2>(vec) = fingerprint(cur, fp);
						auto newpos = fasthash(cur, j);
						add_array(Diff[newpos], vec);
						
						if(ispure(newpos)){
							pure.emplace(newpos);
						}
					}
				}
			};
			for(int i = 0; i < IBF; i++) {
//				cerr<<ispure(i)<<'\n';
				if(ispure(i) == true)
					pure.emplace(i);
			}
			while(!pure.empty()) {
				auto pos = pure.front();
				pure.pop();
				solve(pos);
			}
			sort(decode_Alice.begin(), decode_Alice.end());
			sort(decode_Bob.begin(), decode_Bob.end());
			return make_pair(decode_Alice, decode_Bob);
		}
#undef arr
}; 
