#!/usr/bin/env bash
# Finishes the Table 3 run independently of any terminal / VS Code session (started via
# systemd-run). Resumes: completed steps are skipped, an interrupted step is redone.
cd "$(dirname "$(realpath "$0")")" || exit 1
echo "table3 resumed under systemd $(date +%T)" >> results/full_run.status
BASELINE_EACH=1 RESUME=1 ./run.sh table3 5 access fixed-mmap rwx-mem filep-unlocked gets snprintf \
  printf-mutability system-mutability system-absolute security-file-open interceptable-path \
  reference-policy memcpy strcpy strncpy sprintf all >> results/table3.out 2>&1
python3 table3.py results/table3 > results/table3/table3_print.txt 2>&1
echo "table3 done $(date +%T)" >> results/full_run.status
