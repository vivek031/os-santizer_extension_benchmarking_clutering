"""Story-style speaker notes for slides 9-18 (about 5 minutes in total)."""
STORY = {
    "gap": (
        "(~30 s) So far, the paper. Now the question we asked ourselves: if you really ran this tool, what would you do "
        "with its output? The authors are honest about it: they never measured false positives, because a report is "
        "only a real bug in the right context, like the Go example. And the raw output is noisy: hundreds of thousands "
        "of log lines, the same finding repeated more than 200 times, a severity that only looks at read, write or "
        "execute, and a person sorting it all by hand with grep and awk. That is the gap we picked up."),
    "implemented": (
        "(~40 s) Here is what we built, in four steps. First, we made the kernel tell us the context at the moment of "
        "the event: who is running, who owns the program, who owns the file and its folder. That is a small change in "
        "the eBPF code, about 480 lines of Rust. Second, every report is written as one JSON record, so a script can "
        "read it. Third, we group the duplicates. Fourth, we give each group a risk score with a written reason. And to "
        "make sure our setup still behaves like the paper's, we re-ran its three benchmarks on our VM."),
    "clustering": (
        "(~30 s) First result: grouping. We left OS-Sanitizer running on our VM for about 13 hours. It produced 207 "
        "thousand reports, but only 1,910 distinct findings, about 109 times fewer. The busy passes, like access, "
        "collapse the most, because the same code fires again and again. And because the group key includes the "
        "context, the safe and the dangerous version of the same code never end up in the same group. The three memory "
        "passes are missing here simply because they were switched off, as in the paper, to keep the system fast."),
    "scoring": (
        "(~40 s) Now, which of these 1,910 findings matter? Every group starts at 0.5, undecided, and the evidence "
        "moves it. A root process, a file another user could swap, another writer on the path: the score goes up. "
        "Nobody else can touch the file, a common library pattern, a constant string: it goes down. At 0.5 or more it "
        "is flagged. Think back to the Go example: the same code scores 0.35 in root's own folder and 1.0 in Bob's "
        "folder. The weights are set by hand so that every one can be explained, and the two rules marked 'new' came "
        "from looking at our own results, which I will show in a moment."),
    "benchmarks": (
        "(~15 s) Before trusting any of this, we checked that our VM behaves like the paper's setup. So we repeated "
        "its three benchmarks: tiny worst-case programs, real programs, and a live system."),
    "microbench": (
        "(~30 s) The microbenchmarks are the worst case: a tiny program that does nothing but the monitored call, for "
        "ten seconds. Passes that watch the kernel cost one to ten times per call; the memory passes up to 159 times. "
        "Our exact numbers differ from the paper's because the hardware differs, but the same passes are cheap and the "
        "same passes are expensive, so the reproduction holds."),
    "performance": (
        "(~35 s) In real programs the picture is very different. Compiling, compressing, a database, a chess engine: "
        "the kernel-side passes cost at most about 2 percent. The one clear exception is gcc with filep_unlocked, 1.30 "
        "times, almost exactly the paper's 1.32, because gcc writes all its output with unlocked calls. And in both "
        "studies the memory passes are the expensive ones, which is why they stay off in normal use."),
    "table4": (
        "(~25 s) On the live system, the shape of the reports matches the paper's Table 4: access dominates and is "
        "all INFO, while gets and the system passes are rare. Our run is shorter, so our counts are smaller. But even "
        "so, nobody can read 200 thousand lines, and that brings us back to the ranking."),
    "livevm": (
        "(~35 s) Putting it all together: 207 thousand reports, 1,910 groups, and 99 that score high enough to look at "
        "first, each with a reason. When we inspected the top of the first list, most score-1 items were root reading "
        "files owned by system accounts like systemd-resolve, which are harmless. So we added the two new rules: trust "
        "system accounts, and never flag a process that is not root. The top list dropped from 128 to 99, and from "
        "normal use only two score-1 items remain, which are worth a closer look."),
    "close": (
        "(~20 s) To sum up: the paper shows that eBPF can find real hidden bugs across a whole system at low cost. Our "
        "contribution is making its output usable: the context inside every report, 109 times fewer items to read, "
        "and a ranked list with a reason for each one. Thank you, we are happy to take questions."),
}
