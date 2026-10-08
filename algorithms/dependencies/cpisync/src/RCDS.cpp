//
// Created by Bowen Song on 3/30/19.
//

#include "RCDS.h"

//choose set recon proto
// Mini terminal size default 10
// if not set, levels and partition numbers are subject to different string size
RCDS::RCDS(GenSync::SyncProtocol base_set_proto, size_t terminal_str_size, size_t levels, size_t partition)
        : baseSyncProtocol(base_set_proto), TermStrSize(terminal_str_size), Levels(levels), Partition(partition) {

    Quota_mode = true; // If true, we dont change the files after sync and just give a comm quota
}

bool RCDS::addStr(DataObject *str, vector<DataObject *> &datum, bool sync) {
    if (!isFile((FolderName = str->to_string()))) { // we currently just care about folder
        if (FolderName.back() == '/')FolderName.pop_back();
        for (string f_name : walkRelDir(FolderName))
            setPointers.push_back(new DataObject(f_name));
        singleFileMode = false;
        return true;
    } else {
        setPointers.push_back(new DataObject(FolderName));
        singleFileMode = true;
        return true;
    }
    return false;
}

// authoritative source
bool RCDS::SyncServer(const shared_ptr<Communicant> &commSync, list<DataObject *> &selfMinusOther,
                      list<DataObject *> &otherMinusSelf) {
    Logger::gLog(Logger::METHOD, "Entering RCDS::SyncServer");

    commSync->commListen();

    // make sure we ar syncing the same type of things
    commSync->commSend((singleFileMode ? 1 : 0));
    if (commSync->commRecv_byte() != SYNC_OK_FLAG) {
        Logger::error_and_quit("Wrong Input: trying to Sync a folder with a file.");
    }

    if (singleFileMode) {
        Logger::gLog(Logger::METHOD, "We use RCDS");
        int levels = (int) floor(log10(getFileSize(FolderName)));
        int par = 4;
        commSync->commSend(levels);
        stringSyncServer(commSync, FolderName, levels, par);
    } else {

        (FolderName.back() == '/') ? 0 : FolderName += "/";
        vector<DataObject *> heuristic_set = heuristic_check(setPointers);
        setReconServer(commSync, 10e2, sizeof(size_t), heuristic_set, selfMinusOther, otherMinusSelf);


        commSync->commSend(selfMinusOther.size());
        for (DataObject *f:selfMinusOther) {
            string f_name = hash2filename(f->to_ZZ());

            commSync->commSend((f_name.empty()) ? "$" : f_name);
            if (f_name.empty())continue;
            int mode = 0;
            (commSync->commRecv_byte() == SYNC_OK_FLAG) ? mode = 1 : mode = 2;

            if (mode == 1 and getFileSize(FolderName + f_name) < 500) {
                commSync->commSend(SYNC_FAIL_FLAG);
                mode = 2;
            } else if (mode == 1) {
                commSync->commSend(SYNC_OK_FLAG);// check file size
            }

            if (mode == 2) {
                Logger::gLog(Logger::METHOD, "We use full sync");
                if (Quota_mode) {
                    commSync->commSend((long) getFileSize(FolderName + f_name));
                } else {
                    string content = scanTxtFromFile(FolderName + f_name, INT_MAX);
                    commSync->commSend((content.empty() ? "$" : content));
                }
            } else if (mode == 1) {
                Logger::gLog(Logger::METHOD, "We use RCDS");
                int levels = nearbyint(log10(getFileSize(FolderName + f_name)));
                int par = 4;
                commSync->commSend(levels);
                stringSyncServer(commSync, FolderName + f_name, levels, par);
            } else Logger::error_and_quit("Unkonwn Sync Mode, should never happen in RCDS");

        }
    }
    commSync->commClose();
    return true;
}

bool RCDS::SyncClient(const shared_ptr<Communicant> &commSync, list<DataObject *> &selfMinusOther,
                      list<DataObject *> &otherMinusSelf) {
    Logger::gLog(Logger::METHOD, "Entering RCDS::SyncClient");

    commSync->commConnect();

    // make sure we ar syncing the same type of things
    if (commSync->commRecv_int() != (singleFileMode ? 1 : 0)) {
        commSync->commSend(SYNC_FAIL_FLAG);
        Logger::error_and_quit("Wrong Input: trying to Sync a folder with a file.");
    }
    commSync->commSend(SYNC_OK_FLAG);

    if (singleFileMode) {
        Logger::gLog(Logger::METHOD, "We use RCDS");
        int levels = commSync->commRecv_int();
        int par = 4;
        string syncContent = stringSyncClient(commSync, FolderName, levels, par);
        if (!Quota_mode) writeStrToFile(FolderName, syncContent);
    } else {


        (FolderName.back() == '/') ? 0 : FolderName += "/";
        vector<DataObject *> heuristic_set = heuristic_check(setPointers);

        setReconClient(commSync, 10e2, sizeof(size_t), heuristic_set, selfMinusOther, otherMinusSelf);


        size_t diff_size = commSync->commRecv_size_t();
        for (int i = 0; i < diff_size; ++i) {
            //mode 1: I have a file, lets sync.
            //mode 2: i don't have this file, send me the whole thing.
            int mode = 0;
            string f_name;
            if ((f_name = commSync->commRecv_string()) == "$")continue;
            cout << FolderName + f_name << endl;
            if (isPathExist(FolderName + f_name)) {
                commSync->commSend(SYNC_OK_FLAG);
                mode = 1;
            } else {
                commSync->commSend(SYNC_NO_INFO);
                mode = 2;
            }

            if (mode == 1 and commSync->commRecv_byte() == SYNC_FAIL_FLAG) mode = 2;

            if (mode == 2) {
                cout << "Using Full Sync" << endl;
                Logger::gLog(Logger::METHOD, "We use full sync");
                if (Quota_mode) { // quota mode, full sync data transfer is only going to take time.
                    commSync->addRecvBytesQuote(commSync->commRecv_long());
                } else {
                    string content = commSync->commRecv_string();
                    writeStrToFile(FolderName + f_name, (content == "$" ? "" : content));
                }
            } else if (mode == 1) {
                cout << "Using RCDS" << endl;
                Logger::gLog(Logger::METHOD, "We use RCDS");
                int levels = commSync->commRecv_int();
                int par = 4;
                string syncContent = stringSyncClient(commSync, FolderName + f_name, levels, par);
                if (!Quota_mode) writeStrToFile(FolderName + f_name, syncContent);
                cout<<"Bytes: "<<commSync->getRecvBytesTot()+commSync->getXmitBytesTot()<<endl;
                cout<<"Session Bytes:"<<commSync->getRecvBytes()+commSync->getXmitBytes()<<endl;
            } else Logger::error_and_quit("Unkonwn Sync Mode, should never happen in RCDS");

        }
    }

    commSync->commClose();
    return true;
}

bool RCDS::stringSyncServer(const shared_ptr<Communicant> &commSync, string absfilename, int level, int partition) {
    shared_ptr<SyncMethod> stringHost = make_shared<SetsOfContent>(baseSyncProtocol, level, partition);
    vector<DataObject *> Elems;
    list<DataObject *> selfMinusOther, otherMinusSelf, strelems;
    string content = scanTxtFromFile(absfilename, INT_MAX);
    DataObject *str = new DataObject(content);
    stringHost->addStr(str, Elems, false);
    stringHost->SyncServer(commSync, selfMinusOther, otherMinusSelf);
    delete str;
    return true;
}

string
RCDS::stringSyncClient(const shared_ptr<Communicant> &commSync, string absfilename, int level, int partition) {
    shared_ptr<SyncMethod> stringHost = make_shared<SetsOfContent>(baseSyncProtocol, level, partition);
    vector<DataObject *> Elems;
    list<DataObject *> selfMinusOther, otherMinusSelf, strelems;
    string content = scanTxtFromFile(absfilename, INT_MAX);
    DataObject *res, *str = new DataObject(content);
    map<string, double> CustomResult;
    try {
        stringHost->addStr(str, Elems, false);
    } catch (std::exception &e) {
        cout << e.what() << endl;
    }
    stringHost->SyncClient(commSync, selfMinusOther, otherMinusSelf, CustomResult);
    stringHost->reconstructString(res, strelems);
    content = res->to_string();
    delete res;
    delete str;
    return content;
}