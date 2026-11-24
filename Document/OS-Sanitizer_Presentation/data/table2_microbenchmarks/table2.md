**Table 2 (reproduced): Results of microbenchmarks.** Iteration time [µs], median of trials.

| Pass | Baseline | OS-San. | Ratio | Paper: Baseline | Paper: OS-San. | Paper: Ratio |
|---|---:|---:|---:|---:|---:|---:|
| access | 3.63 | 15.38 | **4.24** | 1.98 | 7.33 | 3.70 |
| fixed_mmap | 9.59 | 53.87 | **5.62** | 7.19 | 27.05 | 3.76 |
| rwx_mem | 5.06 | 48.15 | **9.52** | 2.55 | 15.22 | 5.96 |
| filep_unlocked | 6.78 | 9.68 | **1.43** | 3.55 | 6.07 | 1.71 |
| gets | 78.64 | 110.05 | **1.40** | 54.10 | 60.69 | 1.12 |
| snprintf | 0.33 | 9.37 | **28.43** | 0.28 | 6.81 | 24.04 |
| printf_mut | 0.25 | 8.08 | **31.72** | 0.18 | 6.33 | 34.94 |
| system_mut | 2160.99 | 2244.42 | **1.04** | 4571.43 | 4905.57 | 1.07 |
| system_abs | 2173.44 | 2253.78 | **1.04** | 4465.28 | 4916.42 | 1.10 |
| sec_file_open | 2.81 | 5.07 | **1.81** | 1.38 | 3.22 | 2.33 |
| intercept_path | 3.08 | 14.93 | **4.84** | 1.53 | 6.13 | 4.00 |
| memcpy | 0.05 | 3.46 | **63.47** | 0.07 | 9.96 | 140.19 |
| strcpy | 0.05 | 4.65 | **95.89** | 0.04 | 4.68 | 106.38 |
| strncpy | 0.06 | 10.26 | **159.24** | 0.09 | 9.46 | 103.90 |
| sprintf | 0.08 | 5.15 | **67.95** | 0.10 | 4.77 | 46.56 |

Trials per cell: 10. Paper values: System A (Xeon Gold 6248R VM); this run: see meta.txt.
