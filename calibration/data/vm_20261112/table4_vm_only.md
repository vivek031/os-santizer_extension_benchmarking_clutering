**Table 4 (reproduced): Breakdown of reports by severity, per pass.**

Data: /var/log/os-sanitizer/reports.jsonl; 2026-11-11 13:26 to 2026-11-12 02:51 (13.4 h); 8212 test/calibration reports excluded

| Pass | ERROR | WARN | INFO | Reports | Events¹ |
|---|---:|---:|---:|---:|---:|
| access | 0 | 0 | 109k | 109k | n/a |
| fixed_mmap | 0 | 524 | 13.4k | 13.9k | n/a |
| rwx_mem | 0 | 317 | 0 | 317 | n/a |
| filep_unlocked | 0 | 14 | 0 | 14 | n/a |
| gets | 24 | 0 | 0 | 24 | n/a |
| snprintf | 0 | 2.2k | 0 | 2.2k | n/a |
| printf_mut | 0 | 17 | 0 | 17 | n/a |
| system_mut | 0 | 1 | 0 | 1 | n/a |
| system_abs | 0 | 10 | 0 | 10 | n/a |
| sec_file_open | 1 | 0 | 0 | 1 | n/a |
| intercept_path | 8 | 2.0k | 0 | 2.0k | n/a |
| sprintf ² | 0 | 72.5k | 0 | 72.5k | n/a |
| **Total** | **33** | **77.6k** | **122k** | **200k** | |

¹ Events = number of times the pass's probes executed; os-sanitizer counts these internally but does not write them to the JSON reports.
² Not in the paper's Table 4 (sprintf belongs to --reference-policy but was not tabulated there).

**Report volume (cf. Sec. 6.4.2)**

| Metric | This VM | Paper (5 days) |
|---|---:|---:|
| Collection period | 13.4 h | 5 days |
| Data size | 569 MiB (JSON) | 276 MiB (text log) |
| Log entries | 199,642 | ~679K |
| Unique binary offsets in stack traces | 5,612 | 2,784 |
| Unique binaries | 216 | 127 |
| Entries per unique offset (observation frequency) | 36 | 244 |
