#!/usr/bin/env python3
"""Transparent baseline confidence score + rationale for clustered reports.

This is the interpretable rule baseline the learned model (logistic regression) must beat.
It never drops a report: it only adds `score` (0..1, higher = more likely a real issue),
`rationale` and `reach`.

Each pass is scored by the rule that fits its evidence:
  * file passes (access, intercept_path, sec_file_open): can another user replace or redirect
    what the process opens?  (validated by scenarios.sh / ground_truth.tsv)
  * every other pass: is the bug reachable by a less-privileged attacker (`reach`, below), plus
    the pass's own evidence (data_region, definite_leak, mmap_variant, ...).  Running as root is
    NOT evidence by itself: root compiling its own code crosses no privilege boundary.
  * a pass without a rule gets an empty score and "not scored: ..." -- never a made-up number.

    score.py clusters.csv [-o scored.csv] [--truth ground_truth.tsv --threshold 0.5]

With --truth, clusters are matched to scenarios by filename substring and precision/recall
are reported, plus every true positive that falls below the threshold (must be none).
"""
import argparse
import csv
import sys


def b(v):
    return {"True": True, "False": False}.get(v)


def score_file(r):
    """File passes. Return (score, rationale). Weights are explicit so every number can be argued."""
    reasons, s = [], 0.5
    if r["has_ctx"] != "True":
        return 0.5, "no kernel context (text log): cannot calibrate"
    priv, repl = b(r["privileged"]), b(r["entry_replaceable"])
    writers = int(r["path_writers"]) if r["path_writers"] not in ("", None) else None
    if r["pseudo_path"] == "True":
        return 0.05, "kernel pseudo-file (namespace/pipe/proc): not attacker-replaceable"
    if priv:
        s += 0.15; reasons.append("privileged process")
    else:
        s -= 0.3; reasons.append("unprivileged process (no privilege to steal)")
    if repl is True:
        s += 0.3; reasons.append("entry replaceable by another user")
    elif repl is False:
        s -= 0.3; reasons.append("no other user can replace the entry")
    if writers:
        s += 0.3; reasons.append(f"{writers} other writer(s) on the path")
    if r["pass"] == "sec_file_open" and priv:
        s += 0.2; reasons.append("privileged read of world-writable file")
    # newer kernel-context features (empty for older logs -> no effect)
    if priv and b(r.get("untrusted_input")):
        s += 0.2; reasons.append("privileged process consumed another user's file")
    if priv and b(r.get("unpriv_parent")):
        s += 0.15; reasons.append("launched by unprivileged parent (controls argv/env)")
    if priv and b(r.get("exe_untrusted")):
        s += 0.2; reasons.append("privileged process runs binary owned/writable by another user")
    if b(r.get("exe_setid")):
        s += 0.05; reasons.append("setuid/setgid executable")
    if r["trusted_pkg"]:
        s -= 0.05; reasons.append(f"packaged binary ({r['trusted_pkg']})")
    if int(r["signature_exes"]) > 3:
        s -= 0.05; reasons.append("same code path in many binaries (library idiom)")
    # v2 rule: like the non-file passes, a non-root process crosses no privilege boundary, so it
    # can never be flagged (e.g. sendmail writing its own group-writable mail queue)
    if priv is False and s > 0.45:
        s = 0.45; reasons.append("not root: capped below 0.5")
    return max(0.0, min(1.0, round(s, 3))), "; ".join(reasons)


FILE_PASSES = {"access", "intercept_path", "sec_file_open"}


def reach(r):
    """Can a less-privileged attacker influence this privileged process? Returns (bool|None, why).
    None = no kernel context. Being root is necessary but not sufficient: something the attacker
    controls must flow in (argv/env/stdin from an unprivileged parent, a setuid transition, a file
    another user owns or can write, or a binary another user owns or can write)."""
    if r["has_ctx"] != "True":
        return None, "no kernel context"
    if not b(r["privileged"]):
        return False, "unprivileged process (no privilege to steal)"
    why = [txt for col, txt in (
        ("unpriv_parent", "launched by unprivileged parent"),
        ("setid", "setuid/setgid transition"),
        ("untrusted_input", "consumed another user's file"),
        ("exe_untrusted", "binary owned/writable by another user"),
    ) if b(r.get(col))]
    if why:
        return True, "privileged and reachable: " + ", ".join(why)
    return False, "privileged, but only trusted input/launcher (no boundary crossed)"


# Non-file rules follow the same convention as the file rule and scenarios.sh: without a
# privilege boundary (reach) a cluster stays below 0.5 however bad the code is; reach is what
# pushes it over. Validated on data/ground_truth_v2.tsv.


def _rule_gets(r, rch):
    s, why = 0.45, ["gets() is always unsafe"]
    if rch:
        s += 0.4; why.append("attacker can feed stdin")
    return s, why


def _rule_mutable_string(r, rch):  # printf_mut, system_mut
    region = r.get("data_region") or ""
    if region == "binary-ro":
        return 0.1, ["string is a constant in the binary (not attacker-controllable)"]
    if region == "binary-rw":
        s, why = 0.4, ["string lives in writable binary data"]
    elif region == "runtime":
        s, why = 0.45, ["string built at run time"]
    else:  # usually a short-lived process whose maps were gone before userspace looked
        s, why = 0.4, ["region unresolved"]
    if rch:
        s += 0.3; why.append("attacker may influence the string")
    return s, why


def _rule_system_abs(r, rch):
    cmd = (r.get("command") or "")[:60]
    if not b(r["privileged"]):
        return 0.1, [f"non-absolute command `{cmd}` but no privilege to gain"]
    if b(r.get("setid")):
        # real uid != effective uid: bash (Fedora's /bin/sh) resets euid to the real uid before
        # running the command, so a hijacked PATH only runs code as the attacker (oracle-verified)
        return 0.35, [f"non-absolute command `{cmd}`; setuid caller, but /bin/sh drops privileges"]
    if b(r.get("unpriv_parent")):
        return 0.8, [f"non-absolute command `{cmd}`; full root with PATH from a less-privileged parent"]
    # blind spot: root with an attacker-writable dir in its own PATH (env is not captured)
    return 0.2, [f"non-absolute command `{cmd}`; PATH set by a privileged launcher"]


def _rule_snprintf(r, rch):
    if not b(r.get("definite_leak")):
        return 0.2, ["no definite leak (computed length within buffer)"]
    s, why = 0.4, ["definite leak: wrote past the snprintf buffer"]
    if rch:
        s += 0.35; why.append("leaks a privileged process's memory")
    return s, why


def _rule_fixed_mmap(r, rch):
    variants = set((r.get("mmap_variant") or "").split(";"))
    if "FixedMmapBadProt" in variants:
        return 0.4, ["MAP_FIXED with bad protection"]
    return 0.05, ["address hint only (benign pre-allocation, e.g. ld; paper Sec. 6.4.3)"]


def _rule_rwx_mem(r, rch):
    s, why = 0.3, ["W+X memory (usually a JIT)"]
    if r["trusted_pkg"]:
        s -= 0.1; why.append(f"packaged binary ({r['trusted_pkg']})")
    if rch:
        s += 0.3; why.append("attacker may influence the generated code")
    return s, why


def _rule_filep_unlocked(r, rch):
    return 0.3, ["unsynchronised FILE* use across threads (no privilege dimension)"]


def _rule_sprintf(r, rch):
    # capped below the default 0.5 threshold on purpose: without the source pointer (not captured
    # by the eBPF probe) reach alone cannot show an overflow, it only ranks the cluster higher
    s, why = 0.3, ["weak evidence: report has no source or length information"]
    if rch:
        s += 0.15; why.append("attacker may influence the formatted data")
    return s, why


PASS_RULES = {
    "gets": _rule_gets,
    "printf_mut": _rule_mutable_string,
    "system_mut": _rule_mutable_string,
    "system_abs": _rule_system_abs,
    "snprintf": _rule_snprintf,
    "fixed_mmap": _rule_fixed_mmap,
    "rwx_mem": _rule_rwx_mem,
    "filep_unlocked": _rule_filep_unlocked,
    "sprintf": _rule_sprintf,
}


def score_row(r):
    """Return (score or None, rationale, reach). Dispatches on the pass."""
    rch, rch_why = reach(r)
    if r["pass"] in FILE_PASSES:
        s, why = score_file(r)
        return s, why, rch
    rule = PASS_RULES.get(r["pass"])
    if rule is None:
        return None, f"not scored: no rule for pass {r['pass']}", rch
    if rch is None:
        return 0.5, "no kernel context (text log): cannot calibrate", rch
    s, why = rule(r, rch)
    why.append(rch_why)
    if int(r["signature_exes"]) > 3:
        s -= 0.05; why.append("same code path in many binaries (library idiom)")
    return max(0.0, min(1.0, round(s, 3))), "; ".join(why), rch


def per_pass_summary(rows, threshold):
    by = {}
    for r in rows:
        by.setdefault(r["pass"], []).append(r)
    print(f"\n{'pass':<16}{'clusters':>9}{'scored':>8}{'mean':>7}{f'>={threshold}':>8}")
    for p, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        sc = [r["score"] for r in rs if r["score"] is not None]
        mean = f"{sum(sc) / len(sc):.2f}" if sc else "-"
        print(f"{p:<16}{len(rs):>9}{len(sc):>8}{mean:>7}{sum(s >= threshold for s in sc):>8}")


def truth_hits(t, rows, comms):
    """Scored clusters that belong to ground-truth scenario `t`."""
    if t.get("comm"):  # non-file scenario: its own binary, so comm (+ pass) identifies it
        return [r for r in rows if r["comm"] == t["comm"] and r["score"] is not None
                and (not t.get("pass") or r["pass"] == t["pass"])]
    return [r for r in rows if t["path_substr"] in (r.get("filename") or "")
            and r["comm"] in comms and r["score"] is not None]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clusters")
    ap.add_argument("-o", "--out", default="scored.csv")
    ap.add_argument("--truth")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--comm", default="01_access,05_security_fil,13_interceptabl",
                    help="only clusters from these process names count for --truth (excludes setup noise)")
    ap.add_argument("--sweep", action="store_true", help="print precision/recall for thresholds 0..1")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.clusters)))
    for r in rows:
        r["score"], r["rationale"], r["reach"] = score_row(r)
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))  # unscored last
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"wrote {a.out} ({len(rows)} clusters)")
    per_pass_summary(rows, a.threshold)

    if not a.truth:
        return
    truth = list(csv.DictReader(open(a.truth), delimiter="\t"))
    comms = a.comm.split(",")
    tp = fp = fn = tn = 0
    missed = []
    per = {}  # pass -> [TP, FP, TN, FN]
    print(f"\n{'scenario':<26}{'label':<8}{'clusters':>9}{'score':>8}  rationale")
    for t in truth:
        hits = truth_hits(t, rows, comms)
        grp = per.setdefault(t.get("pass") or "file passes", [0, 0, 0, 0])
        if t["label"] == "none":
            print(f"{t['scenario']:<26}{t['label']:<8}{len(hits):>9}{'-':>8}  (expect no report)")
            continue
        for r in hits:
            pos = r["score"] >= a.threshold
            print(f"{t['scenario']:<26}{t['label']:<8}{1:>9}{r['score']:>8}  {r['rationale']}")
            if t["label"] == "tp":
                tp += pos; fn += not pos
                grp[0] += pos; grp[3] += not pos
                if not pos:
                    missed.append(t["scenario"])
            elif t["label"] == "fp":
                fp += pos; tn += not pos
                grp[1] += pos; grp[2] += not pos
        if not hits:
            print(f"{t['scenario']:<26}{t['label']:<8}{0:>9}{'-':>8}  NOT REPORTED")
            if t["label"] == "tp":
                fn += 1; grp[3] += 1; missed.append(t["scenario"] + " (not reported)")
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    print(f"\nthreshold {a.threshold}: TP={tp} FP={fp} TN={tn} FN={fn}  precision={prec:.2f} recall={rec:.2f}")
    print("true positives below threshold:", missed or "none")
    if len(per) > 1:
        print(f"\n{'pass':<16}{'TP':>4}{'FP':>4}{'TN':>4}{'FN':>4}")
        for p_, (a_, b_, c_, d_) in per.items():
            print(f"{p_:<16}{a_:>4}{b_:>4}{c_:>4}{d_:>4}")

    if a.sweep:
        pts = []
        for t in truth:
            if t["label"] not in ("tp", "fp"):
                continue
            for r in truth_hits(t, rows, comms):
                pts.append((r["score"], t["label"] == "tp"))
        print(f"\n{'threshold':>9}{'TP':>4}{'FP':>4}{'FN':>4}{'TN':>4}{'precision':>11}{'recall':>8}{'flagged':>9}")
        for th in [i / 20 for i in range(0, 21)]:
            tp_ = sum(1 for s_, y in pts if y and s_ >= th)
            fn_ = sum(1 for s_, y in pts if y and s_ < th)
            fp_ = sum(1 for s_, y in pts if not y and s_ >= th)
            tn_ = sum(1 for s_, y in pts if not y and s_ < th)
            p_ = f"{tp_ / (tp_ + fp_):.2f}" if tp_ + fp_ else "  -"
            r_ = f"{tp_ / (tp_ + fn_):.2f}" if tp_ + fn_ else "  -"
            print(f"{th:>9.2f}{tp_:>4}{fp_:>4}{fn_:>4}{tn_:>4}{p_:>11}{r_:>8}{tp_ + fp_:>6}/{len(pts)}")


if __name__ == "__main__":
    sys.exit(main())
