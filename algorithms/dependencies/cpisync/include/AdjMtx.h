//
// Created by Bowen on 10/3/18.
// This is for adjacency matrix
// Allow negative weights for directed graph
//
//

#ifndef CPISYNCLIB_ADJMTX_H
#define CPISYNCLIB_ADJMTX_H


#include <NTL/ZZ.h>
#include <vector>
#include <utility>
#include <string>
#include "Auxiliary.h"
#include "DataObject.h"
#include <map>

using std::vector;
using std::string;
using std::stringstream;
using std::pair;
using namespace NTL;

class AdjMtx {
public:
    // CONTRUCTOR AND DISTRUCTOR
    AdjMtx();

    ~AdjMtx();

    /**
     * append to vertex list
     * @param shingle <ZZ>
     * @return
     */
    bool addNewVex(string shingle);

    /**
     * Add a list of vertex at once
     * @param _ver list of shingles
     */
    void create(const vector<string> &_ver);

    /**
     * list of shingles
     * @return list of vertices
     */
    vector<string> getGraphVex() {
        vector<string> res;
        for (auto vex : vertex) res.push_back(ZZtoStr(vex.first));
        return res;
    }

    /**
     * number pf verticies in the graph
     * @return
     */
    size_t getNumVex() {
        return vertex.size();
    }

    /**
     * check if vex is one of the Vertices
     * @param vex
     * @return
     */
    bool contains(string vex) {
        return vertex.find(StrtoZZ(vex)) != vertex.end();
    }

    /**
     * print the graph of concerned vertex
     * @param print_vertex ONLY applicable to string input
     */

    void printGraph() { printGraph(vertex); };

    // wrapper functions
    bool addWeigth(string vfrom, string vto, int add_weight = 1) {
        return addWeigth(StrtoZZ(vfrom), StrtoZZ(vto), add_weight);
    };

    bool setWeight(string vfrom, string vto, int set_weight) {
        return setWeight(StrtoZZ(vfrom), StrtoZZ(vto), set_weight);
    };

    bool delWeigth(string vfrom, string vto, int del_weight = 1) {
        return delWeigth(StrtoZZ(vfrom), StrtoZZ(vto), del_weight);
    };

    int getWeight(string vfrom, string vto) {
        return getWeight(StrtoZZ(vfrom), StrtoZZ(vto));
    };

    // special fxn for UD getting the number of unique incomming edges
    int getInDegree(string edge) {
        auto it = distinct_in_edge.find(StrtoZZ(edge));
        return (it == distinct_in_edge.end()) ? 0 : it->second.size();
    };

protected:
    bool addNewVex(ZZ shingle);

    void create(const vector<ZZ> &_ver);

    void printGraph(map<ZZ, bool> print_vertex);

    bool contains(ZZ vex) {
        return vertex.find(vex) != vertex.end();
    }

    /**
     * change the weight of graph, allow negative
     * @param vfrom
     * @param vto
     * @param del_weight
     * @return
     */
    bool addWeigth(ZZ vfrom, ZZ vto, int add_weight = 1);

    bool setWeight(ZZ vfrom, ZZ vto, int set_weight);

    bool delWeigth(ZZ vfrom, ZZ vto, int del_weight = 1);

    int getWeight(ZZ vfrom, ZZ vto);

private:
    map<pair<ZZ, ZZ>, int> graph;  // if two vex tex is not connected, it would not be in the graph.
    map<ZZ, bool> vertex;

    map<ZZ, std::set<ZZ>> distinct_in_edge;    // special for UD, registering distinctive incoming node
};


#endif //CPISYNCLIB_ADJMTX_H
