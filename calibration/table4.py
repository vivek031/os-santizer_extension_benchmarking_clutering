#!/usr/bin/env python3
"""Reproduce the paper's Table 4 (report severity per pass, Sec. 6.4.3) and the report-volume
statistics of Sec. 6.4.2 from `os-sanitizer --json` output.

    table4.py reports.jsonl [more.jsonl ...] [-o OUT_PREFIX] [--exclude-test]

Writes OUT_PREFIX.md (markdown) and OUT_PREFIX.tex (LaTeX rows), and prints both.
The paper's "Events" column (how often each pass's probes executed) is os-sanitizer's internal
execution counter; it is not part of the JSON reports, so it is shown as "n/a".
--exclude-test drops reports caused by calibration / test activity (see TEST_MARKERS).
"""
import argparse
import collections
import datetime
import json
import os

# order and names as in the paper's Table 4
PASSES = ["access", "fixed_mmap", "rwx_mem", "filep_unlocked", "gets", "snprintf", "printf_mut",
          "system_mut", "system_abs", "sec_file_open", "intercept_path"]
# not in the paper's Table 4 (sprintf is part of --reference-policy but was not tabulated there)
EXTRA = ["sprintf", "strcpy", "strncpy", "memcpy", "leaky_vessel"]
LEVELS = ["ERROR", "WARN", "INFO"]
TEST_MARKERS = ("ossan_cal", "ossan_var", "ossan-scenarios", "cal_work", "/root/os-sanitizer/examples",
                "/os-sanitizer/evaluation/quickbench", "/scratchpad/")


def human(n):
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    if n >= 1_000:
        return f"{n / 1e3:.1f}k" if n < 100_000 else f"{n / 1e3:.0f}k"
    return str(n)


def is_test(r):
    blob = json.dumps(r.get("fields") or {}) + " " + r.get("message", "")
    exe = ((r.get("ctx") or {}).get("exe") or {}).get("path") or ""
    return any(m in blob or m in exe for m in TEST_MARKERS) or r.get("comm", "")[:2].isdigit()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+")
    ap.add_argument("-o", "--out", default="table4")
    ap.add_argument("--exclude-test", action="store_true")
    a = ap.parse_args()

    sev = collections.defaultdict(collections.Counter)
    offsets, binaries = set(), set()
    entries = excluded = 0
    size = sum(os.path.getsize(p) for p in a.logs)
    t_min, t_max = float("inf"), 0.0
    for path in a.logs:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if a.exclude_test and is_test(r):
                    excluded += 1
                    continue
                entries += 1
                sev[r["pass"]][r["level"]] += 1
                t = r.get("time") or 0
                t_min, t_max = min(t_min, t), max(t_max, t)
                for f in r.get("stack") or []:
                    if f.get("path") and f.get("offset") is not None:
                        offsets.add((f["path"], f["offset"]))
                        binaries.add(f["path"])

    hours = (t_max - t_min) / 3600 if entries else 0
    span = (f"{datetime.datetime.fromtimestamp(t_min):%Y-%m-%d %H:%M} to "
            f"{datetime.datetime.fromtimestamp(t_max):%Y-%m-%d %H:%M} ({hours:.1f} h)") if entries else "-"

    md = ["**Table 4 (reproduced): Breakdown of reports by severity, per pass.**", "",
          f"Data: {', '.join(a.logs)}; {span}" + (f"; {excluded} test/calibration reports excluded" if a.exclude_test else ""), "",
          "| Pass | ERROR | WARN | INFO | Reports | Events¹ |", "|---|---:|---:|---:|---:|---:|"]
    tex = []
    for p in PASSES + [p for p in EXTRA if sev.get(p)]:
        c = sev.get(p, collections.Counter())
        row = [human(c[l]) for l in LEVELS]
        extra = " ²" if p in EXTRA else ""
        md.append(f"| {p}{extra} | " + " | ".join(row) + f" | {human(sum(c.values()))} | n/a |")
        tex.append(f"        {p.replace('_', chr(92) + '_')} & " + " & ".join(row) + r" & n/a \\")
    tot = collections.Counter()
    for c in sev.values():
        tot.update(c)
    md.append("| **Total** | " + " | ".join(f"**{human(tot[l])}**" for l in LEVELS) + f" | **{human(entries)}** | |")
    md += ["", "¹ Events = number of times the pass's probes executed; os-sanitizer counts these internally "
           "but does not write them to the JSON reports.",
           "² Not in the paper's Table 4 (sprintf belongs to --reference-policy but was not tabulated there).", "",
           "**Report volume (cf. Sec. 6.4.2)**", "",
           "| Metric | This VM | Paper (5 days) |", "|---|---:|---:|",
           f"| Collection period | {hours:.1f} h | 5 days |",
           f"| Data size | {size / 2**20:.0f} MiB (JSON) | 276 MiB (text log) |",
           f"| Log entries | {entries:,} | ~679K |",
           f"| Unique binary offsets in stack traces | {len(offsets):,} | 2,784 |",
           f"| Unique binaries | {len(binaries):,} | 127 |",
           f"| Entries per unique offset (observation frequency) | {entries / max(len(offsets), 1):.0f} | 244 |"]
    out_md = "\n".join(md) + "\n"
    print(out_md)
    open(a.out + ".md", "w").write(out_md)
    open(a.out + ".tex", "w").write("\n".join(tex) + "\n")
    print(f"wrote {a.out}.md and {a.out}.tex")


if __name__ == "__main__":
    main()
