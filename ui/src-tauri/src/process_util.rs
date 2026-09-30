// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0

//! Shared process/path plumbing for the sidecar and n8n runtimes.
//!
//! `home_dir` / `laya_home` were copy-pasted verbatim into sidecar.rs, n8n.rs and
//! runtime.rs, and the AppImage LD_LIBRARY_PATH scrub was duplicated between the
//! node and python spawn sanitizers. Centralized here so they can't drift (review
//! §5.8 — P7-10).

use std::path::PathBuf;
use std::process::Command;

/// On Windows, attach CREATE_NO_WINDOW so spawned child processes do not
/// flash a console window. No-op on other platforms. Was copy-pasted across
/// sidecar.rs, n8n.rs and lib.rs (issue #33); centralized here so the three
/// copies can't drift.
#[cfg(windows)]
pub(crate) fn no_window(cmd: &mut Command) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x08000000;
    cmd.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(not(windows))]
pub(crate) fn no_window(_cmd: &mut Command) {}

/// Return the lowercased command line for a pid (best-effort, empty on failure).
/// Used to confirm a port-holder is actually a Laya process before we kill it.
#[cfg(unix)]
fn process_cmdline(pid: i32) -> String {
    Command::new("ps")
        .args(["-p", &pid.to_string(), "-o", "command="])
        .output()
        .ok()
        .map(|o| String::from_utf8_lossy(&o.stdout).to_lowercase())
        .unwrap_or_default()
}

#[cfg(windows)]
fn process_cmdline(pid: u32) -> String {
    let mut cmd = Command::new("wmic");
    no_window(&mut cmd);
    cmd.args([
        "process",
        "where",
        &format!("ProcessId={}", pid),
        "get",
        "CommandLine",
    ])
    .output()
    .ok()
    .map(|o| String::from_utf8_lossy(&o.stdout).to_lowercase())
    .unwrap_or_default()
}

/// Best-effort kill of a *Laya* process listening on the given TCP port.
/// Used as a safety net during shutdown to catch orphaned engine processes,
/// and by n8n startup to reclaim the port from stale instances (issue #35 —
/// this lived in lib.rs despite being a process-lifecycle utility consumed
/// by n8n startup).
///
/// `identity` must appear (case-insensitively) in the port-holder's command
/// line for it to be killed — otherwise an unrelated user process that happens
/// to listen on the port would be SIGTERM'd (review §6). Both the engine and the
/// Laya-managed n8n run from `~/.laya/...`, so "laya" identifies both. If the
/// command line can't be read the process is left alone (safe default).
#[cfg(unix)]
pub(crate) fn kill_process_on_port(port: u16, identity: &str) {
    if let Ok(output) = Command::new("lsof")
        .args(["-ti", &format!("tcp:{}", port)])
        .output()
    {
        if output.status.success() {
            let pids = String::from_utf8_lossy(&output.stdout);
            for pid_str in pids.split_whitespace() {
                if let Ok(pid) = pid_str.parse::<i32>() {
                    if !process_cmdline(pid).contains(identity) {
                        log::warn!(
                            "Port {} held by foreign process (pid {}); not killing",
                            port,
                            pid
                        );
                        continue;
                    }
                    log::info!("Killing orphaned process on port {} (pid {})", port, pid);
                    unsafe { libc::kill(pid, libc::SIGTERM); }
                }
            }
        }
    }
}

#[cfg(windows)]
pub(crate) fn kill_process_on_port(port: u16, identity: &str) {
    let mut netstat = Command::new("netstat");
    no_window(&mut netstat);
    if let Ok(output) = netstat.args(["-ano", "-p", "tcp"]).output() {
        if !output.status.success() {
            return;
        }
        let stdout = String::from_utf8_lossy(&output.stdout);
        let needle = format!(":{}", port);
        for line in stdout.lines() {
            if line.contains(&needle) && line.contains("LISTENING") {
                if let Some(pid) = line
                    .split_whitespace()
                    .last()
                    .and_then(|s| s.parse::<u32>().ok())
                {
                    if !process_cmdline(pid).contains(identity) {
                        log::warn!(
                            "Port {} held by foreign process (pid {}); not killing",
                            port,
                            pid
                        );
                        continue;
                    }
                    log::info!("Killing orphaned process on port {} (pid {})", port, pid);
                    let mut tk = Command::new("taskkill");
                    no_window(&mut tk);
                    let _ = tk.args(["/F", "/PID", &pid.to_string()]).status();
                }
            }
        }
    }
}

/// The user's home directory (`HOME` on Unix, `USERPROFILE` on Windows).
pub(crate) fn home_dir() -> Option<PathBuf> {
    #[cfg(unix)]
    {
        std::env::var_os("HOME").map(PathBuf::from)
    }
    #[cfg(windows)]
    {
        std::env::var_os("USERPROFILE").map(PathBuf::from)
    }
}

/// `~/.laya` — the Laya data root.
pub(crate) fn laya_home() -> PathBuf {
    home_dir().unwrap_or_default().join(".laya")
}

/// Strip AppImage-injected `LD_LIBRARY_PATH` entries (anything under
/// `/tmp/.mount_*`) from a command about to be spawned, keeping the rest so the
/// child still resolves genuine system libraries. Shared by the node and python
/// spawn sanitizers, which both had this identical block.
pub(crate) fn sanitize_ld_library_path(cmd: &mut Command) {
    if let Ok(ld) = std::env::var("LD_LIBRARY_PATH") {
        let cleaned: Vec<&str> = ld
            .split(':')
            .filter(|p| !p.starts_with("/tmp/.mount_"))
            .collect();
        if cleaned.is_empty() {
            cmd.env_remove("LD_LIBRARY_PATH");
        } else {
            cmd.env("LD_LIBRARY_PATH", cleaned.join(":"));
        }
    }
}
