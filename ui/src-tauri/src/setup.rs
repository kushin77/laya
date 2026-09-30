// Copyright 2026 Aayush Chawla
// SPDX-License-Identifier: Apache-2.0

//! First-run environment setup orchestration.
//!
//! Extracted from lib.rs (issue #30): the setup-wizard flow's business logic
//! (preflight checks, venv creation, dependency install, n8n + engine startup)
//! is independent of tray/menu wiring and command registration, so it lives
//! here instead of interleaved with them.

use crate::{runtime, sidecar, n8n};
use crate::{EngineProcess, APP_EXITING};
use std::sync::atomic::Ordering;

/// Event payload emitted during setup for frontend progress display.
#[derive(serde::Serialize, Clone)]
pub(crate) struct SetupEvent {
    pub step: &'static str,   // "python", "venv", "deps", "engine"
    pub status: &'static str, // "running", "done", "error"
    pub message: String,
}

/// Run full environment setup with fail-fast preflight checks.
///
/// Steps:
/// 1. Preflight — verify Python 3.10+ and Node.js 18+ are installed
/// 2. Environment — create Python venv
/// 3. Dependencies — pip install requirements
/// 4. Automation — install n8n via npm + start it
/// 5. Engine — start the Laya engine
///
/// Emits `setup-progress` events throughout.
#[tauri::command]
pub(crate) fn setup_environment(app: tauri::AppHandle) {
    use tauri::Emitter;

    std::thread::spawn(move || {
        let emit = |step: &'static str, status: &'static str, msg: &str| {
            let _ = app.emit("setup-progress", SetupEvent {
                step,
                status,
                message: msg.to_string(),
            });
        };

        // ── Step 1: Ensure runtimes (auto-download if missing) ─────
        // Detect system Python/Node first.  If either is missing, download
        // a managed copy into ~/.laya/{python,node}/ so the user doesn't
        // have to install runtimes by hand.  See runtime.rs for details.
        emit("preflight", "running", "Checking runtimes...");

        let app_for_progress = app.clone();
        let ensure_result = runtime::ensure_runtimes(|p| {
            let msg = match p {
                runtime::RuntimeProgress::Phase(s) => s,
                runtime::RuntimeProgress::Bytes { downloaded, total } => match total {
                    Some(t) if t > 0 => format!(
                        "Downloaded {} MB / {} MB",
                        downloaded / 1_048_576,
                        t / 1_048_576
                    ),
                    _ => format!("Downloaded {} MB", downloaded / 1_048_576),
                },
                runtime::RuntimeProgress::Done(s) => s,
            };
            let _ = app_for_progress.emit("setup-progress", SetupEvent {
                step: "preflight",
                status: "running",
                message: msg,
            });
        });

        if let Err(e) = ensure_result {
            emit("preflight", "error", &format!("Runtime provisioning failed: {e}"));
            return;
        }

        // Re-check after the (potentially long) download so we don't keep
        // working through a shutdown.
        if APP_EXITING.load(Ordering::Relaxed) {
            log::info!("App is exiting, aborting setup");
            return;
        }

        // Now resolve the actual interpreter paths — these will pick up the
        // managed install we may have just provisioned.
        let python_path = match sidecar::find_python() {
            Ok((path, ver)) => {
                emit("preflight", "running", &format!("Python {} found. Checking for Node.js...", ver));
                path
            }
            Err(e) => {
                emit("preflight", "error", &e);
                return;
            }
        };

        match n8n::find_node() {
            Ok((_, ver)) => {
                emit("preflight", "done", &format!("Python and Node.js {} ready", ver));
            }
            Err(e) => {
                emit("preflight", "error", &format!("Node.js 22+ is required. {}", e));
                return;
            }
        };

        // ── Step 2: Set up environment ──────────────────────────────
        if !sidecar::check_environment().venv_ready {
            // A venv that exists but isn't ready is broken or was built on an
            // interpreter we no longer accept (e.g. ARM64 / too-new Python,
            // issue #14); create_venv wipes and rebuilds it. Say so, since
            // the rebuild also re-downloads every package.
            let msg = if sidecar::venv_exists() {
                "Rebuilding Python environment (the existing one is incompatible or incomplete)..."
            } else {
                "Creating Python environment..."
            };
            emit("environment", "running", msg);
            match sidecar::create_venv(&python_path) {
                Ok(()) => emit("environment", "done", "Python environment created"),
                Err(e) => {
                    emit("environment", "error", &e);
                    return;
                }
            }
        } else {
            emit("environment", "done", "Python environment ready");
        }

        // ── Step 3: Install Python dependencies ─────────────────────
        // Deliberately runs to completion BEFORE the n8n install (step 4),
        // not in parallel.  n8n's npm install drives node-gyp with the venv
        // Python (npm_config_python) because node-gyp needs setuptools for
        // its distutils shim on Python 3.12+ (see n8n.rs).  That setuptools
        // lives in the venv and is mutated by pip during this step (torch in
        // requirements-ml.txt depends on it, so resolution can uninstall→
        // reinstall it).  Overlapping the two would race node-gyp's read
        // against pip's write of setuptools, so we keep them ordered.
        let env = sidecar::check_environment();
        if !env.deps_installed {
            emit("deps", "running", "Installing Python packages (usually 2-5 minutes)...");
            let app_deps = app.clone();
            match sidecar::install_requirements(|line| {
                let _ = app_deps.emit("setup-progress", SetupEvent {
                    step: "deps",
                    status: "running",
                    message: line.to_string(),
                });
            }) {
                Ok(()) => emit("deps", "done", "All packages installed"),
                Err(e) => { emit("deps", "error", &e); return; }
            }
        } else {
            emit("deps", "done", "Packages up to date");
        }

        // ── Step 4: Install n8n ─────────────────────────────────────
        if !n8n::is_n8n_installed() {
            emit("automation", "running", "Installing n8n (this may take several minutes)...");
            let app_n8n = app.clone();
            match n8n::install_n8n(|line| {
                let _ = app_n8n.emit("setup-progress", SetupEvent {
                    step: "automation",
                    status: "running",
                    message: line.to_string(),
                });
            }) {
                Ok(()) => {}
                Err(e) => { emit("automation", "error", &e); return; }
            }
        }

        if APP_EXITING.load(Ordering::Relaxed) {
            log::info!("App is exiting, aborting setup");
            return;
        }

        // Start n8n
        emit("automation", "running", "Starting n8n...");
        match n8n::startup_n8n() {
            n8n::N8nStartResult::Started | n8n::N8nStartResult::AlreadyRunning => {
                emit("automation", "running", "Waiting for n8n API...");
                if n8n::wait_for_n8n_api(std::time::Duration::from_secs(60)) {
                    emit("automation", "done", "n8n running");
                } else {
                    log::warn!("n8n REST API did not become ready in time — engine will retry");
                    emit("automation", "done", "n8n started (API still loading)");
                }
            }
            other => {
                log::warn!("n8n startup: {:?}", other);
                emit("automation", "error", &format!("Failed to start n8n: {:?}", other));
                return;
            }
        }

        // ── Step 5: Start engine ────────────────────────────────────
        if APP_EXITING.load(Ordering::Relaxed) {
            log::info!("App is exiting, skipping engine spawn");
            return;
        }
        emit("engine", "running", "Starting Laya engine...");
        let engine_state = app.try_state::<EngineProcess>();

        // An engine may already be running from the launch-time spawn: dev
        // mode always spawns at launch, and a Retry re-enters this step while
        // the previous child may still be booting. A second engine would race
        // the first for port 8420 and one of them dies, so reuse a live child
        // and only spawn when there is none (or the stored one has exited).
        let already_running = engine_state
            .as_ref()
            .map(|s| sidecar::child_is_running(&s.0))
            .unwrap_or(false);
        let spawned = if already_running {
            log::info!("Engine already running; waiting for it instead of spawning another");
            Ok(())
        } else {
            sidecar::spawn_engine().map(|child| {
                if let Some(state) = engine_state.as_ref() {
                    if let Ok(mut guard) = state.0.lock() {
                        *guard = Some(child);
                    }
                }
            })
        };

        match spawned {
            Ok(()) => {
                // Watch the child handle while polling so a crash at import
                // (a dependency resolved to an incompatible version, a syntax
                // error in the engine source, ...) reports its exit status and
                // last traceback line instead of a timeout after 60 s.
                let outcome = sidecar::wait_for_engine(
                    std::time::Duration::from_secs(60),
                    engine_state.as_ref().map(|s| &s.0),
                );
                let status = if matches!(outcome, sidecar::EngineWait::Ready) { "done" } else { "error" };
                emit("engine", status, &outcome.describe());
            }
            Err(e) => {
                emit("engine", "error", &e);
            }
        }
    });
}
