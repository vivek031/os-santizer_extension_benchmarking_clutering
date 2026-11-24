#!/usr/bin/env python3
"""Print a Table-3-style overhead table from quickbench hyperfine results.

Usage: table.py results/<tag>
Cells: median(scenario) / median(none); '*' = significant (one-sided Welch t-test, p < 0.05),
same test as evaluation/output/output_SPEC_and_browser_print.py. Writes table.md and table.csv.
"""
import json, os, sys
from statistics import median, stdev
from scipy import stats

d = sys.argv[1]
meta = open(os.path.join(d, "meta.txt")).read()
scen = next(l.split(": ", 1)[1].split() for l in meta.splitlines() if l.startswith("scenarios:"))
wls = [l.split(": ", 1)[1].split("|")[0] for l in meta.splitlines() if l.startswith("workload:")]

def times(sc, w):
    p = os.path.join(d, sc, w + ".json")
    return json.load(open(p))["results"][0]["times"] if os.path.exists(p) else None

base = {w: times("none", w) for w in wls}
mirror = {"xz": "657.xz", "gcc": "602.gcc", "perl": "600.perlbench", "sqlite": "620.omnetpp", "stockfish": "631.deepsjeng"}
rows, csv = [], ["scenario," + ",".join(f"{w}_ratio,{w}_p" for w in wls)]
hdr = "| Pass | " + " | ".join(f"{w} (~{mirror.get(w, '')})" for w in wls) + " |"
rows += [hdr, "|" + "---|" * (len(wls) + 1)]
for sc in scen:
    if sc == "none":
        continue
    cells, cc = [], []
    for w in wls:
        t, b = times(sc, w), base[w]
        if not t or not b:
            cells.append("n/a"); cc.append(","); continue
        r = median(t) / median(b)
        p = stats.ttest_ind(t, b, equal_var=False, alternative="greater").pvalue if len(t) > 1 and len(b) > 1 else float("nan")
        cells.append(f"**{r:.2f}**\\*" if p < 0.05 else f"{r:.2f}")
        cc.append(f"{r:.4f},{p:.4g}")
    rows.append(f"| {sc} | " + " | ".join(cells) + " |")
    csv.append(sc + "," + ",".join(cc))
bt = [f"{median(base[w]):.2f} ± {stdev(base[w]):.2f}" if base[w] and len(base[w]) > 1 else (f"{median(base[w]):.2f}" if base[w] else "n/a") for w in wls]
rows.append("| *Baseline time [s] (median ± σ)* | " + " | ".join(bt) + " |")
out = "\n".join(rows) + "\n\n\\* significant: one-sided Welch's t-test, p < 0.05\n"
print(out)
open(os.path.join(d, "table.md"), "w").write(out)
open(os.path.join(d, "table.csv"), "w").write("\n".join(csv) + "\n")
