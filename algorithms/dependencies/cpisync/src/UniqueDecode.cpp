//
// Created by Bowen on 10/3/18.
//

#include "UniqueDecode.h"
#include "AdjMtx.h"

UniqueDecode::UniqueDecode(const int shingle_len, const char stop_word) : shingleLen(shingle_len), stopWord(stop_word) {
    if(shingle_len < 2) Logger::error_and_quit("UD shingle length has to be 2 or bigger.");
}

UniqueDecode::~UniqueDecode() {};

void UniqueDecode::injectStr(string &str) {
    str = string(1, stopWord) + str; // stop word is char, always size 1
    origStr = str; // TODO: Delete this if not necessary
    MergIndex.clear(); // make sure nothing is in it
    UDonline(str, MergIndex);

    cout << "number of merge shingles: " << MergIndex.size() << endl;
    // we can test if it works here
    vector<string> shingle_set;
    std::map<string, bool> unique;
    for (int i = 0; i < str.size(); ++i) {
        string tmpstr = str.substr(i, shingleLen);
        if (unique[tmpstr]) {
            shingle_set.push_back(tmpstr);
            unique[tmpstr] = true;
        }
    }
    auto reconStr = reconstructDFS(shingle_set, MergIndex);
    cout << reconStr << endl;
    if (str == reconStr)cout << "we are done" << endl;
}

void UniqueDecode::UDonline(const string &str, std::map<string, std::set<size_t>> &merg_idx) {
    // We use "Online algorithm for testing unique decodability"
    // The modification is that we merge everytime we hit false and redo assessment for that index
    // We create shingles one by one
    // other than merge list, everything should have save the merges

    // For easy implementation, we follow UD paper to create O(n^2) whereas it can be promoted to O(n)

    // Sanity check
    if (str.empty()) Logger::error_and_quit("The input string is empty - UDonline");
    if (!merg_idx.empty()) Logger::error_and_quit("The input Merge Index Vector is not empty - UDonline");
    if (str[0] != stopWord) Logger::error_and_quit("No stop word found at the begining of the string - UDonline");

    std::map<string, cvi> isCVI; //Init visited , cycle, index
    AdjMtx adjMatrix;
    vector<string> shingle_history; // history of pure shingles not merges
    int pl = shingleLen - 1;


    for (int i = 0; i < str.size() - pl + 1; ++i) { // go throw the string
        string temp = str.substr(i, pl);
        if (adjMatrix.addNewVex(temp)) { // create vertices
            isCVI[temp] = {false, false, 0}; // init isCycle and isVisited
        }
    }

    size_t tmp_idx = 0; // arrange shingles lexicographic order (based on map key)
    for (auto &cvi : isCVI) cvi.second.idx = (tmp_idx++);

    string head = str.substr(0, pl);
    isCVI[head].isVisited = true;
    shingle_history.push_back(head); // visit the head

    for (size_t j = pl; j < str.size() - pl + 1; ++j) {
        string cur = str.substr(j, pl);

        auto cur_it = isCVI.find(cur);

        if (!cur_it->second.isVisited)
            cur_it->second.isVisited = true;
        else {
            if (adjMatrix.getWeight(shingle_history.back(), cur) ==
                0) {  // does edge w[i-1] -> w[i] not already exist in G?
                if (cur_it->second.isCycle) {  //does w[i] already belongs to a cycle
                    // It is no longer a Uniquely decodable string, we hoping the last two shingles and assess this again
                    // merge with previous shingle
                    // revisit previous shingle
                    mergeNredo(str.substr(j - shingleLen, shingleLen + 1), shingle_history, j,
                               adjMatrix, isCVI);
                    continue;
                } else { // creating a new cycle
                    isCVI[cur].isCycle = true;
                    for (auto hist_it = shingle_history.rbegin(); hist_it != shingle_history.rend(); ++hist_it) {
                        isCVI[*hist_it].isCycle = true; // label w[i] and all the nodes visited since the previous tp a cycle
                        if (*hist_it == cur)
                            break;
                    }
                }
            } else {
                // stepping along an existing cycle
                if (cur_it->second.isCycle) j++;
            }
        }

        if (adjMatrix.getInDegree(cur) > 1) {
            mergeNredo(str.substr(j - shingleLen, shingleLen + 1), shingle_history, j, adjMatrix, isCVI);
            continue;
        }

        if (!adjMatrix.addWeigth(shingle_history.back(), cur, 1)) {
            throw invalid_argument("setWeight error, a vex does not exist");
        }
        shingle_history.push_back(cur);
        adjMatrix.printGraph();
    }
}

/**
 * record merge with the previous shingle
 * add the merged shingle to graph
 * move index backwards to the head of the merged shingle and try again.
 * @param cur_mg
 * @param shingle_history
 * @param j
 * @param adjMatrix
 * @param isCycVis
 */
void UniqueDecode::mergeNredo(const string cur_mg, vector<string> &shingle_history, size_t &j, AdjMtx &adjMatrix,
                              map<string, cvi> &isCycVis) {
    MergIndex[cur_mg].emplace(isCycVis[cur_mg].idx);
    auto newVex = shingle_history.back() + cur_mg.substr(shingleLen);
    if (adjMatrix.addNewVex(newVex))
        isCycVis[newVex] = {false, false};
    j -= shingle_history.back().size();
    if (!shingle_history.empty())shingle_history.pop_back();
}

string UniqueDecode::reconstructDFS(vector<string> &shingle_set, map<string, std::set<size_t>> &merg_idx) {
    // Sanity Checks
    if (shingle_set.empty()) return "";
    // if merg_idx is empty then we have no merges

    // Shingle set has all unique values
    // sort shingle_set
    // merge shingles
    string str;

    return str;
}

bool UniqueDecode::isAllVisited(vector<pair<string, bool>> isVisited_pair) {
    for (auto it = isVisited_pair.begin(); it != isVisited_pair.end(); ++it) {
        if (!it->second) {
            return false;
        }
    }
    return true;
}

vector<ZZ> UniqueDecode::getShingleSet(const string str) {
    vector<ZZ> res;
    for (int i = 0; i < str.size(); ++i) {
        ZZ shingle = StrtoZZ(str.substr(i, shingleLen));
        auto it = find(res.begin(), res.end(), shingle);
        if (it == res.end()) { // not exist in the res set
            res.push_back(shingle);
        }
    }
    return res;
}
