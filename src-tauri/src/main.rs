// Nous Companion - Tauri Backend
// Minimal entry point - all logic is in the frontend (renderer)

use base64::{engine::general_purpose::STANDARD, Engine as _};
use std::env;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::Path;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::path::BaseDirectory;
use tauri::{Emitter, Manager};

const WINDOW_EDGE_SNAP_DISTANCE: i32 = 10;
const WINDOW_EDGE_RELEASE_DISTANCE: i32 = 4;
const WINDOW_EDGE_REARM_DISTANCE: i32 = 24;
const BACKEND_PORT: u16 = 8765;
const BACKEND_CONNECT_TIMEOUT_MS: u64 = 1000;
const BACKEND_STARTUP_TIMEOUT_SECS: u64 = 12;
const BACKEND_WARMUP_SUCCESS_SECS: u64 = 6;
const WINDOWS_CREATE_NO_WINDOW: u32 = 0x08000000;

#[derive(Debug)]
struct BackendProcess {
    child: Child,
    kind: &'static str,
    state_path: Option<PathBuf>,
}

#[derive(Debug, Default)]
struct BackendSupervisor {
    child: Mutex<Option<BackendProcess>>,
    shutting_down: AtomicBool,
    launching: AtomicBool,
}

#[derive(Clone)]
struct AppState {
    backend_supervisor: Arc<BackendSupervisor>,
    backend_ws_host: Arc<Mutex<String>>,
}

#[derive(Debug, Clone)]
struct BackendLayout {
    root: PathBuf,
    script_path: PathBuf,
    source_label: &'static str,
}

#[derive(Debug, Clone)]
struct PythonLaunchCandidate {
    program: String,
    prefix_args: Vec<String>,
    label: String,
    kind: &'static str,
    state_path: Option<PathBuf>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BackendMode {
    Auto,
    Native,
    Wsl,
}

#[derive(Debug, Clone)]
struct BackendState {
    owner_pid: u32,
    kind: String,
    pid: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BackendReadyState {
    Ready,
    Warming,
    Failed,
}

#[derive(Clone, serde::Serialize)]
struct BackendWsConfig {
    ws_host: String,
    ws_port: u16,
}

fn diag_passive_settings() -> bool {
    std::env::var("CODEC_DIAG_PASSIVE_SETTINGS")
        .map(|v| {
            let normalized = v.trim().to_ascii_lowercase();
            matches!(normalized.as_str(), "1" | "true" | "yes" | "on")
        })
        .unwrap_or(false)
}

fn backend_autostart_enabled() -> bool {
    env::var("NOUS_COMPANION_DISABLE_BACKEND_AUTOSTART")
        .map(|value| {
            let normalized = value.trim().to_ascii_lowercase();
            !matches!(normalized.as_str(), "1" | "true" | "yes" | "on")
        })
        .unwrap_or(true)
}

fn default_backend_ws_host() -> String {
    "127.0.0.1".to_string()
}

fn websocket_endpoint_is_reachable(host: &str, port: u16) -> bool {
    let address = format!("{host}:{port}");
    let addrs = match address.to_socket_addrs() {
        Ok(addrs) => addrs.collect::<Vec<_>>(),
        Err(_) => return false,
    };

    for addr in addrs {
        let mut stream = match TcpStream::connect_timeout(
            &addr,
            Duration::from_millis(BACKEND_CONNECT_TIMEOUT_MS),
        ) {
            Ok(stream) => stream,
            Err(_) => continue,
        };

        let timeout = Some(Duration::from_millis(BACKEND_CONNECT_TIMEOUT_MS));
        let _ = stream.set_read_timeout(timeout);
        let _ = stream.set_write_timeout(timeout);

        let request = format!(
            concat!(
                "GET / HTTP/1.1\r\n",
                "Host: {host}:{port}\r\n",
                "Upgrade: websocket\r\n",
                "Connection: Upgrade\r\n",
                "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n",
                "Sec-WebSocket-Version: 13\r\n",
                "\r\n"
            ),
            host = host,
            port = port
        );

        if stream.write_all(request.as_bytes()).is_err() {
            continue;
        }

        let mut response = [0_u8; 256];
        let count = match stream.read(&mut response) {
            Ok(count) if count > 0 => count,
            _ => continue,
        };

        let response = String::from_utf8_lossy(&response[..count]);
        let is_ready =
            response.starts_with("HTTP/1.1 101") || response.starts_with("HTTP/1.0 101");

        if is_ready {
            let _ = stream.write_all(&[0x88, 0x80, 0x00, 0x00, 0x00, 0x00]);
            let _ = stream.flush();
            return true;
        }
    }

    false
}

fn backend_mode() -> BackendMode {
    match env::var("NOUS_COMPANION_BACKEND_MODE") {
        Ok(value) => match value.trim().to_ascii_lowercase().as_str() {
            "native" | "windows" => BackendMode::Native,
            "wsl" => BackendMode::Wsl,
            _ => BackendMode::Auto,
        },
        Err(_) => BackendMode::Auto,
    }
}

fn backend_stdio_enabled() -> bool {
    env::var("NOUS_COMPANION_BACKEND_STDIO")
        .map(|value| {
            let normalized = value.trim().to_ascii_lowercase();
            matches!(normalized.as_str(), "1" | "true" | "yes" | "on")
        })
        .unwrap_or(false)
}

fn backend_is_running() -> bool {
    websocket_endpoint_is_reachable("127.0.0.1", BACKEND_PORT)
}

fn wait_for_backend_ready(
    deadline: Instant,
    supervisor: &BackendSupervisor,
    child: &mut Child,
    ready_path: Option<&Path>,
) -> BackendReadyState {
    let started_at = Instant::now();

    while Instant::now() < deadline {
        if supervisor.shutting_down.load(Ordering::Relaxed) {
            return BackendReadyState::Failed;
        }

        if ready_path.is_some_and(backend_ready_file_exists) {
            return BackendReadyState::Ready;
        }

        match child.try_wait() {
            Ok(Some(status)) => {
                eprintln!("[nous-companion] backend exited early with status: {status}");
                return BackendReadyState::Failed;
            }
            Ok(None) => {}
            Err(err) => {
                eprintln!("[nous-companion] failed to poll backend process: {err}");
                return BackendReadyState::Failed;
            }
        }

        if started_at.elapsed() >= Duration::from_secs(BACKEND_WARMUP_SUCCESS_SECS) {
            return BackendReadyState::Warming;
        }

        thread::sleep(Duration::from_millis(250));
    }

    BackendReadyState::Failed
}

fn source_repo_root_from_exe() -> Option<PathBuf> {
    let exe_dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
    for ancestor in exe_dir.ancestors() {
        let script = ancestor.join("scripts").join("run_nous_companion.py");
        let server = ancestor.join("src").join("server").join("companion_server.py");
        let tauri_manifest = ancestor.join("src-tauri").join("Cargo.toml");
        if script.is_file() && server.is_file() && tauri_manifest.is_file() {
            return Some(ancestor.to_path_buf());
        }
    }
    None
}

fn backend_state_path<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> Option<PathBuf> {
    let dir = app.path().app_data_dir().ok()?;
    fs::create_dir_all(&dir).ok()?;
    Some(dir.join("backend-state.txt"))
}

fn backend_ready_path<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> Option<PathBuf> {
    let dir = app.path().app_data_dir().ok()?;
    fs::create_dir_all(&dir).ok()?;
    Some(dir.join("backend-ready.txt"))
}

fn parse_backend_state(text: &str) -> Option<BackendState> {
    let mut owner_pid = None;
    let mut kind = None;
    let mut pid = None;

    for line in text.lines() {
        let (key, value) = line.split_once('=')?;
        match key.trim() {
            "owner_pid" => owner_pid = value.trim().parse::<u32>().ok(),
            "kind" => kind = Some(value.trim().to_string()),
            "pid" => pid = Some(value.trim().to_string()),
            _ => {}
        }
    }

    Some(BackendState {
        owner_pid: owner_pid?,
        kind: kind?,
        pid: pid?,
    })
}

fn read_backend_state(path: &Path) -> Option<BackendState> {
    let text = fs::read_to_string(path).ok()?;
    parse_backend_state(&text)
}

fn write_backend_state(path: &Path, owner_pid: u32, kind: &str, pid: &str) {
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let data = format!("owner_pid={owner_pid}\nkind={kind}\npid={pid}\n");
    let _ = fs::write(path, data);
}

fn clear_backend_state(path: &Path) {
    let _ = fs::remove_file(path);
}

fn backend_ready_file_exists(path: &Path) -> bool {
    path.is_file()
}

fn clear_backend_ready(path: &Path) {
    let _ = fs::remove_file(path);
}

fn process_exists(pid: u32) -> bool {
    if pid == 0 {
        return false;
    }

    #[cfg(target_os = "windows")]
    {
        let filter = format!("PID eq {pid}");
        let output = Command::new("tasklist")
            .args(["/FI", &filter])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .output();
        if let Ok(output) = output {
            if output.status.success() {
                return String::from_utf8_lossy(&output.stdout)
                    .to_ascii_lowercase()
                    .contains(&pid.to_string());
            }
        }
        false
    }

    #[cfg(not(target_os = "windows"))]
    {
        Command::new("kill")
            .args(["-0", &pid.to_string()])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|status| status.success())
            .unwrap_or(false)
    }
}

fn kill_backend_state(state: &BackendState) {
    match state.kind.as_str() {
        "wsl" if cfg!(target_os = "windows") => {
            let command = format!(
                "kill -TERM {} 2>/dev/null || true; sleep 1; kill -KILL {} 2>/dev/null || true",
                state.pid, state.pid
            );
            let _ = Command::new("wsl.exe")
                .args(["sh", "-lc", &command])
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
        }
        "native" => {
            #[cfg(target_os = "windows")]
            {
                let _ = Command::new("taskkill")
                    .args(["/PID", &state.pid, "/T", "/F"])
                    .stdin(Stdio::null())
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .status();
            }

            #[cfg(not(target_os = "windows"))]
            {
                let _ = Command::new("kill")
                    .args(["-TERM", &state.pid])
                    .stdin(Stdio::null())
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .status();
            }
        }
        _ => {}
    }
}

fn cleanup_stale_backend<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    if let Some(ready_path) = backend_ready_path(app) {
        clear_backend_ready(&ready_path);
    }
    let Some(state_path) = backend_state_path(app) else {
        return;
    };
    let Some(state) = read_backend_state(&state_path) else {
        clear_backend_state(&state_path);
        return;
    };

    if state.owner_pid == std::process::id() || process_exists(state.owner_pid) {
        return;
    }

    eprintln!(
        "[nous-companion] cleaning stale app-managed backend (kind={}, pid={})",
        state.kind, state.pid
    );
    kill_backend_state(&state);
    clear_backend_state(&state_path);
    thread::sleep(Duration::from_millis(750));
}

fn bundled_backend_layout<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> Option<BackendLayout> {
    let script_path = app
        .path()
        .resolve("scripts/run_nous_companion.py", BaseDirectory::Resource)
        .ok()?;
    if !script_path.is_file() {
        return None;
    }
    Some(BackendLayout {
        root: app.path().resource_dir().ok()?,
        script_path,
        source_label: "bundled resources",
    })
}

fn resolve_backend_layout<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> Option<BackendLayout> {
    if cfg!(debug_assertions) {
        if let Some(root) = source_repo_root_from_exe() {
            let script_path = root.join("scripts").join("run_nous_companion.py");
            if script_path.is_file() {
                return Some(BackendLayout {
                    root,
                    script_path,
                    source_label: "source tree",
                });
            }
        }
        return bundled_backend_layout(app);
    }

    bundled_backend_layout(app).or_else(|| {
        source_repo_root_from_exe().and_then(|root| {
            let script_path = root.join("scripts").join("run_nous_companion.py");
            if script_path.is_file() {
                Some(BackendLayout {
                    root,
                    script_path,
                    source_label: "source tree fallback",
                })
            } else {
                None
            }
        })
    })
}

fn maybe_push_python_path(
    candidates: &mut Vec<PythonLaunchCandidate>,
    path: PathBuf,
    label: &str,
    kind: &'static str,
    state_path: Option<PathBuf>,
) {
    if path.is_file() {
        candidates.push(PythonLaunchCandidate {
            program: path.to_string_lossy().into_owned(),
            prefix_args: Vec::new(),
            label: label.to_string(),
            kind,
            state_path,
        });
    }
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

fn normalize_windows_path_for_wsl(path: &Path) -> String {
    let raw = path.to_string_lossy().into_owned();
    if let Some(stripped) = raw.strip_prefix(r"\\?\UNC\") {
        return format!(r"\\{}", stripped);
    }
    if let Some(stripped) = raw.strip_prefix(r"\\?\") {
        return stripped.to_string();
    }
    raw
}

fn manual_windows_path_to_wsl(path: &str) -> Option<String> {
    if let Some(rest) = path.strip_prefix(r"\\wsl.localhost\") {
        let (_, suffix) = rest.split_once('\\')?;
        return Some(format!("/{}", suffix.replace('\\', "/").trim_start_matches('/')));
    }

    if let Some(rest) = path.strip_prefix(r"\\wsl$\") {
        let (_, suffix) = rest.split_once('\\')?;
        return Some(format!("/{}", suffix.replace('\\', "/").trim_start_matches('/')));
    }

    let mut chars = path.chars();
    let drive = chars.next()?;
    if chars.next()? != ':' {
        return None;
    }

    let remainder = &path[2..];
    let remainder = remainder.trim_start_matches(['\\', '/']);
    Some(format!(
        "/mnt/{}/{}",
        drive.to_ascii_lowercase(),
        remainder.replace('\\', "/")
    ))
}

fn configure_probe_command(command: &mut Command) {
    command.stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::null());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(WINDOWS_CREATE_NO_WINDOW);
    }
}

fn wsl_capture(args: &[&str]) -> Option<String> {
    if !cfg!(target_os = "windows") {
        return None;
    }

    let mut command = Command::new("wsl.exe");
    command.args(args);
    configure_probe_command(&mut command);
    let output = command.output().ok()?;
    if !output.status.success() {
        return None;
    }

    let text = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if text.is_empty() {
        None
    } else {
        Some(text)
    }
}

fn wsl_backend_host() -> Option<String> {
    let output = wsl_capture(&["sh", "-lc", "hostname -I | awk '{print $1}'"])?;
    let host = output
        .split_whitespace()
        .next()
        .map(str::trim)
        .filter(|value| !value.is_empty())?;
    Some(host.to_string())
}

fn set_backend_ws_host<R: tauri::Runtime>(app: &tauri::AppHandle<R>, host: &str) {
    let state = app.state::<AppState>();
    let backend_ws_host = Arc::clone(&state.backend_ws_host);
    drop(state);
    let lock_result = backend_ws_host.lock();
    if let Ok(mut slot) = lock_result {
        *slot = host.trim().to_string();
    };
}

fn get_backend_ws_host_from_state(state: &tauri::State<'_, AppState>) -> String {
    state
        .backend_ws_host
        .lock()
        .map(|value| value.clone())
        .unwrap_or_else(|_| default_backend_ws_host())
}

fn resolve_backend_ws_config(state: &tauri::State<'_, AppState>) -> BackendWsConfig {
    BackendWsConfig {
        ws_host: get_backend_ws_host_from_state(state),
        ws_port: BACKEND_PORT,
    }
}

fn windows_path_to_wsl(path: &Path) -> Option<String> {
    let path_text = normalize_windows_path_for_wsl(path);
    if let Some(converted) = manual_windows_path_to_wsl(&path_text) {
        return Some(converted);
    }
    wsl_capture(&["wslpath", "-a", &path_text])
}

fn wsl_launch_candidate<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    layout: &BackendLayout,
) -> Option<PythonLaunchCandidate> {
    if !cfg!(target_os = "windows") {
        return None;
    }

    let root = windows_path_to_wsl(&layout.root)?;
    let state_path = backend_state_path(app)?;
    let state_path_wsl = windows_path_to_wsl(&state_path)?;
    let ready_path = backend_ready_path(app)?;
    let ready_path_wsl = windows_path_to_wsl(&ready_path)?;
    let command = format!(
        "mkdir -p \"$(dirname {state_file})\" \"$(dirname {ready_file})\" && rm -f {ready_file} && cd {root} && export PYTHONUNBUFFERED=1 NOUS_COMPANION_TAURI=1 NOUS_COMPANION_READY_FILE={ready_file} && printf 'owner_pid=%s\\nkind=wsl\\npid=%s\\n' {owner_pid} \"$$\" > {state_file} && if command -v python3 >/dev/null 2>&1; then exec python3 {script}; elif command -v python >/dev/null 2>&1; then exec python {script}; else exit 127; fi",
        state_file = shell_quote(&state_path_wsl),
        ready_file = shell_quote(&ready_path_wsl),
        owner_pid = std::process::id(),
        root = shell_quote(&root),
        script = shell_quote("scripts/run_nous_companion.py"),
    );

    Some(PythonLaunchCandidate {
        program: "wsl.exe".to_string(),
        prefix_args: vec!["sh".to_string(), "-lc".to_string(), command],
        label: "wsl".to_string(),
        kind: "wsl",
        state_path: Some(state_path),
    })
}

fn python_candidates(backend_root: &Path) -> Vec<PythonLaunchCandidate> {
    let mut candidates = Vec::new();

    if let Ok(explicit) = env::var("NOUS_COMPANION_PYTHON") {
        let explicit = explicit.trim();
        if !explicit.is_empty() {
            candidates.push(PythonLaunchCandidate {
                program: explicit.to_string(),
                prefix_args: Vec::new(),
                label: "NOUS_COMPANION_PYTHON".to_string(),
                kind: "native",
                state_path: None,
            });
        }
    }

    if let Ok(virtual_env) = env::var("VIRTUAL_ENV") {
        let path = PathBuf::from(virtual_env);
        if cfg!(target_os = "windows") {
            maybe_push_python_path(
                &mut candidates,
                path.join("Scripts").join("python.exe"),
                "VIRTUAL_ENV",
                "native",
                None,
            );
        } else {
            maybe_push_python_path(
                &mut candidates,
                path.join("bin").join("python"),
                "VIRTUAL_ENV",
                "native",
                None,
            );
        }
    }

    if cfg!(target_os = "windows") {
        maybe_push_python_path(
            &mut candidates,
            backend_root.join(".venv").join("Scripts").join("python.exe"),
            "repo .venv",
            "native",
            None,
        );
        maybe_push_python_path(
            &mut candidates,
            backend_root.join("venv").join("Scripts").join("python.exe"),
            "repo venv",
            "native",
            None,
        );
        candidates.push(PythonLaunchCandidate {
            program: "python".to_string(),
            prefix_args: Vec::new(),
            label: "python".to_string(),
            kind: "native",
            state_path: None,
        });
        candidates.push(PythonLaunchCandidate {
            program: "py".to_string(),
            prefix_args: vec!["-3".to_string()],
            label: "py -3".to_string(),
            kind: "native",
            state_path: None,
        });
    } else {
        maybe_push_python_path(
            &mut candidates,
            backend_root.join(".venv").join("bin").join("python"),
            "repo .venv",
            "native",
            None,
        );
        maybe_push_python_path(
            &mut candidates,
            backend_root.join("venv").join("bin").join("python"),
            "repo venv",
            "native",
            None,
        );
        candidates.push(PythonLaunchCandidate {
            program: "python3".to_string(),
            prefix_args: Vec::new(),
            label: "python3".to_string(),
            kind: "native",
            state_path: None,
        });
        candidates.push(PythonLaunchCandidate {
            program: "python".to_string(),
            prefix_args: Vec::new(),
            label: "python".to_string(),
            kind: "native",
            state_path: None,
        });
    }

    candidates
}

fn launch_candidates<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    layout: &BackendLayout,
) -> Vec<PythonLaunchCandidate> {
    let mut candidates = Vec::new();
    let state_path = backend_state_path(app);

    if cfg!(target_os = "windows") {
        match backend_mode() {
            BackendMode::Wsl => {
                if let Some(candidate) = wsl_launch_candidate(app, layout) {
                    candidates.push(candidate);
                } else {
                    eprintln!("[nous-companion] WSL backend mode requested, but WSL launch path could not be resolved");
                }
                return candidates;
            }
            BackendMode::Auto => {
                eprintln!(
                    "[nous-companion] auto backend mode on Windows: trying native Python first, then WSL fallback"
                );
            }
            BackendMode::Native => {}
        }
    }

    let native_candidates = python_candidates(&layout.root).into_iter().map(|mut candidate| {
        candidate.state_path = state_path.clone();
        candidate
    });
    candidates.extend(native_candidates);

    if cfg!(target_os = "windows") && matches!(backend_mode(), BackendMode::Auto) {
        if let Some(candidate) = wsl_launch_candidate(app, layout) {
            candidates.push(candidate);
        } else {
            eprintln!("[nous-companion] WSL launch unavailable, using native Windows Python only");
        }
    }

    candidates
}

fn configure_backend_command(command: &mut Command) {
    command.stdin(Stdio::null());

    let inherit_stdio = cfg!(debug_assertions) || backend_stdio_enabled();
    if inherit_stdio {
        command.stdout(Stdio::inherit());
        command.stderr(Stdio::inherit());
    } else {
        command.stdout(Stdio::null());
        command.stderr(Stdio::null());
    }

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;

        if !inherit_stdio {
            command.creation_flags(WINDOWS_CREATE_NO_WINDOW);
        }
    }
}

fn start_backend_if_needed<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    supervisor: Arc<BackendSupervisor>,
) {
    set_backend_ws_host(&app, &default_backend_ws_host());

    if !backend_autostart_enabled() {
        eprintln!(
            "[nous-companion] backend autostart disabled by NOUS_COMPANION_DISABLE_BACKEND_AUTOSTART"
        );
        return;
    }

    cleanup_stale_backend(&app);
    let ready_path = backend_ready_path(&app);
    if let Some(path) = &ready_path {
        clear_backend_ready(path);
    }

    if backend_is_running() {
        eprintln!("[nous-companion] backend already running on port {BACKEND_PORT}; leaving it alone");
        return;
    }

    let Some(layout) = resolve_backend_layout(&app) else {
        eprintln!("[nous-companion] backend script not found; skipping autostart");
        return;
    };

    eprintln!(
        "[nous-companion] trying backend autostart from {} at {}",
        layout.source_label,
        layout.script_path.display()
    );

    for candidate in launch_candidates(&app, &layout) {
        if supervisor.shutting_down.load(Ordering::Relaxed) {
            return;
        }
        supervisor.launching.store(true, Ordering::Relaxed);

        let mut command = Command::new(&candidate.program);
        command.args(&candidate.prefix_args);
        command.arg(&layout.script_path);
        command.current_dir(&layout.root);
        command.env("PYTHONUNBUFFERED", "1");
        command.env("NOUS_COMPANION_TAURI", "1");
        if let Ok(data_dir) = app.path().app_data_dir() {
            command.env("NOUS_COMPANION_DATA_DIR", data_dir);
        }
        if candidate.kind == "native" {
            if let Some(path) = &ready_path {
                command.env("NOUS_COMPANION_READY_FILE", path);
            }
        }
        configure_backend_command(&mut command);

        eprintln!(
            "[nous-companion] launching backend via {} from {}",
            candidate.label,
            layout.root.display()
        );

        let mut child = match command.spawn() {
            Ok(child) => child,
            Err(err) => {
                supervisor.launching.store(false, Ordering::Relaxed);
                eprintln!(
                    "[nous-companion] failed to spawn backend with {}: {}",
                    candidate.label, err
                );
                continue;
            }
        };

        if candidate.kind == "wsl" {
            if let Some(host) = wsl_backend_host() {
                eprintln!("[nous-companion] using WSL backend host {}", host);
                set_backend_ws_host(&app, &host);
            } else {
                eprintln!("[nous-companion] could not resolve WSL backend host, falling back to 127.0.0.1");
                set_backend_ws_host(&app, &default_backend_ws_host());
            }
        } else {
            set_backend_ws_host(&app, &default_backend_ws_host());
        }

        let deadline = Instant::now() + Duration::from_secs(BACKEND_STARTUP_TIMEOUT_SECS);
        let ready_state = wait_for_backend_ready(
            deadline,
            &supervisor,
            &mut child,
            ready_path.as_deref(),
        );
        match ready_state {
            BackendReadyState::Ready | BackendReadyState::Warming => {
                if supervisor.shutting_down.load(Ordering::Relaxed) {
                    let _ = child.kill();
                    let _ = child.wait();
                    supervisor.launching.store(false, Ordering::Relaxed);
                    return;
                }

                match ready_state {
                    BackendReadyState::Ready => eprintln!(
                        "[nous-companion] backend autostart succeeded via {}",
                        candidate.label
                    ),
                    BackendReadyState::Warming => eprintln!(
                        "[nous-companion] backend started via {} and is still warming up; renderer will keep retrying",
                        candidate.label
                    ),
                    BackendReadyState::Failed => {}
                }

                if candidate.kind == "native" {
                    if let Some(state_path) = &candidate.state_path {
                        write_backend_state(
                            state_path,
                            std::process::id(),
                            "native",
                            &child.id().to_string(),
                        );
                    }
                }
                if let Ok(mut slot) = supervisor.child.lock() {
                    *slot = Some(BackendProcess {
                        child,
                        kind: candidate.kind,
                        state_path: candidate.state_path.clone(),
                    });
                }
                supervisor.launching.store(false, Ordering::Relaxed);
                return;
            }
            BackendReadyState::Failed => {}
        }

        let _ = child.kill();
        let _ = child.wait();
        supervisor.launching.store(false, Ordering::Relaxed);
    }
    supervisor.launching.store(false, Ordering::Relaxed);

    eprintln!(
        "[nous-companion] backend autostart failed; app will keep retrying the websocket connection"
    );
}

fn shutdown_backend(supervisor: &BackendSupervisor) {
    supervisor.shutting_down.store(true, Ordering::Relaxed);

    if let Ok(mut slot) = supervisor.child.lock() {
        if let Some(mut backend) = slot.take() {
            if backend.kind == "wsl" {
                if let Some(state_path) = &backend.state_path {
                    if let Some(state) = read_backend_state(state_path) {
                        kill_backend_state(&state);
                    }
                    clear_backend_state(state_path);
                }
            }

            let _ = backend.child.kill();
            let _ = backend.child.wait();

            if backend.kind == "native" {
                if let Some(state_path) = &backend.state_path {
                    clear_backend_state(state_path);
                }
            }
            eprintln!("[nous-companion] stopped app-managed backend");
        }
    }
}

#[tauri::command]
async fn resize_window(window: tauri::WebviewWindow, width: f64, height: f64) -> Result<(), String> {
    window.set_size(tauri::Size::Logical(tauri::LogicalSize { width, height }))
        .map_err(|e: tauri::Error| e.to_string())
}

#[tauri::command]
async fn resize_settings_window(app: tauri::AppHandle, width: f64, height: f64) -> Result<(), String> {
    if let Some(settings_window) = app.get_webview_window("settings") {
        settings_window.set_size(tauri::Size::Logical(tauri::LogicalSize { width, height }))
            .map_err(|e: tauri::Error| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
async fn open_settings_window(app: tauri::AppHandle) -> Result<(), String> {
    let passive_settings = diag_passive_settings();

    // Check if settings window already exists
    if let Some(settings_window) = app.get_webview_window("settings") {
        if !passive_settings {
            let _ = settings_window.set_focus();
        }
        let _ = app.emit("settings-window-opened", ());
        return Ok(());
    }
    
    // Create new settings window
    let _settings_window = tauri::WebviewWindowBuilder::new(
        &app,
        "settings",
        tauri::WebviewUrl::App("settings.html".into()),
    )
    .title("Settings")
    .inner_size(720.0, 580.0)
    .resizable(false)
    .maximizable(false)
    .decorations(false)
    .shadow(false)
    .always_on_top(!passive_settings)
    .build()
    .map_err(|e| e.to_string())?;
    
    let _ = app.emit("settings-window-opened", ());
    Ok(())
}

#[tauri::command]
async fn close_settings_window(app: tauri::AppHandle) -> Result<(), String> {
    let _ = app.emit("settings-window-closed", ());
    if let Some(settings_window) = app.get_webview_window("settings") {
        settings_window.close().map_err(|e: tauri::Error| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
async fn close_app(app: tauri::AppHandle, state: tauri::State<'_, AppState>) -> Result<(), String> {
    shutdown_backend(state.backend_supervisor.as_ref());
    app.exit(0);
    Ok(())
}

#[tauri::command]
async fn get_backend_ws_config(state: tauri::State<'_, AppState>) -> Result<BackendWsConfig, String> {
    Ok(resolve_backend_ws_config(&state))
}

#[tauri::command]
async fn backend_is_ready(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
) -> Result<bool, String> {
    if let Some(path) = backend_ready_path(&app) {
        if backend_ready_file_exists(&path) {
            return Ok(true);
        }
    }

    if state.backend_supervisor.launching.load(Ordering::Relaxed) {
        return Ok(false);
    }

    if let Ok(slot) = state.backend_supervisor.child.lock() {
        if slot.is_some() {
            return Ok(false);
        }
    }

    Ok(backend_is_running())
}

#[tauri::command]
async fn frontend_log(message: String) -> Result<(), String> {
    eprintln!("[frontend] {}", message);
    Ok(())
}

#[tauri::command]
async fn read_file_base64(path: String) -> Result<String, String> {
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    Ok(STANDARD.encode(bytes))
}

fn default_downloads_path(filename: &str) -> PathBuf {
    let home = std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
    let downloads = home.join("Downloads");
    let base = if downloads.exists() { downloads } else { home };
    base.join(filename)
}

#[tauri::command]
async fn suggested_export_path(filename: String) -> Result<String, String> {
    Ok(default_downloads_path(&filename).to_string_lossy().into_owned())
}

#[tauri::command]
async fn write_base64_file(path: String, base64_data: String) -> Result<(), String> {
    let trimmed = base64_data
        .split_once(',')
        .map(|(_, data)| data)
        .unwrap_or(base64_data.as_str());
    let bytes = STANDARD.decode(trimmed).map_err(|e| e.to_string())?;
    let target = PathBuf::from(path);
    if let Some(parent) = target.parent() {
        if !parent.as_os_str().is_empty() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
    }
    fs::write(target, bytes).map_err(|e| e.to_string())
}

#[tauri::command]
async fn open_app_folder(app: tauri::AppHandle) -> Result<(), String> {
    let path = app
        .path()
        .app_data_dir()
        .map_err(|_| "Could not resolve app data folder".to_string())?;
    fs::create_dir_all(&path).map_err(|e| e.to_string())?;
    open_in_system(&path.to_string_lossy())
}

#[tauri::command]
async fn open_external_url(url: String) -> Result<(), String> {
    open_in_system(&url)
}

fn open_in_system(target: &str) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("cmd")
            .args(["/c", "start", "", target])
            .spawn()
            .map_err(|e| format!("Failed to open: {}", e))?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(target)
            .spawn()
            .map_err(|e| format!("Failed to open: {}", e))?;
    }
    #[cfg(target_os = "linux")]
    {
        std::process::Command::new("xdg-open")
            .arg(target)
            .spawn()
            .map_err(|e| format!("Failed to open: {}", e))?;
    }
    Ok(())
}

#[tauri::command]
async fn pick_directory(title: Option<String>) -> Result<Option<String>, String> {
    let mut dialog = rfd::FileDialog::new();
    if let Some(title) = title {
        if !title.trim().is_empty() {
            dialog = dialog.set_title(&title);
        }
    }
    Ok(dialog
        .pick_folder()
        .map(|path| path.to_string_lossy().into_owned()))
}

#[derive(Default)]
struct SnapState {
    suppress_next_move: bool,
    snapped_x: Option<i32>,
    snapped_y: Option<i32>,
    cooldown_x: Option<i32>,
    cooldown_y: Option<i32>,
}

fn snap_axis(
    position: i32,
    min: i32,
    max: i32,
    mut snapped_edge: Option<i32>,
    mut cooldown_edge: Option<i32>,
) -> (i32, Option<i32>, Option<i32>) {
    if let Some(edge) = cooldown_edge {
        if (position - edge).abs() > WINDOW_EDGE_REARM_DISTANCE {
            cooldown_edge = None;
        } else {
            return (position, snapped_edge, cooldown_edge);
        }
    }

    if let Some(edge) = snapped_edge {
        let moving_away_from_min = edge == min && position >= edge + WINDOW_EDGE_RELEASE_DISTANCE;
        let moving_away_from_max = edge == max && position <= edge - WINDOW_EDGE_RELEASE_DISTANCE;

        if moving_away_from_min || moving_away_from_max {
            snapped_edge = None;
            cooldown_edge = Some(edge);
            return (position, snapped_edge, cooldown_edge);
        }

        if (position - edge).abs() <= WINDOW_EDGE_SNAP_DISTANCE {
            return (edge, snapped_edge, cooldown_edge);
        }

        snapped_edge = None;
    }

    if (position - min).abs() <= WINDOW_EDGE_SNAP_DISTANCE {
        snapped_edge = Some(min);
        (min, snapped_edge, cooldown_edge)
    } else if (position - max).abs() <= WINDOW_EDGE_SNAP_DISTANCE {
        snapped_edge = Some(max);
        (max, snapped_edge, cooldown_edge)
    } else {
        (position, snapped_edge, cooldown_edge)
    }
}

fn main() {
    let snap_state = Arc::new(Mutex::new(SnapState::default()));
    let backend_supervisor = Arc::new(BackendSupervisor::default());

    let app = tauri::Builder::default()
        .manage(AppState {
            backend_supervisor: Arc::clone(&backend_supervisor),
            backend_ws_host: Arc::new(Mutex::new(default_backend_ws_host())),
        })
        .setup({
            let backend_supervisor = Arc::clone(&backend_supervisor);
            move |app| {
                let handle = app.handle().clone();
                thread::spawn(move || {
                    start_backend_if_needed(handle.clone(), Arc::clone(&backend_supervisor));
                });
                Ok(())
            }
        })
        .on_window_event({
            let snap_state = Arc::clone(&snap_state);
            move |window, event| {
                if window.label() != "main" {
                    return;
                }

                if let tauri::WindowEvent::Moved(position) = event {
                    let mut state = match snap_state.lock() {
                        Ok(state) => state,
                        Err(_) => return,
                    };

                    if state.suppress_next_move {
                        state.suppress_next_move = false;
                        return;
                    }

                    let monitor = match window.current_monitor() {
                        Ok(Some(monitor)) => monitor,
                        _ => return,
                    };

                    let window_size = match window.outer_size() {
                        Ok(size) => size,
                        Err(_) => return,
                    };

                    let work_area = monitor.work_area();
                    let left = work_area.position.x;
                    let top = work_area.position.y;
                    let right = left + work_area.size.width as i32 - window_size.width as i32;
                    let bottom = top + work_area.size.height as i32 - window_size.height as i32;

                    if !matches!(state.snapped_x, Some(edge) if edge == left || edge == right) {
                        state.snapped_x = None;
                    }
                    if !matches!(state.snapped_y, Some(edge) if edge == top || edge == bottom) {
                        state.snapped_y = None;
                    }
                    if !matches!(state.cooldown_x, Some(edge) if edge == left || edge == right) {
                        state.cooldown_x = None;
                    }
                    if !matches!(state.cooldown_y, Some(edge) if edge == top || edge == bottom) {
                        state.cooldown_y = None;
                    }

                    let (snapped_x, snapped_edge_x, cooldown_edge_x) = snap_axis(
                        position.x,
                        left,
                        right,
                        state.snapped_x,
                        state.cooldown_x,
                    );
                    state.snapped_x = snapped_edge_x;
                    state.cooldown_x = cooldown_edge_x;

                    let (snapped_y, snapped_edge_y, cooldown_edge_y) = snap_axis(
                        position.y,
                        top,
                        bottom,
                        state.snapped_y,
                        state.cooldown_y,
                    );
                    state.snapped_y = snapped_edge_y;
                    state.cooldown_y = cooldown_edge_y;

                    if snapped_x == position.x && snapped_y == position.y {
                        return;
                    }

                    state.suppress_next_move = true;
                    drop(state);

                    if window
                        .set_position(tauri::Position::Physical(tauri::PhysicalPosition {
                            x: snapped_x,
                            y: snapped_y,
                        }))
                        .is_err()
                    {
                        if let Ok(mut state) = snap_state.lock() {
                            state.suppress_next_move = false;
                        }
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            resize_window,
            resize_settings_window,
            open_settings_window,
            close_settings_window,
            close_app,
            get_backend_ws_config,
            backend_is_ready,
            frontend_log,
            read_file_base64,
            suggested_export_path,
            write_base64_file,
            open_app_folder,
            open_external_url,
            pick_directory,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    let backend_supervisor_for_run = Arc::clone(&backend_supervisor);
    app.run(move |_app, event| {
        if matches!(
            event,
            tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
        ) {
            shutdown_backend(&backend_supervisor_for_run);
        }
    });

    shutdown_backend(&backend_supervisor);
}
