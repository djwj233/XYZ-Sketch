////
//// Created by Bowen on 10/9/18.
////

#include "PerformanceData.h"

PerformanceData::~PerformanceData() = default;

void PerformanceData::kshingle3D(GenSync::SyncProtocol setReconProto, vector<int> edit_distRange,
                                 vector<int> str_sizeRange, int confidence, string (*stringInput)(int, string),
                                 string src, int portnum) {
    string protoName, str_type;
    if (GenSync::SyncProtocol::CPISync == setReconProto) protoName = "CPISync";
    if (GenSync::SyncProtocol::IBLTSyncSetDiff == setReconProto) protoName = "IBLTSyncSetDiff";
    if (GenSync::SyncProtocol::InteractiveCPISync == setReconProto) protoName = "InteractiveCPISync";

    if (*stringInput == randAsciiStr) str_type = "RandAscii";
    if (*stringInput == randTxt) str_type = "RandText";

    PlotRegister plot;
    plot.create("kshingle " + protoName + " " + str_type,
                {"Str Size", "Edit Diff", "Comm (bits)", "Time Set(s)", "Time Str(s)",
                 "Space (bits)", "Set Recon True", "Str Recon True"});
    //TODO: Separate Comm, and Time, Separate Faile rate.

    for (int str_size : str_sizeRange) {
        cout << to_string(str_size) << endl;
        edit_distRange.clear();
        for (int i = 1; i <= tesPts; ++i) edit_distRange.push_back((int) ((str_size * i) / 4000));
        for (int edit_dist : edit_distRange) {

//            int shingle_len = ceil(log2(str_size));
            int shingle_len = ceil(log10(str_size));

            for (int con = 0; con < confidence; ++con) {


                GenSync Alice = GenSync::Builder().
                        setProtocol(setReconProto).
                        setStringProto(GenSync::StringSyncProtocol::kshinglingSync).
                        setComm(GenSync::SyncComm::socket).
                        setPort(portnum).
                        setShingleLen(shingle_len).
                        build();


                DataObject *Alicetxt = new DataObject(stringInput(str_size, src));

                Alice.addStr(Alicetxt, false);
                GenSync Bob = GenSync::Builder().
                        setProtocol(setReconProto).
                        setStringProto(GenSync::StringSyncProtocol::kshinglingSync).
                        setComm(GenSync::SyncComm::socket).
                        setPort(portnum).
                        setShingleLen(shingle_len).
                        build();

                DataObject *Bobtxt = new DataObject(randStringEdit((*Alicetxt).to_string(), edit_dist));

// Flag true includes backtracking, return false if backtracking fails in the alloted amoun tog memory
                auto str_s = clock();
//                    struct timespec start, finish;
//                    double str_time;

//                    clock_gettime(CLOCK_MONOTONIC, &start);

                bool success_StrRecon = Bob.addStr(Bobtxt, true);

//                    clock_gettime(CLOCK_MONOTONIC, &finish);
//
//                    str_time = (finish.tv_sec - start.tv_sec);
//                    str_time += (finish.tv_nsec - start.tv_nsec) / 1000000000.0;
                double str_time = (double) (clock() - str_s) / CLOCKS_PER_SEC;


                multiset<string> alice_set;
                for (auto item : Alice.dumpElements()) alice_set.insert(item->to_string());
                multiset<string> bob_set;
                for (auto item : Bob.dumpElements()) bob_set.insert(item->to_string());

                int success_SetRecon = multisetDiff(alice_set,
                                                    bob_set).size();// separate set recon success from string recon
//                    auto bobtxtis = Alice.dumpString()->to_string();
//                    bool success_SetRecon = ((*Bobtxt).to_string() ==
//                                             Alice.dumpString()->to_string()); // str Recon is deterministic, if not success , set recon is the problem
                forkHandleReport report = forkHandle(Alice, Bob, false);

                plot.add({to_string(str_size), to_string(edit_dist), to_string(report.bytesXTot),
                          to_string(report.CPUtime), to_string(str_time),
                          to_string(Bob.getVirMem(0)), to_string(success_SetRecon), to_string(success_StrRecon)});

                delete Alicetxt;
                delete Bobtxt;

            }
        }
        plot.update();
    }
}


void PerformanceData::cascadingMissmatch(vector<int> num_error, vector<int> win, vector<int> space) {
    PlotRegister plot;
    vector<string> catag{"win", "space", "symmetric diff", "Total"};
    plot.create("cascading Mismatch", catag);
    for (int w : win) {
        for (int s:space) {
            for (int e : num_error) {
                for (int k = 0; k < 1000; ++k) {

                    int string_size = 2000;
                    vector<size_t> vec;

                    for (int i = 0; i < string_size; ++i) {
                        vec.push_back(rand() % s);
                    }
                    vector<size_t> vec1{vec.begin(), vec.end()};
                    for (int j = 0; j < e; ++j) {
                        vec1[randLenBetween(0, 2 * w + 1)] = rand() % s;
                    }

                    auto SA = ContentDeptPartition(vec, w);
                    auto SB = ContentDeptPartition(vec1, w);

                    plot.add({to_string(w), to_string(e), to_string(multisetDiff(SA, SB).size()),
                              to_string(SA.size() + SB.size())});
                }
                plot.update();
            }
        }
    }
}

void PerformanceData::setsofcontent(GenSync::SyncProtocol setReconProto, vector<int> edit_distRange,
                                    vector<int> str_sizeRange, vector<int> levelRange, vector<int> partitionRange,
                                    vector<int> TershingleLen, vector<int> space, int confidence,
                                    string (*stringInput)(int, string), string src, int instance, int mode) {


    string protoName, str_type;
    if (GenSync::SyncProtocol::IBLTSyncSetDiff == setReconProto) protoName = "IBLTSyncSetDiff";
    if (GenSync::SyncProtocol::InteractiveCPISync == setReconProto) protoName = "InteractiveCPISync";
    if (GenSync::SyncProtocol::CPISync == setReconProto) protoName = "CPISync";

    if (*stringInput == randAsciiStr) str_type = "RandAscii";
    if (*stringInput == randTxt and src.find("Code") != string::npos) str_type = "RandCode";
    if (*stringInput == randTxt and src.find("Book") != string::npos) str_type = "RandBook";


    string last_passed_before_exception;
    vector<string> catag{"", "", "Total Comm (bytes)", "Literal comm", "Partition Sym Diff",
                         "Total Num Partitions", "Time Tree(s)",
                         "Time Recon(s)", "Time Backtrack (included in Time Recon) (s)", "Set Recon Success",
                         "Str Recon Success", "Tree Heap SIze", "High Water Heap", "Rsync Comm"};
    PlotRegister plot;
    if (mode == 1) {
        catag[0] = "Sting Size";
        catag[1] = "Edit Dist ";
        plot.create("Sets of Content " + protoName + " " + str_type + "P" + to_string(partitionRange.front()) + "CL" +
                    to_string(instance), catag);
    } else if (mode == 2) {
        catag[0] = "Sting Size";
        catag[1] = "Edit Dist %";
        plot.create("Sets of Content " + protoName + " " + str_type + "P" + to_string(partitionRange.front()) + "CL" +
                    to_string(instance), catag);
    } else if (mode == 3) {
        catag[0] = "Level";
        catag[1] = "Partition";
        plot.create("Sets of Content " + protoName + " " + str_type + "STR" + to_string(str_sizeRange.front()) + "ED" +
                    to_string(edit_distRange.front()) + "LP" + to_string(instance), catag);
    } else if (mode == 4) {
        catag[0] = "String Size";
        catag[1] = "Space constant";
        plot.create("Sets of Content " + protoName + " " + str_type + "Str " + to_string(str_sizeRange.front()) + "ED" +
                    to_string(edit_distRange.front()) + "SS" + to_string(instance), catag);
    } else if (mode == 5) {
        catag[0] = "Str Size";
        catag[1] = "lvl";
        plot.create("Sets of Content " + protoName + " " + str_type + "ED " + to_string(edit_distRange.front()) + "P" +
                    to_string(partitionRange.front()) + "SL" + to_string(instance), catag);
    }

    //TODO: Separate Comm, and Time, Separate Fail rate.
    for (int i = 0; i < str_sizeRange.size(); ++i) {
//        cout << " - Sets of Content " + protoName + " " + str_type + "str Size: " + to_string(str_size) << endl;
        for (int edit_dist : edit_distRange) {

            for (int lvl:levelRange) {
//                cout << " - Sets of Content " + protoName + " " + str_type + "(" + to_string(lvl) + " lvl)" << endl;

                for (int par: partitionRange) {

                    for (int t : TershingleLen) {
                        for (int s : space) {
                            vector<string> report_vec;

                            // change lvels
                            if (mode == 1 or mode == 4) {
                                if (levelRange.size() != str_sizeRange.size() and space.size() != str_sizeRange.size())
                                    throw invalid_argument(
                                            "In mode 1, String size range and lvl range should have the same size");
                                lvl = levelRange[i];
                                s = space[i];

                            } else if (mode == 3) {
                                s = par * 2;
                            }
                            for (int con = 0; con < confidence; ++con) {
                                try {
//                            cout << "level: " << lvl << ", partitions: " << par
//                                 << ", Confidence: " << con << endl;

                                    DataObject *Alicetxt = new DataObject(stringInput(str_sizeRange[i], src));

                                    last_passed_before_exception = "Alice Create String"; // success Tag


                                    Resources initRes;
                                    initResources(initRes);

                                    GenSync Alice = GenSync::Builder().
                                            setStringProto(GenSync::StringSyncProtocol::SetsOfContent).
                                            setProtocol(setReconProto).
                                            setComm(GenSync::SyncComm::socket).
                                            setTerminalStrSize(10).
                                            setNumPartitions(par).
                                            setShingleLen(t).
                                            setSpace(s).
                                            setlvl(lvl).
                                            setPort(8005 + instance).
                                            build();

                                    last_passed_before_exception = "Alice GenSync"; // success Tag




                                    clock_t strStart = clock();
                                    Alice.addStr(Alicetxt, false);
                                    auto tree_time = (double) (clock() - strStart) / CLOCKS_PER_SEC;
                                    resourceReport(initRes);

                                    last_passed_before_exception = "Alice Add String"; // success Tag

                                    GenSync Bob = GenSync::Builder().
                                            setStringProto(GenSync::StringSyncProtocol::SetsOfContent).
                                            setProtocol(setReconProto).
                                            setComm(GenSync::SyncComm::socket).
                                            setTerminalStrSize(10).
                                            setNumPartitions(par).
                                            setShingleLen(t).
                                            setSpace(s).
                                            setlvl(lvl).
                                            setPort(8005 + instance).
                                            build();

                                    last_passed_before_exception = "Bob GenSync"; // success Tag

                                    string bobtmpstring;
                                    if (mode == 2)
                                        bobtmpstring = randStringEditBurst((*Alicetxt).to_string(),
                                                                           str_sizeRange[i] / edit_dist, src);
                                    else
                                        bobtmpstring = randStringEditBurst((*Alicetxt).to_string(), edit_dist, src);

                                    //(int) (str_size / edit_dist));
//                                    if (bobtmpstring.size() <
//                                        str_sizeRange[i] * 0.5) // keep strings about the same size
//                                        bobtmpstring += randCharacters(str_sizeRange[i] - bobtmpstring.size());
//                                    else if (bobtmpstring.size() >
//                                             str_sizeRange[i] * 1.5) // keep strings about the same size
//                                        bobtmpstring = bobtmpstring.substr(0, str_sizeRange[i]);

                                    DataObject *Bobtxt = new DataObject(bobtmpstring);

                                    last_passed_before_exception = "Bob Create String"; // success Tag



                                    Bob.addStr(Bobtxt, false);

                                    last_passed_before_exception = "Bob Add String"; // success Tag

                                    forkHandleReport report = forkHandle(Alice, Bob, false);

                                    last_passed_before_exception = "String Recon"; // success Tag

                                    bool success_StrRecon = (Alice.dumpString()->to_string() == Bobtxt->to_string());


                                    rsync_stats r_res{0, 0, 0};

                                    if (mode != 2 and mode != 3) {
                                        // rsync recon
                                        writeStrToFile("Alice" + to_string(instance) + ".txt", Alicetxt->to_string());
                                        writeStrToFile("Bob" + to_string(instance) + ".txt", Bobtxt->to_string());

                                        r_res = getRsyncStats("Alice" + to_string(instance) + ".txt",
                                                              "Bob" + to_string(instance) + ".txt");
                                    }


                                    if (!success_StrRecon) // success Tag
                                        last_passed_before_exception +=
                                                ", Alice str size: " + to_string(Alice.dumpString()->to_string().size())
                                                + "Bob Str size: " + to_string(Bobtxt->to_string().size());

                                    report_vec = {"", "",
                                                  to_string(report.bytesXTot + report.bytesRTot),
                                                  to_string(Alice.getCustomResult("Literal comm")),
                                                  to_string(Alice.getCustomResult("Partition Sym Diff")),
                                                  to_string(Alice.getCustomResult("Total Num Partitions")),
                                                  to_string(tree_time),
                                                  to_string(report.totalTime),
                                                  to_string(Alice.getCustomResult("Str Reconstruction Time")),
                                                  to_string(report.success),
                                                  to_string(success_StrRecon),
                                                  to_string(initRes.VmemUsed),
                                                  to_string(Alice.getVirMem(0)),
                                                  to_string(r_res.xmit + r_res.recv)};

                                    delete Alicetxt;
                                    delete Bobtxt;
                                } catch (const std::exception &exc) {
                                    cout << "We failed after " << last_passed_before_exception << endl;
                                    std::cerr << exc.what() << endl;
                                    report_vec = {to_string(0), to_string(0), to_string(0), to_string(0), to_string(0),
                                                  to_string(0), to_string(0), to_string(0), to_string(0), to_string(0),
                                                  to_string(0), to_string(0), to_string(0), to_string(0)};

                                }
                                if (mode == 1) {
                                    report_vec[0] = to_string(str_sizeRange[i]);
//                                    report_vec[1] = to_string((double) 1 / edit_dist);
                                    report_vec[1] = to_string(edit_dist);
                                    plot.add(report_vec);
                                } else if (mode == 2) {
                                    report_vec[0] = to_string(str_sizeRange[i]);
                                    report_vec[1] = to_string((double) 1 / edit_dist);
                                    plot.add(report_vec);
                                } else if (mode == 3) {
                                    report_vec[0] = to_string(lvl);
                                    report_vec[1] = to_string(par);
                                    plot.add(report_vec);
                                } else if (mode == 4) {
                                    report_vec[0] = to_string(str_sizeRange[i]);
                                    report_vec[1] = to_string(s);
                                    plot.add(report_vec);
                                } else if (mode == 5) {
                                    report_vec[0] = to_string(str_sizeRange[i]);
                                    report_vec[1] = to_string(lvl);
                                    plot.add(report_vec);
                                }
                                plot.update();
                            }

                            if (mode == 1 and mode == 2) break;
                        }

                    }
                }

                if (mode == 1 or mode == 4) break;
            }
        }
    }

}


void PerformanceData::setsofcontentREPO(GenSync::SyncProtocol setReconProto, vector<int> edit_distRange, int confidence,
                                        string repo_dir, int instance) {


    string protoName, str_type;
    if (GenSync::SyncProtocol::IBLTSyncSetDiff == setReconProto) protoName = "IBLTSyncSetDiff";
    if (GenSync::SyncProtocol::InteractiveCPISync == setReconProto) protoName = "InteractiveCPISync";
    if (GenSync::SyncProtocol::CPISync == setReconProto) protoName = "CPISync";


    string last_passed_before_exception;
    vector<string> catag{"", "", "Total Comm (bytes)", "Literal comm", "Partition Sym Diff",
                         "Total Num Partitions", "Time Tree(s)",
                         "Time Recon(s)", "Time Backtrack (included in Time Recon) (s)", "Set Recon Success",
                         "Str Recon Success", "Tree Heap SIze", "High Water Heap", "Rsync Comm"};
    PlotRegister plot;

    catag[0] = "REPO Name";
    catag[1] = "Edit Dist ";
    plot.create("Sets of Content " + protoName + " REPO", catag);


    vector<string> report_vec;
    for (string repo_name : getFolderList(repo_dir)) {
        for (int edit_dist:edit_distRange) {
            for (int con = 0; con < confidence; ++con) {

                repo_name = repo_name.substr(repo_name.rfind("/"));
                // cp folder
                string orgfolder = repo_dir + repo_name;
                string edfolder = repo_dir + "/changed";
                subprocess_commandline(
                        ("rsync -r " + orgfolder + " " + edfolder).c_str());
                // edit folder
                randInFolderChange(edit_dist, 300, edfolder);
                // SCSync every file in folder
                auto org = walkabsDir(orgfolder);
                auto ed = walkabsDir(edfolder);
                auto org_files = vector<string>{org.begin(), org.end()};
                auto ed_files = vector<string>{ed.begin(), ed.end()};
                sort(org_files.begin(), org_files.end());
                sort(ed_files.begin(), ed_files.end());
                if (org_files.size() != ed_files.size()) invalid_argument("folders are different");
                long comm_cost = 0;
                double literal_cost = 0;
                for (int i = 0; i < org_files.size(); ++i) {
                    // get total time and comm
                    // rsync folder and get comm and time ...

                    try {
cout<<org_files[i]<<endl;
                        DataObject *Alicetxt = new DataObject(scanTxtFromFile( org_files[i],INT_MAX));

                        last_passed_before_exception = "Alice Create String"; // success Tag
                        size_t lvl = (size_t)floor(log10(Alicetxt->to_string().size()));

                        Resources initRes;
//                    initResources(initRes);

                        GenSync Alice = GenSync::Builder().
                                setStringProto(GenSync::StringSyncProtocol::SetsOfContent).
                                setProtocol(setReconProto).
                                setComm(GenSync::SyncComm::socket).
                                setTerminalStrSize(10).
                                setNumPartitions(4).
                                setShingleLen(2).
                                setSpace(8).
                                setlvl(lvl).
                                setPort(8005 + instance).
                                build();

                        last_passed_before_exception = "Alice GenSync"; // success Tag




                        clock_t strStart = clock();
                        Alice.addStr(Alicetxt, false);
//                        auto tree_time = (double) (clock() - strStart) / CLOCKS_PER_SEC;
//                    resourceReport(initRes);

                        last_passed_before_exception = "Alice Add String"; // success Tag

                        GenSync Bob = GenSync::Builder().
                                setStringProto(GenSync::StringSyncProtocol::SetsOfContent).
                                setProtocol(setReconProto).
                                setComm(GenSync::SyncComm::socket).
                                setTerminalStrSize(10).
                                setNumPartitions(4).
                                setShingleLen(2).
                                setSpace(8).
                                setlvl(lvl).
                                setPort(8005 + instance).
                                build();

                        last_passed_before_exception = "Bob GenSync"; // success Tag



                        DataObject *Bobtxt = new DataObject(scanTxtFromFile( org_files[i],INT_MAX));

                        last_passed_before_exception = "Bob Create String"; // success Tag



                        Bob.addStr(Bobtxt, false);

                        last_passed_before_exception = "Bob Add String"; // success Tag

                        forkHandleReport report = forkHandle(Alice, Bob, false);

                        last_passed_before_exception = "String Recon"; // success Tag

                        bool success_StrRecon = (Alice.dumpString()->to_string() == Bobtxt->to_string());


                        comm_cost += report.bytesXTot + report.bytesRTot;

                        literal_cost += Alice.getCustomResult("Literal comm");

                        delete Alicetxt;
                        delete Bobtxt;
                    } catch (const std::exception &exc) {
                        cout << "We failed after " << last_passed_before_exception << endl;
                        std::cerr << exc.what() << endl;
                        report_vec = {to_string(randTxt(INT_MAX, org_files[i]).size()),
                                      to_string(randTxt(INT_MAX, org_files[i]).size()), to_string(0), to_string(0),
                                      to_string(0),
                                      to_string(0), to_string(0), to_string(0), to_string(0), to_string(0),
                                      to_string(0), to_string(0), to_string(0), to_string(0)};

                    }
                }
                auto r_res = getRsyncStats(orgfolder,
                                           edfolder);


                report_vec = {repo_name, to_string(edit_dist),
                              to_string(comm_cost),
                              to_string(literal_cost),
                              to_string(0),
                              to_string(0),
                              to_string(0),
                              to_string(0),
                              to_string(0),
                              to_string(0),
                              to_string(0),
                              to_string(0),
                              to_string(0),
                              to_string(r_res.xmit + r_res.recv)};

                plot.add(report_vec);

                plot.update();
            }

        }
    }

}


void PerformanceData::strataEst3D(pair<size_t, size_t> set_sizeRange, int confidence) {
    int set_sizeinterval = floor((set_sizeRange.second - set_sizeRange.first) / tesPts);

    PlotRegister plot;
    plot.create("Strata Est", {"Set Size", "Set Diff", "Est"});


    for (int set_size = set_sizeRange.first; set_size <= set_sizeRange.second; set_size += set_sizeinterval) {
        (set_size < set_sizeRange.first + (set_sizeRange.second - set_sizeRange.first) / 2) ? confidence
                                                                                            : confidence = 5;
        cout << "Current Set Size:" + to_string(set_size) << endl;
        printMemUsage();
        int top_set_diff = set_size / 10;
        int set_diffinterval = floor((top_set_diff) / tesPts);

        for (int set_diff = 0; set_diff <= top_set_diff; set_diff += set_diffinterval) {

//            if (set_size>set_sizeRange.second/2)confidence = 100;
//            printMemUsage();
            //printMemUsage();

            for (int conf = 0; conf < confidence; ++conf) {

                StrataEst Alice = StrataEst(sizeof(DataObject));
                StrataEst Bob = StrataEst(sizeof(DataObject));

                for (int j = 0; j < set_size; ++j) {
                    auto tmp = randZZ();
                    if (j < set_size - ceil(set_diff / 2)) Alice.insert(new DataObject(tmp));

                    if (j >= ceil(set_diff / 2)) Bob.insert(new DataObject(tmp));
                }
                plot.add({to_string(set_size), to_string(set_diff), to_string((Alice -= Bob).estimate())});
            }
            //printMemUsage();

        }

        plot.update();
    }
}



// Graph and Plot functions

PlotRegister::PlotRegister() {}

PlotRegister::~PlotRegister() {}

void PlotRegister::create(string _title, vector<string> _labels) {
    data.clear();
    title = _title;
    labels = _labels;
    init();
}

void PlotRegister::init() {
    ofstream myfile;
    //TODO: do soemthing about the directories, this hard coding is not a long term solution
    myfile.open(title + ".txt");

    myfile << accumulate(std::next(labels.begin()), labels.end(),
                         labels[0], // start with first element
                         [](string a, string b) {
                             return a + "|" + b;
                         }) + "\n";


//    myfile<<accumulate(labels.begin(), labels.end(), string("|")) + "\n";
    myfile.close();
}

void PlotRegister::update() {
    ofstream myfile(title + ".txt", ios::app);
    if (!myfile.good()) init();
    for (auto datum : data)
        myfile << accumulate(next(datum.begin()), datum.end(),
                             datum[0], // start with first element
                             [](string a, string b) {
                                 return a + " " + b;
                             }) + "\n";
    data.clear();
    myfile.close();
}

void PlotRegister::add(vector<string> datum) {
    data.push_back(datum);
}

