//
// Created by Bowen Song on 9/23/18.
//


#include "kshinglingSync.h"

kshinglingSync::kshinglingSync(GenSync::SyncProtocol set_sync_protocol, const size_t shingle_size,
                               const char stop_word) : myKshingle(shingle_size, stop_word),
                                                       setSyncProtocol(set_sync_protocol), shingleSize(shingle_size) {
    oneway = true;
    auto setProto_avil = {GenSync::SyncProtocol::IBLTSyncSetDiff, GenSync::SyncProtocol::CPISync,
                          GenSync::SyncProtocol::InteractiveCPISync};
    if (find(setProto_avil.begin(), setProto_avil.end(), set_sync_protocol) == setProto_avil.end())
        throw invalid_argument("Base Set Reconciliation Protocol not supported.");
}

kshinglingSync::~kshinglingSync() {
    for (DataObject *dop : setPointers) delete dop;
}

//Alice
bool kshinglingSync::SyncClient(const shared_ptr<Communicant> &commSync, list<DataObject *> &selfMinusOther,
                                list<DataObject *> &otherMinusSelf, map<string, double> &CustomResult) {
    Logger::gLog(Logger::METHOD, "Entering kshinglingSync::SyncClient");
    bool syncSuccess = true;
    shared_ptr<SyncMethod> setHost;
    // call parent method for book keeping
    SyncMethod::SyncClient(commSync, selfMinusOther, otherMinusSelf);
    // create kshingle

    // connect to server
    commSync->commConnect();
    // ensure that the kshingle size and stopword equal those of the server
    if (!commSync->establishKshingleSend(myKshingle.getStopWord(), oneway)) {
        Logger::gLog(Logger::METHOD_DETAILS,
                     "Kshingle parameters do not match up between client and server!");
        syncSuccess = false;
    }

    // send cycNum
    if (!oneway) {
        if (cycleNum == 0)
            throw invalid_argument(
                    "cycleNum Not prepared by this host, consider enable backtracking before reconciling strings");
        commSync->commSend(cycleNum);
    }
    cycleNum = commSync->commRecv_long();


    // estimate difference
    if (GenSync::SyncProtocol::IBLTSyncSetDiff == setSyncProtocol) {
        StrataEst est = StrataEst(sizeof(shingle));

        for (auto item : myKshingle.getShingles()) {
            auto tmp = new DataObject(TtoZZ(item));
            setPointers.push_back(tmp);
            est.insert(tmp); // Add to estimator
        }

        // since Kshingling are the same, Strata Est parameters would also be the same.
        commSync->commSend(est.getStrata(), false);

        mbar = commSync->commRecv_long(); // cast long to long long

    }

    // reconcile difference + delete extra
    configurate(setHost);
    for (DataObject *dop : setPointers) {
        setHost->addElem(dop); // Add to GenSync
    }

    if (!setHost->SyncClient(commSync, selfMinusOther, otherMinusSelf))
        syncSuccess = false;



    return syncSuccess;
}

//Bob
bool kshinglingSync::SyncServer(const shared_ptr<Communicant> &commSync, list<DataObject *> &selfMinusOther,
                                list<DataObject *> &otherMinusSelf) {
    Logger::gLog(Logger::METHOD, "Entering kshinglingSync::SyncServer");
    bool syncSuccess = true;
    shared_ptr<SyncMethod> setHost;
    SyncMethod::SyncServer(commSync, selfMinusOther, otherMinusSelf);

    commSync->commListen();
    if (!commSync->establishKshingleRecv(myKshingle.getStopWord(), oneway)) {
        Logger::gLog(Logger::METHOD_DETAILS,
                     "Kshingle parameters do not match up between client and server!");
        syncSuccess = false;
    }

    // send cycNum
    auto tmpcycleNum = cycleNum;
    if (!oneway) cycleNum = commSync->commRecv_long();
    commSync->commSend(tmpcycleNum);

    // estimate difference
    if (GenSync::SyncProtocol::IBLTSyncSetDiff == setSyncProtocol) {
        StrataEst est = StrataEst(sizeof(shingle));

        for (auto item : setPointers) {
            est.insert(item); // Add to estimator
        }

        // since Kshingling are the same, Strata Est parameters would also be the same.
        auto theirStarata = commSync->commRecv_Strata();
        mbar = (est -= theirStarata).estimate();
//        mbar = mbar + mbar / 2; // get an upper bound
        commSync->commSend(mbar); // Dangerous cast

    }

    // reconcile difference + delete extra
    configurate(setHost);
    for (DataObject *dop : setPointers) {
        setHost->addElem(dop); // Add to GenSync
    }


    if (setHost->SyncServer(commSync, selfMinusOther, otherMinusSelf))
        syncSuccess = false;

    return syncSuccess;
}

void kshinglingSync::configurate(shared_ptr<SyncMethod> &setHost) {

    int err = 8;// negative log of acceptable error probability for probabilistic syncs

    if (setSyncProtocol == GenSync::SyncProtocol::CPISync) {
        setHost = make_shared<ProbCPISync>(1e4, sizeof(shingle) * 8, err, true);
    } else if (setSyncProtocol == GenSync::SyncProtocol::InteractiveCPISync) {

        setHost = make_shared<InterCPISync>(5, sizeof(shingle) * 8, err, 3, true);
        //(ceil(log(set_size))>1)?:2;
    } else if (setSyncProtocol == GenSync::SyncProtocol::IBLTSyncSetDiff) {

        setHost = make_shared<IBLTSync_SetDiff>(mbar, sizeof(shingle), true);
    }
}

bool kshinglingSync::reconstructString(DataObject *&recovered_string, const list<DataObject *> &mySetData) {

    //if (cycleNum != 0)
        myKshingle.clearSet();

    for (auto elem: mySetData) {
        //change here - send pair
        myKshingle.addtoshingleset(ZZtoT(elem->to_ZZ(), shingle()));
    }
    recovered_string = new DataObject(reconString(cycleNum));
    return cycleNum != 0;
}

bool kshinglingSync::addStr(DataObject *str, vector<DataObject *> &datum, bool backtrack) {
    // call parent add
    SyncMethod::addStr(str, datum, backtrack);
    myKshingle.clearSet();

    cycleNum = myKshingle.inject(str->to_string(), backtrack);

    for (DataObject *dop : setPointers) delete dop; //Clear SetPointers if any
    for (shingle item : myKshingle.getShingles()) {
        setPointers.push_back(new DataObject(TtoZZ(item)));
    }
    datum = setPointers;
    return (!backtrack or cycleNum > 0);
}

long kshinglingSync::getVirMem() {
    return myKshingle.getUsedVM();
}


string kshinglingSync::getName() { return "This is a kshinglingSync of string reconciliation"; }
