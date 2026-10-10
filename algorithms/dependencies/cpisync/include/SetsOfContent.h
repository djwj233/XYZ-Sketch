//
// Created by Bowen Song on 12/9/18.
//

#ifndef CPISYNCLIB_SETSOFCONTENT_H
#define CPISYNCLIB_SETSOFCONTENT_H


#include <vector>
#include <string>
#include <NTL/ZZ.h>
#include "kshingling.h"
#include "StrataEst.h"
#include "CPI.h"
#include "SyncMethod.h"
#include "DataObject.h"
#include <algorithm>
#include <NTL/ZZ_p.h>
#include "Exceptions.h"
#include "InterCPISync.h"
#include "IBLTSync_SetDiff.h"
#include "ProbCPISync.h"
#include "FullSync.h"
#include "ProcessData.h"
#include <thread>


#include "ForkHandle.h" // tobe removed

using std::vector;
using std::hash;
using std::string;
using namespace NTL;
typedef unsigned short sm_i; // small index for lvl, MAX = 65,535 which is terminal string size * partition^lvl = file string size


//// ---------------------------------- Basic Structures

// describes a cycling using first and last and cycle number. Used in backtracking. We pointou the first, then the last, then cycle value./
struct cycle {
    size_t head;
    unsigned int len, cyc;
};

static bool operator==(const cycle &a, const cycle &b) {
    return a.head == b.head and a.len == b.len and a.cyc == b.cyc;
};

static bool operator!=(const cycle &a, const cycle &b) {
    return !(a == b);
};

static ostream &operator<<(ostream &os, const cycle cyc) {
    os << "head: " + to_string(cyc.head) + ", len: " + to_string(cyc.len) + ", cyc: " +
          to_string(cyc.cyc);
    return os;
};

// we manipulate these shingles in a tree
/**
 * first is the first part of a shingle
 * second is the second part of the shingle
 * occurrence, how manny time this occrred
 * compose states the composite of second
 */
struct shingle_hash {
    size_t first, second;
    sm_i lvl, occurr;
};


//Compare and help order struct shingle_hash from a vector
static bool operator<(const shingle_hash &a, const shingle_hash &b) {
    return (a.first < b.first) or
           (a.first == b.first and a.second < b.second) or
           (a.first == b.first and a.second == b.second and a.occurr < b.occurr);
    // we do not consider ordering cytcle since it would be same to ordering "second"
};


//Compare and help differentiate struct shingle_hash
static bool operator==(const shingle_hash &a, const shingle_hash &b) {
    return a.first == b.first and a.second == b.second and a.occurr == b.occurr and a.lvl == b.lvl;
}

static bool operator!=(const shingle_hash &a, const shingle_hash &b) {
    return !(a == b);
};

static string to_string(const vector<size_t> a) {
    string res;
    for (size_t t : a) res += to_string(t) + ":";
    res.pop_back();
    return res;
};

static ostream &operator<<(ostream &os, const shingle_hash shingle) {
    os << "fst: " + to_string(shingle.first) + ", sec: " + to_string(shingle.second) + ", occ: " +
          to_string(shingle.occurr) + ", lvl: " + to_string(shingle.lvl);
    return os;
};

//// ---------------------------------- inline Functions

inline size_t str_to_hash(const string &str) {
    return std::hash<std::string>{}(str);
};


inline vector<size_t> local_mins(const vector<size_t> &hash_val, size_t win_size) {
    // relying on hashMap sorting (We expect HashMap arrange keys in an increasing order)
    // O(nlg(h)^2) because of the map internal tree balancing
    // minimum partition distance
    if (win_size < 1) {
        cout
                << "Content Partition window size is less than 1 and adjusted to 1. Consider adjusting number of partition levels"
                << endl;
        win_size = 1;
    }


//    clock_t start = clock();
    vector<size_t> mins;

    if (2 * win_size + 1 > hash_val.size())
        return mins;

    map<size_t, size_t> hash_occurr;
    for (size_t j = 0; j < 2 * win_size + 1; ++j) {
        auto it = hash_occurr.emplace(hash_val[j], 1);
        if (!it.second) it.first->second++;
    }


//    cout << "first part:" << (double) (clock() - start) / CLOCKS_PER_SEC << endl;
//    start = clock();
//    cout << win_size << endl;
    for (size_t i = win_size; i < hash_val.size() - win_size; ++i) {
        // this define partition rule to be min or equal instead of strictly less as local min
        if (hash_val[i] <= hash_occurr.begin()->first and i - ((mins.empty()) ? 0 : mins.back()) > win_size)
            mins.emplace_back(i);

        // We stop moving if we can't
        if (i + win_size + 1 == hash_val.size()) break;

        // We skip when incoming hash value is the same as leaving
        if (hash_val[i - win_size] == hash_val[i + win_size + 1]) continue;

        auto it_prev = hash_occurr.find(hash_val[i - win_size]);
        if (it_prev != hash_occurr.end()) {
            if (it_prev->second > 1) it_prev->second--;
            else hash_occurr.erase(it_prev);
        }

        auto it_pos = hash_occurr.emplace(hash_val[i + win_size + 1], 1);
        if (!it_pos.second) it_pos.first->second++;

    }
//    cout << "second part:" << (double) (clock() - start) / CLOCKS_PER_SEC << endl;

    return mins;
}

//inline vector<size_t> local_mins(const vector<size_t> &hash_val, size_t win_size) {
//    // relying on hashMap sorting (We expect HashMap arrange keys in an increasing order)
//    // O(nlgw)
//    // minimum partition distance
//    if (win_size < 1) {
//        cout
//                << "Content Partition window size is less than 1 and adjusted to 1. Consider adjusting number of partition levels"
//                << endl;
//        win_size = 1;
//    }
//
//    clock_t start = clock();
//    vector<size_t> mins;
//    list<size_t> hash_occurr;
//    hash_occurr.resize(2 * win_size + 1);
//    for (size_t j = 0; j < 2 * win_size + 1; ++j) {
//        hash_occurr[j] = hash_val[j];
//    }
//    sort(hash_occurr.begin(), hash_occurr.end());
//    cout << "first part:" << (double) (clock() - start) / CLOCKS_PER_SEC << endl;
//    start = clock();
//    cout << win_size << endl;
//    for (size_t i = win_size; i < hash_val.size() - win_size - 1; ++i) {
//        if (hash_val[i] <= hash_occurr.front() and i - ((mins.empty()) ? 0 : mins.back()) >
//                                                   win_size) // this define partition rule to be min or equal instead of strictly less as local min
//            mins.emplace_back(i);
//
//        hash_occurr.erase(lower_bound(hash_occurr.begin(), hash_occurr.end(), hash_val[i - win_size]));
//        hash_occurr.insert(lower_bound(hash_occurr.begin(), hash_occurr.end(), hash_val[i + win_size + 1]),
//                           hash_val[i + win_size + 1]);
//
//
//    }
//    cout << "second part:" << (double) (clock() - start) / CLOCKS_PER_SEC << endl;
//
//    return mins;
//}

//// -------------------------------------- Sets of Content

class SetsOfContent : public SyncMethod {
public:
    SetsOfContent(size_t terminal_str_size, size_t levels, size_t partition, GenSync::SyncProtocol base_set_proto,
                  size_t shingle_size = 2, size_t ter_space = 2);

    SetsOfContent(GenSync::SyncProtocol base_set_proto, size_t levels, size_t partition, size_t terminal_str_size = 10)
            : TermStrSize(terminal_str_size), Levels(levels), Partition(partition),
              baseSyncProtocol(base_set_proto) {
        useExisting = true;
        shingle_c = 2;
        space_c = 2;
    };

    ~SetsOfContent();

    string retriveString();

// functions for SyncMethods
    bool addStr(DataObject *str, vector<DataObject *> &datum, bool sync) override;

    bool SyncClient(const shared_ptr<Communicant> &commSync, list<DataObject *> &selfMinusOther,
                    list<DataObject *> &otherMinusSelf, map<string, double> &CustomResult) override;

    bool SyncServer(const shared_ptr<Communicant> &commSync, list<DataObject *> &selfMinusOther,
                    list<DataObject *> &otherMinusSelf) override;

    string getName() override { return "Sets of Content"; }

    long getVirMem() override { return (long) highwater; };


protected:
    bool useExisting; /** Use Exiting connection for Communication */

private:
    Resources initRes;
    size_t highwater = 0;

    string myString; // original input string
    size_t TermStrSize, Levels, Partition, shingle_c, space_c;

    GenSync::SyncProtocol baseSyncProtocol;

    vector<DataObject *> setPointers; // garbage collector

    vector<std::set<shingle_hash>> myTree; // the hash shingle tree   // RECONCILLING TARGET

    map<size_t, pair<string, pair<size_t, size_t>>> dictionary;  // dictionary strings

    // origin, cycle information to reform this string rep
    map<size_t, vector<size_t>> cyc_dict; // has to be unique

    //requests
    map<size_t, string> term_concern, term_query;
    map<size_t, cycle> cyc_concern, cyc_query;

    /**
     * Create content dependent partitions based on the input string
     * Update Dictionary
     * @param str origin string to be partitioned
     * @param win_size partition size is 2*win_size
     * @param space smaller-more partitions
     * @param shingle_size inter-relation of the string
     * @return vector of substring hashes in origin string order
     */
    vector<size_t> create_HashSet(size_t str_hash, size_t space = NOT_SET, size_t shingle_size = NOT_SET);


    /**
     * Insert string into dictionary
     * @param str a substring
     * @return hash of the string
     * @throw if there is duplicates, suggest using new/multiple hash functions
     */
    size_t add_str_to_dictionary(const string &str) {
        size_t
                hash = str_to_hash(str);
        dictionary.emplace(hash, make_pair(str, make_pair(0, 0)));
//        if (!it.second and str != it.first->second.first and
//            str != myString.substr(it.first->second.second.first, it.first->second.second.second))
//            throw invalid_argument("Dictionary duplicated suggest using new/multiple hash functions");
        return hash;
    };

    size_t add_i_to_dictionary(size_t start_i, size_t len) {
        size_t
                hash = str_to_hash(myString.substr(start_i, len));
        dictionary.emplace(hash, make_pair("", make_pair(start_i, len)));
//        if (!it.second and myString.substr(it.first->second.second.first, it.first->second.second.second) != myString.substr(start_i, len) and
//            it.first->second.first != myString.substr(start_i, len))
//            throw invalid_argument("Dictionary duplicated suggest using new/multiple hash functions");
        return hash;
    };

    string dict_getstr(size_t hash) {
        auto it = dictionary.find(hash);
        if (it != dictionary.end()) {
            if (it->second.first.empty() and it->second.second.second != 0)
                return myString.substr(it->second.second.first, it->second.second.second);
            else return it->second.first;
        }
        return "";
    }

    // only available for local substrings
    // use it in partition tree construction
    pair<size_t, size_t> dict_geti(size_t hash) {
        auto it = dictionary.find(hash);
        if (it != dictionary.end()) return it->second.second;

        return make_pair(0, 0);
    }

    // extract the unique substring hashes from the shingle_hash vector
    vector<size_t> unique_substr_hash(std::set<shingle_hash> hash_set) {
        std::set<size_t> tmp;
        for (shingle_hash item : hash_set) {
            tmp.insert(item.first);
            tmp.insert(item.second);
        }
        return vector<size_t>(tmp.begin(), tmp.end());

    }

    void update_tree_shingles(vector<size_t> hash_vector, sm_i level);

    // getting the poteintial list of next shingles
    vector<shingle_hash>
    get_nxt_shingle_vec(const size_t cur_edge, const map<size_t, vector<shingle_hash>> &last_state_stack,
                        const map<size_t, vector<shingle_hash>> &original_state_stack);

    // functions for backtracking
    /**
     * peice shingle_hashes back to a vector of hashes in the string order
     * @param shingle_set
     * @param str_order
     * @param final_str a hash train in string order
     */
    bool shingle2hash_train(cycle &cyc_info, const std::set<shingle_hash> &shingle_set, vector<size_t> &final_str);

    std::map<size_t, vector<shingle_hash>> tree2shingle_dict(const std::set<shingle_hash> &tree_lvl);

    shingle_hash get_nxt_edge(size_t &current_edge, shingle_hash _shingle);

    /**
     *
     * @param shingle_hash_theirs
     * @param shingle_hash_mine
     * @param groupIDs
     * @return hashes of unknown
     */
    void prepare_querys(list<DataObject *> &shingle_hash_theirs);

//    void prepare_concerns(const vector<shingle_hash> &shingle_hash_theirs, const vector<shingle_hash> &shingle_hash_mine);

    bool answer_queries(std::set<size_t> &theirQueries);

    void go_through_tree();

    // functions for Sync Methods


    //Get fuzzy_shingle in ZZ O(n*log^2(n))
    vector<ZZ> getHashShingles_ZZ() {
        std::set<ZZ> res;
        for (auto treelvl : myTree) {
            for (auto item:treelvl) {
                res.emplace(TtoZZ(item));
            }
        }
        return vector<ZZ>{res.begin(), res.end()};
    };

    size_t getNumofTreeNodes() {
        size_t
                num_treenodes = 0;
        for (auto lvl : myTree) num_treenodes += lvl.size();
        return num_treenodes;
    }

    void SendSyncParam(const shared_ptr<Communicant> &commSync, bool oneWay = false) override;

    void RecvSyncParam(const shared_ptr<Communicant> &commSync, bool oneWay = false) override;

    void configure(shared_ptr<SyncMethod> &setHost, long mbar, size_t elem_size);

    bool reconstructString(DataObject *&recovered_string, const list<DataObject *> &mySetData) override;

    bool setReconClient(const shared_ptr<Communicant> &commSync, long mbar, size_t elem_size,
                        vector<DataObject *> &full_set, list<DataObject *> &selfMinusOther,
                        list<DataObject *> &otherMinusSelf) {
        selfMinusOther.clear();
        otherMinusSelf.clear();
//        cout << "Client Size: " << full_set.size();
        shared_ptr<SyncMethod> setHost;
        SyncMethod::SyncClient(commSync, selfMinusOther, otherMinusSelf);
        configure(setHost, mbar, elem_size);
        for (DataObject *dop : full_set) {
            setHost->addElem(dop); // Add to GenSync
        }
        bool success = setHost->SyncClient(commSync, selfMinusOther, otherMinusSelf);
        if (not SyncMethod::delGroup(full_set, selfMinusOther))
            Logger::error_and_quit("We failed to delete some set elements");
        for (auto item : otherMinusSelf)
            full_set.push_back(item);

//        cout << " with sym Diff: " << selfMinusOther.size() + otherMinusSelf.size() << " After Sync at : "
//             << full_set.size() << endl;

        return success;
    };

    bool setReconServer(const shared_ptr<Communicant> &commSync, long mbar, size_t elem_size,
                        vector<DataObject *> &full_set, list<DataObject *> &selfMinusOther,
                        list<DataObject *> &otherMinusSelf) {
        selfMinusOther.clear();
        otherMinusSelf.clear();
//        cout << "Server Size: " << full_set.size();
        shared_ptr<SyncMethod> setHost;
        SyncMethod::SyncServer(commSync, selfMinusOther, otherMinusSelf);
        configure(setHost, mbar, elem_size);
        for (DataObject *dop : full_set) {
            setHost->addElem(dop); // Add to GenSync
        }
        return setHost->SyncServer(commSync, selfMinusOther, otherMinusSelf);

//        cout << " with sym Diff: " << selfMinusOther.size() + otherMinusSelf.size() << " After Sync at : "
//             << full_set.size() << endl;
    };
};

#endif //CPISYNCLIB_SETSOFCONTENT_H
