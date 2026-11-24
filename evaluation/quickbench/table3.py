#!/usr/bin/env python3
"""Table 3 (standardized benchmarks, overhead ratio over baseline) from a run.sh results dir
recorded with BASELINE_EACH=1.

Usage: table3.py results/<tag>
Each scenario is compared with the pooled baselines measured immediately before and after it
(base_k, base_k+1), which removes slow machine drift over a multi-hour run. Ratio = median
(scenario) / median(baseline); bold = significant (one-sided Welch's t-test, p < 0.05), the same
test as evaluation/output/output_SPEC_and_browser_print.py. Writes table3.md, table3.csv, table3.tex.
"""
import json
import os
import sys
from statistics import median
from scipy import stats

d = sys.argv[1]
meta = open(os.path.join(d, "meta.txt")).read().splitlines()
scen = next(l.split(": ", 1)[1].split() for l in meta if l.startswith("scenarios:"))
wls = [l.split(": ", 1)[1].split("|")[0] for l in meta if l.startswith("workload:")]
MIRROR = {"xz": "657.xz", "gcc": "602.gcc", "perl": "600.perlbench", "sqlite": "620.omnetpp", "stockfish": "631.deepsjeng"}

# paper row order (Table 3) -> (run.sh scenario flag, row label)
ROWS = [("access", "access"), ("fixed-mmap", "fixed_mmap"), ("rwx-mem", "rwx_mem"),
        ("filep-unlocked", "filep_unlocked"), ("gets", "gets"), ("snprintf", "snprintf"),
        ("printf-mutability", "printf_mut"), ("system-mutability", "system_mut"),
        ("system-absolute", "system_abs"), ("security-file-open", "sec_file_open"),
        ("interceptable-path", "intercept_path"), ("reference-policy", "All Previous"), None,
        ("memcpy", "memcpy"), ("strcpy", "strcpy"), ("strncpy", "strncpy"), ("sprintf", "sprintf"),
        ("all", "All Passes")]


def times(sub, w):
    p = os.path.join(d, sub, w + ".json")
    return json.load(open(p))["results"][0]["times"] if os.path.exists(p) else None


order = [s for s in scen if s != "none"]
base_of = {}
for k, sc in enumerate(order):
    base_of[sc] = (f"base_{k:02d}", f"base_{k + 1:02d}")

hdr = "| Pass | " + " | ".join(f"{w} (~{MIRROR.get(w, '')})" for w in wls) + " |"
md = ["**Table 3 (reproduced): overhead ratio over baseline** (stand-in workloads for SPECspeed 2017 Integer)", "",
      hdr, "|" + "---|" * (len(wls) + 1)]
csv = ["pass," + ",".join(f"{w}_ratio,{w}_p" for w in wls)]
tex = []
for row in ROWS:
    if row is None:
        md.append("| | " + " | ".join("" for _ in wls) + " |"); continue
    sc, label = row
    if sc not in base_of:
        continue
    cells, cc, tc = [], [], []
    for w in wls:
        t = times(sc, w)
        b = (times(base_of[sc][0], w) or []) + (times(base_of[sc][1], w) or [])
        if not t or len(b) < 2:
            cells.append("n/a"); cc.append(","); tc.append("n/a"); continue
        r = median(t) / median(b)
        p = stats.ttest_ind(t, b, equal_var=False, alternative="greater").pvalue
        sig = p < 0.05
        cells.append(f"**{r:.2f}**" if sig else f"{r:.2f}")
        cc.append(f"{r:.4f},{p:.4g}")
        tc.append((r"\significant{" if sig else r"\insignificant{") + f"{r:.2f}}}")
    md.append(f"| {label} | " + " | ".join(cells) + " |")
    csv.append(label + "," + ",".join(cc))
    tex.append(f"        {label.replace('_', chr(92) + '_')} & " + " & ".join(tc) + r" \\")

bases = sorted(x for x in os.listdir(d) if x.startswith("base_"))
bt = []
for w in wls:
    allb = [x for b in bases for x in (times(b, w) or [])]
    bt.append(f"{median(allb):.2f}" if allb else "n/a")
md.append("| *Baseline time [s]* | " + " | ".join(bt) + " |")
md += ["", "**Bold** = significant (one-sided Welch's t-test, p < 0.05). Each scenario is compared with "
       "the baselines measured directly before and after it. Workloads are stand-ins, not SPEC CPU2017."]
out = "\n".join(md) + "\n"
print(out)
open(os.path.join(d, "table3.md"), "w").write(out)
open(os.path.join(d, "table3.csv"), "w").write("\n".join(csv) + "\n")
open(os.path.join(d, "table3.tex"), "w").write("\n".join(tex) + "\n")
