#!/usr/bin/env python3
"""Deduplicate OS-Sanitizer reports into clusters and extract calibration features.

Input:  JSON-lines written by `os-sanitizer --json FILE` (preferred), or the classic text
        log (stdout / journalctl). Text logs lack credentials, so most features are empty.
Output: clusters.csv  - one row per cluster with features and an empty `label` column
                        for human triage (tp / fp / unsure)
        summary on stdout (raw reports -> clusters, per pass).

A cluster is (pass, executable identity, top-K resolved stack frames). Frames are
(binary, file offset) pairs, which are stable across runs and ASLR.
"""
import argparse
import collections
import csv
import json
import os
import re
import stat
import subprocess
import sys

TOP_K = 5
PSEUDO_PREFIXES = ("net:[", "pipe:[", "socket:[", "anon_inode:", "/proc/", "/sys/", "/dev/", "mnt:[", "user:[")

# ---------------------------------------------------------------- parsing

TEXT_HEAD = re.compile(
    r"^\[(?P<time>\S+)\s+(?P<level>INFO|WARN|ERROR)\s+os_sanitizer\] (?P<comm>.+?) \(pid: (?P<pid>\d+)(?:, thread: \d+)?\)(?P<rest>.*)$"
)
TEXT_FRAME = re.compile(r"^\s+#\d+ 0x(?P<ip>[0-9a-f]+)(?:\s+\((?P<path>.+)\+0x(?P<off>[0-9a-f]+)\))?")

# message fragments -> pass name used by os-sanitizer's OsSanitizerReport::pass()
TEXT_PASS = [
    ("after accessing it via", "access"),
    ("with permissions", "sec_file_open"),
    ("which may be intercepted", "intercept_path"),
    ("invoked strcpy", "strcpy"),
    ("invoked strncpy", "strncpy"),
    ("invoked memcpy", "memcpy"),
    ("invoked sprintf", "sprintf"),
    ("snprintf-constructed", "snprintf"),
    ("printf-like", "printf_mut"),
    ("non-constant command", "system_mut"),
    ("non-absolute command", "system_abs"),
    ("FILE* function", "filep_unlocked"),
    ("writable and executable", "rwx_mem"),
    ("mmap", "fixed_mmap"),
    ("invoked gets", "gets"),
    ("leaky vessel", "leaky_vessel"),
]


def parse_text(lines):
    cur = None
    for line in lines:
        m = TEXT_HEAD.match(line)
        if m:
            if cur:
                yield cur
            rest = m["rest"]
            pass_ = next((p for frag, p in TEXT_PASS if frag in rest), "unknown")
            fname = re.search(r"(?:opened|access) `?(/[^' ]+|[a-z]+:\[\d+\])", rest)
            cur = {
                "pass": pass_, "level": m["level"], "comm": m["comm"], "pid": int(m["pid"]),
                "ctx": None, "fields": {"filename": fname.group(1) if fname else None},
                "stack": [], "message": m["comm"] + rest,
            }
            continue
        if cur is not None:
            f = TEXT_FRAME.match(line)
            if f:
                cur["stack"].append({
                    "ip": int(f["ip"], 16), "path": f["path"],
                    "offset": int(f["off"], 16) if f["off"] else None,
                })
            elif not line.startswith(" "):
                yield cur
                cur = None
    if cur:
        yield cur


def load(path):
    with open(path, errors="replace") as fh:
        first = fh.readline()
        fh.seek(0)
        if first.lstrip().startswith("{"):
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)
        else:
            yield from parse_text(fh)

# ---------------------------------------------------------------- features


def frame_key(fr):
    if fr.get("path") and fr.get("offset") is not None:
        return f"{os.path.basename(fr['path'])}+{fr['offset']:#x}"
    return "?"


def exe_identity(r):
    exe = ((r.get("ctx") or {}).get("exe") or {})
    if exe.get("path_verified") and exe.get("path"):
        return exe["path"]
    if exe.get("ino"):
        return f"ino:{exe['dev']}:{exe['ino']}"
    return "comm:" + r["comm"].strip("()")


def ctx_signature(r):
    """Coarse execution context. Same code + same stack in a different context (e.g. root in a
    root-owned dir vs root in a user-owned dir) must NOT be merged: that is exactly the
    difference between a benign and an exploitable report (paper Sec. 2, Scenarios 1 vs 2)."""
    ctx = r.get("ctx")
    if not ctx:
        return "noctx"
    fields = r.get("fields") or {}
    priv = ctx.get("euid") == 0 or ctx.get("fsuid") == 0
    repl = replaceable_by_other(ctx.get("obj"), ctx.get("fsuid"))
    writers = bool(fields.get("writer_uids") or fields.get("world_writable_component"))
    sig = f"priv={int(priv)},repl={repl},writers={int(writers)}"
    # a privileged process that has consumed another user's file must not be merged with the
    # same code path running on trusted input only (older JSON without the field: unchanged)
    if "untrusted_open" in ctx:
        sig += f",untrusted={int(bool(ctx['untrusted_open']))}"
    return sig


def cluster_key(r):
    frames = tuple(frame_key(f) for f in r["stack"][:TOP_K])
    return (r["pass"], exe_identity(r), frames, ctx_signature(r))


_rpm_cache = {}


def rpm_owner(path):
    """Package owning `path` (trusted-binary signal), or None. Cached; Fedora/RHEL only."""
    if not path or not path.startswith("/"):
        return None
    if path not in _rpm_cache:
        try:
            out = subprocess.run(["rpm", "-qf", "--qf", "%{NAME}", path],
                                 capture_output=True, text=True, timeout=10)
            _rpm_cache[path] = out.stdout.strip() if out.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            _rpm_cache[path] = None
    return _rpm_cache[path]


def replaceable_by_other(obj, fsuid):
    """Can a user other than `fsuid`/root replace the directory entry? (parent dir check)"""
    if obj is None:
        return None
    pmode = int(obj["parent_mode"], 8)
    puid = obj["parent_uid"]
    if puid not in (0, fsuid):
        return True  # parent owned by someone else
    writable_by_others = bool(pmode & (stat.S_IWGRP | stat.S_IWOTH))
    if not writable_by_others:
        return False
    if pmode & stat.S_ISVTX:  # sticky: others may only replace entries they own
        return obj["uid"] not in (0, fsuid)
    return True


# v2 scoring rule: system service accounts (uid/gid <= SYS_ID_MAX, e.g. systemd-resolve, nginx,
# postgres, smmsp) are part of the OS and are trusted like root. Used only for the scoring
# features; the cluster key (ctx_signature) keeps the original definition, so clusters are unchanged.
SYS_ID_MAX = 999


def trusted_id(i, own):
    return i is not None and (i == 0 or i == own or i <= SYS_ID_MAX)


def replaceable_by_untrusted(obj, fsuid):
    """Like replaceable_by_other, but a parent dir owned/group-writable by a system account does
    not count: only a real (non-system) user, or everyone, can swap the entry."""
    if obj is None:
        return None
    pmode = int(obj["parent_mode"], 8)
    if not trusted_id(obj["parent_uid"], fsuid):
        return True  # parent owned by a real other user
    if pmode & stat.S_IWOTH:
        writable = True  # world-writable: anyone
    elif pmode & stat.S_IWGRP:
        writable = not trusted_id(obj.get("parent_gid"), -1)  # group of real users only
    else:
        writable = False
    if not writable:
        return False
    if pmode & stat.S_ISVTX:  # sticky: others may only replace entries they own
        return not trusted_id(obj["uid"], fsuid)
    return True


# where the suspicious data (template, command, copy source) lives, least to most attacker-reachable
DATA_REGION_RANK = ("binary-ro", "binary-rw", "runtime")


def _joined(values, limit=500):
    return ";".join(sorted({str(v) for v in values if v not in (None, "")}))[:limit] or None


def pass_evidence(reps):
    """Pass-specific evidence for the non-file passes, aggregated over the whole cluster
    (worst case wins: one leaking or runtime-built instance is enough to make the cluster suspect).
    Empty (None) when the pass does not report the field or the log predates it."""
    regions = {r.get("data_region") for r in reps} & set(DATA_REGION_RANK)
    fields = [r.get("fields") or {} for r in reps]
    leaks = [f["definite_leak"] for f in fields if "definite_leak" in f]
    return {
        # printf_mut / system_mut / system_abs / snprintf / str*cpy / memcpy: constant in a binary
        # (binary-ro) vs built at run time (runtime); None = not reported or address unmapped
        "data_region": max(regions, key=DATA_REGION_RANK.index) if regions else None,
        "definite_leak": any(leaks) if leaks else None,           # snprintf
        "mmap_variant": _joined(f.get("variant") for f in fields),  # fixed_mmap
        "mmap_prot": _joined(f.get("protection") for f in fields),  # fixed_mmap
        "command": _joined(f.get("command") for f in fields),      # system_mut / system_abs
    }


def features(reps):
    r0 = reps[0]
    ctx = r0.get("ctx") or {}
    fields = r0.get("fields") or {}
    fsuid = ctx.get("fsuid")
    obj = ctx.get("obj")
    fname = fields.get("filename") or ""
    exe = ctx.get("exe") or {}
    pkg = rpm_owner(exe.get("path")) if exe.get("path_verified") else None
    writers = fields.get("writer_uids") or []
    times = sorted(r.get("time") for r in reps if r.get("time"))
    span = (times[-1] - times[0]) if len(times) > 1 else 0.0
    priv = (ctx.get("euid") == 0 or fsuid == 0) if ctx else None
    # newer kernel-context fields; None when the log predates them
    exe_mode = int(exe["mode"], 8) if exe.get("mode") is not None else None
    exe_uid = exe.get("uid")
    parent_uid = ctx.get("parent_uid")
    return {
        "has_ctx": bool(ctx),
        "privileged": (ctx.get("euid") == 0 or fsuid == 0) if ctx else None,
        "setid": (ctx.get("uid") != ctx.get("euid")) if ctx else None,
        "obj_owner_differs": (obj["uid"] not in (0, fsuid)) if obj else None,
        "entry_replaceable": replaceable_by_untrusted(obj, fsuid) if ctx else None,
        # writers on the path that are real (non-system) users, plus "everyone"
        "path_writers": len([u for u in writers if not trusted_id(u, fsuid)])
        + (1 if fields.get("world_writable_component") else 0)
        if r0["pass"] == "intercept_path" else None,
        "pseudo_path": fname.startswith(PSEUDO_PREFIXES) if fname else None,
        "trusted_pkg": pkg,
        # privileged process that opened a file owned/writable by another user (input taint proxy)
        "untrusted_input": bool(ctx["untrusted_open"]) if "untrusted_open" in ctx else None,
        # privileged process launched by an unprivileged parent (parent controls argv/env/stdin)
        "unpriv_parent": (priv and parent_uid != 0) if parent_uid is not None else None,
        # privileged process running a binary another user owns or can write
        "exe_untrusted": (priv and (not trusted_id(exe_uid, -1) or bool(exe_mode & 0o022)))
        if exe_uid is not None and exe_mode is not None else None,
        "exe_setid": bool(exe_mode & (stat.S_ISUID | stat.S_ISGID)) if exe_mode is not None else None,
        **pass_evidence(reps),
        "count": len(reps),
        "distinct_pids": len({r["pid"] for r in reps}),
        "rate_per_min": round(len(reps) / (span / 60), 2) if span > 0 else None,
    }

# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+", help="JSON-lines or text logs")
    ap.add_argument("-o", "--out", default="clusters.csv")
    args = ap.parse_args()

    clusters = collections.OrderedDict()
    raw = collections.Counter()
    for path in args.logs:
        for r in load(path):
            raw[r["pass"]] += 1
            clusters.setdefault(cluster_key(r), []).append(r)

    # prevalence: in how many distinct executables does the same top-K stack signature occur?
    sig_exes = collections.defaultdict(set)
    for (p, exe, frames, _ctx) in clusters:
        sig_exes[(p, frames)].add(exe)

    rows = []
    for (p, exe, frames, ctxsig), reps in clusters.items():
        f = features(reps)
        lv = collections.Counter(r["level"] for r in reps)
        rows.append({
            "pass": p, "exe": exe, "comm": reps[0]["comm"],
            "max_level": max(lv, key=["INFO", "WARN", "ERROR"].index),
            "ctx_sig": ctxsig,
            "signature_exes": len(sig_exes[(p, frames)]),
            **f,
            "filename": ";".join(sorted({(r.get("fields") or {}).get("filename") or "" for r in reps}))[:2000],
            "top_frames": " | ".join(frames),
            "example": reps[0]["message"][:300],
            "label": "",
        })
    rows.sort(key=lambda r: (["ERROR", "WARN", "INFO"].index(r["max_level"]), -r["count"]))

    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["pass"])
        w.writeheader()
        w.writerows(rows)

    per_pass = collections.Counter(r["pass"] for r in rows)
    total = sum(raw.values())
    print(f"{total} reports -> {len(rows)} clusters ({total / max(len(rows), 1):.1f} reports/cluster)")
    print(f"{'pass':<16}{'reports':>10}{'clusters':>10}")
    for p, n in raw.most_common():
        print(f"{p:<16}{n:>10}{per_pass[p]:>10}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    sys.exit(main())
