// Copyright (c) OS-Sanitizer developers, 2024, licensed under the EUPL-1.2-or-later.
//
// See LICENSE at the root of this repository (or a legal translation in LICENSE-translations).

#![feature(core_intrinsics)]
#![no_std]
#![no_main]

use aya_ebpf::EbpfContext;
use aya_ebpf::bindings::{BPF_F_REUSE_STACKID, BPF_F_USER_STACK};
use aya_ebpf::cty::{c_void, size_t, uintptr_t};
use aya_ebpf::helpers::bpf_get_current_pid_tgid;
use aya_ebpf::helpers::generated::{bpf_get_current_comm, bpf_probe_read_user_str};
use aya_ebpf::macros::map;
use aya_ebpf::macros::uprobe;
use aya_ebpf::maps::{HashMap, LruHashMap, PerCpuArray, PerfEventArray, StackTrace};
use aya_ebpf::programs::ProbeContext;
use aya_log_ebpf::{debug, error, info, warn};
use core::ffi::c_ulong;
use core::hint::unreachable_unchecked;

use os_sanitizer_common::CopyViolation::Strlen;
use os_sanitizer_common::OsSanitizerError::*;
use os_sanitizer_common::ProgId;
use os_sanitizer_common::{
    CTX_OFFSET, CopyViolation, EXECUTABLE_LEN, MaybeOwnedArray, ObjInfo, OsSanitizerError,
    OsSanitizerReport, ReportCtx, SERIALIZED_SIZE, ToctouVariant, USERSTR_LEN,
};

use crate::binding::vm_area_struct;
use crate::binding::{cred, dentry, file, inode, mm_struct, super_block, task_struct};
use crate::statistics::update_tracking;
use crate::strlen::STRLEN_MAP;

pub(crate) type Hasher = rustc_hash::FxHasher;

#[unsafe(link_section = "license")]
pub static LICENSE: [u8; 4] = *b"GPL\0";

#[allow(
    improper_ctypes_definitions,
    nonstandard_style,
    unnecessary_transmutes,
    unused,
    clippy::all
)]
mod binding;
mod do_faccessat;
mod do_statx;
mod filep_unlocked;
mod fixed_mmap;
mod leaky_vessel;
mod memcpy;
mod open_permissions;
mod printf_mutability;
mod rwx_mem;
mod security_file_open;
mod snprintf;
mod sprintf;
pub(crate) mod statistics;
mod strcpy;
mod strlen;
mod strncpy;
mod sys_openat2;
mod system_absolute;
mod system_mutability;
mod toctou_2005;
mod vfs_fstatat;

#[map(name = "IGNORED_PIDS")]
pub static IGNORED_PIDS: HashMap<u32, u8> = HashMap::with_max_entries(1 << 12, 0);

#[map]
pub static FLAGGED_FILE_OPEN_PIDS: LruHashMap<u64, (ToctouVariant, u64)> =
    LruHashMap::with_max_entries(1 << 12, 0);

#[map(name = "FUNCTION_REPORT_QUEUE")]
pub static FUNCTION_REPORT_QUEUE: PerfEventArray<[u8; SERIALIZED_SIZE]> = PerfEventArray::new(0);

#[map(name = "STATS_QUEUE")]
pub static STATS_QUEUE: PerfEventArray<[u8; SERIALIZED_SIZE]> = PerfEventArray::new(0);

#[map(name = "STACKTRACES")]
pub static STACK_MAP: StackTrace = StackTrace::with_max_entries(1 << 20, 0);

#[inline(always)]
fn emit_error<C: EbpfContext>(probe: &C, e: OsSanitizerError, name: &str) -> u32 {
    match e {
        MissingArg(op, idx) => {
            error!(probe, "{}: Missing arg {} while handling {}", op, idx, name);
        }
        CouldntReadKernel(op, ptr, num_bytes) => {
            error!(
                probe,
                "{}: Couldn't read kernel address 0x{:x} ({} bytes) while handling {}",
                op,
                ptr,
                num_bytes,
                name
            );
        }
        CouldntReadUser(op, ptr, num_bytes, e) => {
            debug!(
                probe,
                "{}: Couldn't read user address 0x{:x} ({} bytes) while handling {} ({})",
                op,
                ptr,
                num_bytes,
                name,
                e
            );
        }
        CouldntRecoverStack(op, errno) => {
            info!(probe, "{}: Couldn't recover stacktrace: {}", op, errno);
        }
        CouldntGetPath(op, errno) => {
            info!(probe, "{}: Couldn't recover path: {}", op, errno);
        }
        CouldntGetComm(op, errno) => {
            error!(probe, "{}: Couldn't recover comm: {}", op, errno);
        }
        CouldntAccessBuffer(op) => {
            error!(
                probe,
                "{}: Couldn't access buffer while handling {}", op, name
            );
        }
        InvalidUtf8(op) => {
            warn!(
                probe,
                "{}: Encountered invalid UTF8 while handling {}", op, name
            );
        }
        OutOfSpace(op) => {
            error!(probe, "{}: Ran out of space while handling {}", op, name);
        }
        RacefulAccess(op) => {
            error!(
                probe,
                "{}: Performed a raceful operation while handling {}", op, name
            );
        }
        ImpossibleFile => {
            error!(
                probe,
                "Encountered an impossible file while handling {}", name
            );
        }
        Unreachable(condition) => {
            error!(
                probe,
                "Encountered an unreachable code block while handling {}: {}", name, condition
            );
        }
        CouldntFindVma(op, errno, pid, tgid) => {
            // this is noisy
            info!(
                probe,
                "Failed to find VMA for an address in pid {} (tgid: {}) while handling {}: {} ({})",
                pid,
                tgid,
                name,
                op,
                errno
            );
        }
        UnexpectedNull(op) => {
            error!(
                probe,
                "Unexpected null pointer while handling {}: {}", name, op, errno
            );
        }
        SerialisationError(op) => {
            error!(probe, "Couldn't serialise {}: {}", name, op);
        }
    }
    e.into()
}

#[map]
static ACCESS_MAP: LruHashMap<(u64, u64, u64), (ToctouVariant, u64)> =
    LruHashMap::with_max_entries(1 << 16, 0);

#[inline(always)]
unsafe fn try_check_bad_copy(
    _probe: &ProbeContext,
    pid_tgid: u64,
    srcptr: uintptr_t,
    src_len: size_t,
) -> Result<Option<(CopyViolation, u64, u64)>, OsSanitizerError> {
    let mut report = None;

    if src_len != 0 && Some(&src_len) == STRLEN_MAP.get(&(pid_tgid, srcptr)) {
        report = Some((Strlen, src_len as u64, 0));
    }

    Ok(report)
}

#[map]
pub static REPORT_SCRATCH: PerCpuArray<[u8; SERIALIZED_SIZE]> = PerCpuArray::with_max_entries(1, 0);
#[map]
pub static STRING_SCRATCH: PerCpuArray<[u8; USERSTR_LEN]> = PerCpuArray::with_max_entries(2, 0);

#[inline(always)]
pub(crate) unsafe fn report_stack_id<C: EbpfContext>(
    ctx: &C,
    op: &'static str,
) -> Result<u64, OsSanitizerError> {
    STACK_MAP
        .get_stackid::<C>(ctx, (BPF_F_USER_STACK | BPF_F_REUSE_STACKID) as u64)
        .map_err(|e| CouldntRecoverStack(op, e))
        .map(|i| i as u64)
}

#[inline(always)]
pub(crate) unsafe fn read_str(
    usermode_ptr: uintptr_t,
    op: &'static str,
) -> Result<MaybeOwnedArray<u8, USERSTR_LEN>, OsSanitizerError> {
    let ptr = STRING_SCRATCH
        .get_ptr_mut(0)
        .ok_or(CouldntAccessBuffer("emit-report"))?;
    let buf = &mut *ptr;
    buf.fill(0);
    let mut res = -1;
    for _ in 0..32 {
        res = bpf_probe_read_user_str(
            buf.as_mut_ptr() as *mut c_void,
            buf.len() as u32,
            usermode_ptr as *const c_void,
        );
        if res >= 0 {
            break;
        }
    }

    if res < 0 {
        Err(CouldntReadUser(op, usermode_ptr as u64, 0, res))
    } else {
        Ok(buf)
    }
}

#[inline(always)]
pub(crate) unsafe fn emit_report<C: EbpfContext>(
    ctx: &C,
    report: &OsSanitizerReport,
) -> Result<(), OsSanitizerError> {
    emit_report_obj(ctx, report, core::ptr::null())
}

/// tgid -> 1 once the process, while privileged, opened a file another user controls.
#[map]
pub static UNTRUSTED_OPEN: LruHashMap<u32, u8> = LruHashMap::with_max_entries(1 << 14, 0);

/// Observe-only LSM hook (always allows): marks privileged processes that open a regular
/// file owned by a non-root user, or writable by everyone. Pseudo filesystems are skipped.
#[aya_ebpf::macros::lsm(hook = "file_open")]
fn lsm_untrusted_open(ctx: aya_ebpf::programs::LsmContext) -> i32 {
    unsafe { mark_untrusted_open(&ctx) };
    0
}

#[inline(always)]
unsafe fn mark_untrusted_open(ctx: &aya_ebpf::programs::LsmContext) {
    use core::ptr::addr_of;
    const PROC_SUPER_MAGIC: u64 = 0x9fa0;
    const SYSFS_MAGIC: u64 = 0x6265_6572;
    let fsuid = {
        let task = aya_ebpf::helpers::generated::bpf_get_current_task() as *const task_struct;
        if task.is_null() {
            return;
        }
        let cred = rk_ptr(addr_of!((*task).cred));
        if cred.is_null() {
            return;
        }
        rk(addr_of!((*cred).fsuid.val))
    };
    if fsuid != 0 {
        return;
    }
    let f: *const file = ctx.arg(0);
    if f.is_null() {
        return;
    }
    let ino = rk_ptr(addr_of!((*f).f_inode) as *const *const inode);
    if ino.is_null() {
        return;
    }
    let mode: u16 = rk(addr_of!((*ino).i_mode));
    if mode & 0xF000 != 0x8000 {
        return; // regular files only
    }
    let sb = rk_ptr(addr_of!((*ino).i_sb) as *const *const super_block);
    if !sb.is_null() {
        let magic = rk(addr_of!((*sb).s_magic)) as u64;
        if magic == PROC_SUPER_MAGIC || magic == SYSFS_MAGIC {
            return;
        }
    }
    let owner: u32 = rk(addr_of!((*ino).i_uid.val));
    if owner != 0 || mode & 0o002 != 0 {
        let tgid = (bpf_get_current_pid_tgid() >> 32) as u32;
        let _ = UNTRUSTED_OPEN.insert(&tgid, &1u8, 0);
    }
}

/// Per-CPU scratch for the context trailer; built here rather than on the 512-byte eBPF
/// stack, which some passes (intercept_path) nearly exhaust already.
#[map]
pub static CTX_SCRATCH: PerCpuArray<ReportCtx> = PerCpuArray::with_max_entries(1, 0);

/// Like [`emit_report`], additionally recording owner/mode of `f` (and its parent
/// directory) when `f` is non-null.
#[inline(always)]
pub(crate) unsafe fn emit_report_obj<C: EbpfContext>(
    ctx: &C,
    report: &OsSanitizerReport,
    f: *const file,
) -> Result<(), OsSanitizerError> {
    let ptr = REPORT_SCRATCH
        .get_ptr_mut(0)
        .ok_or(CouldntAccessBuffer("emit-report"))?;
    let buf = &mut *ptr;
    report
        .serialise_into(&mut buf[..CTX_OFFSET])
        .map_err(|_| SerialisationError("emit-report"))?;
    let c = &mut *CTX_SCRATCH
        .get_ptr_mut(0)
        .ok_or(CouldntAccessBuffer("emit-report ctx"))?;
    fill_ctx(c, f);
    c.serialise_into(&mut buf[CTX_OFFSET..])
        .map_err(|_| SerialisationError("emit-report ctx"))?;
    FUNCTION_REPORT_QUEUE.output(ctx, buf, 0);
    Ok(())
}

/// Reads a kernel value, yielding zero on failure; context collection is best-effort and
/// must never prevent a report from being emitted.
#[inline(always)]
unsafe fn rk<T: Default>(src: *const T) -> T {
    aya_ebpf::helpers::bpf_probe_read_kernel(src).unwrap_or_default()
}

#[inline(always)]
unsafe fn rk_ptr<T>(src: *const *const T) -> *const T {
    aya_ebpf::helpers::bpf_probe_read_kernel(src).unwrap_or(core::ptr::null())
}

/// Captures the credentials and executable identity of the current task, plus owner/mode of
/// file `f` and its parent directory if `f` is non-null. Writes in place into `c`.
#[inline(always)]
unsafe fn fill_ctx(c: &mut ReportCtx, f: *const file) {
    use aya_ebpf::helpers::generated::{
        bpf_get_current_cgroup_id, bpf_get_current_task, bpf_ktime_get_boot_ns,
    };
    use core::ptr::addr_of;

    let uid_gid = aya_ebpf::helpers::bpf_get_current_uid_gid();
    c.uid = uid_gid as u32;
    c.gid = (uid_gid >> 32) as u32;
    c.cgroup_id = bpf_get_current_cgroup_id();
    c.ts_boot_ns = bpf_ktime_get_boot_ns();
    c.euid = 0;
    c.egid = 0;
    c.fsuid = 0;
    c.fsgid = 0;
    c.exe_ino = 0;
    c.exe_dev = 0;
    c.exe_uid = 0;
    c.exe_mode = 0;
    c.parent_uid = 0;
    c.obj = None;
    c.untrusted_open = UNTRUSTED_OPEN
        .get(&((bpf_get_current_pid_tgid() >> 32) as u32))
        .copied()
        .unwrap_or(0);

    let task = bpf_get_current_task() as *const task_struct;
    if !task.is_null() {
        let cred = rk_ptr(addr_of!((*task).cred));
        if !cred.is_null() {
            c.euid = rk(addr_of!((*cred).euid.val));
            c.egid = rk(addr_of!((*cred).egid.val));
            c.fsuid = rk(addr_of!((*cred).fsuid.val));
            c.fsgid = rk(addr_of!((*cred).fsgid.val));
        }
        let parent = rk_ptr(addr_of!((*task).real_parent) as *const *const task_struct);
        if !parent.is_null() {
            let pcred = rk_ptr(addr_of!((*parent).cred));
            if !pcred.is_null() {
                c.parent_uid = rk(addr_of!((*pcred).uid.val));
            }
        }
        let mm = rk_ptr(addr_of!((*task).mm) as *const *const mm_struct);
        if !mm.is_null() {
            let exe = rk_ptr(addr_of!((*mm).__bindgen_anon_1.exe_file) as *const *const file);
            if !exe.is_null() {
                let ino = rk_ptr(addr_of!((*exe).f_inode) as *const *const inode);
                if !ino.is_null() {
                    c.exe_ino = rk(addr_of!((*ino).i_ino)) as u64;
                    c.exe_uid = rk(addr_of!((*ino).i_uid.val));
                    c.exe_mode = rk(addr_of!((*ino).i_mode));
                    let sb = rk_ptr(addr_of!((*ino).i_sb) as *const *const super_block);
                    if !sb.is_null() {
                        c.exe_dev = rk(addr_of!((*sb).s_dev));
                    }
                }
            }
        }
    }

    if f.is_null() {
        return;
    }
    let ino = rk_ptr(addr_of!((*f).f_inode) as *const *const inode);
    if ino.is_null() {
        return;
    }
    let mut o = ObjInfo {
        uid: rk(addr_of!((*ino).i_uid.val)),
        gid: rk(addr_of!((*ino).i_gid.val)),
        mode: rk(addr_of!((*ino).i_mode)),
        ..ObjInfo::default()
    };
    let d = rk_ptr(addr_of!((*f).f_path.dentry) as *const *const dentry);
    if !d.is_null() {
        let p = rk_ptr(addr_of!((*d).d_parent) as *const *const dentry);
        if !p.is_null() {
            let pino = rk_ptr(addr_of!((*p).d_inode) as *const *const inode);
            if !pino.is_null() {
                o.parent_uid = rk(addr_of!((*pino).i_uid.val));
                o.parent_gid = rk(addr_of!((*pino).i_gid.val));
                o.parent_mode = rk(addr_of!((*pino).i_mode));
            }
        }
    }
    c.obj = Some(o);
}

macro_rules! always_bad_call {
    ($name: ident, $variant: ident) => {
        ::paste::paste! {
            #[uprobe]
            fn [< uprobe_ $name >](probe: ProbeContext) -> u32 {
                match unsafe { [< try_uprobe_ $name >](&probe) } {
                    Ok(res) => res,
                    Err(e) => emit_error(&probe, e, concat!(concat!("os_sanitizer_", stringify!($name)), "_uprobe")),
                }
            }

            #[inline(always)]
            unsafe fn [< try_uprobe_ $name >](probe: &ProbeContext) -> Result<u32, OsSanitizerError> {
                let pid_tgid = bpf_get_current_pid_tgid();

                if IGNORED_PIDS.get(&((pid_tgid >> 32) as u32)).is_some() {
                    return Ok(0);
                }
                update_tracking(pid_tgid, ProgId::[< uprobe_ $name >]);

                let stack_id = STACK_MAP
                    .get_stackid::<ProbeContext>(probe, (BPF_F_USER_STACK | BPF_F_REUSE_STACKID) as u64)
                    .map_err(|e| CouldntRecoverStack(stringify!($name), e))? as u64;

                let mut executable = [0u8; EXECUTABLE_LEN];

                // we do this manually because the existing implementation is restricted to 16 bytes
                let res = bpf_get_current_comm(
                    executable.as_mut_ptr() as *mut c_void,
                    executable.len() as u32,
                );
                if res < 0 {
                    return Err(CouldntGetComm(concat!(stringify!($name), " comm"), res));
                }

                let report = OsSanitizerReport::$variant {
                    executable,
                    pid_tgid,
                    stack_id,
                };

                $crate::emit_report(probe, &report)?;

                Ok(0)
            }
        }
    };
}

always_bad_call!(access, Access);
always_bad_call!(gets, Gets);

// helpers for different emitted bindgen results
#[cfg(feature = "anon-struct")]
#[inline(always)]
unsafe fn access_vm_flags(vm_area: &vm_area_struct) -> binding::vm_flags_t {
    vm_area.__bindgen_anon_2.vm_flags
}
#[cfg(not(feature = "anon-struct"))]
#[inline(always)]
fn access_vm_flags(vm_area: &vm_area_struct) -> u64 {
    vm_area.vm_flags
}
#[cfg(feature = "anon-struct")]
#[inline(always)]
unsafe fn access_vm_start(vm_area: &vm_area_struct) -> c_ulong {
    vm_area.__bindgen_anon_1.__bindgen_anon_1.vm_start
}
#[cfg(not(feature = "anon-struct"))]
#[inline(always)]
fn access_vm_start(vm_area: &vm_area_struct) -> c_ulong {
    vm_area.vm_start
}
#[cfg(feature = "anon-struct")]
#[inline(always)]
unsafe fn access_vm_end(vm_area: &vm_area_struct) -> c_ulong {
    vm_area.__bindgen_anon_1.__bindgen_anon_1.vm_end
}
#[cfg(not(feature = "anon-struct"))]
#[inline(always)]
fn access_vm_end(vm_area: &vm_area_struct) -> c_ulong {
    vm_area.vm_end
}

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { unreachable_unchecked() }
}
