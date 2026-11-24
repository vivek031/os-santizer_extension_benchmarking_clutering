#!/usr/bin/env bash
# Table 2 (microbenchmarks) runner, adapted from evaluation/microbenchmark/eval_microbench.sh.
# Differences from the original:
#   * os-sanitizer is started ONCE per pass (all with-os-san trials run under one instance),
#     i.e. 15 starts/stops instead of 150 -- probe removal can crash running processes on
#     kernels older than 6.14 (journald crashed this way on this VM);
#   * waits until all probes are attached instead of a fixed `sleep 3`;
#   * builds into a separate folder, leaving examples/ untouched.
# Output format is identical to the original (lines "microbenchmark <pass>" / "Iterations: N";
# first TRIALS with os-sanitizer, then TRIALS without), so the paper's
# evaluation/output/output_microbenchmark_print.py logic applies unchanged.
#
# Usage (as root): ./run_table2.sh <tag> <trials> [pass ...]
set -uo pipefail
HERE=$(dirname "$(realpath "$0")")
REPO=$(dirname "$(dirname "$HERE")")
TAG=${1:?tag}; TRIALS=${2:?trials}; shift 2
OS_SAN=${OS_SAN:-/usr/local/bin/os-sanitizer}
OUT="$HERE/results/$TAG"; BUILD="$OUT/build"
mkdir -p "$OUT"

# same order/name mapping as eval_microbench.sh
ALL_OPTS=(access gets rwx-mem memcpy strcpy strncpy security-file-open sprintf snprintf printf-mutability system-mutability system-absolute filep-unlocked fixed-mmap interceptable-path)
declare -A EX=([access]=01_access [gets]=02_gets [rwx-mem]=03_rwx_mem [memcpy]=04_memcpy [strcpy]=04_strcpy
  [strncpy]=04_strncpy [security-file-open]=05_security_file_open [sprintf]=06_sprintf [snprintf]=07_snprintf
  [printf-mutability]=08_printf_mutability [system-mutability]=09_system_mutability [system-absolute]=10_system_abs
  [filep-unlocked]=11_filep_unlocked [fixed-mmap]=12_fixed_mmap [interceptable-path]=13_interceptable_path)
OPTS=("$@"); [[ ${#OPTS[@]} -gt 0 ]] || OPTS=("${ALL_OPTS[@]}")

# build microbenchmark variants in a private copy of examples/
rm -rf "$BUILD"; cp -a "$REPO/examples" "$BUILD"
make -s -C "$BUILD" clean >/dev/null 2>&1
make -s -C "$BUILD" all OPTION='-DMICROBENCHMARK' >"$OUT/build.log" 2>&1 || { echo "build failed, see $OUT/build.log"; exit 1; }
chmod o+w "$BUILD/dir1"; chmod 666 "$BUILD/05_demo_file.txt"

stop_ossan() {
  pkill -INT -x os-sanitizer 2>/dev/null
  for _ in $(seq 1 30); do pgrep -x os-sanitizer >/dev/null || return 0; sleep 1; done
  pkill -KILL -x os-sanitizer 2>/dev/null; sleep 2
}
wait_ready() {
  local log=$1 last=-1 stable=0 n
  for _ in $(seq 1 240); do
    sleep 1
    pgrep -x os-sanitizer >/dev/null || { echo "os-sanitizer died"; tail -5 "$log"; return 1; }
    n=$(grep -c -E 'loading|attaching' "$log" 2>/dev/null || true)
    if [[ "$n" -gt 0 && "$n" == "$last" ]]; then stable=$((stable + 1)); else stable=0; fi
    last=$n; [[ $stable -ge 3 ]] && return 0
  done
  return 1
}
run_one() { # prints "Iterations: N" (from the program)
  local exe=$1
  if [[ $exe == 02_gets ]]; then
    yes "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMNOPQRSTUVWXYZ" | ./"$exe" 2>/dev/null
  else
    ./"$exe" </dev/null 2>/dev/null
  fi | grep "Iterations: "
}

{
  echo "date: $(date -Is)"; echo "host: $(uname -r) | $(nproc) vCPU"
  echo "os-sanitizer: $OS_SAN sha256=$(sha256sum "$OS_SAN" | cut -c1-16)"; echo "trials: $TRIALS"
} > "$OUT/meta.txt"

stop_ossan
cd "$BUILD"
for opt in "${OPTS[@]}"; do
  exe=${EX[$opt]}
  echo "microbenchmark $opt"
  RUST_LOG=info "$OS_SAN" --"$opt" > "$OUT/ossan_$opt.log" 2>&1 &
  if ! wait_ready "$OUT/ossan_$opt.log"; then echo "  SKIP: os-sanitizer not ready" >&2; stop_ossan; continue; fi
  for i in $(seq 1 "$TRIALS"); do run_one "$exe"; sleep 1; done
  stop_ossan
  echo "  os-san reports for $exe: $(grep -c "os_sanitizer] ${exe:0:15}" "$OUT/ossan_$opt.log")" >&2
  # logs reach GBs per pass: keep a sample only (the full log was written during the run,
  # so its I/O cost is part of the measurement, as in the original script)
  head -n 2000 "$OUT/ossan_$opt.log" > "$OUT/ossan_$opt.sample.log"; rm -f "$OUT/ossan_$opt.log"
  sleep 3
  for i in $(seq 1 "$TRIALS"); do run_one "$exe"; sleep 1; done
done
echo "done $(date +%T)" >&2
