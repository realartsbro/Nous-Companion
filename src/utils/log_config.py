"""Logging configuration for Nous Companion.

Thread-safe, idempotent, cross-platform (Windows/WSL2/macOS/Linux).
Designed for single-instance desktop app with moderate log volume.

Gracefully degrades: if no log path is writable, the app continues
with console-only logging rather than crashing.

Architecture
------------
Root logger is set to DEBUG.  Handler-level levels control visibility:
stderr defaults to WARNING (blocking third-party noise), file handler
defaults to DEBUG (capturing everything).  The stderr handler uses a
deny-list filter for known-noisy loggers rather than an allow-list,
so new app packages are visible without registration.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path, PureWindowsPath

_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"
_LOGGER_NAME = "nous_companion"
_METADATA_FILENAME = "logging.json"

# Cached configured state
_configured_log_path: Path | None = None
_configured_lock = threading.Lock()

# Deny-list of noisy third-party loggers suppressed at WARNING.
# Anything NOT in this list is allowed through — no manual registration
# needed when adding new app packages.
_NOISY_LOGGERS = ("asyncio", "urllib3", "websockets", "PIL", "gradio_client",
                  "aiohttp", "aiohttp.access", "charset_normalizer", "numpy",
                  "soundfile", "matplotlib")

# Env-var override for additional noisy loggers at runtime:
#   NOUS_COMPANION_SILENT_LOGGERS=httpx,botocore,google.auth
_EXTRA_SILENT = os.environ.get("NOUS_COMPANION_SILENT_LOGGERS", "").strip()
if _EXTRA_SILENT:
    _NOISY_LOGGERS += tuple(name.strip() for name in _EXTRA_SILENT.split(",") if name.strip())


# ── Platform helpers ──────────────────────────────────────────────────────

def _is_wsl() -> bool:
    return "WSL_DISTRO_NAME" in os.environ or "WSL_INTEROP" in os.environ


def _wsl_to_posix(windows_path: str) -> str:
    """Translate Windows path (C:\\Users\\…) to WSL path (/mnt/c/Users/…)."""
    try:
        result = subprocess.run(
            ["wslpath", "-u", windows_path],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    p = PureWindowsPath(windows_path)
    if p.drive and len(p.drive) >= 2 and p.drive[1] == ":":
        drive_letter = p.drive[0].lower()
        rest = str(p.relative_to(p.drive)).replace("\\", "/")
        if rest and rest != ".":
            return f"/mnt/{drive_letter}/{rest}"
    return windows_path


# ── Path resolution (pure — no side effects) ──────────────────────────────

def _resolve_log_candidates() -> list[Path]:
    """Return candidate log paths in priority order.

    Pure function — does not touch the filesystem.
    Catches RuntimeError from Path.home() in container/CI environments.
    """
    candidates: list[Path] = []

    data_dir = os.environ.get("NOUS_COMPANION_DATA_DIR", "").strip()
    if data_dir:
        if _is_wsl() and ":" in data_dir[:3]:
            data_dir = _wsl_to_posix(data_dir)
        candidates.append(Path(data_dir) / "nous-companion-debug.log")

    try:
        home = Path.home()
    except RuntimeError:
        home = None

    if home is not None:
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
            candidates.append(base / "nous-companion" / "nous-companion-debug.log")
        elif sys.platform == "darwin":
            candidates.append(
                home / "Library" / "Application Support" / "nous-companion"
                / "nous-companion-debug.log"
            )
        else:
            xdg = os.environ.get("XDG_DATA_HOME", str(home / ".local" / "share"))
            candidates.append(Path(xdg) / "nous-companion" / "nous-companion-debug.log")

    candidates.append(
        Path(tempfile.gettempdir()).resolve() / "nous-companion-debug.log"
    )

    return candidates


# ── Cleanup pre-existing basicConfig handlers ─────────────────────────────

def _cleanup_basicconfig_handlers() -> None:
    """Remove unnamed StreamHandlers left by earlier ``logging.basicConfig()``.

    Only targets ``StreamHandler`` instances with no formatter — the
    signature of ``basicConfig()`` output.  Handlers with explicit
    formatters are left alone.
    """
    root = logging.getLogger()
    evicted = 0
    for h in list(root.handlers):
        if isinstance(h, logging.StreamHandler) and h.formatter is None:
            root.removeHandler(h)
            h.close()
            evicted += 1
    if evicted:
        print(
            f"[LOG_CONFIG] Evicted {evicted} unnamed handler(s) "
            f"from basicConfig — check entry points",
            flush=True,
        )


# ── Secure file creation (with fchmod for existing files) ─────────────────

def _open_log_secure(path: Path) -> None:
    """Create (or open) log file with ``0o600`` permissions.

    Uses ``os.open`` with explicit mode for new files, and ``os.fchmod``
    on the returned fd to enforce permissions even on **existing** files
    (``O_CREAT`` ignores mode when the file already exists).
    """
    fd = os.open(
        str(path),
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        mode=stat.S_IRUSR | stat.S_IWUSR,  # 0o600
    )
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Windows: fchmod not supported on all backends
    os.close(fd)


# ── Safe formatter (prevents log injection) ───────────────────────────────

class _SafeFormatter(logging.Formatter):
    """Formatter that sanitises control characters in the final string.

    Escapes newlines, carriage returns, tabs, null bytes, and ANSI escape
    sequences in the **completed formatted string** after all
    interpolation.  Thread-safe — does not mutate ``LogRecord`` state.
    """

    _ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

    def format(self, record: logging.LogRecord) -> str:
        result = super().format(record)
        # Escape newlines and CRs (prevents log injection)
        result = result.replace("\n", "\\n").replace("\r", "\\r")
        # Strip ANSI escape sequences (prevents hidden-redaction attacks)
        result = self._ANSI_ESCAPE.sub("", result)
        # Replace tabs and null bytes with safe representations
        result = result.replace("\t", "\\t").replace("\x00", "\\0")
        return result


# ── Resilient RotatingFileHandler ─────────────────────────────────────────

class _ResilientRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """A rotating file handler that:

    * Recovers gracefully if rotation fails on Windows due to a log-viewer
      lock (``PermissionError`` in ``doRollover``).
    * Re-opens the stream if ``doRollover`` fails mid-way.
    * NOTE: ``FileNotFoundError`` (tmpwatch) and disk-full are **not**
      handled here — ``BaseRotatingHandler.emit()`` routes all exceptions
      to ``handleError()``, which drops the record silently.  These
      scenarios are accepted as inherent limitations of
      ``RotatingFileHandler`` in a desktop app context.
    """

    def doRollover(self) -> None:
        """Override to catch Windows sharing violations during rotation
        without losing the log stream."""
        try:
            super().doRollover()
        except PermissionError:
            # Rotation failed (log viewer holds lock on backup file).
            # Ensure the stream is still usable for subsequent writes.
            if self.stream is None or self.stream.closed:
                try:
                    Path(self.baseFilename).parent.mkdir(parents=True, exist_ok=True)
                    self.stream = self._open()
                except OSError:
                    self.stream = None


# ── Metadata file for Rust log-path coordination ─────────────────────────

def _write_log_metadata(log_path: Path) -> None:
    """Write a small JSON metadata file for Rust discovery.

    Uses ``_open_log_secure`` (with ``fchmod``) and ``chmod`` on the
    result to guarantee ``0o600`` even if a stale ``.tmp`` exists.
    """
    meta_dir = log_path.parent
    meta_path = meta_dir / _METADATA_FILENAME
    tmp = meta_path.with_suffix(".tmp")
    try:
        # Remove stale temp file (owns wrong permissions)
        tmp.unlink(missing_ok=True)
        _open_log_secure(tmp)
        tmp.write_text(
            json.dumps({
                "debug_log_path": str(log_path),
                "version": 1,
                "pid": os.getpid(),
                "log_level": logging.getLevelName(
                    logging.getLogger().getEffectiveLevel()
                ),
            }, indent=2),
            encoding="utf-8",
        )
        # Double-check permissions after write (write_text doesn't preserve them)
        tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
        tmp.rename(meta_path)
    except OSError:
        pass


# ── Main setup entry point ───────────────────────────────────────────────

def setup_logging(log_path: Path | None = None, verbose: bool = False) -> Path | None:
    """Configure root logger with dual console + rotating file handlers.

    Idempotent and thread-safe.  Returns the resolved log path, or
    ``None`` if no path is writable (graceful degradation — the app
    continues with console-only logging).

    Parameters
    ----------
    log_path
        Explicit path override (first call only).
    verbose
        If ``True``, DEBUG+ appears on stdout.  Env override via
        ``NOUS_COMPANION_VERBOSE`` (accepts ``1``, ``true``, ``yes``,
        ``on``, ``y``).

    Returns
    -------
    Path or None
        The resolved log file path, or ``None`` if no candidate is writable.
    """
    global _configured_log_path

    with _configured_lock:
        root = logging.getLogger()

        # ── Idempotency ─────────────────────────────────────────────────────
        if any(
            (h.name or "").startswith(f"{_LOGGER_NAME}_")
            for h in root.handlers
        ):
            if _configured_log_path is not None:
                return _configured_log_path
            for h in root.handlers:
                if isinstance(h, logging.handlers.RotatingFileHandler) and (
                    h.name or ""
                ).startswith(f"{_LOGGER_NAME}_"):
                    return Path(h.baseFilename)
            return _resolve_log_candidates()[-1]

        # ── Evict pre-existing basicConfig handlers ────────────────────────
        _cleanup_basicconfig_handlers()

        root.setLevel(logging.DEBUG)
        fmt = _SafeFormatter(_FORMAT, _DATE_FMT)

        # ── Env var overrides ──────────────────────────────────────────────
        raw_verbose = os.environ.get("NOUS_COMPANION_VERBOSE", "").strip().lower()
        if raw_verbose in ("1", "true", "yes", "on", "y"):
            verbose = True

        raw_level = os.environ.get("NOUS_COMPANION_LOG_LEVEL", "").strip().upper()
        if raw_level:
            file_level = getattr(logging, raw_level, None)
            if file_level is None:
                raise ValueError(
                    f"Invalid NOUS_COMPANION_LOG_LEVEL: {raw_level!r}. "
                    f"Valid: DEBUG, INFO, WARNING, ERROR, CRITICAL"
                )
        else:
            file_level = logging.DEBUG

        # ── Console: DUAL handlers ─────────────────────────────────────────
        if verbose:
            out = logging.StreamHandler(sys.stdout)
            out.name = f"{_LOGGER_NAME}_stdout"
            out.setLevel(logging.INFO)
            out.setFormatter(fmt)
            root.addHandler(out)

        err = logging.StreamHandler(sys.stderr)
        err.name = f"{_LOGGER_NAME}_stderr"
        err.setLevel(logging.DEBUG if verbose else logging.WARNING)
        err.setFormatter(fmt)
        root.addHandler(err)

        # ── File: DEBUG+, auto-rotate ──────────────────────────────────────
        if log_path is not None:
            candidates = [Path(log_path)]
        else:
            candidates = _resolve_log_candidates()

        used_path: Path | None = None
        last_error: OSError | None = None
        for candidate in candidates:
            try:
                candidate.parent.mkdir(parents=True, exist_ok=True)
                _open_log_secure(candidate)
                used_path = candidate
                break
            except OSError as exc:
                last_error = exc
                continue

        if used_path is None:
            # Graceful degradation: continue with console-only logging
            print(
                f"[LOG_CONFIG] Cannot open debug log file "
                f"(last error: {last_error}). Continuing without file logging.",
                flush=True,
            )
            _configured_log_path = None
            # Still suppress noisy loggers
            for noisy in _NOISY_LOGGERS:
                logging.getLogger(noisy).setLevel(logging.WARNING)
            return None

        fh = _ResilientRotatingFileHandler(
            str(used_path),
            maxBytes=5_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        fh.name = f"{_LOGGER_NAME}_file"
        fh.setLevel(file_level)
        fh.setFormatter(fmt)
        root.addHandler(fh)

        # ── Suppress known noisy third-party loggers ───────────────────────
        for noisy in _NOISY_LOGGERS:
            logging.getLogger(noisy).setLevel(logging.WARNING)

        _configured_log_path = used_path
        _write_log_metadata(used_path)
        return used_path


# ── Phase-1 compatibility shim ───────────────────────────────────────────

def _debug_log_shim(message: str, category: str = "shim") -> None:
    """Phase-1 compatibility shim for ``CompanionServer._debug_log``.

    Preserves the legacy ``print()`` to stdout, while also routing through
    the new logging pipeline.  In Phase 2 the ``print()`` is removed
    per-category.

    .. note::
       If called before ``setup_logging()``, the structured log record
       goes to ``logging.lastResort`` (stderr, WARNING+) and is dropped
       at DEBUG level.  The ``print()`` still works.  Early-init logs
       before ``setup_logging()`` do not reach the file.
    """
    print(message, flush=True)
    logging.getLogger(f"{_LOGGER_NAME}.{category}").debug("%s", message)


# ═══════════════════════════════════════════════════════════ Phase 3 — redaction + log access

import urllib.parse as _urllib_parse

_REDACT_PATTERNS = [
    re.compile(p) for p in [
        r"\b(?:api[_-]?key|bearer|authorization|token|password|secret|private_key)\b",
        r"\bsk-[a-zA-Z0-9]{20,}\b",
        r"\bsk-ant-[a-z0-9]{32,}\b",
        r"\bAKIA[A-Z0-9]{16}\b",
        r"\bASIA[A-Z0-9]{16}\b",
        r"\bghp_[a-zA-Z0-9]{36}\b",
        r"\bgithub_pat_[a-zA-Z0-9_]{80,}\b",
        r"\bhf_[a-zA-Z0-9]{20,}\b",
    ]
]

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_URL_PATTERN = re.compile(r"https?://\S+")


def _redact_url(m: re.Match) -> str:
    url = m.group(0)
    try:
        parsed = _urllib_parse.urlparse(url)
        if parsed.username:
            url = url.replace(parsed.username, "[REDACTED]", 1)
        if parsed.password:
            url = url.replace(parsed.password, "[REDACTED]", 1)
        if parsed.query:
            qs = "&".join(f"{k}=[REDACTED]" for k in _urllib_parse.parse_qs(parsed.query))
            url = url.replace("?" + parsed.query, "?" + qs)
        return url
    except Exception:
        return url


def _redact_paths(line: str) -> str:
    line = re.sub(r"/home/[^/\s]+", "~", line)
    line = re.sub(r"/mnt/c/Users/[^/\\\s]+", "~", line)
    line = re.sub(r"C:\\Users\\[^\\\s]+", "~", line)
    return line


def _redact_line(line: str) -> str:
    for pat in _REDACT_PATTERNS:
        line = pat.sub("[REDACTED]", line)
    line = _URL_PATTERN.sub(_redact_url, line)
    line = _redact_paths(line)
    line = _ANSI_ESCAPE_RE.sub("", line)
    return line


def redact_logs(text: str) -> str:
    """Redact sensitive content from log text, then truncate to last 500 lines."""
    lines = [_redact_line(l) for l in text.split("\n")]
    return "\n".join(lines[-500:])


def get_log_text() -> str:
    """Return the last 500 lines of the debug log, redacted."""
    if _configured_log_path is None:
        return "[LOG_CONFIG] No log file configured."
    try:
        with open(_configured_log_path, encoding="utf-8") as f:
            text = f.read()
        return redact_logs(text)
    except Exception as e:
        return f"[LOG_CONFIG] Failed to read log: {e}"
