**Table 3 (reproduced): overhead ratio over baseline** (stand-in workloads for SPECspeed 2017 Integer)

| Pass | xz (~657.xz) | gcc (~602.gcc) | perl (~600.perlbench) | sqlite (~620.omnetpp) | stockfish (~631.deepsjeng) |
|---|---|---|---|---|---|
| access | **1.02** | 1.00 | 1.00 | 1.02 | 1.00 |
| fixed_mmap | 1.00 | 1.00 | 1.00 | 1.00 | 0.99 |
| rwx_mem | 1.01 | 1.00 | 1.00 | 1.01 | 1.01 |
| filep_unlocked | 1.00 | **1.30** | 0.97 | **1.01** | 1.00 |
| gets | 1.00 | 1.01 | 1.00 | 0.97 | 1.01 |
| snprintf | 1.02 | **1.07** | **1.04** | 1.01 | 1.01 |
| printf_mut | 1.00 | **1.02** | **1.02** | 1.03 | 1.01 |
| system_mut | 1.00 | 1.00 | 1.01 | 1.00 | **1.01** |
| system_abs | 1.01 | 1.00 | 1.01 | 1.01 | 1.02 |
| sec_file_open | 1.00 | 0.99 | **1.01** | 1.00 | 1.01 |
| intercept_path | **1.00** | 0.99 | 1.00 | 1.01 | 1.00 |
| All Previous | 0.98 | **1.45** | **1.17** | **1.04** | **1.03** |
| |  |  |  |  |  |
| memcpy | 1.02 | **1.32** | **1.06** | **4.31** | **1.03** |
| strcpy | **1.04** | **1.32** | **1.05** | **4.32** | 1.01 |
| strncpy | 1.00 | **1.34** | **1.07** | **4.28** | **1.03** |
| sprintf | 1.01 | **1.06** | 1.00 | 1.01 | 0.99 |
| All Passes | **1.05** | **1.77** | **1.05** | **4.33** | **1.03** |
| *Baseline time [s]* | 19.87 | 19.89 | 6.57 | 8.96 | 13.48 |

**Bold** = significant (one-sided Welch's t-test, p < 0.05). Each scenario is compared with the baselines measured directly before and after it. Workloads are stand-ins, not SPEC CPU2017.
