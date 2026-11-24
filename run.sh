#!/usr/bin/env bash
# Install the latest os-sanitizer build and start the system-wide collector as a systemd service:
#   binary : target/release/os-sanitizer -> /usr/local/sbin/os-sanitizer-collect
#            (previous binary kept as os-sanitizer-collect.prev)
#   passes : --reference-policy (12 of 15; all except memcpy, strcpy, strncpy)
#   reports: /var/log/os-sanitizer/reports.jsonl (JSON, all levels: INFO/WARN/ERROR)
#   textlog: journald, all levels: INFO/WARN/ERROR (journalctl -u os-sanitizer-collect)
# Keeps running after VS Code / SSH sessions end and across reboots.
#
# Usage: sudo ./run.sh
set -euo pipefail

SERVICE=os-sanitizer-collect
UNIT=/etc/systemd/system/$SERVICE.service
BIN=/usr/local/sbin/os-sanitizer-collect
BUILD=$(dirname "$(realpath "$0")")/target/release/os-sanitizer
LOGDIR=/var/log/os-sanitizer
REPORTS=$LOGDIR/reports.jsonl

[[ $EUID -eq 0 ]] || { echo "run as root: sudo $0"; exit 1; }
[[ -x $BUILD ]]   || { echo "missing $BUILD (run: cargo build --release)"; exit 1; }
[[ -f $UNIT ]]    || { echo "missing $UNIT"; exit 1; }

# 0. stop the collector so nothing writes to the file while it is moved / replaced
systemctl stop "$SERVICE" 2>/dev/null || true

# 0b. install the latest build (only if it differs from the installed one)
if [[ -f $BIN ]] && cmp -s "$BUILD" "$BIN"; then
    echo "installed binary is already the latest build"
else
    [[ -f $BIN ]] && cp -p "$BIN" "$BIN.prev" && echo "previous binary kept as $BIN.prev"
    install -m 755 "$BUILD" "$BIN"
    restorecon "$BIN" 2>/dev/null || true   # SELinux: label bin_t so systemd may execute it
    echo "installed latest build -> $BIN"
fi
echo "binary: $(sha256sum "$BIN" | cut -c1-16)  built $(date -r "$BUILD" '+%F %T')"
"$BIN" --help | grep -q -- '--json' || { echo "installed binary lacks --json"; exit 1; }

# 1. keep earlier reports separate from the new data (never overwrite an archive)
mkdir -p "$LOGDIR"
if [[ -s $REPORTS ]]; then
    if [[ ! -e $LOGDIR/reports_3pass_old.jsonl ]]; then
        ARCHIVE=$LOGDIR/reports_3pass_old.jsonl
    else
        ARCHIVE=$LOGDIR/reports_$(date +%Y%m%d_%H%M%S).jsonl
    fi
    mv "$REPORTS" "$ARCHIVE"
    echo "archived previous reports -> $ARCHIVE"
fi

# 2. switch the service to --reference-policy
sed -i "s|^ExecStart=.*|ExecStart=$BIN --reference-policy -v 0 --json $REPORTS|" "$UNIT"

# 3. text log level info = INFO + WARN + ERROR reports (the JSON file gets all levels anyway)
sed -i 's|^Environment="RUST_LOG=.*"|Environment="RUST_LOG=info"|' "$UNIT"

# 4. reload, enable at boot, start
systemctl daemon-reload
systemctl enable --now "$SERVICE"

# 5. show the result
sleep 5
echo "---- unit settings"
grep -E '^(Environment|ExecStart)' "$UNIT"
echo "---- service"
systemctl is-active "$SERVICE"
echo "---- reports so far: $(wc -l < "$REPORTS" 2>/dev/null || echo 0) in $REPORTS"
