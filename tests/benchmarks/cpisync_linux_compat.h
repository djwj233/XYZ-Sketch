#pragma once

#include <ctime>
#include <iostream>

#include "../../external/cpisync/include/ProcessData.h"

#ifdef __linux__
inline double cpisyncCompatFinishTime(Resources& res) {
    clock_gettime(CLOCK_MONOTONIC, &res.finish_time);
    double elapsed = static_cast<double>(res.finish_time.tv_sec - res.start_time.tv_sec);
    elapsed += static_cast<double>(res.finish_time.tv_nsec - res.start_time.tv_nsec) / 1000000000.0;
    return elapsed;
}

inline void initResources(Resources& res) {
    clock_gettime(CLOCK_MONOTONIC, &res.start_time);
    res.finish_time = res.start_time;
    res.TimeElapsed = 0.0;
    res.VmemUsed = 0;
}

inline void resourceReport(Resources& res) {
    res.TimeElapsed = cpisyncCompatFinishTime(res);
    res.VmemUsed = static_cast<size_t>(getValue());
}
#endif
