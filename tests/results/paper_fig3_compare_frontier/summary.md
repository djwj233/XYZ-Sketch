# Figure 3 Frontier Summary

| d | algorithm | variant | parameter | R_w30 | success | update/elem s | decode/diff s | status |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 100 | cpisync | mbar_search,bits=30,epsilon=64 | 100 | 2.2666666666666666 | 1.0 | 0.0 | 0.00010319879999999997 | ok |
| 100 | iblt | capacity_search | 141 | 4.512 | 0.92 | 1.2731570999999998e-07 | 5.967631999999998e-07 | ok |
| 100 | minisketch | capacity_search,field_bits=30 | 100 | 1.0 | 1.0 | 1.2706994400000005e-06 | 6.160159199999999e-05 | ok |
| 100 | negentropy | frame_search,timestamp=value | 4096 | 86.22933333333333 | 1.0 | 0.0 | 2.19493692e-05 | ok |
| 100 | riblt | symbol_search,symbol_bits=64 | 156 | 2.944 | 0.87 | 2.2331629499999994e-07 | 3.74624613e-05 | unresolved |
| 100 | xyz_v1 | basic,fixed | 1 | 1.0693333333333332 | 1.0 | 2.581602699999999e-07 | 8.292407530000001e-05 | ok |
| 100 | xyz_v2 | circular,heuristic-a-z | 25 | 1.6333333333333333 | 0.92 | 5.229505999999999e-08 | 4.969080960000002e-05 | ok |
| 300 | cpisync | mbar_search,bits=30,epsilon=64 | 300 | 2.097777777777778 | 1.0 | 0.0 | 0.0001465636333333333 | ok |
| 300 | iblt | capacity_search | 389 | 4.16 | 0.91 | 9.354405e-08 | 3.964926666666666e-07 | ok |
| 300 | minisketch | capacity_search,field_bits=30 | 299 | 1.0 | 1.0 | 1.8004502866666666e-06 | 5.038966769999998e-05 | ok |
| 300 | negentropy | frame_search,timestamp=value | 4096 | 123.63822222222223 | 1.0 | 0.0 | 2.748398446666666e-05 | ok |
| 300 | riblt | symbol_search,symbol_bits=64 | 449 | 3.072 | 0.96 | 2.2287304833333335e-07 | 4.4542891466666655e-05 | ok |
| 300 | xyz_v1 | basic,fixed | 1 | 1.0677777777777777 | 1.0 | 6.620514283333331e-07 | 0.00018507940490000002 | ok |
| 300 | xyz_v2 | circular,heuristic-a-z | 67 | 1.459111111111111 | 0.95 | 4.8797313333333346e-08 | 5.134395083333334e-05 | ok |
| 1000 | cpisync | mbar_search,bits=30,epsilon=64 | 1050 | 0.0 | 0.0 | 0.0 | 0.0 | job_timeout |
| 1000 | iblt | capacity_search | 1258 | 4.0256 | 0.93 | 5.50035725e-08 | 3.3318719999999994e-07 | ok |
| 1000 | minisketch | capacity_search,field_bits=30 | 1000 | 1.0 | 1.0 | 3.915011290499999e-06 | 0.0001048494613 | ok |
| 1000 | negentropy | frame_search,timestamp=value | 4096 | 156.8248 | 1.0 | 0.0 | 2.189937850999999e-05 | ok |
| 1000 | riblt | symbol_search,symbol_bits=64 | 1416 | 2.9994666666666667 | 0.88 | 2.716746450000001e-07 | 4.660439597999999e-05 | unresolved |
| 1000 | xyz_v1 | basic,fixed | 1 | 1.0670333333333333 | 1.0 | 1.9375764959999993e-06 | 0.0004763839953399999 | ok |
| 1000 | xyz_v2 | circular,heuristic-a-z | 210 | 1.372 | 0.95 | 3.851772549999999e-08 | 5.667141323e-05 | ok |
| 3000 | cpisync | mbar_search,bits=30,epsilon=64 |  |  | 0.0 | 0.0 | 0.0 | job_timeout |
| 3000 | iblt | capacity_search | 3725 | 3.9744 | 0.88 | 6.069644466666665e-08 | 1.9487873666666657e-07 | unresolved |
| 3000 | minisketch | capacity_search,field_bits=30 | 2999 | 1.0 | 1.0 | 1.0094179504000003e-05 | 0.00027549811406666654 | ok |
| 3000 | negentropy | frame_search,timestamp=value | 4096 | 124.32782222222222 | 1.0 | 0.0 | 3.067074550333334e-05 | ok |
| 3000 | riblt | symbol_search,symbol_bits=64 | 4153 | 2.852977777777778 | 0.87 | 2.6604558849999996e-07 | 4.382728017000001e-05 | unresolved |
| 3000 | xyz_v1 | basic,fixed | 1 | 1.0668111111111112 | 1.0 | 5.7611255916666666e-06 | 0.0013418233481166666 | ok |
| 3000 | xyz_v2 | circular,heuristic-a-z | 600 | 1.3066666666666666 | 0.87 | 5.22099215e-08 | 6.111538300333335e-05 | unresolved |
| 10000 | cpisync | mbar_search,bits=30,epsilon=64 |  |  | 0.0 | 0.0 | 0.0 | job_timeout |
| 10000 | iblt | capacity_search | 12327 | 3.94464 | 0.91 | 4.111743110000001e-08 | 1.4174471600000006e-07 | ok |
| 10000 | minisketch | capacity_search,field_bits=30 | 10000 | 0.0 | 0.0 | 0.0 | 0.0 | job_timeout |
| 10000 | negentropy | frame_search,timestamp=value | 4096 | 187.66266666666667 | 1.0 | 0.0 | 0.00011034308099300001 | ok |
| 10000 | riblt | symbol_search,symbol_bits=64 | 13766 | 2.86912 | 0.94 | 2.0178920099999997e-07 | 4.484913367699999e-05 | ok |
| 10000 | xyz_v1 | basic,fixed | 1 | 0.0 | 0.0 | 0.0 | 0.0 | job_timeout |
| 10000 | xyz_v2 | circular,heuristic-a-z | 1926 | 1.25832 | 0.85 | 6.408974975e-08 | 7.286304616700003e-05 | unresolved |
| 30000 | cpisync | mbar_search,bits=30,epsilon=64 |  |  | 0.0 | 0.0 | 0.0 | job_timeout |
| 30000 | iblt | capacity_search | 36824 | 3.928 | 0.92 | 4.007526415e-08 | 1.4223459966666668e-07 | ok |
| 30000 | minisketch | capacity_search,field_bits=30 |  |  | 0.0 | 0.0 | 0.0 | job_timeout |
| 30000 | negentropy | frame_search,timestamp=value | 4096 | 83.68138666666667 | 1.0 | 0.0 | 4.633791407566667e-05 | ok |
| 30000 | riblt | symbol_search,symbol_bits=64 | 40856 | 2.897777777777778 | 0.92 | 2.013214102e-07 | 1.7966692632333324e-05 | ok |
| 30000 | xyz_v1 | basic,fixed | 1 | 0.0 | 0.0 | 0.0 | 0.0 | job_timeout |
| 30000 | xyz_v2 | circular,heuristic-a-z | 5579 | 1.2149822222222222 | 0.83 | 5.6877307599999966e-08 | 6.771237996800001e-05 | unresolved |
| 100000 | iblt | capacity_search | 122607 | 3.923424 | 0.96 | 4.613959535809285e-08 | 1.6012628329999994e-07 | ok |
| 100000 | xyz_v1 | basic,fixed | 1 | 0.0 | 0.0 | 0.0 | 0.0 | job_timeout |
| 100000 | xyz_v2 | circular,heuristic-a-z | 18129 | 0.0 | 0.0 | 0.0 | 0.0 | job_timeout |
