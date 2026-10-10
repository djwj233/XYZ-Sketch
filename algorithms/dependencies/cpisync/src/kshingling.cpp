//
// Created by Bowen on 9/18/18.
// Break string into a fixed length set of shingles
// reconstruct a possible string from shingle set
// calculate if that is the only sting available
//

#include "kshingling.h"


K_Shingle::K_Shingle(const size_t shingle_size, const char stop_word)
        : k(shingle_size), stopword(stop_word) {
    virtualMemMonitor(initVM);

}

K_Shingle::~K_Shingle() {}

void K_Shingle::create(const string str) {
    //  Sanity check

    if (str.find(stopword) != string::npos) {
        Logger::error_and_quit("Input string includes Stopword, consider changing the stop word");
    }

    if (k >= str.size()) {
        Logger::error_and_quit("Shingle size has to be smaller than the string length");
        //return false;
    } else if (k < 2) {
        Logger::gLog(Logger::METHOD, "Minimum shingle size has to be bigger than 1, we changed it to 2");
        k = 2;
    } else if (str.empty()) {
        Logger::gLog(Logger::METHOD, "Empty Input String");
    }
    //create a set of shingle in shingleSet
    // first do it in map, then vector
    std::map<shingle, idx_t> shingle_map;
    for (int i = 0; i < orig_string.size() - k + 1; ++i) {
        shingle tmp = shingle{.vex = orig_string.substr(i, k - 1), .edge=orig_string.substr(i + k - 1, 1), .occurr=1};
        auto map_it = shingle_map.find(tmp);
        if (map_it == shingle_map.end())
            shingle_map.emplace(tmp, 1);
        else
            map_it->second++;
    }
    for (auto item : shingle_map) { // dump them in shingle set
        shingle tmp = item.first;
        tmp.occurr = item.second;
        addtoshingleset(tmp);
    }
}

vector<shingle> K_Shingle::getNxtShingle_vec(string cur, const map<string, vector<shingle>> &last_state) {
    if (cur.empty()) Logger::error_and_quit("Empty starting string");
    vector<shingle> res_lst;
    auto last_it = last_state.find(cur);
    if (last_it != last_state.end()) {
        for (auto tmp_shingle : last_it->second) {
            if (tmp_shingle.occurr > 0) res_lst.emplace_back(tmp_shingle);
        }
    } else {
        auto org_it = shingleMAP.find(cur);
        if (org_it == shingleMAP.end()) return res_lst;
        else return org_it->second;
    }
    return res_lst;
}

// worst case space complexity |s|N^2, N = number of shingles, s = shingle, but it is faster.
bool K_Shingle::shingle2string(idx_t& str_order, string &final_str) {

    // Sanity Check
    if (shingleMAP.empty()) Logger::error_and_quit("Shingles not created, please insert string before backtracking");

    vector<map<string, vector<shingle>>> stateStack; // record changed shingles from last step
    vector<vector<shingle>> nxtEdgeStack;
    stateStack.emplace_back(map<string, vector<shingle>>());
//    initResources(initRes); // initiate Recourses tracking
    idx_t current_cyc = 0;
    string cur, str;

    shingle last_shingle;
    // find head
    if (final_str.empty()) {
        for (auto s : shingleMAP) {
            if (s.first[0] == stopword) {
                if (s.second.size() > 1)
                    Logger::error_and_quit(
                            "String start has " + to_string(s.second.size()) + " possible following edges.");

                cur = s.first;
                break;
            }
        }
    } else {
        cur = final_str.substr(0, k-1);
    }


    str = cur;
    while (!stateStack.empty() and stateStack.size() == nxtEdgeStack.size() + 1) { // while state stack is not empty
        vector<shingle> nxtEdges = getNxtShingle_vec(cur, stateStack.back());

        if (!nxtEdges.empty() and not (str.size() > 1 and str.back() == stopword)) { // if we can go further
            last_shingle = mv2nxtshingle(cur, nxtEdges.back());
            nxtEdges.pop_back();
            nxtEdgeStack.push_back(nxtEdges);
        } else if (!nxtEdgeStack.empty() and !nxtEdgeStack.back().empty()) { //see if we have other path at the current stage
            last_shingle = mv2nxtshingle(cur, nxtEdgeStack.back().back());
            nxtEdgeStack.back().pop_back();
            stateStack.pop_back();
            str.pop_back();
        } else if (!nxtEdgeStack.empty() and nxtEdgeStack.back().empty()) { // walk back see other path
            if(str.size()>1) str.pop_back();
            while (!nxtEdgeStack.empty() and nxtEdgeStack.back().empty()) {
                nxtEdgeStack.pop_back();
                stateStack.pop_back();
                if (str.size() > 1) str.pop_back();
            }
            if (nxtEdgeStack.empty()) return false;
            if (!nxtEdgeStack.back().empty()) {
                last_shingle = mv2nxtshingle(cur, nxtEdgeStack.back().back());
                nxtEdgeStack.back().pop_back();
                stateStack.pop_back();
            }
        }
        str += cur.back();
        auto last_state = stateStack.back();
        auto last_it = last_state.find(last_shingle.vex);
        if (last_it != last_state.end()) {
            for (auto &tmp:last_it->second) {
                if (tmp == last_shingle) {
                    tmp.occurr--;
                    break;
                }
            }
        } else {
            auto org_it = shingleMAP.find(last_shingle.vex);
            if (org_it == shingleMAP.end())
                Logger::error_and_quit("We can not find a shingle, set reconciliation failed.");
            for (auto tmp : org_it->second) {
                if (tmp == last_shingle)tmp.occurr--;
                last_state[tmp.vex].push_back(tmp);
            }
        }
        stateStack.push_back(last_state);


//        if (!resourceMonitor(initRes, MAX_TIME, MAX_VM_SIZE)) return false;

        // if we reached a stopping criteria
        if (str.size() > 1 and str.back() == stopword) {
            current_cyc++;
            if (str == final_str || (current_cyc == str_order and str_order != 0)) {
                str_order = current_cyc;
                str.pop_back();
                final_str = str.substr(1);
                //HeapProfilerStop();
                return true;
            }
        }

    }


    return false;
}

shingle K_Shingle::mv2nxtshingle(string &cur, shingle _shingle) {
    cur = _shingle.vex.substr(1) + _shingle.edge;
    return _shingle;
}
//void K_Shingle::shingle2string_recursion(vector<pair<string,int>> changed_shingleSet, string curEdge, int &strCollect_ind,int &str_order,string &finalstr, string str) {
//
//    auto lst = getEdges(curEdge.substr(1), changed_shingleSet);
//    for (auto it = lst.begin(); it != lst.end(); ++it) {
//        pair<string, int> tempedge = *it;
//        str += tempedge.first.substr(k - 1);
//
//        if (it->second > 1) {
//            it->second--;
//            find(changed_shingleSet.begin(), changed_shingleSet.end(), tempedge)->second--;
//        } else {
//            //lst.erase(it);
//            changed_shingleSet.erase(remove(changed_shingleSet.begin(), changed_shingleSet.end(), tempedge), changed_shingleSet.end());
//        }
//        if (tempedge.first.substr(k - 1) == stopword) {
//            if (changed_shingleSet.size() == 0) {
//                strCollect_ind++;
//                if (str == orig_string || strCollect_ind - 1 == str_order) {
//                    str_order = strCollect_ind - 1;
//                    finalstr = str.substr(1,str.size()-2);
//                }
//            }
//
//        }
//        shingle2string(changed_shingleSet, tempedge.first, strCollect_ind, str_order, finalstr, str);
//        if (strCollect_ind-1==str_order && str_order!=-1){
//            return;
//        }
//        if (tempedge.second > 1) {
//            it->second++;
//            find(changed_shingleSet.begin(), changed_shingleSet.end(), tempedge)->second++;
//        } else {
//            //lst.push_back(*it);
//            changed_shingleSet.push_back(tempedge);
//        }
//        str.pop_back();
//    }
//}


// iterative method using indexing
//void K_Shingle::incrementEdgeCount(const string ver, map<string,idx_t> & shingle_map) {
//    if (!ver.empty()) {
//
//        auto it = shingle_map.find(ver);
//        (it != shingle_map.end()) ? shingle_map[ver] += 1 : shingle_map[ver] = 1;
//
//    } else {
//        throw invalid_argument("No string in vertex");
//    }
//}
//
//
//vector<idx_t>  K_Shingle::getEdgeIdx(const string verStart, vector<idx_t> changed_shingleOccur) {
//    if (!verStart.empty()) { // verStart not empty
//        vector<idx_t> templst;
//        // sorted list, start to find it then, as soon as the next is not starting with the substring, bail.
//        for (idx_t i = 0; i < shingleSet.size(); ++i) {
//            if (shingleSet[i].first.substr(0,verStart.size()) == verStart && changed_shingleOccur[i]>0){
//                templst.push_back(i);
//            }
//        }
//        return templst; // no hit unless last element is included in the list
//    } else {
//        throw invalid_argument("No vertex start string for searching");
//    }
//}
//
//pair<string,idx_t> K_Shingle::reconstructStringBacktracking(idx_t strOrder) {
//    idx_t strCollect_size = 0;
//    string startString;
//
//
//    //sort it in lexicographic order
//    sort(shingleSet.begin(), shingleSet.end());
//    auto changed_shingleSet = shingleSet;
//
//    // find the head
//    for (auto it = changed_shingleSet.begin(); it != changed_shingleSet.end(); ++it) {
//        if (it->first[0] == stopword) {
//            startString = it->first;
//            it->second--;
//            break;
//        }
//    }
//// Get the string or string cycle number
//    if (!startString.empty()) {
////        // Delete the first edge by value
//        string final_str;
//        shingle2string(changed_shingleSet, startString, strCollect_size, strOrder, final_str, startString);
//        if (strCollect_size == 0 || strCollect_size < strOrder) { // failed to recover a string
//            return make_pair("", 0);  // return 0 for fail
//        }
//        return make_pair(final_str, strOrder);
//    } else {
//        throw invalid_argument("Shingle Set does not have a start point");
//    }
//}
//
//bool K_Shingle::shingle2string(vector<pair<string,idx_t>> changed_shingleOccur, string curEdge, idx_t &strCollect_size,
//                               idx_t &str_order, string &final_str, string str) {
//
//
///**
// * nxtEdgeStack: [[idx of nxt edges];[];...] Register the state of nxt possible edges
// * stateStack: [[occr of shingles ];[];...] Register the state of shigle set occurrences
// */
//    vector<vector<idx_t>> nxtEdgeStack, stateStack; // check and can not be negative
//    //initResources(initRes); // initiate Recourses tracking
//
//    vector<idx_t> origiState(changed_shingleOccur.size()); // compose the original state
//    for (idx_t i = 0; i < changed_shingleOccur.size(); ++i) {
//        origiState[i] = changed_shingleOccur[i].second;
//    }
//
//    // predict auxilary Mem size
//    pMem = sizeof(idx_t)*changed_shingleOccur.size()*(orig_string.size()-k)*2;
//
//    // Init Original state
//    stateStack.push_back(origiState);
//    idx_t nxt_idx = 0;
//    while (!stateStack.empty() and stateStack.size() == nxtEdgeStack.size() + 1) { // while state stack is not empty
//
////        if (!virtualMemMonitor(initVM))
////            return false;
//
//        //printMemUsage();
//        auto nxtEdges = getEdgeIdx(curEdge.substr(1), stateStack.back());
//
//        if (!nxtEdges.empty()) { // If we can go further with this route
//            nxt_idx = nxtEdges.back();
//            nxtEdges.pop_back();
//            nxtEdgeStack.push_back(nxtEdges);
//        } else if (!nxtEdgeStack.empty() and stateStack.size() == nxtEdgeStack.size() + 1 and
//                   !nxtEdgeStack.back().empty()) { //if this route is dead, we should look for other options
//            if (!str.empty()) str.pop_back();
//
//            //look for other edge options
//            nxt_idx = nxtEdgeStack.back().back();
//            nxtEdgeStack.back().pop_back();
//
//            stateStack.pop_back();
//            //(!stateStack.empty()) ? stateStack.push_back(stateStack.back()) : stateStack.push_back(origiState);
//        } else if (!stateStack.empty() and stateStack.size() == nxtEdgeStack.size() + 1 and
//                   nxtEdgeStack.back().empty()) {// if this state is dead and we should look back a state
//            if (!str.empty()) str.pop_back();
//            // look back a state or multiple if we have empty nxt choice (unique nxt edge)
//            while (!nxtEdgeStack.empty() and nxtEdgeStack.back().empty()) {
//                nxtEdgeStack.pop_back();
//                stateStack.pop_back();
//                if (!str.empty()) str.pop_back();
//            }
//            if (nxtEdgeStack.empty()) {
//                return false;
//            } else if (!nxtEdgeStack.back().empty()) {
//                nxt_idx = nxtEdgeStack.back().back();
//                nxtEdgeStack.back().pop_back();
//                stateStack.pop_back();
//            }
//        } else if (stateStack.size() != nxtEdgeStack.size() + 1) {
//            throw invalid_argument("state stack and nxtEdge Stack size miss match" + to_string(stateStack.size())
//                                   + ":" + to_string(nxtEdgeStack.size()));
//        }
//
//        if (!resourceMonitor( initRes, MAX_TIME, MAX_VM_SIZE))
//            return false;
//
//        str += shingleSet[nxt_idx].first.back();
//
//        // Change and register our state for shingle occurrence and nxt edges
//        stateStack.push_back(stateStack.back());
//        stateStack.back()[nxt_idx] -= 1;
//
//        curEdge = shingleSet[nxt_idx].first;
//
//        // if we reached a stop point
//        if (shingleSet[nxt_idx].first.back() == stopword and emptyState(stateStack.back())) {
//            strCollect_size++;
//            if (str == orig_string || (strCollect_size == str_order and str_order != 0)) {
//                str_order = strCollect_size;
//                final_str = str.substr(1, str.size() - 2);
//            }
//        }
//
//        if (strCollect_size == str_order && str_order != 0) {
//            resourceReport(initRes);
//            return true;
//        }
//    }
//    return false;
//}
