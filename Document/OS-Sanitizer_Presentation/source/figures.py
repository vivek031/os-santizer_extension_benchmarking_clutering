"""Render the deck's figures as PNGs (used in the PPTX and saved for the report)."""
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

INK, MUTED, GRID = "#172033", "#4A5568", "#D5DCE8"
BLUE, ORANGE, GREY, PEACH = "#2F6FDB", "#D9622B", "#9AA3AE", "#FBEADF"
BG = "#FAFAF7"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 13, "axes.edgecolor": GREY, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
})


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=220, bbox_inches="tight")
    plt.close(fig)


# 1. Table 2: microbenchmarks, ours vs paper, log scale ---------------------------------------
T2 = [("access", 4.24, 3.70), ("fixed_mmap", 5.62, 3.76), ("rwx_mem", 9.52, 5.96),
      ("filep_unlocked", 1.43, 1.71), ("gets", 1.40, 1.12), ("snprintf", 28.43, 24.04),
      ("printf_mut", 31.72, 34.94), ("system_mut", 1.04, 1.07), ("system_abs", 1.04, 1.10),
      ("sec_file_open", 1.81, 2.33), ("intercept_path", 4.84, 4.00), ("memcpy", 63.47, 140.19),
      ("strcpy", 95.89, 106.38), ("strncpy", 159.24, 103.90), ("sprintf", 67.95, 46.56)]
fig, ax = plt.subplots(figsize=(8.2, 6.4))
n = len(T2)
ax.axhspan(10.5, 14.5, color=PEACH, zorder=0)
for i, (name, ours, paper) in enumerate(T2):
    ax.plot([ours, paper], [i, i], color="#C5CCD8", lw=2.5, zorder=1)
    ax.scatter(paper, i, s=90, color=GREY, zorder=2, edgecolor="white", linewidth=1.5)
    ax.scatter(ours, i, s=90, color=BLUE, zorder=3, edgecolor="white", linewidth=1.5)
    ax.text(260, i, f"{ours:.2f}×  /  {paper:.2f}×", va="center", fontsize=11.5, color=MUTED)
ax.set_xscale("log")
ax.set_xlim(0.9, 220)
ax.set_xticks([1, 10, 100])
ax.set_xticklabels(["1×", "10×", "100×"])
ax.set_yticks(range(n))
ax.set_yticklabels([t[0] for t in T2], fontfamily="DejaVu Sans Mono", fontsize=12)
ax.invert_yaxis()
ax.grid(axis="x", color=GRID, ls="--", lw=1)
ax.set_xlabel("slowdown per iteration (log scale, 10 trials)")
ax.legend(handles=[Line2D([], [], marker="o", ls="", color=BLUE, ms=9, label="Our VM"),
                   Line2D([], [], marker="o", ls="", color=GREY, ms=9, label="Paper"),
                   Patch(color=PEACH, label="memory passes")],
          loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, frameon=False)
ax.text(260, -1.2, "ours / paper", fontsize=11.5, color=MUTED, fontweight="bold", va="center")
save(fig, "fig_table2_microbenchmarks.png")

# 2. Table 3: real-workload overhead heatmap ---------------------------------------------------
WL = ["xz", "gcc", "perl", "sqlite", "stockfish"]
T3 = [("access", [1.02, 1.00, 1.00, 1.02, 1.00], [1, 0, 0, 0, 0]),
      ("fixed_mmap", [1.00, 1.00, 1.00, 1.00, 0.99], [0] * 5),
      ("rwx_mem", [1.01, 1.00, 1.00, 1.01, 1.01], [0] * 5),
      ("filep_unlocked", [1.00, 1.30, 0.97, 1.01, 1.00], [0, 1, 0, 1, 0]),
      ("gets", [1.00, 1.01, 1.00, 0.97, 1.01], [0] * 5),
      ("snprintf", [1.02, 1.07, 1.04, 1.01, 1.01], [0, 1, 1, 0, 0]),
      ("printf_mut", [1.00, 1.02, 1.02, 1.03, 1.01], [0, 1, 1, 0, 0]),
      ("system_mut", [1.00, 1.00, 1.01, 1.00, 1.01], [0, 0, 0, 0, 1]),
      ("system_abs", [1.01, 1.00, 1.01, 1.01, 1.02], [0] * 5),
      ("sec_file_open", [1.00, 0.99, 1.01, 1.00, 1.01], [0, 0, 1, 0, 0]),
      ("intercept_path", [1.00, 0.99, 1.00, 1.01, 1.00], [1, 0, 0, 0, 0]),
      ("All previous", [0.98, 1.45, 1.17, 1.04, 1.03], [0, 1, 1, 1, 1]),
      ("memcpy", [1.02, 1.32, 1.06, 4.31, 1.03], [0, 1, 1, 1, 1]),
      ("strcpy", [1.04, 1.32, 1.05, 4.32, 1.01], [1, 1, 1, 1, 0]),
      ("strncpy", [1.00, 1.34, 1.07, 4.28, 1.03], [0, 1, 1, 1, 1]),
      ("sprintf", [1.01, 1.06, 1.00, 1.01, 0.99], [0, 1, 0, 0, 0]),
      ("All passes", [1.05, 1.77, 1.05, 4.33, 1.03], [1, 1, 1, 1, 1])]


def shade(v):
    if v <= 1.05:
        return "#FBEADF", INK
    if v <= 1.20:
        return "#F2C3A6", INK
    if v <= 2.0:
        return "#E58D5C", INK
    return "#B4511F", "white"


fig, ax = plt.subplots(figsize=(8.0, 8.2))
for r, (name, vals, sig) in enumerate(T3):
    y = r + (0.5 if r >= 12 else 0)
    for c, v in enumerate(vals):
        bg, fg = shade(v)
        ax.add_patch(plt.Rectangle((c + 0.04, y + 0.06), 0.92, 0.88, color=bg, lw=0))
        ax.text(c + 0.5, y + 0.5, f"{v:.2f}", ha="center", va="center", color=fg, fontsize=12,
                fontweight="bold" if sig[c] else "normal")
    ax.text(-0.12, y + 0.5, name, ha="right", va="center", fontsize=12,
            fontfamily="DejaVu Sans" if name.startswith("All") else "DejaVu Sans Mono",
            fontweight="bold" if name.startswith("All") else "normal")
for c, w in enumerate(WL):
    ax.text(c + 0.5, -0.4, w, ha="center", va="center", fontsize=12.5, fontweight="bold")
ax.set_xlim(-2.6, 5)
ax.set_ylim(18.0, -0.9)
ax.axis("off")
ax.text(-2.6, 18.0, "Run time ÷ baseline (5 trials). Bold = significant, one-sided Welch's t-test p < 0.05.",
        fontsize=10.5, color=MUTED, va="bottom")
save(fig, "fig_table3_real_workloads_heatmap.png")

# 3. Table 4: reports per pass, ours (13.4 h) vs paper (24 h) ------------------------------------
T4 = [("access", 109000, 839000), ("fixed_mmap", 13900, 707000), ("rwx_mem", 317, 62900),
      ("filep_unlocked", 14, 0), ("gets", 24, 0), ("snprintf", 2200, 11300), ("printf_mut", 17, 0),
      ("system_mut/abs", 11, 0), ("sec_file_open", 1, 346), ("intercept_path", 2000, 1821),
      ("sprintf", 72500, None)]
fig, ax = plt.subplots(figsize=(8.2, 5.6))
ys = range(len(T4))
h = 0.38
ax.barh([y - h / 2 for y in ys], [max(t[1], 0.8) for t in T4], height=h, color=BLUE, label="Our VM (13.4 h)")
ax.barh([y + h / 2 for y in ys], [max(t[2] or 0.8, 0.8) for t in T4], height=h, color=GREY, label="Paper (24 h)")
for y, (name, o, p) in zip(ys, T4):
    if p is None:
        ax.text(1.2, y + h / 2, "not tabulated", va="center", fontsize=10, color=MUTED)
    elif p == 0:
        ax.text(1.2, y + h / 2, "0", va="center", fontsize=10, color=MUTED)
ax.set_xscale("log")
ax.set_xlim(0.8, 3e6)
ax.set_yticks(list(ys))
ax.set_yticklabels([t[0] for t in T4], fontfamily="DejaVu Sans Mono", fontsize=11.5)
ax.invert_yaxis()
ax.grid(axis="x", color=GRID, ls="--", lw=1)
ax.set_xlabel("reports per pass (log scale)")
ax.legend(frameon=False, loc="lower right")
save(fig, "fig_table4_reports_per_pass.png")

# 4. Clustering reduction -------------------------------------------------------------------------
# all 12 passes seen on the VM (13.4 h), from calibration/data/vm_20261112/cluster_summary.txt
CL = [("access", 115834, 783), ("sprintf", 72545, 667), ("fixed_mmap", 13938, 118),
      ("intercept_path", 2807, 186), ("snprintf", 2241, 44), ("rwx_mem", 323, 38),
      ("filep_unlocked", 54, 33), ("system_abs", 50, 17), ("gets", 30, 11),
      ("printf_mut", 23, 9), ("sec_file_open", 8, 3), ("system_mut", 1, 1)]
fig, ax = plt.subplots(figsize=(9.4, 6.4))
ys = list(range(len(CL)))
h = 0.38
ax.barh([y - h / 2 for y in ys], [r for _, r, _ in CL], height=h, color="#B8BFCA", label="reports")
ax.barh([y + h / 2 for y in ys], [c for _, _, c in CL], height=h, color=BLUE, label="clusters")
for y, (name, r, c) in zip(ys, CL):
    f = r / c
    fewer = f"{f:.0f}× fewer" if f >= 10 else (f"{f:.1f}× fewer" if f > 1.05 else "no duplicates")
    ax.text(3.2e5, y, f"{r:,} → {c:,}", va="center", ha="left", fontsize=15, color=INK, fontweight="bold")
    ax.text(1.2e7, y, fewer, va="center", ha="left", fontsize=15, color=MUTED)
ax.set_xscale("log")
ax.set_xlim(0.8, 2.2e5)
ax.set_xticks([1, 10, 100, 1000, 10000, 100000])
ax.set_xticklabels(["1", "10", "100", "1k", "10k", "100k"])
ax.set_yticks(ys)
ax.set_yticklabels([t[0] for t in CL], fontfamily="DejaVu Sans Mono", fontsize=15)
ax.invert_yaxis()
ax.grid(axis="x", color=GRID, ls="--", lw=1)
ax.set_xlabel("count (log scale)", fontsize=14)
ax.tick_params(axis="x", labelsize=13)
ax.text(3.2e5, -1.1, "reports → clusters", fontsize=14, color=MUTED, fontweight="bold", va="center")
ax.text(1.2e7, -1.1, "reduction", fontsize=14, color=MUTED, fontweight="bold", va="center")
ax.legend(frameon=False, loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, fontsize=14)
save(fig, "fig_clustering_per_pass.png")

# 5. Score histogram ------------------------------------------------------------------------------
H = [222, 12, 163, 888, 303, 156, 53, 14, 29, 70]  # v2 scoring (service accounts trusted, non-root capped)
fig, ax = plt.subplots(figsize=(7.2, 4.2))
cols = [BLUE if i < 5 else ORANGE for i in range(10)]
ax.bar([i / 10 + 0.05 for i in range(10)], H, width=0.085, color=cols)
for i, v in enumerate(H):
    ax.text(i / 10 + 0.05, v + 12, str(v), ha="center", fontsize=11, color=INK)
ax.set_xticks([i / 10 for i in range(11)])
ax.set_xlim(0, 1)
ax.set_xlabel("score")
ax.set_ylabel("clusters")
ax.grid(axis="y", color=GRID, ls="--", lw=1)
ax.legend(handles=[Patch(color=BLUE, label="below 0.5"), Patch(color=ORANGE, label="flagged, 0.5 and up")],
          frameon=False, loc="upper right")
save(fig, "fig_score_histogram.png")

# 6. Precision / recall vs threshold ---------------------------------------------------------------
TH = [i / 20 for i in range(21)]
P = [.23, .23, .23, .24, .24, .23, .23, .41, .47, .80, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
R = [1, 1, 1, 1, 1, .9, .9, .9, .9, .8, .8, .8, .8, .5, .5, .4, .4, .3, .3, .3, .3]
fig, ax = plt.subplots(figsize=(6.4, 4.4))
ax.plot(TH, P, color=BLUE, lw=2.5, label="Precision")
ax.plot(TH, R, color=ORANGE, lw=2.5, label="Recall")
ax.axvline(0.5, color=INK, ls="--", lw=1.5)
ax.scatter([0.5, 0.5], [1.0, 0.8], color=[BLUE, ORANGE], s=60, zorder=3, edgecolor="white")
ax.text(0.53, 0.88, "threshold 0.5\nP 1.00 · R 0.80", fontsize=11.5, color=INK)
ax.set_xlim(0, 1)
ax.set_ylim(0, 1.05)
ax.set_xlabel("score threshold")
ax.grid(color=GRID, ls="--", lw=1)
ax.legend(frameon=False, loc="lower left")
save(fig, "fig_precision_recall.png")

# 7. Scoring waterfall: Scenario 1 vs Scenario 2 ------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharex=True)
cases = [("Scenario 1: root, root-owned dir (FP)", [("start", 0.5), ("+0.15 privileged", 0.15),
                                                    ("−0.30 nobody can swap", -0.30)], 0.35),
         ("Scenario 2: root, dir of uid 1001 (TP)", [("start", 0.5), ("+0.15 privileged", 0.15),
                                                     ("+0.30 swappable entry", 0.30), ("+0.30 writer on path", 0.30),
                                                     ("−0.05 library idiom", -0.05)], 1.0)]
for ax, (title, steps, final) in zip(axes, cases):
    run, labels = 0.0, []
    for i, (lab, d) in enumerate(steps):
        if i == 0:
            ax.barh(i, d, color=GREY, height=0.6)
            run = d
        else:
            left = run if d > 0 else run + d
            ax.barh(i, abs(d), left=left, color=ORANGE if d > 0 else BLUE, height=0.6)
            run += d
        labels.append(lab)
    ax.barh(len(steps), final, color=INK, height=0.6)
    labels.append(f"= {final:.2f}" + (" (capped)" if run > 1 else ""))
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=11.5)
    ax.invert_yaxis()
    ax.axvline(0.5, color=INK, ls="--", lw=1.2)
    ax.axvline(1.0, color=GREY, ls=":", lw=1.2)
    ax.set_xlim(0, 1.3)
    ax.set_title(title, fontsize=12.5, loc="left", color=INK)
fig.tight_layout()
save(fig, "fig_scoring_waterfall.png")
print("figures written to", OUT)
