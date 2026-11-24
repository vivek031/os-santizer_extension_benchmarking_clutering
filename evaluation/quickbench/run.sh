#!/usr/bin/env bash
# Quickbench runner: Table-3-style overhead measurement of OS-Sanitizer on small CLI workloads.
#
# Usage (as root):  ./run.sh <tag> <trials> <scenario>...
#   e.g.            ./run.sh smoke 1 none all
#                   ./run.sh small6 5 none reference-policy access security-file-open strcpy all
# Env: OS_SAN=/path/to/os-sanitizer (default: /usr/local/bin/os-sanitizer)
#
# For each scenario: start os-sanitizer system-wide (except "none"), wait until all probes are
# attached, run every workload <trials> times with hyperfine, stop os-sanitizer, cool down.
set -uo pipefail
HERE=$(dirname "$(realpath "$0")")
TAG=${1:?tag}; TRIALS=${2:?trials}; shift 2
SCENARIOS=("$@"); [[ ${#SCENARIOS[@]} -gt 0 ]] || { echo "need scenarios"; exit 1; }
OS_SAN=${OS_SAN:-/usr/local/bin/os-sanitizer}
OUT="$HERE/results/$TAG"; IN="$HERE/inputs"; WL="$HERE/workloads"
mkdir -p "$OUT"

# name|command (run from inputs/)
WORKLOADS=(
  "xz|xz -6 -T1 -c data.tar > /dev/null"
  "gcc|gcc -O2 -c sqlite3.c -o /dev/null"
  "perl|perl $WL/wordfreq.pl corpus.txt > /dev/null"
  "sqlite|sqlite3 :memory: < $WL/sqlite_bench.sql > /dev/null"
  "stockfish|stockfish bench 16 1 17 > /dev/null 2>&1"
)

stop_ossan() {
  pkill -INT -x os-sanitizer 2>/dev/null
  for _ in $(seq 1 30); do pgrep -x os-sanitizer >/dev/null || return 0; sleep 1; done
  pkill -KILL -x os-sanitizer 2>/dev/null; sleep 2
}

wait_ready() { # wait until the os-sanitizer log stops growing (all probes attached)
  local log=$1 last=-1 stable=0 n
  for _ in $(seq 1 240); do
    sleep 1
    pgrep -x os-sanitizer >/dev/null || { echo "os-sanitizer died, see $log"; tail -5 "$log"; return 1; }
    n=$(grep -c -E 'loading|attaching' "$log" 2>/dev/null || true)
    if [[ "$n" -gt 0 && "$n" == "$last" ]]; then stable=$((stable + 1)); else stable=0; fi
    last=$n
    [[ $stable -ge 3 ]] && { echo "  ready: $n probe load/attach lines"; return 0; }
  done
  echo "  timeout waiting for probes"; return 1
}

{
  echo "date: $(date -Is)"; echo "host: $(uname -r) | $(nproc) vCPU | $(free -g | awk '/Mem/{print $2}') GiB"
  echo "cpu: $(lscpu | sed -n 's/Model name: *//p' | head -1)"
  echo "os-sanitizer: $OS_SAN sha256=$(sha256sum "$OS_SAN" | cut -c1-16)"
  echo "trials: $TRIALS"; echo "scenarios: ${SCENARIOS[*]}"
  printf 'workload: %s\n' "${WORKLOADS[@]}"
} > "$OUT/meta.new"
if [[ "${RESUME:-0}" == 1 && -f "$OUT/meta.txt" ]]; then
  echo "resumed: $(date -Is)" >> "$OUT/meta.txt"; rm -f "$OUT/meta.new"
else
  mv "$OUT/meta.new" "$OUT/meta.txt"
fi

# BASELINE_EACH=1: measure a fresh baseline (dir base_NN) before every scenario and once at the
# end, so each scenario can be compared with the baselines right before and after it (removes
# machine drift over long runs; see table3.py).
run_scenario() { # run_scenario <scenario> <dir>
  local sc=$1 dir=$2 w done_all=1
  # RESUME=1: skip steps whose results are complete; redo an interrupted (partial) step
  if [[ "${RESUME:-0}" == 1 ]]; then
    for w in "${WORKLOADS[@]}"; do [[ -s "$dir/${w%%|*}.json" ]] || done_all=0; done
    if [[ $done_all == 1 ]]; then echo "=== skip (complete): $sc -> $(basename "$dir")"; return; fi
    rm -rf "$dir"
  fi
  echo "=== scenario: $sc -> $(basename "$dir")  ($(date +%T))"
  mkdir -p "$dir"
  if [[ "$sc" != "none" ]]; then
    RUST_LOG=info "$OS_SAN" --"$sc" > "$dir/ossan.log" 2>&1 &
    wait_ready "$dir/ossan.log" || { stop_ossan; return; }
  fi
  cd "$IN"
  for w in "${WORKLOADS[@]}"; do
    name=${w%%|*}; cmd=${w#*|}
    hyperfine --style basic --runs "$TRIALS" --export-json "$dir/$name.json" -n "$name" "$cmd" 2>&1 \
      | grep -E 'Time \(mean|Range' | sed "s/^/  [$name] /"
  done
  cd "$HERE"
  if [[ "$sc" != "none" ]]; then
    stop_ossan
    echo "  os-sanitizer reports logged: $(grep -c -E ' WARN | ERROR | INFO ' "$dir/ossan.log" || true), log size: $(du -h "$dir/ossan.log" | cut -f1)"
    if [[ "${KEEP_LOGS:-0}" != 1 ]]; then  # logs can reach GBs (memcpy): keep a sample
      head -n 2000 "$dir/ossan.log" > "$dir/ossan.sample.log"; rm -f "$dir/ossan.log"
    fi
  fi
  sleep 5
}

stop_ossan
i=0
for sc in "${SCENARIOS[@]}"; do
  if [[ "${BASELINE_EACH:-0}" == 1 && "$sc" != "none" ]]; then
    run_scenario none "$OUT/base_$(printf %02d $i)"; i=$((i + 1))
  fi
  run_scenario "$sc" "$OUT/$sc"
done
[[ "${BASELINE_EACH:-0}" == 1 ]] && run_scenario none "$OUT/base_$(printf %02d $i)"
echo "done: $OUT  ($(date +%T))"
