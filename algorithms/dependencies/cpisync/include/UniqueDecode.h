//
// Created by Bowen on 10/3/18.
// This is based on uniquely decodable shingles
//

#ifndef CPISYNCLIB_UNIQUEDECODE_H
#define CPISYNCLIB_UNIQUEDECODE_H

#include <NTL/ZZ.h>
#include <vector>
#include <utility>
#include <string>
#include "AdjMtx.h"
#include "Auxiliary.h"
#include "DataObject.h"

using std::vector;
using std::string;
using std::stringstream;
using std::pair;
using namespace NTL;

/**
 * is shingle part of a cycle
 * is shingle visited
 * shingle number
 */
struct cvi{
    bool isVisited, isCycle;
    size_t idx;
};



class UniqueDecode {
public:
    /**
     * Construct a K_Shingle set object with k as each shingle size
     * @param k fixing shingle size to be k
     */
    UniqueDecode(const int shingle_len, const char stop_word = '$');

    // Default deconstructor
    ~UniqueDecode();

    void injectStr(string& str);

    string reconstructDFS(vector<string>& shingle_set, map<string,std::set<size_t>>& merg_idx);

    /**
     * Get shingle set with size k
     * @param str
     * @return
     */
    vector<ZZ> getShingleSet(const string str);

    vector<ZZ> getMergeInd(const string str);

protected:
    void UDonline(const string& str, std::map<string,std::set<size_t>>& merg_idx);

    void mergeNredo(const string cur,vector<string>& shingle_history, size_t& j, AdjMtx& adjMatrix, map<string,cvi>& isCycVis);

    int longgestNxtShingle(int str_i, vector<ZZ> shingle_set, string str);

    int longgestPrevShingle(int str_i, vector<ZZ> shingle_set, string str);

    vector<vector<pair<string,bool>>::iterator> potNxtLst(const string nxt, vector<pair<string, bool>> &isVisited);

    void shingle2str(string &str, vector<pair<string, bool>> &isVisited);

    bool isAllVisited(vector<pair<string, bool>> isVisited_pair);

private:
    char stopWord;
    int shingleLen;
    string origStr;
    map<string,std::set<size_t>> MergIndex; //str is the second shingle to be merged with index of a shingle (first shingle) which has index value as the order of shingle set
};

#endif //CPISYNCLIB_UNIQUEDECODE_H
