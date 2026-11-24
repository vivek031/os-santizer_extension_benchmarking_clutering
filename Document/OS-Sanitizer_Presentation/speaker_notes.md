# Speaker notes: OS-Sanitizer presentation (18 slides)

Slides 9-18 are written as one story of about 5 minutes; times in brackets.

## Slide 1: Title slide

~30 s. Introduce ourselves and the paper: OS-Sanitizer, USENIX Security 2026, from CISPA and MPI-SP. Two halves. First about 5 minutes on the paper: the problem, the motivating Go example, how an eBPF pass works (Figure 2), the families of passes, and the VM we reproduced it on. Then about 5 minutes on our work: the gaps we found, what we implemented (kernel context, JSON output, clustering and scoring), and three benchmarks that reproduce the paper's Tables 2, 3 and 4.

## Slide 2: Latent defects never fail a test

~45 s. Classic dynamic testing works by example: run the program, and if something fails you know there is a bug. The chain at the bottom is error, defect, fault, failure. AddressSanitizer or unit tests sit at the fault and failure end: they fire only once the bad behaviour happens, and compiler sanitizers need a rebuild. But many defects are latent: they become a fault only in a particular environment, for example when another user can touch the files a root process opens. The paper asks whether we can infer the defect from runs that behaved fine, using runtime events as context: dynamic defect inference. Why at the OS level with eBPF: no recompilation, the whole system in any language, and it sees the context (credentials, ownership, permissions) that decides whether a code smell is exploitable.

## Slide 3: Same Go code, four contexts

~60 s. A one-line Go program calls os.RemoveAll. Is it vulnerable? From the code alone: no, it is just rm -rf. But the old implementation first checks with Fstatat whether the entry is a directory (1), then opens it unconditionally (2): a time-of-check to time-of-use window. Scenario 1: Alice as root deletes only root-owned trees; nobody else can touch them, so it is safe. Scenario 2: Bob can write directory B; between check and use he replaces C with a symlink, and root deletes a directory Bob chose. Scenario 3: the path goes through Bob's directory, so he can redirect it beforehand without racing. Scenario 4: Bob owns the binary itself; root executing it means Bob runs code as root. Identical code is safe or exploitable depending purely on the execution context, which a runtime tool can see. This bug was really found by OS-Sanitizer. Keep it in mind: our scoring layer encodes exactly the difference between Scenario 1 and Scenario 2.

## Slide 4: intercept_path: six programs, one open()

~75 s, the key paper slide. This table is Figure 2 of the paper, read top to bottom in the kernel's call order. intercept_path catches Scenarios 2 to 4. Checking only the final file's permissions is not enough: any directory along the path can be hijacked, and checking components afterwards from user space would race. So the pass rides along with the kernel's own path resolution. (1) filp_open_fentry, at the entry of do_filp_open, saves the user's requested path. (2) openat_fentry, on path_openat, clears any state left for this thread so the report is specific to this open. (3) As link_path_walk resolves each component, the kernel calls inode_permission, where inode_perm_lsm runs as an LSM program and accumulates which users and groups could modify each component. (4) may_open_fentry records the requested permissions (read, write, exec), later used for severity. (5) At security_file_open the helper bpf_d_path is available, so open_perm_fentry gets the canonical path, reads everything in the map, and emits a report if someone other than the actor could redirect the path. (6) filp_open_fexit cleans up on return. The general recipe for every pass: decide what you need to know, find kernel or user events that expose it, record it in a map, and let the last program decide whether to report.

## Slide 5: Paper Figure 2

~40 s. This is the paper's Figure 2, the information flow inside the intercept_path pass. On the right, the kernel functions that run when a program opens a file, top to bottom. On the left, the six eBPF programs attached to them, and what each one passes to the next through BPF maps: the original path, a clean state, the list of users who can modify each path component, and the access mode. open_perm_fentry, at security_file_open, decides and sends the serialized report; filp_open_fexit cleans up. The pass flags a path that another user could redirect, for example through a symbolic link or a folder they can write.

## Slide 6: Who, what, who else, where

~40 s. This is what intercept_path emits for Scenario 2 (paper Listing 3, shortened). It answers four questions: (1) who is acting (root:root), (2) what access was requested (MAY_READ), (3) who else could intercept the path (uid bob), and (4) where in the binary: a stack trace of binary plus file offset, which is stable across runs and ASLR and can be symbolised to source lines later. Severity is assigned in user space by the kind of access: executing a file someone else can swap is ERROR (Scenario 4, rarely intended), read or write is WARN because there are benign uses like indexers running as root, and the plain TOCTOU pattern of Scenario 1 is INFO. The launcher, a ~2.5k-line Rust systemd service, processes reports in five stages: deserialize, map the stack trace, filter and assign severity, print, and symbolize offline in bulk. Note: severity depends on the pass and access kind, not on context. That is the gap we come back to.

## Slide 7: 15 passes in four families

~45 s. intercept_path was six programs forming one pass; the paper implements 15 passes in four families. (1) Fault-prone system interactions: access (stat or access before open, the TOCTOU pattern), fixed_mmap (MAP_FIXED overlapping existing maps), rwx_mem (writable and executable memory, typical of JITs). (2) Fault-prone library usage via libc uprobes: gets (always unsafe), snprintf (a truncation footgun that leaks memory), printf_mut and system_mut (mutable format strings and commands), system_abs (system() with a relative command, so PATH decides what runs), filep_unlocked (unlocked FILE* use across threads). (3) Environmental defects: sec_file_open (opening a file with unsafe permissions) and intercept_path. (4) Unsafe memory-function usage: memcpy, strcpy, strncpy, sprintf. These hook hot user-space functions, so every call costs a context switch: 46 to 140 times slower in microbenchmarks, and the paper leaves them off for long-term use. Every program in a pass has one role: report, enrich, clean up stale state, or filter known false positives. All passes are about 2.8k lines of Rust using the aya library.

## Slide 8: Testbed: Fedora 39 VM with BPF-LSM

~30 s. We reproduced everything on one virtual machine that closely matches the paper's System A: Fedora 39 Server running as a VM. Ours runs under VirtualBox (with KVM paravirtualisation) on an AMD Ryzen 5 5600G, with 10 vCPUs, 22 GiB RAM plus 8 GiB swap, and a 100 GB disk. The kernel is 6.11.9, and BPF is in the active LSM list (selinux, bpf, landlock), which the LSM-based programs need. Toolchain: Rust nightly 1.102 with the aya eBPF library, bpf-linker, clang 17 and bpftool 7.5. OS-Sanitizer runs as a systemd service with the reference policy, and we added a JSON output mode that feeds our Python clustering and scoring scripts. One difference: the paper used a server VM for benchmarks and a laptop for the month-long study; we did both on this one VM.

## Slide 9: Gaps in the paper

(~30 s) So far, the paper. Now the question we asked ourselves: if you really ran this tool, what would you do with its output? The authors are honest about it: they never measured false positives, because a report is only a real bug in the right context, like the Go example. And the raw output is noisy: hundreds of thousands of log lines, the same finding repeated more than 200 times, a severity that only looks at read, write or execute, and a person sorting it all by hand with grep and awk. That is the gap we picked up.

## Slide 10: What we implemented

(~40 s) Here is what we built, in four steps. First, we made the kernel tell us the context at the moment of the event: who is running, who owns the program, who owns the file and its folder. That is a small change in the eBPF code, about 480 lines of Rust. Second, every report is written as one JSON record, so a script can read it. Third, we group the duplicates. Fourth, we give each group a risk score with a written reason. And to make sure our setup still behaves like the paper's, we re-ran its three benchmarks on our VM.

## Slide 11: Clustering result: 109× fewer items to read

(~30 s) First result: grouping. We left OS-Sanitizer running on our VM for about 13 hours. It produced 207 thousand reports, but only 1,910 distinct findings, about 109 times fewer. The busy passes, like access, collapse the most, because the same code fires again and again. And because the group key includes the context, the safe and the dangerous version of the same code never end up in the same group. The three memory passes are missing here simply because they were switched off, as in the paper, to keep the system fast.

## Slide 12: Scoring criteria: start at 0.5, flag at ≥ 0.5

(~40 s) Now, which of these 1,910 findings matter? Every group starts at 0.5, undecided, and the evidence moves it. A root process, a file another user could swap, another writer on the path: the score goes up. Nobody else can touch the file, a common library pattern, a constant string: it goes down. At 0.5 or more it is flagged. Think back to the Go example: the same code scores 0.35 in root's own folder and 1.0 in Bob's folder. The weights are set by hand so that every one can be explained, and the two rules marked 'new' came from looking at our own results, which I will show in a moment.

## Slide 13: Three benchmarks on our VM

(~15 s) Before trusting any of this, we checked that our VM behaves like the paper's setup. So we repeated its three benchmarks: tiny worst-case programs, real programs, and a live system.

## Slide 14: Cost of each pass in the worst case

(~30 s) The microbenchmarks are the worst case: a tiny program that does nothing but the monitored call, for ten seconds. Passes that watch the kernel cost one to ten times per call; the memory passes up to 159 times. Our exact numbers differ from the paper's because the hardware differs, but the same passes are cheap and the same passes are expensive, so the reproduction holds.

## Slide 15: Real programs: kernel passes cost almost nothing

(~35 s) In real programs the picture is very different. Compiling, compressing, a database, a chess engine: the kernel-side passes cost at most about 2 percent. The one clear exception is gcc with filep_unlocked, 1.30 times, almost exactly the paper's 1.32, because gcc writes all its output with unlocked calls. And in both studies the memory passes are the expensive ones, which is why they stay off in normal use.

## Slide 16: Table 4: reports per pass and severity

(~25 s) On the live system, the shape of the reports matches the paper's Table 4: access dominates and is all INFO, while gets and the system passes are rare. Our run is shorter, so our counts are smaller. But even so, nobody can read 200 thousand lines, and that brings us back to the ranking.

## Slide 17: From 207,854 reports to 99 to review first

(~35 s) Putting it all together: 207 thousand reports, 1,910 groups, and 99 that score high enough to look at first, each with a reason. When we inspected the top of the first list, most score-1 items were root reading files owned by system accounts like systemd-resolve, which are harmless. So we added the two new rules: trust system accounts, and never flag a process that is not root. The top list dropped from 128 to 99, and from normal use only two score-1 items remain, which are worth a closer look.

## Slide 18: Context turns warnings into ranked findings

(~20 s) To sum up: the paper shows that eBPF can find real hidden bugs across a whole system at low cost. Our contribution is making its output usable: the context inside every report, 109 times fewer items to read, and a ranked list with a reason for each one. Thank you, we are happy to take questions.
