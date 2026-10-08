//
// Created by Bowen on 10/9/18.
//

#ifndef CPISYNCLIB_PERFORMANCEDATA_H
#define CPISYNCLIB_PERFORMANCEDATA_H

#include "GenSync.h"
#include "kshinglingSync.h"
#include "StrataEst.h"
#include "ForkHandle.h"
#include <fstream>
#include <numeric>
#include <thread>

static multiset<size_t> ContentDeptPartition(vector<size_t> hash_val, size_t win_size) {

    vector<size_t> mins; // min positions
    map<size_t, size_t> hash_occurr;
    for (size_t j = 0; j < 2 * win_size; ++j) {
        auto it = hash_occurr.find(hash_val[j]);
        if (it != hash_occurr.end())
            it->second++;
        else
            hash_occurr[hash_val[j]] = 1;
    }

    for (size_t i = win_size + 1; i < hash_val.size() - win_size + 1; ++i) {
        if (hash_val[i - 1] <= hash_occurr.begin()->first and i - ((!mins.empty()) ? mins.back() : 0) > win_size)
            mins.push_back(i - 1);
        auto it_prev = hash_occurr.find(hash_val[i - win_size - 1]);
        if (it_prev != hash_occurr.end())
            it_prev->second--;

        auto it_pos = hash_occurr.find(hash_val[i + win_size]);
        if (it_pos != hash_occurr.end())
            it_pos->second++;
        else
            hash_occurr[hash_val[i + win_size]] = 1;
    }

    return multiset<size_t>(mins.begin(), mins.end());
}



class PerformanceData {
public:
    PerformanceData(int tes_pts) {
        tesPts = tes_pts;
    };

    ~PerformanceData();

    enum class StringReconProtocol {
        UNDEFINED,
        BEGIN,
        KshinglingSync = BEGIN,
        SetsOfContent,
        END
    };


    void kshingle3D(GenSync::SyncProtocol setReconProto, vector<int> edit_distRange,
                    vector<int> str_sizeRange, int confidence, string (*stringInput)(int, string), string src,
                    int portnum);

    void setsofcontent(GenSync::SyncProtocol setReconProto, vector<int> edit_distRange,
                       vector<int> str_sizeRange, vector<int> levelRange, vector<int> partitionRange,
                       vector<int> TershingleLen, vector<int> space, int confidence, string (*stringInput)(int, string),
                       string src, int instance, int mode);

    void setsofcontentREPO(GenSync::SyncProtocol setReconProto, vector<int> edit_distRange, int confidence,
                           string repo_dir, int instance);

    void strataEst3D(pair<size_t, size_t> set_sizeRange, int confidence);

    void cascadingMissmatch(vector<int> num_error, vector<int> win, vector<int> space);


private:

    int mbar, tesPts;
    size_t bits;


    /**
     * explore relation of edit distance and set difference in kshingling
     * @param shingle_len
     * @param str_size
     * @param edit_dist
     */
    int setdiff(int shingle_len, int str_size, int edit_dist);


};


class PlotRegister { // Export Data into a txt file for external code to graph
public:
    PlotRegister();

    ~PlotRegister();

    void create(string _title, vector<string> _labels);// init - open a file with a title and labels
    void add(vector<string> datum); // add to data
    void update(); // bulk insert to what is in the data, clear data, close file after.
private:

    void init();

    string title; // title of the graph, used as file name
    vector<string> labels; //label including units
    vector<vector<string>> data; // Number of
};

#endif //CPISYNCLIB_PERFORMANCEDATA_H
