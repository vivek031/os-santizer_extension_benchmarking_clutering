#!/usr/bin/env bash
# Quickbench setup: installs dependencies and creates fixed, reusable inputs in ./inputs.
# Inputs are generated once so every scenario/trial processes identical data.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
mkdir -p inputs results

sudo dnf install -y -q hyperfine perl stockfish sqlite gcc python3-scipy unzip

# 1) SQLite amalgamation (gcc workload)
if [[ ! -f inputs/sqlite3.c ]]; then
    curl -sSfL -o inputs/sqlite.zip https://www.sqlite.org/2024/sqlite-amalgamation-3460100.zip
    unzip -q -j -o inputs/sqlite.zip '*/sqlite3.c' '*/sqlite3.h' -d inputs
    rm inputs/sqlite.zip
fi

# 2) data.tar (xz workload): deterministic tar of system text/binary content (~64 MiB)
if [[ ! -f inputs/data.tar ]]; then
    find /usr/share/doc /usr/share/licenses /usr/include -type f -size -2M 2>/dev/null | LC_ALL=C sort \
        | tar --no-recursion --mtime=2024-01-01 --owner=0 --group=0 -cf - -T - 2>/dev/null \
        | head -c $((64 * 1024 * 1024)) > inputs/data.tar || true
fi

# 3) corpus.txt (perl workload): ~48 MiB of text
if [[ ! -f inputs/corpus.txt ]]; then
    find /usr/share/doc /usr/share/licenses /usr/include -type f \( -name '*.h' -o -name '*.txt' -o -name '*.md' -o -name 'README*' -o -name 'LICENSE*' -o -name 'COPYING*' \) 2>/dev/null \
        | LC_ALL=C sort | xargs cat 2>/dev/null | head -c $((48 * 1024 * 1024)) > inputs/corpus.txt || true
fi

ls -la inputs
