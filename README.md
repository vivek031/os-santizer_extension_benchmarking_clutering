# os-sanitizer

This README is updated with all steps tested on Fedora 42.
Your mileage may vary.

> This fork adds structured JSON reports, a system-wide collector, report clustering and
> false-positive calibration, and a quick overhead benchmark. See
> [Extension: clustering, calibration and benchmarking](#extension-clustering-calibration-and-benchmarking).

## Prerequisites

1. Install clang (you need at least libclang.so) of your choice.
2. Install Rust *nightly*: https://rustup.rs/
3. Install bpf-linker: `cargo install --force --git https://github.com/aya-rs/bpf-linker bpf-linker`
4. Install `bpftool` for your system (e.g., for Ubuntu: `sudo apt install linux-tools-common`)
5. Install `aya-tool`: `cargo install bindgen-cli; cargo install --git https://github.com/aya-rs/aya aya-tool`

## Generate Bindings

Your system will use different struct layouts for kernel structures depending on its version.
To generate a fresh set of bindings, use the command:

```sh
aya-tool generate task_struct dentry > os-sanitizer-ebpf/src/binding.rs
```

## Build

```bash
cargo build --release
```

You can additionally add a `--target` flag to specify a target architecture, but you will need a binding file for your
desired target.

## Run

```bash
sudo env RUST_LOG=info ./target/release/os-sanitizer --help
```

If you used a different target, you will need to use `./target/<TARGET>/release/os-sanitizer` instead.

### Installing as a service

```bash
cargo build --release
sudo cp target/release/os-sanitizer /usr/local/sbin/
sudo cp target/release/os-sanitizer-symbolizer /usr/local/bin/
sudo cp os-sanitizer.service /usr/lib/systemd/system/
sudo systemctl enable os-sanitizer
sudo service os-sanitizer start
```

You can then monitor for warnings under:

```bash
sudo journalctl -b -fu os-sanitizer
```

### Symbolisation

Not all OSes have good debuginfod support. This has been tested on Fedora, but is known to not
fetch source information on Ubuntu.

From: https://ubuntu.com/server/docs/service-debuginfod
> Currently, the service only provides DWARF information. There are plans to make it also index and serve source-code in
> the future.

You need to install `debuginfod-find` for your system and set the `DEBUGINFOD_URLS` variable
accordingly before using symbolisation.

To symbolise the logs from os-sanitizer, you will need to apply the symboliser to a _finite length_
input. For example, you can run os-sanitizer and pipe it to a file:

```bash
RUST_LOG=info cargo xtask run --access | tee access.log
```

Then, in another terminal, you can do:

```bash
os-sanitizer-symbolizer access.log
```

If you're using the service form of os-sanitizer, you can similarly do:

```bash
sudo journalctl -b -u os-sanitizer | os-sanitizer-symbolizer
```

As a fun little bonus: os-sanitizer-symbolizer also symoblises ASAN stacktraces -- fun!

## Extension: clustering, calibration and benchmarking

OS-Sanitizer reports are heavily duplicated (the paper measures ~244 log entries per unique report)
and whether a report matters depends on its execution context (paper Sec. 8.2). This extension
automates the deduplication and adds a transparent, context-aware confidence score.

```
os-sanitizer --json  ──>  reports.jsonl  ──>  cluster.py  ──>  clusters.csv  ──>  score.py  ──>  scored.csv
 (run.sh, system-wide)                       (dedup)                          (score + rationale)
```

### JSON report output (`--json FILE`)

`os-sanitizer --json FILE` appends every report as one JSON object per line, next to the normal
text log. Besides the message and level, each record carries:

- `stack`: the full resolved stack as (binary, file offset) pairs, stable across runs and ASLR;
- `ctx`: kernel-captured credentials (uid/euid/fsuid, ...), executable identity and owner/mode,
  owner and mode of the opened object and its parent directory, `parent_uid`, and
  `untrusted_open` (a root process opened a file owned or writable by another user);
- `fields`: pass-specific values (filename, command, `definite_leak`, mmap variant, ...);
- `data_region`: where a template/command/copy source lives (`binary-ro` constant,
  `binary-rw`, or `runtime`).

### `run.sh`: system-wide collector

```bash
cargo build --release
sudo ./run.sh
```

Installs the build as `/usr/local/sbin/os-sanitizer-collect` (keeping the previous binary as
`.prev`) and runs it as the systemd service `os-sanitizer-collect` with `--reference-policy`
(12 of 15 passes; memcpy, strcpy and strncpy are off for overhead reasons). Reports go to
`/var/log/os-sanitizer/reports.jsonl`, and the text log goes to
`journalctl -u os-sanitizer-collect`. An existing `reports.jsonl` is archived, never overwritten.
The service survives logout and reboots; it expects the unit file
`/etc/systemd/system/os-sanitizer-collect.service` to exist.

### `calibration/`

| File | What it does |
|---|---|
| `cluster.py` | Groups reports into clusters keyed by (pass, executable, top-5 stack frames, execution context) and writes one row per cluster with features and an empty `label` column for manual triage. The context is part of the key on purpose: the same code in a benign and an exploitable context must not be merged. Also reads the plain text log, with fewer features. |
| `score.py` | Adds a `score` (0..1), a human-readable `rationale` and `reach` to every cluster. It never drops a report. File passes (access, intercept_path, sec_file_open) are scored by whether another user can replace or redirect what a privileged process opens. Every other pass has its own rule based on its evidence (`definite_leak`, `data_region`, mmap variant, ...) and on **reach**: privileged *and* exposed to something an attacker controls (unprivileged parent, setuid transition, another user's file, or a binary another user can write). Running as root alone is not evidence, and without reach no non-file cluster reaches 0.5. A pass without a rule gets an empty score ("not scored"). |
| `scenarios.sh` | Builds labelled ground truth. The same example binary runs in a benign and an exploitable context (root with trusted input, unprivileged user, root reading attacker data, setuid root run by a user, root with an attacker-writable `PATH` directory). system_abs labels come from an exploit oracle: a fake `ls` records the uid it actually ran as. Setuid copies live in `root:<uid> 0750` dirs and set-id bits are stripped on exit. |
| `table4.py` | Reproduces the paper's Table 4 (report severity per pass) and the report-volume statistics from JSON reports. |
| `data/` | Scenario runs, ground truth (`ground_truth.tsv`, `ground_truth_v2.tsv`), cluster and score outputs, and the VM collection results (`vm_20261112/`). |

Typical use:

```bash
# cluster and score the system-wide log (snapshot first: the file is still being written)
head -n "$(wc -l < /var/log/os-sanitizer/reports.jsonl)" /var/log/os-sanitizer/reports.jsonl > snapshot.jsonl
python3 calibration/cluster.py snapshot.jsonl -o clusters.csv
python3 calibration/score.py clusters.csv -o scored.csv

# rebuild and check the ground truth (root, collector running with --json)
(cd examples && make all)
sudo calibration/scenarios.sh examples /var/tmp/ossan-scenarios 3
#   then cut the new lines out of reports.jsonl and:
python3 calibration/cluster.py scenarios.jsonl -o scen_clusters.csv
python3 calibration/score.py scen_clusters.csv --truth /var/tmp/ossan-scenarios/ground_truth.tsv --sweep
```

Results on `data/ground_truth_v2.tsv` at threshold 0.5: **precision 1.00, recall 0.80** (8 TP,
0 FP, 34 TN, 2 FN). With 10 positive scenarios this validates the rules' logic rather than
measuring real-world accuracy. Known limits:

- **root with an attacker-writable directory in its own `PATH`**: the environment is not captured,
  so this real system_abs issue scores low;
- **inherited file descriptors** (e.g. stdin redirected from a user's file) are not seen by
  `untrusted_open`, which only marks files the process opens itself;
- **printf_mut** drops templates that start with `%` and contain only format specifiers
  (an upstream noise filter), so a pure `%p%p%n` payload is never reported;
- **sprintf** reports carry no source or length, so their score is capped below 0.5;
- under `--reference-policy`, exploitable access/sec_file_open opens are reported as `intercept_path`.

### `evaluation/quickbench/`: overhead benchmarks

| File | What it does |
|---|---|
| `setup.sh` | Installs dependencies and creates fixed inputs once (SQLite amalgamation for gcc, `data.tar` for xz, `corpus.txt` for perl), so every trial processes identical data. |
| `run.sh <tag> <trials> <scenario>...` | Table-3-style overhead measurement: for each scenario (`none`, `all`, `reference-policy`, or a single pass) starts os-sanitizer system-wide, waits until all probes are attached, runs every workload with hyperfine, then stops it. Set `OS_SAN` to choose the binary. |
| `run_table2.sh` | Paper Table 2 microbenchmarks; starts os-sanitizer once per pass (probe removal can crash running processes on kernels older than 6.14). Output format matches the original evaluation scripts. |
| `finish_table3.sh` | Finishes a Table 3 run detached from the terminal (via `systemd-run`), skipping completed steps. |
| `table.py`, `table2.py`, `table3.py` | Print the overhead tables next to the paper's values. |

```bash
cd evaluation/quickbench
sudo ./setup.sh
sudo ./run.sh small6 5 none reference-policy access security-file-open strcpy all
python3 table3.py results/small6
```

### Not in the repository

Large generated files are git-ignored (GitHub rejects files over 100 MB): `evaluation/quickbench/results/`,
`inputs/data.tar` and `inputs/corpus.txt` (recreate with `setup.sh`), `calibration/data/enriched_*/`,
and the compiled `examples/` binaries (`make all`).
