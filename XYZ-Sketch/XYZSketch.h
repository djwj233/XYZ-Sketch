#ifndef XYZSketch_H
#define XYZSketch_H

#include <bits/stdc++.h>
#include "tools.cpp"
using namespace std;

struct Cell {
    int c; poly p; Cell();
} ;
struct XYZSketch {
    vector<Cell> B;
    int size();
    void init();
    Cell & operator [] (int);
    friend XYZSketch operator - (XYZSketch, XYZSketch);
    void InsertToCell(int, int);
    void Update(int);
    pair<vector<int>, vector<int> > PureCellDecode(int);
    bool PureCellVerify(int);
    void Extract(int, int);
    variant<pair<vi, vi>, bool> Decode();
} ;
XYZSketch Encode(vector<int>) ;
#endif