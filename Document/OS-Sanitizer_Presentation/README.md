# OS-Sanitizer presentation: slides, figures and benchmark data

Course: Computer System Security · Presenters: Pradeep Kumar Mahato, Vivek Kumar
Paper: A. Crump et al., "OS-Sanitizer: System-wide Latent Defect Inference in Linux Applications", USENIX Security 2026 (`../OS-Sanitizer.pdf`).
Talk format: 10 min presentation + 5 min Q&A, 18 slides (paper: slides 1–8, our work: slides 9–18).

## Files

| Path | What it is |
|---|---|
| `OS-Sanitizer_Presentation.pdf` | The same deck as PDF (18 pages), exported from the PowerPoint |
| `OS-Sanitizer_Presentation.pptx` | The deck as PowerPoint (18 slides), with speaker notes on every slide (fonts: Calibri, Consolas) |
| `speaker_notes.md` | All speaker notes, slide by slide, with timing hints |
| `figures/` | The figures used in the deck, as 220 dpi PNGs |
| `data/` | The raw benchmark tables and CSVs behind every number in the deck |
| `source/` | `figures.py` and `build_pptx.py`, which regenerate the figures and the PPTX |

## Slide outline

| # | Slide |
|---|---|
| 1 | Title |
| 2 | Problem: latent defects never fail a test |
| 3 | Motivating example: same Go code (`os.RemoveAll`), four contexts |
| 4 | Defect inference with eBPF: `intercept_path`, six programs, one `open()` |
| 5 | Paper Figure 2 (image) with three points on intercept_path |
| 6 | Example report and severity levels |
| 7 | 15 passes in four families |
| 8 | Our testbed: Fedora 39 VM with BPF-LSM |
| 9 | Gaps in the paper (five points) |
| 10 | What we implemented (five points, one per gap) |
| 11 | Clustering result: 109× fewer items to read (all 12 passes) |
| 12 | Scoring criteria: score for every criterion, file passes and other passes |
| 13 | Three benchmarks on our VM (Tables 2, 3, 4) |
| 14 | Table 2 (microbenchmarks): cost of each pass in the worst case |
| 15 | Table 3 (real programs): workloads, overhead table, comparison with the paper |
| 16 | Table 4 (paper layout): reports per pass and severity, ours vs paper, plus report volume |
| 17 | Result on the live system: from 207,854 reports to 99 to review first |
| 18 | Conclusion (results) and questions |

## Figures

| File | Slide | Shows |
|---|---|---|
| `fig_paper_figure2.png` | 5 | The paper's Figure 2 (information flow in intercept_path) |
| `fig_clustering_per_pass.png` | 11 | All 12 passes: reports vs clusters (log scale), with "reports → clusters" and "N× fewer" per pass |
| `fig_clustering_reduction.png` | (backup) | Older version: reports per cluster for the six busiest passes |
| `fig_scoring_waterfall.png` | (backup) | Score build-up for Scenario 1 (0.35, suppressed) vs Scenario 2 (1.00, flagged) |
| `fig_table2_microbenchmarks.png` | 14 | Slowdown per pass, our VM vs paper, log scale |
| `fig_table3_real_workloads_heatmap.png` | 15 | Overhead ratio per pass and workload; bold = significant |
| `fig_table4_reports_per_pass.png` | (backup) | Reports per pass, our VM (13.4 h) vs paper (24 h), log scale |
| `fig_score_histogram.png` | 17 | Clusters per score bin; orange = flagged (≥ 0.5) |
| `fig_precision_recall.png` | (not in deck) | Calibration: precision and recall vs score threshold (removed from the talk) |

## Testbed

| Spec | Paper (System A) | Our VM |
|---|---|---|
| OS | Fedora 39 Server VM | Fedora 39 Server VM |
| Kernel | not stated | 6.11.9-100.fc39 |
| Hypervisor | KVM | VirtualBox (KVM paravirtualisation) |
| CPU | Intel Xeon Gold 6248R | AMD Ryzen 5 5600G |
| vCPUs / RAM | 4 / 24 GiB | 10 / 22 GiB + 8 GiB swap |
| Active LSMs | not stated | lockdown, capability, yama, selinux, bpf, landlock, ima, evm |
| Toolchain | Rust + aya | Rust nightly 1.102, aya, bpf-linker, clang 17.0.6, bpftool 7.5 |

## Benchmarks

### 1. Microbenchmarks (paper Table 2) — `data/table2_microbenchmarks/`
- What runs: the paper's 15 C programs from `examples/`, one per pass. Each runs exactly the flagged pattern in a tight loop for 10 s, and the iterations are counted.
- Trials: 10 with os-sanitizer and 10 without, per pass. os-sanitizer is started once per pass, not per trial (runner: `evaluation/quickbench/run_table2.sh`).
- Result: kernel-side passes are 1.0–9.5× slower, the snprintf and printf_mut hooks about 30×, and the memory passes 63–159×. The ranking matches the paper.

### 2. Real workloads (paper Table 3) — `data/table3_real_workloads/`
- SPEC CPU 2017 is licensed, so we used five open stand-ins:

| Workload | Command | Stands in for |
|---|---|---|
| xz | `xz -6 -T1` on a 64 MiB tar | 657.xz |
| gcc | `gcc -O2 -c sqlite3.c` (9 MB source) | 602.gcc |
| perl | `wordfreq.pl` on 48 MiB of text | 600.perlbench |
| sqlite | `sqlite_bench.sql`: 4M rows, string-heavy, in memory | 620.omnetpp |
| stockfish | `stockfish bench 16 1 17` | 631.deepsjeng |

- Configurations: 17 in total. Each pass alone, all non-memory passes ("All previous"), and all passes.
- Trials: 5 per configuration, timed with hyperfine. A fresh baseline is measured before and after every configuration to cancel drift.
- Significance: one-sided Welch's t-test, p < 0.05, the same test as the paper.
- Result: single kernel-side passes cost ≤ 2%. `filep_unlocked` on gcc is 1.30× (paper: 1.32×). With all non-memory passes on, gcc is 1.45× (paper: 1.36×). The memory hooks make sqlite about 4.3× slower.

### 3. Live system (paper Table 4 and §6.4.2) — `data/table4_live_system/`, `data/clustering_scoring/`
- Collection: 13.4 h of normal VM use with the reference policy and JSON output (2026-11-11 13:26 to 2026-11-12 02:51).
- Volume, with calibration runs excluded (paper in brackets): 199,642 entries (~679K in 5 days), 5,612 unique stack offsets (2,784), 216 binaries (127), 36 entries per offset (244).
- Including the calibration runs there are 207,854 reports. They form 1,910 clusters (109 reports per cluster); With the v2 scoring rules, 322 clusters score ≥ 0.5 and 99 score ≥ 0.8 (v1: 349 and 128).
- Caveat: the paper's "Events" column (probe executions) is an internal counter that is not written to the JSON output, so we do not report it.
- Caveat: the 24 `gets` ERROR reports in the calibration-excluded table are probably our own setuid test copies, which are identified only by inode and so slip past the filter. Check this before presenting.

### 4. Calibration scenarios (not presented; data kept for reference) — `data/calibration/`
- What runs: 33 matched scenarios built by `calibration/scenarios.sh` across 11 passes. The same binary runs in a benign context and in an exploitable one, with uid 1001 as the attacker.
- Labels: ground truth comes from how each scenario is constructed. `system_abs` is labelled by an exploit oracle: a fake `ls` logs the uid it actually ran as.
- Result at threshold 0.5, over 44 labelled clusters: TP 8, FP 0, TN 34, FN 2, so precision 1.00 and recall 0.80. The file passes are perfect: 6/6 TPs found and 3/3 FPs suppressed.
- Missed TPs:
  - `g_root_uinput`: the parent shell opens the attacker's file for stdin, so the process itself never opens it.
  - `x_root_upath`: the attacker controls PATH, but environment variables are not captured.
- The threshold sweep is in `score_results_threshold_sweep.txt`.

## Where the work lives in the repository
- Kernel context trailer and JSON output (476 added lines of Rust in existing files, plus the new 199-line json_out.rs): `os-sanitizer-common/src/lib.rs`, `os-sanitizer-ebpf/src/main.rs`, `os-sanitizer/src/json_out.rs`, `os-sanitizer/src/main.rs`
- Clustering: `calibration/cluster.py` · Scoring: `calibration/score.py` · Table 4: `calibration/table4.py` · Scenarios: `calibration/scenarios.sh`
- Benchmark runners: `evaluation/quickbench/run.sh`, `run_table2.sh`, `table2.py`, `table3.py`
- Online deck source (Slides artifact files): `/root/os-sanitizer/presentation/project/`

## Regenerating
```bash
python -m venv venv && venv/bin/pip install matplotlib python-pptx Pillow
venv/bin/python source/figures.py figures
venv/bin/python source/build_pptx.py /root/os-sanitizer/presentation/project/slides figures OS-Sanitizer_Presentation.pptx
```

## Scoring v2 (rules added after inspecting the top of the list)
1. **System service accounts are trusted.** Folders or files owned (or group-writable) by accounts with uid/gid ≤ 999 (e.g. `systemd-resolve`, `nginx`, `postgres`, `redis`, `smmsp`) no longer count as "another user can swap the file" or "writer on the path". Changed in `calibration/cluster.py` (`replaceable_by_untrusted`, `trusted_id`); the cluster key is unchanged, so the 1,910 clusters stay the same.
2. **A non-root process is capped at 0.45** for the file passes, as the other passes already were (e.g. `sendmail` writing its own mail queue). Changed in `calibration/score.py`.

| | v1 | v2 |
|---|---|---|
| Score ≥ 0.5 | 349 | 322 |
| Score ≥ 0.8 | 128 | 99 |
| Score = 1.0 | 80 | 61 (59 are our own exploitable test cases) |
| Score = 1.0 from normal use | 19 | 2 (one program reading the CA certificate bundle) |

Test cases still give 8 TP / 0 FP / 34 TN / 2 FN. Old scripts kept as `cluster.py.v1` and `score.py.v1`; results in `data/clustering_scoring/vm_scored_v2.csv`.
