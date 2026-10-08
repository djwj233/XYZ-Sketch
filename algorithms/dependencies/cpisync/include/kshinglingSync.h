//
// Created by Bowen Song on 9/23/18.
// Use one or all set recon methods
//

#ifndef CPISYNCLIB_KSHINGLINGSYNC_H
#define CPISYNCLIB_KSHINGLINGSYNC_H

#include "GenSync.h"
#include "SyncMethod.h"
#include "Auxiliary.h"
#include "kshingling.h"
#include "StrataEst.h"
#include "IBLTSync_SetDiff.h"
#include "ProbCPISync.h"
#include "InterCPISync.h"

class kshinglingSync : public SyncMethod {
public:
    // Constructors and destructors

    /**
     * Constructor for K-shingling Sync
     * @param set_sync_protocol based on a set sync protocal
     * @param shingle_size has to be at least 2, the higher the size the higher the communication and auxilary space complexity, lower the time cost
     * @param stop_word default '$' which is avoid by randAsciiStr()
     */
    kshinglingSync(GenSync::SyncProtocol set_sync_protocol, const size_t shingle_size,
                   const char stop_word = '$');

    ~kshinglingSync();

    /**
     *
     * @param commSync
     * @param selfString
     * @param otherString
     * @param Estimate whether estimate using existing estimation protocol, set mbar (maximum difference) if false
     * @return
     */
    bool SyncClient(const shared_ptr<Communicant> &commSync, list<DataObject *> &selfMinusOther,
                    list<DataObject *> &otherMinusSelf, map<string, double> &CustomResult) override;

    bool SyncServer(const shared_ptr<Communicant> &commSync, list<DataObject *> &selfMinusOther,
                    list<DataObject *> &otherMinusSelf) override;

    bool reconstructString(DataObject *&recovered_string, const list<DataObject *> &mySetData) override;

    bool addStr(DataObject *str, vector<DataObject *> &datum, bool backtrack) override;


    // Get the name of the sync method
    string getName() override;

    /**
     * Get the amount of virtual mem used in bytes
     * @return virtual mem used in bytes
     */
    long getVirMem() override;

protected:
    bool oneway;
private:
    K_Shingle myKshingle;

    long cycleNum;

    size_t shingleSize = 0, eltSize = 0; // defined by shingle size
    size_t mbar = 0; // defined by set difference estimator ... not necessarily a global variable

    GenSync::SyncProtocol setSyncProtocol;

    //Mem handle
    vector<DataObject *> setPointers;


    /**
     * Configure set recon protocols
     */
    void configurate(shared_ptr<SyncMethod> &setHost);

    string reconString(idx_t cycNum) {
        string str;
        myKshingle.shingle2string(cycNum,str);
        return str;
    };

};

#endif //CPISYNCLIB_KSHINGLINGSYNC_H
