#!/usr/bin/env python3
"""Table 2 (microbenchmarks) from run_table2.sh output.

Usage: table2.py results/<tag>/stdout.txt
Same computation as evaluation/output/output_microbenchmark_print.py:
iteration time [µs] = 10 s * 1e6 / median(iterations); ratio = with / without.
Writes table2.md and table2.tex next to the input.
"""
import os
import sys
from statistics import median, stdev

path = sys.argv[1]
data, cur = {}, None
for line in open(path):
    line = line.strip()
    if line.startswith("microbenchmark "):
        cur = line.split(" ", 1)[1]; data[cur] = []
    elif line.startswith("Iterations: ") and cur:
        data[cur].append(int(line.split(": ")[1]))

# paper order and paper values (baseline µs, OS-San µs, ratio)
PAPER = [("access", "access", 1.98, 7.33, 3.70), ("fixed-mmap", "fixed_mmap", 7.19, 27.05, 3.76),
         ("rwx-mem", "rwx_mem", 2.55, 15.22, 5.96), ("filep-unlocked", "filep_unlocked", 3.55, 6.07, 1.71),
         ("gets", "gets", 54.10, 60.69, 1.12), ("snprintf", "snprintf", 0.28, 6.81, 24.04),
         ("printf-mutability", "printf_mut", 0.18, 6.33, 34.94), ("system-mutability", "system_mut", 4571.43, 4905.57, 1.07),
         ("system-absolute", "system_abs", 4465.28, 4916.42, 1.10), ("security-file-open", "sec_file_open", 1.38, 3.22, 2.33),
         ("interceptable-path", "intercept_path", 1.53, 6.13, 4.00), ("memcpy", "memcpy", 0.07, 9.96, 140.19),
         ("strcpy", "strcpy", 0.04, 4.68, 106.38), ("strncpy", "strncpy", 0.09, 9.46, 103.90),
         ("sprintf", "sprintf", 0.10, 4.77, 46.56)]

md = ["**Table 2 (reproduced): Results of microbenchmarks.** Iteration time [µs], median of trials.", "",
      "| Pass | Baseline | OS-San. | Ratio | Paper: Baseline | Paper: OS-San. | Paper: Ratio |",
      "|---|---:|---:|---:|---:|---:|---:|"]
tex = []
for opt, name, pb, po, pr in PAPER:
    v = data.get(opt)
    if not v or len(v) < 2 or len(v) % 2:
        md.append(f"| {name} | n/a | n/a | n/a | {pb:.2f} | {po:.2f} | {pr:.2f} |"); continue
    n = len(v) // 2
    with_os, without = v[:n], v[n:]
    if min(with_os) == 0 or min(without) == 0:
        md.append(f"| {name} | n/a | n/a | n/a | {pb:.2f} | {po:.2f} | {pr:.2f} |"); continue
    tb = 10e6 / median(without); to = 10e6 / median(with_os); r = to / tb
    md.append(f"| {name} | {tb:.2f} | {to:.2f} | **{r:.2f}** | {pb:.2f} | {po:.2f} | {pr:.2f} |")
    tex.append(f"        {name.replace('_', chr(92) + '_')} & {tb:.2f} & {to:.2f} & {r:.2f} " + r"\\")
md += ["", f"Trials per cell: {len(next(iter(data.values()))) // 2 if data else 0}. "
       "Paper values: System A (Xeon Gold 6248R VM); this run: see meta.txt."]
out = "\n".join(md) + "\n"
print(out)
d = os.path.dirname(path)
open(os.path.join(d, "table2.md"), "w").write(out)
open(os.path.join(d, "table2.tex"), "w").write("\n".join(tex) + "\n")
