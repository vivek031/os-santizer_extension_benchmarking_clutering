#!/bin/bash
# Labelled matched-pair scenarios for false-positive calibration.
#
# The same example binary (same code, same stack) is run in a benign and in an exploitable
# context, mirroring Scenarios 1-3 of the OS-Sanitizer paper (Sec. 2). Ground truth comes from
# construction, not from opinion: "tp" = an unprivileged user can replace/redirect what a
# privileged process opens; "fp" = no privilege boundary is crossed.
#
# Usage (as root, with os-sanitizer already running with --json):
#   calibration/scenarios.sh <examples-dir-with-built-binaries> <work-dir> [repeats]
# Writes <work-dir>/ground_truth.tsv  (scenario  label  path_substr  rationale  comm  pass)
#   file passes  : matched by path_substr (+ score.py --comm)
#   other passes : each scenario runs its own copy of the example binary named <scenario>
#                  (<= 15 chars), so it is matched exactly by comm + pass
#
# Non-file passes use the same convention: "tp" = a less-privileged user controls the input,
# argv or environment that reaches the reported defect in a privileged process; "fp" = no
# privilege boundary is crossed (even if the code is wrong); "unsure" = boundary crossed but
# the defect's effect is not attacker-observable here (excluded from precision/recall).
# system_abs labels come from an exploit oracle: a fake `ls` records the uid it really ran as.
set -euo pipefail
EX=$(realpath "$1"); W=$2; N=${3:-3}
U=1001   # unprivileged uid/gid; no account needed (setpriv)
as_user() { setpriv --reuid=$U --regid=$U --clear-groups "$@"; }

rm -rf "$W"; mkdir -p "$W"; chmod 755 "$W"
cp "$EX"/01_access "$EX"/05_security_file_open "$EX"/13_interceptable_path "$W"/
GT="$W/ground_truth.tsv"
printf "scenario\tlabel\tpath_substr\trationale\tcomm\tpass\n" > "$GT"
# setuid-root copies of gets/printf/system demos are a local root hole while they exist:
# their dirs are root:$U 0750 and every set-id bit is stripped on exit, whatever happens
trap 'find "$W" -type f -perm /6000 -exec chmod ug-s {} + 2>/dev/null || true' EXIT

mk() {  # mk <dir> <owner> <mode>
  mkdir -p "$1"; chown "$2:$2" "$1"; chmod "$3" "$1"
}
put() { # put <file> <owner> <mode>
  echo secret > "$1"; chown "$2:$2" "$1"; chmod "$3" "$1"
}
gt() { printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$1" "$2" "$3" "$4" "${5:-}" "${6:-}" >> "$GT"; }
gtc() { # gtc <scenario> <label> <pass> <rationale>   (matched by comm = scenario)
  gt "$1" "$2" "" "$4" "$1" "$3"; }
run() { # run <who> <dir> <binary>
  for _ in $(seq 1 "$N"); do
    if [ "$1" = root ]; then (cd "$2" && "$W/$3" >/dev/null 2>&1 || true)
    else (cd "$2" && as_user "$W/$3" >/dev/null 2>&1 || true); fi
  done
}

# ---- access pass: access()/stat() then open() (TOCTOU pattern) -------------------------
d=$W/A_root_rootdir;  mk $d 0 755;  put $d/sensitive_information.txt 0 644
gt A_root_rootdir fp A_root_rootdir/ "root, root-owned dir and file: nobody else can swap the entry (Scenario 1)"
run root $d 01_access

d=$W/A_root_userdir;  mk $d $U 755; put $d/sensitive_information.txt $U 644
gt A_root_userdir tp A_root_userdir/ "root opens in a dir owned by uid $U, who can swap the file between check and use (Scenario 2)"
run root $d 01_access

d=$W/A_user_userdir;  mk $d $U 755; put $d/sensitive_information.txt $U 644
gt A_user_userdir fp A_user_userdir/ "uid $U in its own dir: no privilege boundary"
run user $d 01_access

d=$W/A_root_sticky_rootfile; mk $d 0 1777; put $d/sensitive_information.txt 0 644
gt A_root_sticky_rootfile fp A_root_sticky_rootfile/ "sticky world-writable dir but root-owned entry: others cannot replace it"
run root $d 01_access

d=$W/A_root_sticky_userfile; mk $d 0 1777; put $d/sensitive_information.txt $U 644
gt A_root_sticky_userfile tp A_root_sticky_userfile/ "sticky dir, entry owned by uid $U: owner can replace it under root"
run root $d 01_access

# ---- intercept_path pass: a path component writable by someone else -------------------
d=$W/I_root_userdir; mk $d 0 755; mk $d/dir1 $U 755; mk $d/dir1/dir2 0 755
put $d/dir1/dir2/sensitive_information.txt 0 644
gt I_root_userdir tp I_root_userdir/ "root traverses dir1 owned by uid $U, who can redirect dir2 (Scenario 3)"
run root $d 13_interceptable_path

d=$W/I_root_worldw; mk $d 0 755; mk $d/dir1 0 777; mk $d/dir1/dir2 0 755
put $d/dir1/dir2/sensitive_information.txt 0 644
gt I_root_worldw tp I_root_worldw/ "root traverses a world-writable non-sticky dir"
run root $d 13_interceptable_path

d=$W/I_user_owntree; mk $d $U 755; mk $d/dir1 $U 755; mk $d/dir1/dir2 $U 755
put $d/dir1/dir2/sensitive_information.txt $U 644
gt I_user_owntree none I_user_owntree/ "uid $U in its own tree: should not be reported at all"
run user $d 13_interceptable_path

# ---- sec_file_open pass: opening a world-writable file --------------------------------
d=$W/S_root_ww; mk $d 0 755; put $d/05_demo_file.txt 0 666
gt S_root_ww tp S_root_ww/ "root reads a file any user can modify"
run root $d 05_security_file_open

d=$W/S_user_ww_own; mk $d $U 755; put $d/05_demo_file.txt $U 666
gt S_user_ww_own unsure S_user_ww_own/ "uid $U reads its own world-writable file: weakness, no privilege gain"
run user $d 05_security_file_open

# ======================================================================================
# Non-file passes. Contexts (the code and stack are identical inside each group):
#   root_trusted : root, root-owned binary/dir/input           -> fp (no boundary)
#   user_own     : uid $U runs it                              -> fp (no privilege to gain)
#   root_uinput  : root, but stdin/data file owned by uid $U   -> attacker controls the data
#   setuid       : root-owned 4755 copy run by uid $U          -> attacker controls argv/env/stdin
# ======================================================================================
SAFE_IN=$W/.in_root; echo hello > "$SAFE_IN"; chmod 644 "$SAFE_IN"

inst() { # inst <name> <example> <dir> <dir-owner:group> <dir-mode> [setuid]
  [ ${#1} -le 15 ] || { echo "name too long for comm: $1"; exit 1; }
  mkdir -p "$3"; chown "$4" "$3"; chmod "$5" "$3"
  cp "$EX/$2" "$3/$1"; chown 0:0 "$3/$1"; chmod "${6:-755}" "$3/$1"
}
go() { # go <who> <dir> <bin> <stdin> [argv0|-] [PATH]
  local who=$1 dir=$2 bin=$3 in=$4 a0=${5:--} path=${6:-}
  local pre=()
  [ "$who" = root ] || pre+=(setpriv --reuid=$U --regid=$U --clear-groups)
  [ -z "$path" ] || pre+=(env "PATH=$path")
  for _ in $(seq 1 "$N"); do
    if [ "$a0" = - ]; then
      (cd "$dir" && "${pre[@]}" timeout 20 "./$bin") < "$in" >/dev/null 2>&1 || true
    else
      (cd "$dir" && "${pre[@]}" timeout 20 bash -c 'exec -a "$0" "$1"' "$a0" "./$bin") < "$in" >/dev/null 2>&1 || true
    fi
  done
}
std() { # std <prefix> <example> <pass>: the root_trusted / user_own fp pair
  inst "$1_root_trusted" "$2" "$W/$1_root_trusted" 0:0 755
  gtc "$1_root_trusted" fp "$3" "root, root-owned binary, dir and input: no boundary"
  go root "$W/$1_root_trusted" "$1_root_trusted" "$SAFE_IN"
  inst "$1_user_own" "$2" "$W/$1_user_own" $U:$U 755
  gtc "$1_user_own" fp "$3" "uid $U runs it: no privilege to gain"
  go user "$W/$1_user_own" "$1_user_own" "$SAFE_IN"
}
suid() { # suid <name> <example>: root-owned setuid copy in a dir only root and $U can enter
  inst "$1" "$2" "$W/$1" 0:$U 750 4755
}

# ---- gets: unbounded read of stdin --------------------------------------------------
std g 02_gets gets
d=$W/g_root_uinput; inst g_root_uinput 02_gets $d 0:0 755
U_IN=$W/g_uinput_src/input; mkdir -p "${U_IN%/*}"; chown $U:$U "${U_IN%/*}"; echo hello > "$U_IN"; chown $U:$U "$U_IN"
gtc g_root_uinput tp gets "root reads stdin from a file uid $U writes: attacker controls gets() input"
go root $d g_root_uinput "$U_IN"
suid g_setuid 02_gets
gtc g_setuid tp gets "setuid root, run by uid $U, who controls stdin"
go user "$W/g_setuid" g_setuid "$SAFE_IN"

# ---- printf_mut: template is argv[0] -------------------------------------------------
std p 08_printf_mutability printf_mut
suid p_setuid_argv0 08_printf_mutability
gtc p_setuid_argv0 tp printf_mut "setuid root, uid $U picks argv[0] = the format string"
# not a pure '%p%p..' payload: os-sanitizer drops templates that start with % and contain only
# specifier characters (main.rs, vsnprintf-chunking filter), so such a payload is never reported
go user "$W/p_setuid_argv0" p_setuid_argv0 "$SAFE_IN" 'id=%p%p%p%p%p%p%p%p'

# ---- system_abs: system("ls") -> PATH lookup; label from oracle ---------------------
std x 10_system_abs system_abs
fake_ls() { # fake_ls <dir>: uid-$U-owned ls that records the effective uid it ran as
  mkdir -p "$1"; printf '#!/bin/sh\nid -u >> "%s/oracle"\n' "$1" > "$1/ls"
  chmod 755 "$1/ls"; chown -R $U:$U "$1"; rm -f "$1/oracle"
}
oracle_label() { # tp if the attacker's ls ever ran as root, fp if only as the user, else unsure
  if grep -qx 0 "$1/oracle" 2>/dev/null; then echo tp
  elif [ -s "$1/oracle" ]; then echo fp; else echo unsure; fi
}
UBIN=$W/x_ubin_root; fake_ls "$UBIN"
d=$W/x_root_upath; inst x_root_upath 10_system_abs $d 0:0 755
go root $d x_root_upath "$SAFE_IN" - "$UBIN:/usr/bin:/bin"
gtc x_root_upath "$(oracle_label "$UBIN")" system_abs \
  "root's PATH starts with a dir uid $U owns (oracle: $(sort -u "$UBIN/oracle" 2>/dev/null | tr '\n' ' '))"
UBIN=$W/x_ubin_suid; fake_ls "$UBIN"
suid x_setuid_upath 10_system_abs
go user "$W/x_setuid_upath" x_setuid_upath "$SAFE_IN" - "$UBIN:/usr/bin:/bin"
gtc x_setuid_upath "$(oracle_label "$UBIN")" system_abs \
  "setuid root, uid $U sets PATH (oracle: $(sort -u "$UBIN/oracle" 2>/dev/null | tr '\n' ' '))"

# ---- snprintf: definite leak, but always to /dev/null --------------------------------
std n 07_snprintf snprintf
suid n_setuid 07_snprintf
gtc n_setuid unsure snprintf "setuid root leaks stack bytes, but only into /dev/null"
go user "$W/n_setuid" n_setuid "$SAFE_IN"

# ---- sprintf: constant source that fits the buffer -----------------------------------
inst f_root_trusted 06_sprintf $W/f_root_trusted 0:0 755
gtc f_root_trusted fp sprintf "constant 4.4 KB source into a 5 KB stack buffer, root, no boundary"
go root $W/f_root_trusted f_root_trusted "$SAFE_IN"
suid f_setuid 06_sprintf
gtc f_setuid fp sprintf "setuid root, but the formatted data is a constant uid $U cannot change"
go user "$W/f_setuid" f_setuid "$SAFE_IN"

# ---- fixed_mmap: MAP_FIXED over the process's own mapping ----------------------------
inst m_root_trusted 12_fixed_mmap $W/m_root_trusted 0:0 755
gtc m_root_trusted fp fixed_mmap "root, fixed remap of its own private page"
go root $W/m_root_trusted m_root_trusted "$SAFE_IN"
suid m_setuid 12_fixed_mmap
gtc m_setuid fp fixed_mmap "setuid root, but neither address nor contents depend on the user"
go user "$W/m_setuid" m_setuid "$SAFE_IN"

# ---- filep_unlocked: 4 threads, fputc_unlocked on one FILE* ---------------------------
inst u_root_trusted 11_filep_unlocked $W/u_root_trusted 0:0 755
gtc u_root_trusted fp filep_unlocked "root, threads race on a root-owned output file"
go root $W/u_root_trusted u_root_trusted "$SAFE_IN"
suid u_setuid 11_filep_unlocked
gtc u_setuid fp filep_unlocked "setuid root, but the raced data is not user-controlled"
go user "$W/u_setuid" u_setuid "$SAFE_IN"

# ---- rwx_mem: mmap a file in cwd, then mprotect W+X ----------------------------------
d=$W/r_root_trusted; inst r_root_trusted 03_rwx_mem $d 0:0 755; put $d/sensitive_information.txt 0 644
gtc r_root_trusted fp rwx_mem "root maps its own root-owned file W+X"
go root $d r_root_trusted "$SAFE_IN"
d=$W/r_user_own; inst r_user_own 03_rwx_mem $d $U:$U 755; put $d/sensitive_information.txt $U 644
gtc r_user_own fp rwx_mem "uid $U maps its own file W+X"
go user $d r_user_own "$SAFE_IN"
d=$W/r_root_ufile; inst r_root_ufile 03_rwx_mem $d 0:0 755; put $d/sensitive_information.txt $U 644
gtc r_root_ufile unsure rwx_mem "root maps a uid-$U file W+X, but never executes it"
go root $d r_root_ufile "$SAFE_IN"

echo "scenarios done: $(($(wc -l < "$GT") - 1)) scenarios x $N runs; ground truth in $GT"
