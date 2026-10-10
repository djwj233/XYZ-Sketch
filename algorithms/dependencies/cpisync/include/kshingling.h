//
// Created by Bowen Song on 9/15/18.
// Based on
//

#ifndef CPISYNCLIB_KSHINGLING_H
#define CPISYNCLIB_KSHINGLING_H

#include <vector>
#include <utility>
#include <string>
#include <NTL/ZZ.h>
#include <sstream>
#include "Auxiliary.h"
#include "DataObject.h"
#include "ProcessData.h"

using std::vector;
using std::hash;
using std::string;
using std::stringstream;
using std::pair;
using namespace NTL;

typedef unsigned int idx_t;

static const double MAX_TIME = 300; // secs
static const size_t MAX_VM_SIZE = 1e10; //bytes

struct shingle {
    string vex, edge;
    idx_t occurr;
};

//Compare and help differentiate struct shingle

//Compare and help order struct shingle_hash from a vector
static bool operator<(const shingle &a, const shingle &b) {
    return (a.vex < b.vex) or
           (a.vex == b.vex and a.edge < b.edge) or
           (a.vex == b.vex and a.edge == b.edge and a.occurr < b.occurr);
};

static bool operator==(const shingle &a, const shingle &b) {
    return a.vex == b.vex and a.edge == b.edge and a.occurr == b.occurr;
};

static bool operator!=(const shingle &a, const shingle &b) {
    return !(a == b);
};

class K_Shingle {
public:
    // Communicant needs to access the internal representation of an kshingle to send it and receive it
//    friend class Communicant;

    /**
     * Construct a K_Shingle set object with k as each shingle size
     * @param k fixing shingle size to be k
     */
    K_Shingle(const size_t shingle_size, const char stop_word = '$');

    // Default deconstructor
    ~K_Shingle();

    idx_t inject(const string str, bool back_track) {
        shingleMAP.clear();
        orig_string = stopword + str + stopword;
        create(str);
        idx_t cyc_num = 0;
        if (back_track)
            shingle2string(cyc_num, orig_string);
        return cyc_num;
    };

    /**
     * Iterative function reconstructing string from a shingle set
     * Operation returns multiple strings if Eulerian Cycle exists in the modified De Brujin Graph representation of the shingle set
     * @param changed_shingleSet a set of shingles available at a recursive stage
     * @param curEdge current edge vertex sting
     * @param strColl a vector of strings that is returnable from the shingle set, Returnable object
     * @param str current string
     * @return whether this process is successfully.
     */
    bool shingle2string(idx_t& str_order, string &final_str);

    // get methods
    /**
     * @return The number of element in she shingle set
     */
    size_t getSetSize() const {
        return setSize;
    }

    void clearSet() {
        shingleSet.clear();
        shingleMAP.clear();
    }

    vector<shingle> getShingles() { return shingleSet; }


    char getStopWord() const {
        return stopword;
    }


    string getOriginString() {
        if (orig_string.empty() || orig_string == string(2, stopword)) return "";
        return orig_string;
    }


    size_t getUsedVM() { // bytes
        return initRes.VmemUsed;
    };

    double getUsedTime() { //secs
        return initRes.TimeElapsed;
    }

    void addtoshingleset(shingle s) {
        shingleSet.emplace_back(s);
        shingleMAP[s.vex].emplace_back(s);
    }

private:
    // local data

    //default constructor
    K_Shingle();

    size_t initVM = 0, setSize; // keeps track of Ram usage
    Resources initRes;
    // k and stopword better be the same between two hosts, or should be transferred.
    size_t k = 0;  //shingle size

    const char stopword;  // default stop word is "$"

    // resetable parameters
    map<string, vector<shingle>> shingleMAP; // transfer shingleSet to other host
    vector<shingle> shingleSet;

    string orig_string;  // original string with stopwords on both ends

    /**
     * GET THE NEXT POSSIBLE EDGES
     */
    vector<shingle> getNxtShingle_vec(string cur, const map<string, vector<shingle>> &last_state);


    shingle mv2nxtshingle(string &cur, shingle _shingle);

    /**
     * create a set of k-shingles from String str
     * This operation always succeed
     * @param str Original string
     */
    void create(const string str);

};

#endif //CPISYNCLIB_KSHINGLING_H
