"""Build OS-Sanitizer_Presentation.pptx (18 slides) mirroring the Slides artifact.

usage: build_pptx.py <slides_html_dir> <figures_dir> <out.pptx>
Coordinates are written in px of a 1920x1080 canvas (1 px = 6350 EMU); font sizes in pt.
"""
import html
import os
import re
import sys

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

SLIDES_DIR, FIG, OUT = sys.argv[1:4]

BODY, MONO = "Calibri", "Consolas"
INK, MUTED, FAINT = "172033", "4A5568", "6B7280"
BLUE_T, ORANGE_T = "2F5EA8", "A9461A"          # text accents
BLUE, ORANGE, DARK_OR = "2F6FDB", "D9622B", "B4511F"
PAPER_BG, OURS_BG, DARK_BG = "FAFAF7", "EEF2F8", "141B2B"
CARD, CARD_LINE = "FBFCFE", "D5DCE8"
LIGHT_T, LIGHT_M = "F2F0EA", "AEB8C9"
SKY, PEACH = "8DB3F5", "F29A6B"
TOTAL = 18


def px(v):
    return Emu(int(round(v * 6350)))


def rgb(h):
    return RGBColor.from_string(h.lstrip("#").upper())


def notes_for(sid):
    raw = open(os.path.join(SLIDES_DIR, f"{sid}.html"), encoding="utf-8").read()
    m = re.search(r"<aside>(.*?)</aside>", raw, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


prs = Presentation()
prs.slide_width, prs.slide_height = px(1920), px(1080)
BLANK = prs.slide_layouts[6]


def set_bullet(p, indent=30):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(int(indent * 6350)))
    pPr.set("indent", str(int(-indent * 6350)))
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
        for e in pPr.findall(qn(tag)):
            pPr.remove(e)
    pPr.append(pPr.makeelement(qn("a:buChar"), {"char": "•"}))


def set_number(p, indent=40):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(int(indent * 6350)))
    pPr.set("indent", str(int(-indent * 6350)))
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
        for e in pPr.findall(qn(tag)):
            pPr.remove(e)
    pPr.append(pPr.makeelement(qn("a:buAutoNum"), {"type": "arabicPeriod"}))


def tb(slide, x, y, w, h, paras, size=18, color=INK, font=BODY, bold=False, italic=False, align=None,
       anchor=MSO_ANCHOR.TOP, after=0, line=None, bullet=False, margin=0, name=None, numbered=False):
    """paras: list of paragraphs; a paragraph is a str or a list of str / (str, opts) runs."""
    s = slide.shapes.add_textbox(px(x), px(y), px(w), px(h))
    if name:
        s.name = name
    tf = s.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = px(margin)
    tf.vertical_anchor = anchor
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        runs = para if isinstance(para, list) else [para]
        for run in runs:
            t, o = (run, {}) if isinstance(run, str) else run
            r = p.add_run()
            r.text = t
            f = r.font
            f.size = Pt(o.get("size", size))
            f.bold = o.get("b", bold)
            f.italic = o.get("i", italic)
            f.color.rgb = rgb(o.get("color", color))
            f.name = o.get("font", font)
        if align is not None:
            p.alignment = align
        if line:
            p.line_spacing = line
        if after:
            p.space_after = Pt(after)
        if bullet:
            set_bullet(p)
        if numbered:
            set_number(p)
    return s


def box(slide, x, y, w, h, fill=None, line=None, lw=1.0, radius=0, shape=None):
    kind = shape or (MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE)
    s = slide.shapes.add_shape(kind, px(x), px(y), px(w), px(h))
    if radius and kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = min(0.5, radius / min(w, h))
    if fill:
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
    else:
        s.fill.background()
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(lw)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    return s


def arrow(slide, x, y, w=40, h=22, color="9AA3AE"):
    return box(slide, x, y, w, h, fill=color, shape=MSO_SHAPE.RIGHT_ARROW)


def img(slide, path, x, y, w, h, align="center"):
    iw, ih = Image.open(path).size
    scale = min(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    dx = x + (w - dw) / 2 if align == "center" else x
    pic = slide.shapes.add_picture(path, px(dx), px(y + (h - dh) / 2), px(dw), px(dh))
    pic.name = os.path.basename(path)
    return pic


def table(slide, x, y, w, fracs, rows, size=15, row_h=56, head_fill="E6EAF0", head_color=INK,
          fills=(PAPER_BG, "F2F1EC"), font=BODY):
    """rows[0] is the header. A cell is str or (str, opts) with opts b / color / fill / align / font."""
    shp = slide.shapes.add_table(len(rows), len(fracs), px(x), px(y), px(w), px(row_h * len(rows)))
    t = shp.table
    t._tbl.tblPr.set("firstRow", "0")
    t._tbl.tblPr.set("bandRow", "0")
    for j, f in enumerate(fracs):
        t.columns[j].width = px(w * f)
    for i, row in enumerate(rows):
        t.rows[i].height = px(row_h)
        for j, v in enumerate(row):
            text, o = (v, {}) if isinstance(v, str) else v
            c = t.cell(i, j)
            c.fill.solid()
            c.fill.fore_color.rgb = rgb(o.get("fill", head_fill if i == 0 else fills[(i - 1) % 2]))
            c.margin_left = c.margin_right = px(16)
            c.margin_top = c.margin_bottom = px(6)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = c.text_frame.paragraphs[0]
            p.alignment = o.get("align", PP_ALIGN.LEFT)
            r = p.add_run()
            r.text = text
            r.font.size = Pt(o.get("size", size))
            r.font.name = o.get("font", font)
            r.font.bold = o.get("b", i == 0)
            r.font.color.rgb = rgb(o.get("color", head_color if i == 0 else INK))
    return shp


def new_slide(sid, bg, eyebrow=None, title=None, num=None, eyebrow_color=BLUE_T, dark=False, notes=None):
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = rgb(bg)
    if eyebrow:
        tb(s, 128, 92, 1400, 40, [eyebrow.upper()], size=12, bold=True, color=eyebrow_color, name="Eyebrow")
    if title:
        tb(s, 128, 132, 1664, 90, [title], size=32, bold=True, color=LIGHT_T if dark else INK, name="Title",
           anchor=MSO_ANCHOR.TOP)
    if num:
        tb(s, 1552, 56, 240, 36, [f"{num:02d} / {TOTAL}"], size=12, color=LIGHT_M if dark else FAINT,
           align=PP_ALIGN.RIGHT, name="Page number")
    s.notes_slide.notes_text_frame.text = notes if notes is not None else notes_for(sid)
    return s


B = lambda t: (t, {"b": True})                       # noqa: E731
C = lambda t, col, b=True: (t, {"color": col, "b": b})  # noqa: E731
M = lambda t, **k: (t, {"font": MONO, **k})           # noqa: E731

# ============================================================== 1 cover (as edited online)
s = new_slide("cover", DARK_BG, notes="~30 s. Introduce ourselves and the paper: OS-Sanitizer, USENIX Security 2026, from CISPA and MPI-SP. Two halves. First about 5 minutes on the paper: the problem, the motivating Go example, how an eBPF pass works (Figure 2), the families of passes, and the VM we reproduced it on. Then about 5 minutes on our work: the gaps we found, what we implemented (kernel context, JSON output, clustering and scoring), and three benchmarks that reproduce the paper's Tables 2, 3 and 4.")
tb(s, 128, 284, 1100, 40, ["E0-256  COMPUTER SYSTEM SECURITY"], size=12, bold=True, color=PEACH)
tb(s, 128, 340, 1100, 130, ["OS-Sanitizer"], size=52, bold=True, color=LIGHT_T)
tb(s, 128, 486, 1100, 70, ["Latent defect inference with eBPF and report clustering and scoring"], size=20, color=LIGHT_T)
box(s, 128, 610, 160, 2, fill="3A4560")
tb(s, 128, 650, 1100, 50, ["Pradeep Kumar Mahato 26954 · Vivek Kumar 26357"], size=15, bold=True, color=LIGHT_T)

# ============================================================== 2 problem
s = new_slide("problem", PAPER_BG, "The paper · Problem", "Latent defects never fail a test", 2)
tb(s, 128, 270, 1664, 330, [
    ["Testing finds bugs only when something ", B("fails")],
    ["Latent defects: ", B("safe in one context, exploitable in another")],
    ["ASan / MSan: rebuild needed, catch only the fault"],
    ["OS-Sanitizer ", B("infers the defect"), " from benign runs, via eBPF"],
], size=24, bullet=True, after=18)
cols = [("Error", 128), ("Defect", 560), ("Fault", 992), ("Failure", 1424)]
for i, (word, cx) in enumerate(cols):
    tb(s, cx, 700, 368, 70, [word], size=28, bold=True, color=INK if word == "Defect" else FAINT, align=PP_ALIGN.CENTER)
    if i < 3:
        tb(s, cx + 368, 700, 64, 70, ["→"], size=28, color="9AA3AE", align=PP_ALIGN.CENTER)
box(s, 560, 790, 368, 6, fill=BLUE)
box(s, 992, 790, 800, 6, fill=ORANGE)
tb(s, 560, 810, 368, 40, ["OS-Sanitizer"], size=16, bold=True, color=BLUE_T, align=PP_ALIGN.CENTER)
tb(s, 992, 810, 800, 40, ["ASan, MSan, tests"], size=16, bold=True, color=ORANGE_T, align=PP_ALIGN.CENTER)

# ============================================================== 4 motivating example
s = new_slide("motivating", PAPER_BG, "The paper · Motivating example", "Same Go code, four contexts", 3)
box(s, 128, 270, 800, 320, fill="1B2333", radius=16)
tb(s, 160, 296, 740, 280, [
    [("// Go os.RemoveAll, before 2024", {"color": LIGHT_M})],
    ["Fstatat(parentFd, base, &st) ", ("① CHECK", {"color": PEACH})],
    ["if !isDir(st) { return }"],
    [("// race window", {"color": LIGHT_M})],
    ["openFdAt(parentFd, base)    ", ("② USE", {"color": PEACH})],
], size=15, font=MONO, color=LIGHT_T, line=1.2)
tb(s, 128, 630, 800, 230, [
    ["A/            alice"],
    ["├─ B/         ", ("bob (attacker)", {"color": ORANGE_T})],
    ["│  └─ C → ../D"],
    ["└─ D/ └─ E/   alice"],
], size=17, font=MONO, line=1.2)
tb(s, 990, 280, 802, 420, [
    [C("S1 safe: ", BLUE_T), "root-only tree"],
    [C("S2 exploitable: ", ORANGE_T), "Bob swaps C mid-race"],
    [C("S3 exploitable: ", ORANGE_T), "path crosses Bob’s dir"],
    [C("S4 exploitable: ", ORANGE_T), "Bob owns the binary"],
], size=23, bullet=True, after=20)
box(s, 990, 750, 802, 110, fill="FBEADF", radius=12)
tb(s, 1020, 750, 750, 110, ["Real bug, now fixed in Go, Docker, Kubernetes, runc"], size=17, anchor=MSO_ANCHOR.MIDDLE)

# ============================================================== 5 intercept_path (Fig. 2)
s = new_slide("interceptpath", PAPER_BG, "The paper · Defect inference with eBPF (Fig. 2)",
              "intercept_path: six programs, one open()", 4)
rep = {"fill": "FCEFE6", "b": True}
mono = {"font": MONO}
table(s, 128, 260, 1664, [0.28, 0.30, 0.13, 0.29], [
    ["Kernel function", "eBPF program", "Role", "Collects"],
    [("do_filp_open", mono), ("filp_open_fentry", mono), "Enrich", "requested path"],
    [("path_openat", mono), ("openat_fentry", mono), "Clean", "reset state"],
    [("link_path_walk", mono), ("inode_perm_lsm", mono), "Enrich", "writers per dir"],
    [("may_open", mono), ("may_open_fentry", mono), "Enrich", "access mode"],
    [("security_file_open", {**rep, **mono}), ("open_perm_fentry", {**rep, **mono}), ("Report", rep),
     ("real path → report", rep)],
    [("do_filp_open (exit)", mono), ("filp_open_fexit", mono), "Clean", "free state"],
], size=18, row_h=72)
tb(s, 128, 830, 1664, 130, [
    ["Programs share one ", B("per-thread eBPF map")],
    ["Report if ", B("another user can redirect"), " the path"],
], size=21, bullet=True, after=10)

# ============================================================== 5 paper Figure 2 (added online)
s = new_slide("a896d9e1", PAPER_BG, num=5, notes="~40 s. This is the paper's Figure 2, the information flow inside the intercept_path pass. On the right, the kernel functions that run when a program opens a file, top to bottom. On the left, the six eBPF programs attached to them, and what each one passes to the next through BPF maps: the original path, a clean state, the list of users who can modify each path component, and the access mode. open_perm_fentry, at security_file_open, decides and sends the serialized report; filp_open_fexit cleans up. The pass flags a path that another user could redirect, for example through a symbolic link or a folder they can write.")
img(s, os.path.join(FIG, "fig_paper_figure2.png"), 0, 0, 878, 1080, align="left")
tb(s, 952, 160, 840, 760, [
    ["Attaches six eBPF programs to monitor file-path resolution and permission checks in the Linux kernel."],
    ["Tracks requested paths, file permissions, and users/groups that can modify path components using BPF Maps."],
    ["Detects potentially unsafe path redirection by attackers through symbolic links or modifiable directories."],
], size=19, bullet=True, after=22)

# ============================================================== 6 example report
s = new_slide("report", PAPER_BG, "The paper · Example report", "Who, what, who else, where", 6)
box(s, 128, 270, 880, 420, fill="1B2333", radius=16)
tb(s, 164, 300, 820, 380, [
    ["[WARN] listing-1 (pid 204448)"],
    [("① acting as root:root", {"color": SKY})],
    ["   accessed /tmp/…/A/B"],
    [("② with [\"MAY_READ\"]", {"color": SKY})],
    [("③ interceptable by uids [bob]", {"color": PEACH})],
    [("④ #0 listing-1+0x286e", {"color": LIGHT_M})],
    [("   #1 listing-1+0x5fab8 …", {"color": LIGHT_M})],
], size=18, font=MONO, color=LIGHT_T, line=1.15)
tb(s, 1080, 280, 712, 40, ["Severity by access kind"], size=16, bold=True, color=MUTED)
tb(s, 1080, 340, 712, 340, [
    [C("ERROR", ORANGE_T), ": execute (S4)"],
    [B("WARN"), ": read / write (S2, S3)"],
    [C("INFO", FAINT), ": pattern only (S1)"],
], size=24, bullet=True, after=22)

# ============================================================== 7 passes
s = new_slide("passes", PAPER_BG, "The paper · eBPF passes", "15 passes in four families", 7)
table(s, 128, 260, 1664, [0.20, 0.62, 0.18], [
    ["Family", "Passes", "Hook"],
    ["System calls", ("access, fixed_mmap, rwx_mem", mono), "kernel"],
    ["Library usage", ("gets, snprintf, printf_mut, system_mut, system_abs, filep_unlocked", mono), "libc"],
    ["Environment", ("sec_file_open, intercept_path", mono), "kernel + LSM"],
    ["Memory", ("memcpy, strcpy, strncpy, sprintf", mono), "libc"],
], size=18, row_h=96)
tb(s, 128, 820, 1664, 140, [
    ["Each program ", B("reports"), ", ", B("enriches"), ", ", B("cleans up"), " or ", B("filters")],
    ["Memory passes: 46–140× slower, ", B("off by default")],
], size=21, bullet=True, after=12)

# ============================================================== 8 testbed
s = new_slide("testbed", PAPER_BG, "Implementation · Our VM", "Testbed: Fedora 39 VM with BPF-LSM", 8, notes="~30 s. We reproduced everything on one virtual machine that closely matches the paper's System A: Fedora 39 Server running as a VM. Ours runs under VirtualBox (with KVM paravirtualisation) on an AMD Ryzen 5 5600G, with 10 vCPUs, 22 GiB RAM plus 8 GiB swap, and a 100 GB disk. The kernel is 6.11.9, and BPF is in the active LSM list (selinux, bpf, landlock), which the LSM-based programs need. Toolchain: Rust nightly 1.102 with the aya eBPF library, bpf-linker, clang 17 and bpftool 7.5. OS-Sanitizer runs as a systemd service with the reference policy, and we added a JSON output mode that feeds our Python clustering and scoring scripts. One difference: the paper used a server VM for benchmarks and a laptop for the month-long study; we did both on this one VM.")
table(s, 128, 260, 980, [0.28, 0.34, 0.38], [
    ["Spec", "Paper", "Ours"],
    ["OS", "Fedora 39", B("Fedora 39")],
    ["Kernel", "n/a", B("6.11.9")],
    ["Hypervisor", "KVM", B("VirtualBox")],
    ["CPU", "Xeon 6248R", B("Ryzen 5 5600G")],
    ["vCPUs", "4", B("10")],
    ["RAM", "24 GiB", B("22 GiB")],
], size=19, row_h=88)
tb(s, 1180, 290, 612, 500, [
    ["BPF LSM enabled"], ["Rust nightly + aya"], ["systemd service + ", B("JSON output")],
    ["All experiments on ", B("one VM")],
], size=23, bullet=True, after=26)

# ============================================================== 9 gaps in the paper
s = new_slide("gap", PAPER_BG, "Our work · Gaps in the paper", "Gaps in the paper", 9, eyebrow_color=ORANGE_T,
              notes='~45 s. This slide lists what the paper leaves open. First, the authors never measure false positives; in Section 8.2 they say deciding whether a report is a real bug is deeply non-trivial. Second, the reason is context: as in the motivating example, the same code is safe or exploitable depending on who runs it and who owns the files. Third, the tool writes one line per occurrence, so duplicates had to be grouped by hand: in five days they got about 679 thousand log entries, roughly 244 copies of each finding. Fourth, severity is fixed per pass: it depends on the access type, read, write or execute, not on how exploitable the situation is. The access pass reports every check-then-open as INFO, even when another user could exploit it; intercept_path does check whether another user could redirect the path, but every such read is WARN, whether the other user is an attacker or a system service. And related reports from different passes are not linked: the Go bug showed up as an INFO from access and a WARN from intercept_path, and a person had to connect them. Fifth, every report had to be checked by a person: the authors read the logs, filtered them with grep, awk and sort, looked up the source code, and reproduced the behaviour, about two hours a week for a month. Our work targets exactly these gaps.')
tb(s, 128, 280, 1664, 620, [
    [B("No false-positive rate."), " The authors say judging a report is “deeply non-trivial” (§8.2)."],
    [B("The verdict depends on context."), " The same code is safe or exploitable depending on who runs it and who owns the files."],
    [B("Duplicates are grouped by hand."), " 679K log entries in 5 days, about 244 copies of each finding."],
    [B("Severity is fixed per pass."), " It depends on the access type (read, write, execute), not on how exploitable the situation is; related reports from different passes are not linked."],
    [B("Reports are checked by hand."), " A person reads and filters them with grep, awk and sort: about 2 hours a week."],
], size=21, bullet=True, after=22)

# ============================================================== 10 what we implemented
s = new_slide("implemented", PAPER_BG, "Our work · Implementation", "What we implemented", 10, eyebrow_color=ORANGE_T,
              notes="~60 s. On top of the paper's tool we built five things. One, kernel context: in the eBPF code every report now gets a 128-byte context block, filled in inside the kernel at the moment of the event, so it is exact even for processes that exit right away. It holds the real, effective and file-system user IDs; the executable's inode, owner and permissions; the parent process's user ID; and the owner and permissions of the file and of its parent folder, because whoever owns the folder can replace the file. We also added a new LSM hook that only observes, never blocks: it marks a root process that opens a file owned by another user or writable by everyone. About 476 added lines of Rust in os-sanitizer-ebpf and os-sanitizer-common. Two, JSON output: a new --json option writes one complete record per report: pass, severity, program, PID, time, the kernel context, the pass's own details such as which users can write the path, and the full stack trace resolved to binary plus offset, which stays the same across runs. Three, clustering: cluster.py puts reports in the same group when they have the same pass, the same program, the same top five stack frames, and the same context: is it root, can another user swap the file, are there other writers. Four, scoring gives each group a 0 to 1 risk score with a written reason; the exact criteria are on slide 12. Five, evaluation: we reproduced the paper's Tables 2, 3 and 4 on our VM.")


def _para(tf, first, runs, size, color=INK):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    for run in runs:
        t, o = (run, {}) if isinstance(run, str) else run
        r = p.add_run()
        r.text = t
        r.font.size = Pt(o.get("size", size))
        r.font.bold = o.get("b", False)
        r.font.name = o.get("font", BODY)
        r.font.color.rgb = rgb(o.get("color", color))
    return p


def _indent(p, marl, ind, bu):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(int(marl * 6350)))
    pPr.set("indent", str(int(-ind * 6350)))
    pPr.append(bu(pPr))


shape = s.shapes.add_textbox(px(128), px(262), px(1664), px(690))
tf = shape.text_frame
tf.word_wrap = True
tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
MONO_T = {"font": MONO, "color": MUTED, "size": 14}
items = [
    (0, 1, [B("Kernel context"), "  ", ("os-sanitizer-ebpf, -common · ~476 lines of Rust", MONO_T)]),
    (1, 0, ["Every report gets a context block filled in the kernel at the event: user IDs (real, effective, file-system), "
            "the program’s owner and permissions, the parent’s user ID, the owner and permissions of the file and its folder"]),
    (1, 0, ["New LSM hook (observe only): flags a root process that opens another user’s file"]),
    (0, 2, [B("JSON output"), "  ", ("--json · json_out.rs", MONO_T)]),
    (1, 0, ["One record per report: pass, severity, program, PID, time, kernel context, pass details "
            "(e.g. who can write the path), full stack as binary + offset"]),
    (0, 3, [B("Clustering"), "  ", ("cluster.py", MONO_T)]),
    (1, 0, ["Same group if same ", B("pass + program + top-5 stack frames + context"),
            " (root? can another user swap the file? other writers?)"]),
    (0, 4, [B("Scoring"), "  ", ("score.py", MONO_T)]),
    (1, 0, ["Gives each cluster a 0–1 risk score with a written reason (criteria on slide 12)"]),
    (0, 5, [B("Evaluation"), ":  reproduced the paper’s Tables 2, 3 and 4 on our VM"]),
]
for i, (lvl, num, runs) in enumerate(items):
    if lvl == 0:
        p = _para(tf, i == 0, runs, 19)
        _indent(p, 44, 44, lambda pp, n=num: pp.makeelement(qn("a:buAutoNum"), {"type": "arabicPeriod", "startAt": str(n)}))
        p.space_before = Pt(0 if i == 0 else 12)
        p.space_after = Pt(4)
    else:
        p = _para(tf, False, runs, 16, color="2D3748")
        _indent(p, 84, 26, lambda pp: pp.makeelement(qn("a:buChar"), {"char": "–"}))
        p.space_after = Pt(4)

# ============================================================== 11 clustering result
s = new_slide("clustering", PAPER_BG, "Our work · Clustering", "Clustering result: 109× fewer items to read", 11,
              eyebrow_color=ORANGE_T, notes='~40 s. This is what clustering achieved on our VM in 13.4 hours. Each row is one pass: the grey bar is how many reports it produced, the blue bar how many clusters remain, on a log scale. On the right, the exact numbers. For example, access produced 115,834 reports, which collapse into 783 clusters: on average each cluster holds 148 copies of the same finding, so it is 148 times fewer items to read. Overall 207,854 reports become 1,910 clusters, 109 times fewer. The busy passes shrink the most, because the same code runs again and again: access, fixed_mmap (the dynamic loader on every program start) and sprintf. Rare passes such as gets, printf_mut or system barely shrink, because their few reports are already different findings, and system_mut had only one report. Because the cluster key includes the context, a root case and a normal-user case of the same code never end up in the same cluster. Note that only 12 of the 15 passes appear: memcpy, strcpy and strncpy were switched off in this live run, as in the paper, because their overhead is very large (4 to 159 times slower) and would slow down every running program. We still measured all 15 passes in the performance benchmarks.')
tb(s, 128, 238, 1664, 60, [[B("207,854 → 1,910"), " · busy passes shrink most · rare passes barely shrink · "
                             "root and normal-user cases stay apart"]], size=17, color=MUTED)
img(s, os.path.join(FIG, "fig_clustering_per_pass.png"), 128, 296, 1664, 590)
tb(s, 128, 900, 1664, 50, [[B("Note: "), "memcpy, strcpy and strncpy were switched off in this live run. Their overhead is very large "
                            "(4–159× slower), so turning them off kept running programs from slowing down, as in the paper."]],
   size=14, color=MUTED)

# ============================================================== 12 scoring (full criteria)
s = new_slide("scoring", PAPER_BG, "Our work · Scoring", "Scoring criteria: start at 0.5, flag at ≥ 0.5", 12,
              eyebrow_color=ORANGE_T)
R = PP_ALIGN.RIGHT
rt = lambda t, b=False: (t, {"align": R, "b": b})  # noqa: E731
tb(s, 128, 252, 900, 36, ["File passes (access, intercept_path, sec_file_open)"], size=14, bold=True, color=MUTED)
table(s, 128, 292, 900, [0.72, 0.28], [
    ["Criterion", rt("Score", True)],
    ["Start", rt("0.50")],
    ["Root process / normal-user process", rt("+0.15 / −0.30")],
    [("Not root: never above 0.45 (new)", {"b": True}), rt("cap 0.45", True)],
    ["Another user can swap the file / nobody can", rt("+0.30 / −0.30")],
    ["Another user can write a folder on the path", rt("+0.30")],
    ["Root reads a world-writable file", rt("+0.20")],
    ["Root process already read another user’s file", rt("+0.20")],
    ["Root process started by a normal user", rt("+0.15")],
    ["Root runs a program others can modify", rt("+0.20")],
    ["Program is setuid / setgid", rt("+0.05")],
    ["Packaged program (rpm) / library code", rt("−0.05 each")],
    ["Kernel pseudo-file (/proc, pipe, socket)", rt("= 0.05")],
    [("System accounts (uid ≤ 999) trusted like root (new)", {"b": True}), rt("no penalty", True)],
], size=14, row_h=46)
tb(s, 1100, 252, 692, 36, ["Other passes · (+x) only if a normal user can reach root"], size=14, bold=True,
   color=MUTED)
table(s, 1100, 292, 692, [0.42, 0.58], [
    ["Pass", rt("Score", True)],
    ["gets", rt("0.45 (+0.40)")],
    ["printf/system_mut", rt("0.10 const · 0.45 (+0.30)")],
    ["system_abs", rt("0.80 user parent · ≤ 0.35")],
    ["snprintf", rt("0.20 · leak 0.40 (+0.35)")],
    ["fixed_mmap", rt("0.05 hint · 0.40 bad prot.")],
    ["rwx_mem", rt("0.30 (+0.30)")],
    ["filep_unlocked", rt("0.30")],
    ["sprintf", rt("0.30 (+0.15)")],
], size=14, row_h=50)
tb(s, 1100, 790, 692, 70, [
    [B("Example: "), "S1 = 0.35 (low) · S2 = 1.00 (flagged)"],
], size=15, after=6)
box(s, 1100, 850, 692, 190, fill="F2F1EC", radius=10)
tb(s, 1120, 862, 652, 170, [
    [B("Note: weights are hand-set, not learned.")],
    ["±0.30 = attacker can directly control the file · 0.15–0.20 = indirect sign that attacker input reaches root · "
     "0.05 = weak hint. Below 0.5 unless a privilege boundary is crossed. Scores capped to 0–1; can be tuned with labelled data."],
], size=12, color=MUTED, after=4)

# ============================================================== 12 benchmarks
s = new_slide("benchmarks", PAPER_BG, "Our work · Evaluation", "Three benchmarks on our VM", 13, eyebrow_color=ORANGE_T, notes="~30 s. We ran three benchmarks, all on the same VM, to reproduce the paper's Tables 2, 3 and 4. Table 2: the paper's 15 small C programs, one per pass, each repeating the flagged pattern in a loop for 10 seconds; 10 trials with and without OS-Sanitizer. This is the worst case. Table 3: real programs. The paper used SPEC CPU 2017, which is a paid benchmark suite, so we used free programs that do the same kind of work: gcc compiling code, xz compressing files, a perl text script, an in-memory SQLite database and the stockfish chess engine. 5 trials each, with a fresh baseline before and after each configuration. Table 4: we left OS-Sanitizer running for 13.4 hours of normal use and counted the reports per pass.")
table(s, 128, 270, 1664, [0.30, 0.42, 0.28], [
    ["Benchmark", "What we ran", "Measures"],
    [("Table 2 · micro", {"b": True}), "15 small C programs", "worst-case slowdown"],
    [("Table 3 · real", {"b": True}), "xz, gcc, perl, sqlite, stockfish", "run-time overhead"],
    [("Table 4 · live", {"b": True}), "13.4 h of normal use", "reports per pass"],
], size=18, row_h=86)
tb(s, 128, 680, 1664, 120, [[B("Why not SPEC? "), "The paper used SPEC CPU 2017, a paid benchmark suite. We used free "
                            "programs that do the same kind of work instead: compiling code (gcc), compressing files (xz), "
                            "text processing (perl), a database (sqlite) and a chess engine (stockfish)."]], size=17, color=MUTED)

# ============================================================== 13 Table 2
s = new_slide("microbench", PAPER_BG, "Benchmark · Table 2 · Microbenchmarks", "Cost of each pass in the worst case", 14,
              eyebrow_color=ORANGE_T, notes="~45 s. This is the paper's Table 2, repeated on our VM. A microbenchmark is a tiny test program that does only one thing. There is one per pass: for example the access test only calls stat() and then open() on a file, over and over, in a loop that does nothing else for 10 seconds; that is what a tight loop means. We count how many loops it completes with and without OS-Sanitizer, 10 times each, and the ratio is the slowdown shown here: blue is our VM, grey is the paper, on a log scale. Because the program does nothing except the monitored call, this is the worst case: every bit of OS-Sanitizer's cost is visible. Passes that watch the kernel cost about 1 to 10 times. The memory passes, shaded, hook memcpy, strcpy and similar functions that normally take only nanoseconds, so the cost of jumping into eBPF dominates: 63 to 159 times. Our absolute numbers differ from the paper's because the CPU and the virtual machine differ, but the same passes are cheap and the same passes are expensive in both, which shows our reproduction is consistent. Real programs do much more than one call, so their slowdown is far smaller, as the next slide shows.")
img(s, os.path.join(FIG, "fig_table2_microbenchmarks.png"), 128, 250, 1040, 690, align="left")
tb(s, 1220, 270, 572, 660, [
    [B("Test:"), " one tiny C program per pass, repeating only the flagged call (e.g. stat → open) for 10 s"],
    [B("Measure:"), " loops per second with vs without OS-Sanitizer (10 runs)"],
    [B("Kernel passes:"), " 1–10× slower"],
    [B("Memory passes:"), " 63–159× slower"],
    [B("Our results agree with the paper:"), " the same passes are cheap and the same are expensive"],
], size=16, bullet=True, after=14)

# ============================================================== 14 Table 3
s = new_slide("performance", PAPER_BG, "Benchmark · Table 3 · Real programs", "Real programs: kernel passes cost almost nothing",
              15, eyebrow_color=ORANGE_T, notes="~50 s. This is the paper's Table 3 on our VM: how much slower real programs run with OS-Sanitizer on. The paper used SPEC CPU 2017, so we picked five free programs, each with a fixed input: xz compresses a 64 MiB tar archive of 4,964 system files at level 6, taking about 20 seconds; gcc compiles sqlite3.c, a single C file of 257,679 lines, with -O2, also about 20 seconds; a 20-line perl script counts word frequencies in 48 MiB of text, about 6 million words, in 6.6 seconds; sqlite inserts 4 million rows into an in-memory table, builds two indexes and runs three queries, in 9 seconds; and Stockfish 17 runs its built-in chess benchmark to depth 17 in 13.5 seconds. Each cell is run time divided by the baseline: 1.00 means no slowdown; darker is slower; bold means statistically significant with Welch's t-test, as in the paper; 5 runs each. The pattern matches the paper's Table 3. The five passes that hook the kernel (access, fixed_mmap, rwx_mem, sec_file_open, intercept_path) cost at most 2 percent alone here and at most 7 percent in the paper. filep_unlocked slows gcc by 1.30 times, the paper measured 1.32 for the same case, because gcc writes its output with unlocked stdio calls. With all non-memory passes together gcc is 1.45 times slower, the paper 1.36. The memory passes are the expensive ones in both: sqlite 4.3 times here, up to 6.3 times on perlbench among the paper's SPEC programs.")
img(s, os.path.join(FIG, "fig_table3_real_workloads_heatmap.png"), 100, 228, 790, 790, align="left")
tb(s, 920, 236, 872, 36, ["Workloads (5 runs each · baseline = without OS-Sanitizer)"], size=14, bold=True, color=MUTED)
table(s, 920, 276, 872, [0.17, 0.66, 0.17], [
    ["Program", "What it does", rt("Baseline", True)],
    ["xz", "compress 64 MiB tar (4,964 files)", rt("19.9 s")],
    ["gcc", "compile sqlite3.c (257,679 lines)", rt("19.9 s")],
    ["perl", "count 6.0 M words in 48 MiB text", rt("6.6 s")],
    ["sqlite", "4 M rows in memory, 3 queries", rt("9.0 s")],
    ["stockfish", "Stockfish 17 chess, depth 17", rt("13.5 s")],
], size=16, row_h=52)
tb(s, 920, 612, 872, 36, ["Same pattern as the paper’s Table 3"], size=14, bold=True, color=MUTED)
table(s, 920, 652, 872, [0.56, 0.22, 0.22], [
    ["Finding", rt("Ours", True), rt("Paper", True)],
    ["Kernel-hook pass alone", rt("≤ 1.02×"), rt("≤ 1.07×")],
    ["filep_unlocked on gcc", rt("1.30×", True), rt("1.32×")],
    ["All non-memory passes, gcc", rt("1.45×"), rt("1.36×")],
    ["Memory passes, worst program", rt("4.3×", True), rt("6.3×")],
], size=16, row_h=52)

# ============================================================== 15 Table 4 (paper layout)
s = new_slide("table4", PAPER_BG, "Benchmark · Table 4 · Live system", "Table 4: reports per pass and severity", 16,
              eyebrow_color=ORANGE_T, notes="~45 s. This is the paper's Table 4, in the same layout: for every pass, how many reports had each severity, ERROR, WARN or INFO. On the left our VM, 13.4 hours of normal use with our own test runs removed; on the right the paper's numbers, 24 hours on a laptop. The pattern is the same. access, the check-then-open pattern, is by far the largest and is always INFO: 109 thousand here, 839 thousand in the paper. fixed_mmap is mostly INFO from the dynamic loader. rwx_mem and snprintf give WARNs. intercept_path gives a couple of thousand WARNs and a few ERRORs. gets and the system passes are rare. Our run is shorter, so our counts are smaller. sprintf is extra: it is in the reference policy but the paper did not list it. The paper's Events column, how often each probe fired, is an internal counter that is not written to the log, so we cannot show it. On the right, the volume numbers from Section 6.4.2: about 200 thousand log entries, 5,612 unique stack offsets in 216 programs, so 36 entries per offset compared with 244 in the paper. If asked: the 24 gets ERRORs are most likely our own setuid test copies that slipped past the filter.")
HD = {"fill": "E6EAF0", "b": True, "align": PP_ALIGN.RIGHT}
HL = {"fill": "E6EAF0", "b": True}
OURS_H = {"fill": "DCE7FA", "b": True, "align": PP_ALIGN.CENTER}
PAP_H = {"fill": "ECEAE3", "b": True, "align": PP_ALIGN.CENTER}
r_ = lambda t, b=False: (t, {"align": PP_ALIGN.RIGHT, "b": b})  # noqa: E731
rows = [("access", "0", "0", "109k", "0", "0", "839k"),
        ("fixed_mmap", "0", "524", "13.4k", "0", "0", "707k"),
        ("rwx_mem", "0", "317", "0", "0", "62.9k", "0"),
        ("filep_unlocked", "0", "14", "0", "0", "0", "0"),
        ("gets", "24", "0", "0", "0", "0", "0"),
        ("snprintf", "0", "2.2k", "0", "0", "11.3k", "0"),
        ("printf_mut", "0", "17", "0", "0", "0", "0"),
        ("system_mut", "0", "1", "0", "0", "0", "0"),
        ("system_abs", "0", "10", "0", "0", "0", "0"),
        ("sec_file_open", "1", "0", "0", "0", "1", "345"),
        ("intercept_path", "8", "2.0k", "0", "1", "275", "1.5k"),
        ("sprintf *", "0", "72.5k", "0", "–", "–", "–")]
data = [[("", HL), ("Our VM", OURS_H), ("", OURS_H), ("", OURS_H), ("Paper (Table 4)", PAP_H), ("", PAP_H), ("", PAP_H)],
        [("Pass", HL), ("ERROR", HD), ("WARN", HD), ("INFO", HD), ("ERROR", HD), ("WARN", HD), ("INFO", HD)]]
for name, *vals in rows:
    data.append([(name, {"font": MONO, "size": 13})] + [r_(v) for v in vals])
data.append([("Total", {"b": True}), r_("33", True), r_("77.6k", True), r_("122k", True), r_("1", True), r_("74.5k", True),
             r_("1.55M", True)])
tshape = table(s, 128, 240, 1150, [0.25, 0.125, 0.125, 0.125, 0.125, 0.125, 0.125], data, size=14, row_h=40)
tt = tshape.table
tt.cell(0, 1).merge(tt.cell(0, 3))
tt.cell(0, 4).merge(tt.cell(0, 6))
tb(s, 128, 940, 1150, 120, [
    ["* sprintf was switched on in our run, but the paper’s Table 4 does not list it."],
    ["ERROR = runs a file others can change · WARN = reads/writes it · INFO = risky pattern only."],
    ["Paper: Table 4 counts come from a 24-hour run; the volume numbers (right) from 5 days. Its “Events” column is not saved in the log, so it is left out."],
], size=11, color=MUTED, after=2)
tb(s, 1320, 240, 472, 36, ["Report volume (paper §6.4.2, 5 days)"], size=14, bold=True, color=MUTED)
table(s, 1320, 282, 472, [0.42, 0.30, 0.28], [
    ["Metric", r_("Ours", True), r_("Paper", True)],
    ["Time", r_("13.4 h"), r_("5 days")],
    ["Log entries", r_("199,642"), r_("~679K")],
    ["Stack offsets", r_("5,612"), r_("2,784")],
    ["Binaries", r_("216"), r_("127")],
    ["Per offset", r_("36", True), r_("244")],
], size=14, row_h=46)
tb(s, 1320, 640, 472, 200, [["Same shape: ", B("access"), " dominates (always INFO); gets and system passes are rare."]],
   size=15, color=INK)

# ============================================================== 17 live VM: ranking result
s = new_slide("livevm", PAPER_BG, "Our work · Result on the live system", "From 207,854 reports to 99 to review first", 17,
              eyebrow_color=ORANGE_T, notes='~40 s. This slide puts clustering and scoring together on the live VM, 13.4 hours including our own test runs. The table is a funnel: 207,854 raw reports become 1,910 clusters; 322 clusters score at least 0.5, and 99 score at least 0.8. So instead of reading 200 thousand log lines, a person starts with the 99 highest-risk clusters, each with a written reason. Nothing is deleted; low scores are just placed lower in the list. The histogram shows how the scores are spread: most clusters sit around 0.3 to 0.4; the orange bars are the flagged ones. These numbers already include two rules we added after inspecting the top of the list. First, many root programs reading the DNS settings under /run/systemd/resolve scored 1.0 because that folder belongs to the systemd-resolve account; system service accounts such as systemd-resolve, nginx, postgres or smmsp are part of the operating system, so they are now trusted like root. Second, sendmail, which is not root, scored 0.8 while writing its own mail queue; a process that is not root can no longer be flagged. With these rules the top list shrank from 128 to 99 clusters, and the score-1.0 clusters from normal use went from 19 to 2. Of the 61 clusters still at 1.0, 59 are our own deliberately exploitable test cases; the remaining 2 are one program reading the system CA certificate bundle, which needs a closer look.')
hl = {"fill": "FCEFE6", "b": True}
table(s, 128, 300, 660, [0.70, 0.30], [
    ["Step", rt("Count", True)],
    ["Raw reports", rt("207,854")],
    ["After clustering", rt("1,910")],
    ["Score ≥ 0.5", rt("322")],
    [("Score ≥ 0.8 (review first)", hl), ("99", {**hl, "align": R})],
], size=18, row_h=80)
img(s, os.path.join(FIG, "fig_score_histogram.png"), 840, 260, 952, 520)
tb(s, 128, 810, 1664, 120, [
    ["Highest-risk clusters come first, each with a reason; nothing is deleted"],
    ["New rules (trust system accounts, cap non-root): top list 128 → 99; score-1.0 clusters from normal use 19 → 2"],
], size=17, bullet=True, after=8)

# ============================================================== 18 conclusion
s = new_slide("close", DARK_BG, "Conclusion", "Context turns warnings into ranked findings", 18, eyebrow_color=PEACH,
              dark=True, notes='~30 s, then Q&A. The paper shows that eBPF can find latent, context-dependent bugs across a whole system with low overhead; the authors found more than 40 real issues. Its open problems were the flood of duplicate reports and the missing context for judging them. We added that context to every report, grouped 207,854 reports into 1,910 clusters, and scored them with simple, explainable rules, so a person starts with 99 high-scoring clusters instead of 200 thousand log lines. The kernel-side passes cost at most about 2 percent on real programs. Thank you; we are happy to take questions.')
tb(s, 128, 280, 1664, 50, ["Results"], size=19, bold=True, color=SKY)
tb(s, 128, 345, 1664, 400, [
    ["Paper: 40+ real bugs found with eBPF"],
    ["Clustering: ", B("109× fewer"), " items (207,854 → 1,910)"],
    ["Scoring: ", B("99"), " clusters to review first"],
    ["Overhead: ", B("≤ 2%"), " for kernel passes on real programs"],
], size=22, color=LIGHT_T, bullet=True, after=16)
tb(s, 128, 790, 1664, 120, ["Questions?"], size=40, bold=True, color=LIGHT_T, anchor=MSO_ANCHOR.MIDDLE)

# story-style speaker notes for slides 9-18 (override)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from story_notes import STORY  # noqa: E402
ORDER = ["cover", "problem", "motivating", "interceptpath", "a896d9e1", "report", "passes", "testbed", "gap",
         "implemented", "clustering", "scoring", "benchmarks", "microbench", "performance", "table4", "livevm", "close"]
for _sid, _slide in zip(ORDER, prs.slides):
    if _sid in STORY:
        _slide.notes_slide.notes_text_frame.text = STORY[_sid]

prs.core_properties.title = "OS-Sanitizer: Paper & Our Extension"
prs.core_properties.author = "Pradeep Kumar Mahato, Vivek Kumar"
prs.save(OUT)
print("wrote", OUT, len(prs.slides), "slides")
