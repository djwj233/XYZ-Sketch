//
// Created by Bowen on 10/3/18.
//

#include "AdjMtx.h"

AdjMtx::AdjMtx() = default;
AdjMtx::~AdjMtx() = default;

void AdjMtx::create(const vector<ZZ>& _ver) {
    for (auto vex : _ver) {
        addNewVex(vex);
    }
}

void AdjMtx::create(const vector<string>& _ver) {
    for (auto vex : _ver) {
        addNewVex(StrtoZZ(vex));
    }
}


bool AdjMtx::addNewVex(string shingle) {
//    auto v = new DataObject(shingle);
//    return addNewVex(v->to_ZZ());
    return addNewVex(StrtoZZ(shingle));
}

bool AdjMtx::addNewVex(ZZ shingle) {
    if(vertex.find(shingle) != vertex.end())
        return false;

    vertex[shingle] = true;
    return true;
}

bool AdjMtx::setWeight(ZZ vfrom, ZZ vto, int set_weight){
    if (contains(vto) and contains(vfrom)) {
        pair<ZZ, ZZ> vexpair{vfrom, vto};
        auto temp = graph.find(vexpair);
        if (temp != graph.end()) {
            temp->second = set_weight;
            if(set_weight == 0) distinct_in_edge[vto].erase(vfrom);
        } else{
            graph.insert(make_pair(vexpair,set_weight));
            distinct_in_edge[vto].insert(vfrom);
        }
        return true;
    }
    return false;
}

bool AdjMtx::addWeigth(ZZ vfrom, ZZ vto, int add_weight){
    return setWeight(vfrom,vto,getWeight(vfrom,vto)+add_weight);
}




bool AdjMtx::delWeigth(ZZ vfrom, ZZ vto, int del_weight){
    return setWeight(vfrom,vto,getWeight(vfrom,vto)-del_weight);
}


void AdjMtx::printGraph(map<ZZ,bool> print_vertex){
    cout << "  ";
    for (auto vex: print_vertex) {
        cout << ZZtoStr(vex.first)<< "|";
    }
    cout << "\n";
    for (auto vexi: print_vertex){
        cout << ZZtoStr(vexi.first)<< "|";
        for (auto vexj: print_vertex){
            cout << getWeight(vexi.first,vexj.first)<< "|";
        }
        cout << "\n";
    }
}


int AdjMtx::getWeight(ZZ vfrom, ZZ vto) {
    auto temp = graph.find({vfrom,vto});
    if (temp != graph.end()){
        return temp->second;
    }
    return 0;
}