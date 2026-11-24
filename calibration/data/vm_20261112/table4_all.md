**Table 4 (reproduced): Breakdown of reports by severity, per pass.**

Data: /var/log/os-sanitizer/reports.jsonl; 2026-11-11 13:26 to 2026-11-12 02:51 (13.4 h)

| Pass | ERROR | WARN | INFO | Reports | Events¹ |
|---|---:|---:|---:|---:|---:|
| access | 0 | 0 | 116k | 116k | n/a |
| fixed_mmap | 0 | 533 | 13.4k | 13.9k | n/a |
| rwx_mem | 0 | 323 | 0 | 323 | n/a |
| filep_unlocked | 0 | 54 | 0 | 54 | n/a |
| gets | 30 | 0 | 0 | 30 | n/a |
| snprintf | 0 | 2.2k | 0 | 2.2k | n/a |
| printf_mut | 0 | 23 | 0 | 23 | n/a |
| system_mut | 0 | 1 | 0 | 1 | n/a |
| system_abs | 0 | 50 | 0 | 50 | n/a |
| sec_file_open | 1 | 7 | 0 | 8 | n/a |
| intercept_path | 37 | 2.8k | 17 | 2.8k | n/a |
| sprintf ² | 0 | 72.5k | 0 | 72.5k | n/a |
| **Total** | **68** | **78.5k** | **129k** | **208k** | |

¹ Events = number of times the pass's probes executed; os-sanitizer counts these internally but does not write them to the JSON reports.
² Not in the paper's Table 4 (sprintf belongs to --reference-policy but was not tabulated there).

**Report volume (cf. Sec. 6.4.2)**

| Metric | This VM | Paper (5 days) |
|---|---:|---:|
| Collection period | 13.4 h | 5 days |
| Data size | 569 MiB (JSON) | 276 MiB (text log) |
| Log entries | 207,854 | ~679K |
| Unique binary offsets in stack traces | 6,098 | 2,784 |
| Unique binaries | 243 | 127 |
| Entries per unique offset (observation frequency) | 34 | 244 |
