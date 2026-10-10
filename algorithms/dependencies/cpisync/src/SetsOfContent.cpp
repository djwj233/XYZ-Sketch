//
// Created by Bowen Song on 12/9/18.
//

#include "SetsOfContent.h"

SetsOfContent::SetsOfContent(size_t terminal_str_size, size_t levels, size_t partition,
                             GenSync::SyncProtocol base_set_proto, size_t shingle_size, size_t space)
        : TermStrSize(terminal_str_size), Levels(levels), Partition(partition), baseSyncProtocol(base_set_proto),
          shingle_c(shingle_size), space_c(space) {
    SyncID = SYNC_TYPE::SetsOfContent;
    if (levels > USHRT_MAX or levels < 2)
        throw invalid_argument("Num of Level specified should be between 2 and " + to_string(USHRT_MAX));
    useExisting = false;
//    initResources(initRes);
}

SetsOfContent::~SetsOfContent() {
    for (DataObject *dop : setPointers) delete dop;
}

vector<size_t> SetsOfContent::create_HashSet(size_t str_hash, size_t space, size_t shingle_size) {
    // space and shingle_size has to match between reconciling strings
    // Time Complexity 2n, where n is the string size.
    vector<size_t> hash_val, hash_set;
    auto str_i = dict_geti(str_hash);
    auto str = dict_getstr(str_hash);
    if (str_i.second == 0) return hash_set;
    size_t win_size = floor((str_i.second / Partition) / 2);

    /* ---------original begin  */
    // if the substring is smaller than the terminal string size, we do not partition it anymore.
    if (str_i.second <= TermStrSize) {
        hash_set = {str_hash};
    } else { // else we partitions it
        if (space == 0)  Logger::error_and_quit("Space for windowing is 0 at create_HashSet");
        if (shingle_size < 2)  Logger::error_and_quit("Shingle size should not go under 2");
        for (size_t i = 0; i < str.size() - shingle_size + 1; ++i) {
            std::hash<std::string> shash;
            hash_val.push_back(shash(str.substr(i, shingle_size)) % space);
        }
        size_t prev = str_i.first;

        for (size_t min:local_mins(hash_val, win_size)) {
            min += str_i.first;
            hash_set.push_back(add_i_to_dictionary(prev, min - prev));
            prev = min;
        }

        hash_set.push_back(add_i_to_dictionary(prev, str_i.second - (prev - str_i.first)));
    }
    /* ---------original end  */
    /* ---------fixed win size begin */
//    if (str.size() <= TermStrSize) {
//        hash_set = {str_to_hash(str)};
//    }else {
//        for (int i = 0; i < str.size(); i += win_size) {
//            hash_set.push_back(add_to_dictionary(str.substr(i, win_size)));
//        }
//    }
    /* ---------fixed win size end */

    /* ---------fixed hash value begin */
//    if (str.size() <= TermStrSize) {
//        hash_set = {add_to_dictionary(str)};
//    }else {size_t prev = 0;
//    auto hash_content = hashcontent_dict[str_to_hash(str)];
//                for (size_t min:local_mins(hash_content, win_size)) {
//
//                    min+=shingle_size;
//            hash_set.push_back(add_to_dictionary(str.substr(prev, min - prev)));
//                    hashcontent_dict[str_to_hash(str.substr(prev, min - prev))] = {hash_content.begin()+(prev-shingle_size),hash_content.begin()+(min-shingle_size)};
//
//                    prev = min;
//        }
//        hash_set.push_back(add_to_dictionary(str.substr(prev)));
//        hashcontent_dict[str_to_hash(str.substr(prev))] = {hash_content.begin()+(prev-shingle_size),hash_content.end()};
//
//    }
    /* ---------fixed hash value end */

    // write it to cyc-dict
    auto cyc_it = cyc_dict.find(str_hash);
    if (cyc_it == cyc_dict.end()) // check if cyc exists
        cyc_dict[str_hash] = hash_set; // update cyc_dict
    else if (cyc_it->second != hash_set and cyc_it->second.size() == 1 and cyc_it->second.front() == cyc_it->first)
        cyc_dict[str_hash] = hash_set;// last stage no partition, update cyc_dict
    else if (cyc_it->second != hash_set) // check if it is getting overwritten
        Logger::error_and_quit("More than one answer is possible for cyc_dict");

    return hash_set;
}


void SetsOfContent::go_through_tree() {
    myTree.clear(); // should be redundant

    auto String_Size = pow(Partition, Levels) *
                       TermStrSize; // calculate a supposed string size, a string size that make sense with the parameters

    if (String_Size < 1)
        Logger::error_and_quit(
                "fxn go_through_tree - parameters do not make sense - num of par: " + to_string(Partition) +
                ", num of lvls: " +
                to_string(Levels) + ", Terminal String Size: " + to_string(TermStrSize) + ", Actual String Size: " +
                to_string(myString.size()));

    size_t shingle_size = 2 * pow(shingle_c,
                                  Levels); //(Parameter c, terminal rolling hash window size)
    if (shingle_size < 1)
        Logger::error_and_quit("Consider larger the parameters for auto shingle size to be more than 1");
    size_t space = 4 * pow(space_c, Levels); //126 for ascii content (Parameter terminal space)
    vector<size_t> cur_level;
    // fill up the tree
    myTree.resize(Levels);

    // put up the first level
    update_tree_shingles({add_i_to_dictionary(0, myString.size())}, 0);

/* ---------fixed hash value begin */
//vector<size_t> hash_val;
//            for (size_t i = 0; i < myString.size() - shingle_size + 1; ++i) {
//            std::hash<std::string> shash;
//            hash_val.push_back(shash(myString.substr(i, shingle_size)) % space);
//        }
//    hashcontent_dict[str_to_hash(myString)] = hash_val;
/* ---------fixed hash value end */

    for (int l = 1; l < Levels; ++l) {
//        clock_t time = clock();
        // Fill up Cycle Dictionary for non terminal strings
        for (auto substr_hash:unique_substr_hash(myTree[l - 1])) {

            cur_level = create_HashSet(substr_hash, space, shingle_size);
            update_tree_shingles(cur_level, l);

        }
//        cout << "time: " << (double) (clock() - time) / CLOCKS_PER_SEC << endl;
        space = floor(space / space_c);
        shingle_size = floor(shingle_size / shingle_c);
    }

}


// what i am missing, and what they would be sending to me
void SetsOfContent::prepare_querys(list<DataObject *> &otherMinusSelf) {

    term_query.clear();// should be empty anyway
    cyc_query.clear();

    std::set<size_t> dup;// void duplicate (when a partition stay the same from upper level)

    for (DataObject *shingle_zz: otherMinusSelf) {
        shingle_hash shingle = ZZtoT(shingle_zz->to_ZZ(), shingle_hash());
        if (dup.emplace(shingle.second).second)
            cyc_query.erase(shingle.second); // if duplicated, we want the lower level
        if (dictionary.find(shingle.second) == dictionary.end()) { // if it is not found anywhere
            if (shingle.lvl < Levels - 1)
                cyc_query.emplace(shingle.second, cycle{0, 0, 0});
            else
                term_query.emplace(shingle.second, "");
        }
    }
//    for(auto lvl : theirTree) for (auto shingle : lvl) cout<< shingle<<endl; // TODO: delete this print tree function

}


bool SetsOfContent::answer_queries(std::set<size_t> &theirQueries) {
    cyc_concern.clear();
    term_concern.clear();

    for (auto rit = myTree.rbegin(); rit != myTree.rend(); ++rit) { // search the tree from bottom up
        for (auto shingle : *rit) {
            auto it = theirQueries.find(shingle.second);
            if (it != theirQueries.end()) {
                if (Levels - 1 == shingle.lvl)
                    term_concern.emplace(shingle.second, dict_getstr(shingle.second));
                else {
                    vector<size_t> tmp_vec = cyc_dict[shingle.second];
                    cycle tmp = cycle{.head = tmp_vec.front(), .len = (unsigned int) tmp_vec.size(), .cyc=0};

                    if (!shingle2hash_train(tmp, myTree[shingle.lvl + 1], cyc_dict[shingle.second])) {
                        continue;
                    }
                    cyc_concern[shingle.second] = tmp;
                }
                theirQueries.erase(it); // we solved it, then we get rid of it.
            }
        }
    }
    return theirQueries.empty();
}

void SetsOfContent::update_tree_shingles(vector<size_t> hash_vector, sm_i level) {
    if (myTree.size() <= level)  Logger::error_and_quit("We have exceeded the levels of the tree");
    if (hash_vector.size() > 100)
        cout << "It is advised to not exceed 100 partitions for fast backtracking at Level: " + to_string(level) +
                " Current set size: " + to_string(hash_vector.size()) << endl;
    if (hash_vector.empty()) return;


    map<pair<size_t, size_t>, size_t> tmp;

    // make shingles including a number of start shingles size of shingle size - 1
    for (int i = 0; i < hash_vector.size(); ++i) {
        size_t shingle;
        (i > 0) ? shingle = hash_vector[i - 1] : shingle = 0;

        if (tmp.find({shingle, hash_vector[i]}) != tmp.end())
            tmp[{shingle, hash_vector[i]}]++;
        else
            tmp[{shingle, hash_vector[i]}] = 1;
    }
    if (tmp.empty())
        throw invalid_argument(
                "update_tree shingle is empty");

    for (auto item = tmp.begin(); item != tmp.end(); ++item) {
        if (item->second > USHRT_MAX)
            Logger::error_and_quit(
                    "Shingle occurrance is larger than USHRT_MAX, (backtracking could be infeasiable and our shingle_hash carrier is overflown)");
        myTree[level].insert(
                shingle_hash{item->first.first, item->first.second, level, (sm_i) item->second});
    }

}

// Backtracking using front ab dn back and cycle number
//// functions for backtracking
//bool SetsOfContent::shingle2hash_train(cycle& cyc_info, set<shingle_hash>& shingle_set, vector<size_t>& final_str) {
//
////    // edge case if there is only one shinlge in the set
////    if (shingle_set.empty()) throw invalid_argument("Nothing is passed into shingle2hash_train");
////
////    if (shingle_set.size() == 1) {// edge case of just one shingle
////        if (cyc_info.cyc == 0) {// we find cycle number
////            cyc_info.cyc = 1;
////            cout<<"shingle2hash_train, i should never happend"<<endl; // delete if proven tobe useless
////            return true;
////        } else { // we find string
////            return true;
////        }
////    }
//    auto changed_shingle_set = tree2shingle_dict(shingle_set); // get a shingle dict from a level of a tree for fast next edge lookup
//
//    if (changed_shingle_set.empty()) throw invalid_argument("the shingle_vec provided is empty for shingle2hash_train");
//
//    vector<map<size_t, vector<shingle_hash>>> stateStack;
//    vector<vector<shingle_hash>> nxtEdgeStack;
//    stateStack.push_back(changed_shingle_set);// Init Original state
//    size_t strCollect_size = 0, curEdge =0;
//    vector<size_t> str; // temprary string hash train to last be compared/placed in final_str
//
//
//    for (auto head_shingles : changed_shingle_set[(size_t)0]) {
//        if (cyc_info.head == head_shingles.second) {
//            str.push_back(head_shingles.second);
//            curEdge = head_shingles.second;
//            break;
//        }
//    }
//
//
//    if (cyc_info.cyc == 0) { // find head from "final_str" (we are finding cycle number)
//        //if we only have one, then we are done with cycle number one and head ==tail
//        if (final_str.size() == 1 && cyc_info.head == cyc_info.tail) {
//            cyc_info.cyc = 1;
//            final_str = str;
//            return true;
//        }
//    } else if (cyc_info.cyc > 0) {// find head from "final_str" (we are retrieving the string from cycle number)
//        if (cyc_info.cyc == 1 && cyc_info.head == cyc_info.tail) {
//            final_str = str;
//            return true;
//        }
//    }
//    //    Resources initRes;
////    initResources(initRes); // initiate Recourses tracking
//
//
//    shingle_hash last_edge;
//
//    while (!stateStack.empty() and stateStack.size() == nxtEdgeStack.size() + 1) { // while state stack is not empty
//        vector<shingle_hash> nxtEdges = stateStack.back()[curEdge];
//
//        if (!nxtEdges.empty()) { // If we can go further with this route
//            last_edge = get_nxt_edge(curEdge, nxtEdges.back());
//            nxtEdges.pop_back();
//            nxtEdgeStack.push_back(nxtEdges);
//        } else if (!nxtEdgeStack.empty() and stateStack.size() == nxtEdgeStack.size() + 1 and
//                   !nxtEdgeStack.back().empty()) { //if this route is dead, we should look for other options
//            if (!str.empty()) str.pop_back();
//
//            //look for other edge options
//            last_edge = get_nxt_edge(curEdge, nxtEdgeStack.back().back());
//            nxtEdgeStack.back().pop_back();
//
//            stateStack.pop_back();
//            //(!stateStack.empty()) ? stateStack.push_back(stateStack.back()) : stateStack.push_back(origiState);
//        } else if (!stateStack.empty() and stateStack.size() == nxtEdgeStack.size() + 1 and !nxtEdgeStack.empty() and
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
//                last_edge = get_nxt_edge(curEdge, nxtEdgeStack.back().back());
//                nxtEdgeStack.back().pop_back();
//                stateStack.pop_back();
//            }
//        } else if (stateStack.size() != nxtEdgeStack.size() + 1) {
//            throw invalid_argument("state stack and nxtEdge Stack size miss match" + to_string(stateStack.size())
//                                   + ":" + to_string(nxtEdgeStack.size()));
//        }
//
//        str.push_back(curEdge);
//
//        // Change and register our state for shingle occurrence and nxt edges
//        stateStack.push_back(stateStack.back());
//        for (auto &tmp_shingle: stateStack.back()[last_edge.first]) {
//            if (tmp_shingle == last_edge) {
//                tmp_shingle.occurr--;
//                break;
//            }
//        }
//
//
////
////        if (!resourceMonitor( initRes, MAX_TIME, MAX_VM_SIZE))
////            return false;
//
//        // if we reached a stop point
//        if (curEdge == cyc_info.tail) {
//            strCollect_size++;
//            if (str == final_str || (strCollect_size == cyc_info.cyc and cyc_info.cyc != 0)) {
//                cyc_info.cyc = strCollect_size;
//                final_str = str;
//            }
//        }
//
//        if (strCollect_size == cyc_info.cyc && cyc_info.cyc != 0) {
//            return true;
//        }
//    }
//    return false;
//}

//bool SetsOfContent::empty_state(vector<shingle_hash> state) {
//    for (shingle_hash item : state) {
//        if (item.occurr > 0) return false;
//    }
//    return true;
//}

vector<shingle_hash> SetsOfContent::get_nxt_shingle_vec(const size_t cur_edge,
                                                        const map<size_t, vector<shingle_hash>> &last_state_stack,
                                                        const map<size_t, vector<shingle_hash>> &original_state_stack) {
    vector<shingle_hash> res_vec;

    auto from_stateStack = last_state_stack.find(cur_edge);

    if (from_stateStack != last_state_stack.end()) {
        for (auto tmp_shingle: from_stateStack->second) {
            if (tmp_shingle.occurr > 0) res_vec.push_back(tmp_shingle);
        }
    } else {
        auto cur_it = original_state_stack.find(cur_edge);
        if (cur_it == original_state_stack.end())return res_vec; // there is no possible edge(no edge after this)
        for (auto tmp_shingle: cur_it->second) {
            if (tmp_shingle.occurr > 0) res_vec.push_back(tmp_shingle);
        }
    }

    return res_vec;
}

// functions for backtracking using front, length, and cycle number
bool SetsOfContent::shingle2hash_train(cycle &cyc_info, const std::set<shingle_hash> &shingle_set,
                                       vector<size_t> &final_str) {

    map<size_t, vector<shingle_hash>> original_state_stack = tree2shingle_dict(
            shingle_set); // get a shingle dict from a level of a tree for fast next edge lookup

    if (shingle_set.empty())
        Logger::error_and_quit(
                "the shingle_set provided is empty for shingle2hash_train, we accessed a tree level with no shingle.");

    vector<map<size_t, vector<shingle_hash>>> stateStack;
    vector<vector<shingle_hash>> nxtEdgeStack;
    stateStack.push_back(
            map<size_t, vector<shingle_hash>>());// Init Original state - nothing changed, state stack only records what is changed
    size_t strCollect_size = 0, curEdge = 0;
    vector<size_t> str; // temprary string hash train to last be compared/placed in final_str


    for (auto head_shingles : original_state_stack[(size_t) 0]) {
        if (cyc_info.head == head_shingles.second) {
            str.push_back(head_shingles.second);
            curEdge = head_shingles.second;
            break;
        }
    }


    if (cyc_info.cyc == 0) { // find head from "final_str" (we are finding cycle number)
        //if we only have one, then we are done
        if (final_str.size() == 1 && cyc_info.len == 1) {
            cyc_info.cyc = 1;
            final_str = str;
            return true;
        }
    } else if (cyc_info.cyc > 0) {// find head from "final_str" (we are retrieving the string from cycle number)
        if (cyc_info.cyc == 1 && cyc_info.len == 1) {
            final_str = str;
            return true;
        }
    }
    //    Resources initRes;
//    initResources(initRes); // initiate Recourses tracking


    shingle_hash last_edge;

    while (!stateStack.empty() and stateStack.size() == nxtEdgeStack.size() + 1) { // while state stack is not empty
        vector<shingle_hash> nxtEdges = get_nxt_shingle_vec(curEdge, stateStack.back(), original_state_stack);

        if (!nxtEdges.empty() and str.size() < cyc_info.len) { // If we can go further with this route
            last_edge = get_nxt_edge(curEdge, nxtEdges.back());
            nxtEdges.pop_back();
            nxtEdgeStack.push_back(nxtEdges);
        } else if (!nxtEdgeStack.empty() and stateStack.size() == nxtEdgeStack.size() + 1 and
                   !nxtEdgeStack.back().empty()) { //if this route is dead, we should look for other options
            if (!str.empty()) str.pop_back();

            //look for other edge options
            last_edge = get_nxt_edge(curEdge, nxtEdgeStack.back().back());
            nxtEdgeStack.back().pop_back();

            stateStack.pop_back();
        } else if (!stateStack.empty() and stateStack.size() == nxtEdgeStack.size() + 1 and !nxtEdgeStack.empty() and
                   nxtEdgeStack.back().empty()) {// if this state is dead and we should look back a state
            if (!str.empty()) str.pop_back();
            // look back a state or multiple if we have empty nxt choice (unique nxt edge)
            while (!nxtEdgeStack.empty() and nxtEdgeStack.back().empty()) {
                nxtEdgeStack.pop_back();
                stateStack.pop_back();
                if (!str.empty()) str.pop_back();
            }
            if (nxtEdgeStack.empty()) {
                return false;
            } else if (!nxtEdgeStack.back().empty()) {
                last_edge = get_nxt_edge(curEdge, nxtEdgeStack.back().back());
                nxtEdgeStack.back().pop_back();
                stateStack.pop_back();
            }
        } else if (stateStack.size() != nxtEdgeStack.size() + 1) {
            Logger::error_and_quit("state stack and nxtEdge Stack size miss match" + to_string(stateStack.size())
                                   + ":" + to_string(nxtEdgeStack.size()));
        }

        str.push_back(curEdge);

        // Change and register our state for shingle occurrence and nxt edges
        map<size_t, vector<shingle_hash>> tmp_stack = stateStack.back();
        bool found = false;
        auto from_stateStack = tmp_stack.find(last_edge.first);
        if (from_stateStack != tmp_stack.end()) {// it is in the state_stack(previously touched shingle)
            for (auto &tmp_shingle: from_stateStack->second) {
                if (tmp_shingle == last_edge) {
                    tmp_shingle.occurr--;
                    found = true;
                    break;
                }
            }
        }

        if (!found) { // it is never touched,. fetch from original state
            for (auto tmp_shingle: original_state_stack[last_edge.first]) {
                if (tmp_shingle == last_edge) {
                    tmp_shingle.occurr--;
                }
                tmp_stack[tmp_shingle.first].push_back(tmp_shingle);
            }
        }

        stateStack.push_back(tmp_stack);

//
//        if (!resourceMonitor( initRes, MAX_TIME, MAX_VM_SIZE))
//            return false;

        // if we reached a stop point
        if (str.size() == cyc_info.len) {
            strCollect_size++;
            if (str == final_str || (strCollect_size == cyc_info.cyc and cyc_info.cyc != 0)) {
                cyc_info.cyc = strCollect_size;
                final_str = str;
                auto old_mem = initRes.VmemUsed;
//                resourceMonitor(initRes, 300, SIZE_T_MAX);
                (old_mem < initRes.VmemUsed) ? highwater = initRes.VmemUsed : highwater = old_mem;
            }
        }


        if (strCollect_size == cyc_info.cyc && cyc_info.cyc != 0) {
            //HeapProfilerStop();
            return true;
        }
    }
    return false;
}

std::map<size_t, vector<shingle_hash>> SetsOfContent::tree2shingle_dict(const std::set<shingle_hash> &tree_lvl) {
    // prepare shingle_set in a map, and microsorted(sorted for shingles with same head)
    std::map<size_t, vector<shingle_hash>> res;
    for (shingle_hash shingle : tree_lvl) {
        res[shingle.first].push_back(shingle);
    }


    for (auto &shingle : res) {
        std::sort(shingle.second.begin(), shingle.second.end());
    }
    return res;
}

shingle_hash SetsOfContent::get_nxt_edge(size_t &current_edge, shingle_hash _shingle) {
    current_edge = _shingle.second;
    return _shingle;
}

string SetsOfContent::retriveString() {
    // retrace cycles bottom-up and delete from query after tracing
    string substring;
//    for (auto lvl : theirTree) for (auto item:lvl) cout << item << endl; // TODO: detele this print tree function
    for (int i = myTree.size() - 2; i >= 0; --i) {
        for (shingle_hash shingle : myTree[i]) {
            auto it = cyc_query.find(shingle.second);
            if (it != cyc_query.end()) {
                vector<size_t> tmp;
                substring = "";
                cycle tmp_cyc = it->second;
                if (!shingle2hash_train(tmp_cyc, myTree[i + 1], tmp))
                    substring = dict_getstr(shingle.second);
                for (size_t hash:tmp) {
                    if (dictionary.find(hash) == dictionary.end())
                        cout << "Recover may have failed - Dictionary lookup failed for " << hash << " at level "
                             << shingle.lvl << endl;
                    substring += dict_getstr(hash);
                }
                add_str_to_dictionary(substring);
            }
        }
    }

    return (substring.empty()) ? myString : substring;
}


// functions for  SyncMethods
bool SetsOfContent::addStr(DataObject *str_p, vector<DataObject *> &datum, bool sync) {
    Logger::gLog(Logger::METHOD,
                 "Entering SetsOfContent::addStr. Parameters - num of par: " + to_string(Partition) + ", num of lvls: "
                 + to_string(Levels) + ", Terminal String Size: " + to_string(TermStrSize) + ", Actual String Size: " +
                 to_string(myString.size()));

    myString = str_p->to_string();
    SyncMethod::addStr(str_p, datum, sync); // calls super class for book keeping

    if (myString.empty()) return false;

    if (myString.size() / pow(Partition, Levels) < 1)
        invalid_argument("Terminal String size could end up less than 1, limited at" + to_string(TermStrSize) +
                         ", please consider lessen the levels or number of partitions");

    if (Levels == NOT_SET)  Logger::error_and_quit("Consider set a Level value bigger than 0");


    go_through_tree();

//    //TODO: delete below
//    //show the info of the tree
//    for(auto lvl:myTree) {
//        vector<size_t> lvl_vec;
//        for(auto item : lvl) (item.lvl<myTree.size()-1)?lvl_vec.push_back(cyc_dict[item.second].size()) : lvl_vec.push_back(dict_getstr(item.second).size());
//        sort(lvl_vec.begin(),lvl_vec.end());
//        cout<<"max: "<<lvl_vec.back()<<", min: "<<lvl_vec.front()<<", median: "<<getMedian(lvl_vec)<<", lvl size: "<<lvl_vec.size()<<endl;
//    }
//    std::set<size_t> unique_hashes;
//    for (auto term :myTree.back()){
//        unique_hashes.insert(term.second);
//    }
//    cout<<"We have "<<unique_hashes.size()<<" unique terminal hashes over "<<myTree.back().size() <<" shingles"<<endl;
//    //TODO: delete above

    for (DataObject *dop : setPointers) delete dop;
    setPointers.clear();
    for (auto item : getHashShingles_ZZ()) {
        setPointers.push_back(new DataObject(item));
    }
    datum = setPointers;
    return true;
}

void SetsOfContent::SendSyncParam(const shared_ptr<Communicant> &commSync, bool oneWay) {
    Logger::gLog(Logger::METHOD, "Entering SendSyncParam::SendSyncParam");
    // take care of parent sync method for sync mode
//    SyncMethod::SendSyncParam(commSync);
    commSync->commSend(enumToByte(SyncID));
    commSync->commSend((size_t) TermStrSize);
    commSync->commSend((size_t) Levels);
    commSync->commSend((size_t) Partition);
    if (commSync->commRecv_byte() == SYNC_FAIL_FLAG)
        throw SyncFailureException("Sync parameters do not match.");
    Logger::gLog(Logger::COMM, "Sync parameters match");
}

void SetsOfContent::RecvSyncParam(const shared_ptr<Communicant> &commSync, bool oneWay) {
    Logger::gLog(Logger::METHOD, "Entering SetsOfContent::RecvSyncParam");
    // take care of parent sync method
//    SyncMethod::RecvSyncParam(commSync);

    byte theSyncID = commSync->commRecv_byte();
    size_t TermStrSize_C = (size_t) commSync->commRecv_size_t();
    size_t Levels_C = (size_t) commSync->commRecv_size_t();
    size_t Partition_C = (size_t) commSync->commRecv_size_t();

    if (theSyncID != enumToByte(SyncID) ||
        TermStrSize_C != TermStrSize ||
        Levels_C != Levels ||
        Partition_C != Partition) {
        // report a failure to establish sync parameters
        commSync->commSend(SYNC_FAIL_FLAG);
        Logger::gLog(Logger::COMM, "Sync parameters differ from client to server: Client has (" +
                                   to_string(TermStrSize_C) + "," + to_string(Levels_C) + "," + toStr(Partition_C) +
                                   ").  Server has (" + to_string(TermStrSize) + "," + to_string(Levels) + "," +
                                   to_string(Partition) + ").");
        throw SyncFailureException("Sync parameters do not match.");
    }
    commSync->commSend(SYNC_OK_FLAG);
    Logger::gLog(Logger::COMM, "Sync parameters match");
}

bool SetsOfContent::SyncServer(const shared_ptr<Communicant> &commSync, list<DataObject *> &selfMinusOther,
                               list<DataObject *> &otherMinusSelf) {

    Logger::gLog(Logger::METHOD, "Entering SetsOfContent::SyncServer");
    if (!useExisting) {
        cout<<"i should not be here"<<endl;
        commSync->commListen();
        RecvSyncParam(commSync);
    }

    long mbar = 0;
    if (GenSync::SyncProtocol::IBLTSyncSetDiff == baseSyncProtocol) {
        StrataEst est = StrataEst(sizeof(shingle_hash));

        for (auto item : setPointers) {
            est.insert(item);
        }
        // since main Param are the same, Strata Est parameters would also be the same.
        mbar = (est -= commSync->commRecv_Strata()).estimate();

        commSync->commSend(mbar); // Dangerous cast
    } else if (GenSync::SyncProtocol::CPISync == baseSyncProtocol) {
        mbar = pow(2, 10); // initial prob CPIsync
    }

    // ------------------------- Sync hash shingles

    bool success = false;
    size_t top_mbar = pow(2 * Partition, Levels) * 2; // Upper bound on the number of symmetrical difference
    while (!success and mbar < top_mbar) { // if set recon failed, This can be caused by error rate and small mbar
        success = setReconServer(commSync, mbar, sizeof(shingle_hash), setPointers, selfMinusOther, otherMinusSelf);
        success = ((SYNC_SUCCESS == commSync->commRecv_int()) and success);
        success ? commSync->commSend(SYNC_SUCCESS) : commSync->commSend(SYNC_FAILURE);
        if (success or GenSync::SyncProtocol::IBLTSyncSetDiff != baseSyncProtocol) break;

        Logger::gLog(Logger::METHOD,
                     "SetsOfContent::SyncServer - mbar doubled from " + to_string(mbar) + " to " +
                     to_string(2 * (mbar + 1)));
        mbar = 2 * (mbar + 1);
    }

    // -------------------- get questions
    size_t query_size = commSync->commRecv_size_t();
    std::set<size_t> queries;
    for (size_t i = 0; i < query_size; ++i) {// get queries
        queries.emplace(commSync->commRecv_size_t());
    }

    if (!answer_queries(queries))
        cout << "We failed to answer all the questions, this sync should fail" << endl;


//    cout << "we answered " << cyc_concern.size() << " cycles and " << term_concern.size() << " hashes" << endl;

    for (auto dic : term_concern) {
        string tmp_str = dict_getstr(dic.first);
        if (!tmp_str.empty())
            commSync->commSend(tmp_str);
        else
            commSync->commSend("$");
    }

//    commSync->commSend((int) cyc_concern.size());
    for (auto groupcyc : cyc_concern) {
        commSync->commSend(TtoZZ(groupcyc.second), sizeof(cycle));
    }


//    commSync->commSend(SYNC_SUCCESS);
//    cout<<"Server Close"<<endl;
    if (!useExisting) {
        Logger::gLog(Logger::METHOD, "Server Set Of Content Done");
        commSync->commClose();
    }
    return success;
}

bool SetsOfContent::SyncClient(const shared_ptr<Communicant> &commSync, list<DataObject *> &selfMinusOther,
                               list<DataObject *> &otherMinusSelf, map<string, double> &CustomResult) {

    Logger::gLog(Logger::METHOD, "Entering SetsOfContent::SyncClient");
    if (!useExisting) {
        commSync->commConnect();
        SendSyncParam(commSync);
    }

    long mbar = 0;
    if (GenSync::SyncProtocol::IBLTSyncSetDiff == baseSyncProtocol) {
        StrataEst est = StrataEst(sizeof(shingle_hash));

        for (auto item :setPointers) {
            est.insert(item); // Add to estimator
        }
        commSync->commSend(est.getStrata(), false);

        mbar = commSync->commRecv_long();

    } else if (GenSync::SyncProtocol::CPISync == baseSyncProtocol) {
        mbar = pow(2, 10); // initial prob CPIsync
    }



    // ------------------------- Sync hash shingles


    bool success = false;
    size_t top_mbar = pow(2 * Partition, Levels) * 2; // Upper bound on the number of symmetrical difference
    while (!success and mbar < top_mbar) { // if set recon failed, This can be caused by error rate and small mbar
        success = setReconClient(commSync, mbar, sizeof(shingle_hash), setPointers, selfMinusOther, otherMinusSelf);
        success ? commSync->commSend(SYNC_SUCCESS) : commSync->commSend(SYNC_FAILURE);
        success = (commSync->commRecv_int() == SYNC_SUCCESS) and success;
        if (success or GenSync::SyncProtocol::IBLTSyncSetDiff != baseSyncProtocol) break;

        Logger::gLog(Logger::METHOD,
                     "SetsOfContent::SyncClient - mbar doubled from " + to_string(mbar) + " to " +
                     to_string(2 * (mbar + 1)));
        cout << "SetsOfContent::SyncClient - mbar doubled from " + to_string(mbar) + " to " + to_string(2 * (mbar + 1))
             << endl;
        mbar = 2 * (mbar + 1);
    }

    CustomResult["Partition Sym Diff"] = (selfMinusOther.size() +
                                          otherMinusSelf.size()); // recorder # symmetrical partition difference
    CustomResult["Total Num Partitions"] =
            (getNumofTreeNodes() - selfMinusOther.size()) * 2 + selfMinusOther.size() + otherMinusSelf.size();
//    cout << "After Set Recon, we used comm bytes: " << commSync->getRecvBytesTot() + commSync->getXmitBytesTot() << endl;

    prepare_querys(otherMinusSelf);

    // -------------------- ask questions
    commSync->commSend(cyc_query.size() + term_query.size());
    for (auto cyc:cyc_query) {// ask about cycles
        commSync->commSend(cyc.first);
    }
    for (auto term:term_query) {// ask about cycles
        commSync->commSend(term.first);
    }

//    cout << "After Query, we used comm bytes: " << commSync->getRecvBytesTot() + commSync->getXmitBytesTot() << endl;

// --------------------- get answers from server
//    cout << "We queried " << cyc_query.size() << " cycles and " << term_query.size() << " hashes" << endl;



//    cout << "After Cyc Responce, we used comm bytes: " << commSync->getRecvBytesTot() + commSync->getXmitBytesTot() << endl;
    size_t LiteralData = commSync->getRecvBytesTot() + commSync->getXmitBytesTot();


    // two edge cases:
    // 1: a partition can be not partitioned at an upper-level and partitioned at the next level.
    // 2: a partition can be partitioned to terminal string size limit at an upper level and not be partitioned again later.
    for (int i = 0; i < term_query.size(); ++i) {
        auto tmp = commSync->commRecv_string();
        if (tmp != "$") {
            auto it = cyc_query.find(add_str_to_dictionary(
                    tmp)); // we search from bottom up, if there are strings reached terminal size and not partitioned later, it would not need cycle tracing
            if (it != cyc_query.end())
                cyc_query.erase(it);
        }
    }

    CustomResult["Literal comm"] = commSync->getRecvBytesTot() + commSync->getXmitBytesTot() - LiteralData;


    for (auto &cyc:cyc_query) {
        cyc.second = ZZtoT(commSync->commRecv_ZZ(sizeof(cycle)), cycle());
    }
//    cout << "After Term Responce, we used comm bytes: " << commSync->getRecvBytesTot() + commSync->getXmitBytesTot() << endl;


//    cout<<"Client Close"<<endl;
    if (!useExisting) {
        Logger::gLog(Logger::METHOD, "Client Set Of Content Done");
        commSync->commClose();
    }
    return success;
}


void SetsOfContent::configure(shared_ptr<SyncMethod> &setHost, long mbar, size_t elem_size) {
    if (GenSync::SyncProtocol::IBLTSyncSetDiff == baseSyncProtocol)
        setHost = make_shared<IBLTSync_SetDiff>(mbar, elem_size, true);
    else if (GenSync::SyncProtocol::InteractiveCPISync == baseSyncProtocol)
        setHost = make_shared<InterCPISync>(5, elem_size * 8, 64, 3, true);
    else if (GenSync::SyncProtocol::CPISync == baseSyncProtocol)
        setHost = make_shared<ProbCPISync>(mbar, elem_size * 8, 64, true);
}

bool SetsOfContent::reconstructString(DataObject *&recovered_string, const list<DataObject *> &mySetData) {
    myTree.clear();
    myTree.resize(Levels);
    for (auto s_zz : mySetData) {
        shingle_hash shingle = ZZtoT(s_zz->to_ZZ(), shingle_hash());
        myTree[shingle.lvl].insert(shingle);
    }

    myString = retriveString();
    recovered_string = new DataObject(myString);
    return true;
}

