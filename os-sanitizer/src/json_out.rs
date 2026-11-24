// Copyright (c) OS-Sanitizer developers, 2024, licensed under the EUPL-1.2-or-later.
//
// See LICENSE at the root of this repository (or a legal translation in LICENSE-translations).

//! Structured (JSON-lines) report output, intended for automated post-processing such as
//! deduplication and false-positive calibration. One self-contained JSON object per report.

use std::collections::HashMap;
use std::ffi::CStr;
use std::fs::{File, OpenOptions};
use std::io::{LineWriter, Write};
use std::os::unix::fs::MetadataExt;
use std::path::Path;
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

use once_cell::sync::Lazy;
use serde_json::{Value, json};

use os_sanitizer_common::{
    CopyViolation, ObjInfo, OpenViolation, OsSanitizerReport, ReportCtx, SnprintfViolation,
};

pub struct JsonSink(Mutex<LineWriter<File>>);

impl JsonSink {
    pub fn open(path: &Path) -> std::io::Result<Self> {
        let f = OpenOptions::new().create(true).append(true).open(path)?;
        Ok(Self(Mutex::new(LineWriter::new(f))))
    }

    pub fn write(&self, record: &Value) {
        if let Ok(mut w) = self.0.lock() {
            let _ = serde_json::to_writer(&mut *w, record);
            let _ = w.write_all(b"\n");
        }
    }
}

/// One resolved stack frame: instruction pointer plus (binary, file offset) if resolvable.
pub struct Frame {
    pub ip: u64,
    pub path: Option<String>,
    pub offset: Option<u64>,
}

fn cstr(bytes: &[u8]) -> Option<String> {
    CStr::from_bytes_until_nul(bytes)
        .ok()
        .map(|s| s.to_string_lossy().into_owned())
}

/// Kernel-internal dev_t (MAJOR << 20 | MINOR) to "major:minor".
fn kdev(dev: u32) -> String {
    format!("{}:{}", dev >> 20, dev & 0xfffff)
}

fn obj_json(o: &ObjInfo) -> Value {
    json!({
        "uid": o.uid, "gid": o.gid, "mode": format!("{:o}", o.mode),
        "parent_uid": o.parent_uid, "parent_gid": o.parent_gid,
        "parent_mode": format!("{:o}", o.parent_mode),
    })
}

/// Best-effort executable path. The kernel-captured inode/device is authoritative; the path
/// from /proc is only reported as `verified` if it still refers to that same inode.
/// (pid, exe inode) -> (path, verified). Avoids a readlink+stat per report, which halves
/// throughput on report floods (e.g. --memcpy). Keyed on the inode so an exec in the same
/// pid is never served a stale path.
static EXE_CACHE: Lazy<Mutex<HashMap<(u32, u64), (Option<String>, bool)>>> =
    Lazy::new(|| Mutex::new(HashMap::new()));

fn exe_json(pid: u32, ctx: &ReportCtx) -> Value {
    let key = (pid, ctx.exe_ino);
    let cached = EXE_CACHE.lock().ok().and_then(|c| c.get(&key).cloned());
    let (path, verified) = cached.unwrap_or_else(|| {
        let path = std::fs::read_link(format!("/proc/{pid}/exe")).ok();
        let verified = path
            .as_ref()
            .and_then(|p| {
                let m = std::fs::metadata(p).ok()?;
                let dev = m.dev();
                let (maj, min) = (libc::major(dev) as u32, libc::minor(dev) as u32);
                Some(m.ino() == ctx.exe_ino && maj == ctx.exe_dev >> 20 && min == ctx.exe_dev & 0xfffff)
            })
            .unwrap_or(false);
        let entry = (path.map(|p| p.to_string_lossy().into_owned()), verified);
        if let Ok(mut c) = EXE_CACHE.lock() {
            if c.len() > 4096 {
                c.clear();
            }
            c.insert(key, entry.clone());
        }
        entry
    });
    json!({
        "ino": ctx.exe_ino,
        "dev": kdev(ctx.exe_dev),
        "path": path,
        "path_verified": verified,
        "uid": ctx.exe_uid,
        "mode": format!("{:o}", ctx.exe_mode),
    })
}

/// Pass-specific fields, typed rather than embedded in prose.
fn fields(r: &OsSanitizerReport) -> Value {
    use OsSanitizerReport::*;
    match r {
        RwxVma { start, end, .. } => json!({ "start": start, "end": end }),
        PrintfMutability { template_param, template, .. } => {
            json!({ "template_param": template_param, "template": cstr(template) })
        }
        SystemMutability { command_param, command, .. }
        | SystemAbsolute { command_param, command, .. } => {
            json!({ "command_param": command_param, "command": cstr(command) })
        }
        FilePointerLocking { .. } | Gets { .. } | Access { .. } => json!({}),
        Sprintf { dest, .. } => json!({ "dest": dest }),
        Snprintf { srcptr, size, computed, count, kind, .. } => json!({
            "srcptr": srcptr, "size": size, "computed": computed, "count": count,
            "definite_leak": *kind == SnprintfViolation::DefiniteLeak,
        }),
        Strcpy { dest, src, len_checked, .. } => {
            json!({ "dest": dest, "src": src, "len_checked": len_checked })
        }
        Strncpy { len, allocated, dest, src, variant, .. }
        | Memcpy { len, allocated, dest, src, variant, .. } => json!({
            "len": len, "allocated": allocated, "dest": dest, "src": src,
            "variant": match variant { CopyViolation::Strlen => "strlen", CopyViolation::Malloc => "malloc" },
        }),
        Open { i_mode, filename, variant, .. } => {
            let (kind, via) = match variant {
                OpenViolation::Perms => ("perms", None),
                OpenViolation::Toctou(v, _) => ("toctou", Some(v.to_string())),
            };
            json!({ "filename": cstr(filename), "i_mode": format!("{i_mode:o}"), "violation": kind, "checked_via": via })
        }
        UnsafeOpen { uid, gid, original, filename, uids, gids, mask, everyone, .. } => json!({
            "filename": cstr(filename),
            "original": original.as_ref().and_then(|o| cstr(o)),
            "acting_uid": uid, "acting_gid": gid,
            "writer_uids": uids.iter().copied().take_while(|&u| u != 0).collect::<Vec<_>>(),
            "writer_gids": gids.iter().copied().take_while(|&g| g != 0).collect::<Vec<_>>(),
            "world_writable_component": everyone,
            "mask": mask,
        }),
        FixedMmap { protection, variant, .. } => {
            json!({ "protection": protection, "variant": format!("{variant:?}") })
        }
        LeakyVessel { orig_pid, orig_uid, setuid_stack, .. } => {
            json!({ "orig_pid": orig_pid, "orig_uid": orig_uid, "setuid_seen": *setuid_stack != 0 })
        }
        Toctou2005 { filename, .. } => json!({ "filename": cstr(filename) }),
        Statistics { .. } => json!({}),
    }
}

#[allow(clippy::too_many_arguments)]
pub fn record(
    pass: &str,
    level: log::Level,
    comm: &str,
    pid: u32,
    tid: u32,
    report: &OsSanitizerReport,
    ctx: Option<&ReportCtx>,
    frames: &[Frame],
    message: &str,
    data_region: Option<&str>,
) -> Value {
    let wall = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or_default();
    json!({
        "schema": 1,
        "time": wall,
        "pass": pass,
        "level": level.as_str(),
        "comm": comm,
        "pid": pid,
        "tid": tid,
        "ctx": ctx.map(|c| json!({
            "uid": c.uid, "gid": c.gid, "euid": c.euid, "egid": c.egid,
            "fsuid": c.fsuid, "fsgid": c.fsgid,
            "cgroup_id": c.cgroup_id, "ts_boot_ns": c.ts_boot_ns,
            "parent_uid": c.parent_uid,
            "untrusted_open": c.untrusted_open != 0,
            "exe": exe_json(pid, c),
            "obj": c.obj.as_ref().map(obj_json),
        })),
        "fields": fields(report),
        "data_region": data_region,
        "stack": frames.iter().map(|f| json!({ "ip": f.ip, "path": f.path, "offset": f.offset })).collect::<Vec<_>>(),
        "message": message,
    })
}
