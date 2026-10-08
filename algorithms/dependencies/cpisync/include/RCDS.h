//
// Created by Bowen Song on 3/28/19.
//
// A shell for "SetsofContent" to handle folder and file (Recursive Content-Dependent Shingling Sync)
// Using heuristics compare digest of two files that has the same name, size.
// if same, skip reconciling them.
// If files are too small, (under certain limit), if diff, just full sync

// Folder: (current implementation)
// get folder dests and put all names in a list with abs path
// go through each and ask the other side to sync with one of the modes:
// 1: no file name match - send the entire file over
// 2: file name match size not match - set of content sync
// 3: file name and size match - skip (we think they are the same)

#include <SetsOfContent.h>

#ifndef CPISYNCLIB_RCDS_H
#define CPISYNCLIB_RCDS_H

class RCDS : public SyncMethod {
public:
    RCDS(GenSync::SyncProtocol base_set_proto, size_t terminal_str_size = 10, size_t levels = NOT_SET,
         size_t partition = NOT_SET);

    ~RCDS() { for (auto dop:setPointers)delete dop; };

    /**
     * Init a folder
     * @param str
     * @param datum
     * @param sync
     * @return
     */
    bool addStr(DataObject *str, vector<DataObject *> &datum, bool sync) override; // add folder or file location

    bool SyncClient(const shared_ptr<Communicant> &commSync, list<DataObject *> &selfMinusOther,
                    list<DataObject *> &otherMinusSelf) override; // heristics

    bool SyncServer(const shared_ptr<Communicant> &commSync, list<DataObject *> &selfMinusOther,
                    list<DataObject *> &otherMinusSelf) override;

    string getName() override { return "Recursive Content-Dependent Shingling Sync"; }

private:
    GenSync::SyncProtocol baseSyncProtocol;
    size_t TermStrSize, Levels, Partition;
    string FolderName;
    vector<DataObject *> setPointers;
    map<size_t, string> Dict_fname;
    bool Quota_mode, singleFileMode;


    void configure(shared_ptr<SyncMethod> &setHost, long mbar, size_t elem_size) {
        if (GenSync::SyncProtocol::IBLTSyncSetDiff == baseSyncProtocol)
            setHost = make_shared<IBLTSync_SetDiff>(mbar, elem_size, true);
        else if (GenSync::SyncProtocol::InteractiveCPISync == baseSyncProtocol)
            setHost = make_shared<InterCPISync>(5, elem_size * 8, 64, 3, true);
        else if (GenSync::SyncProtocol::CPISync == baseSyncProtocol)
            setHost = make_shared<ProbCPISync>(mbar, elem_size * 8, 64, true);
        setHost = make_shared<InterCPISync>(5, elem_size * 8, 64, 3, true);
    }

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

    /**
     * we check name and file size
     */
    vector<DataObject *> heuristic_check(vector<DataObject *> &filename_set) {
        vector<DataObject *> res;
        for (DataObject *f_name: filename_set) {
//            string filename = FolderName+f_name->to_string();
            string heuristic_info = f_name->to_string() + to_string(getFileSize(FolderName + f_name->to_string()));
            size_t digest = str_to_hash(heuristic_info);
            if (!Dict_fname.emplace(digest, f_name->to_string()).second)
                Logger::error_and_quit("Duplicated File name or Hash Collision");
            res.push_back(new DataObject(to_ZZ(digest)));
        }
        return res;
    }

    string hash2filename(ZZ zz){ return Dict_fname[conv<size_t >(zz)];};

    bool stringSyncServer(const shared_ptr<Communicant> &commSync,string absfilename,int level, int partition);
    string stringSyncClient(const shared_ptr<Communicant> &commSync,string absfilename,int level, int partition);

};

#endif //CPISYNCLIB_RCDS_H
