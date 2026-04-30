"""Shared Hermes runtime helpers for Nous Companion."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


def runtime_config_path() -> Path:
    """Return the user-level runtime config path for bootstrap settings."""
    return Path.home() / ".nous-companion" / "runtime.json"


def load_runtime_overrides() -> dict[str, str]:
    """Load bootstrap overrides stored outside Hermes home."""
    data = load_json(runtime_config_path(), {})
    if not isinstance(data, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key, value in data.items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            cleaned[str(key)] = text
    return cleaned


def save_runtime_overrides(updates: dict[str, str | None]) -> dict[str, str]:
    """Persist bootstrap overrides, removing empty values."""
    merged = load_runtime_overrides()
    for key, value in updates.items():
        text = str(value).strip() if value is not None else ""
        if text:
            merged[key] = text
        else:
            merged.pop(key, None)

    path = runtime_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2, sort_keys=True), encoding="utf-8")
    return merged


def _detect_windows_wsl_hermes_home() -> Path | None:
    """Try to locate the default WSL Hermes home from native Windows Python."""
    if os.name != "nt":
        return None

    try:
        proc = subprocess.run(
            ["wsl.exe", "sh", "-lc", "printf '%s\\n%s' \"$WSL_DISTRO_NAME\" \"$HOME\""],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except Exception:
        return None

    parts = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if len(parts) < 2:
        return None

    distro = parts[0]
    linux_home = parts[1]
    suffix = linux_home.replace("/", "\\").lstrip("\\")
    candidates = [
        Path(rf"\\wsl.localhost\{distro}\{suffix}\.hermes"),
        Path(rf"\\wsl$\{distro}\{suffix}\.hermes"),
    ]
    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


def detect_default_hermes_home() -> Path:
    """Best-effort Hermes home auto-detection for the current platform."""
    local_default = Path.home() / ".hermes"
    if (local_default / "config.yaml").exists() or (local_default / ".env").exists():
        return local_default

    wsl_candidate = _detect_windows_wsl_hermes_home()
    if wsl_candidate:
        return wsl_candidate

    if local_default.exists():
        return local_default

    return local_default


def resolve_hermes_home(override: str | Path | None = None) -> Path:
    """Return the Hermes home directory, honoring standard overrides."""
    runtime_overrides = load_runtime_overrides()
    candidate = (
        override
        or os.environ.get("NOUS_COMPANION_HERMES_HOME")
        or os.environ.get("HERMES_HOME")
        or runtime_overrides.get("hermes_home")
    )
    if candidate:
        return Path(candidate).expanduser()
    return detect_default_hermes_home()


def hermes_path(*parts: str, hermes_home: str | Path | None = None) -> Path:
    """Build an absolute path inside Hermes home."""
    return resolve_hermes_home(hermes_home).joinpath(*parts)


def load_json(path: str | Path, default: Any) -> Any:
    """Load JSON from disk, returning a caller-supplied default on failure."""
    target = Path(path)
    if not target.exists():
        return default
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_yaml(path: str | Path, default: Any) -> Any:
    """Load YAML from disk, returning a caller-supplied default on failure."""
    target = Path(path)
    if not target.exists():
        return default
    try:
        import yaml

        return yaml.safe_load(target.read_text(encoding="utf-8")) or default
    except Exception:
        return default


def load_hermes_env(hermes_home: str | Path | None = None) -> dict[str, str]:
    """Read Hermes .env values without requiring the parent shell to source them."""
    values: dict[str, str] = {}
    env_path = hermes_path(".env", hermes_home=hermes_home)
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def get_env_value(
    key: str,
    hermes_home: str | Path | None = None,
    default: str = "",
) -> str:
    """Resolve a setting from process env first, then Hermes .env."""
    value = os.environ.get(key)
    if value is not None:
        return value
    return load_hermes_env(hermes_home).get(key, default)


def get_api_server_url(hermes_home: str | Path | None = None) -> str:
    """Resolve Hermes API server base URL from env/.env with sane defaults."""
    host = get_env_value("API_SERVER_HOST", hermes_home=hermes_home, default="127.0.0.1").strip() or "127.0.0.1"
    port = get_env_value("API_SERVER_PORT", hermes_home=hermes_home, default="8642").strip() or "8642"
    return f"http://{host}:{port}/v1"


def get_api_server_key(hermes_home: str | Path | None = None) -> str:
    """Resolve Hermes API server key from env/.env, with legacy config fallback."""
    key = get_env_value("API_SERVER_KEY", hermes_home=hermes_home, default="").strip()
    if key:
        return key

    config = load_yaml(hermes_path("config.yaml", hermes_home=hermes_home), {})
    api_server = config.get("platforms", {}).get("api_server", {})
    return (
        str(api_server.get("key", "")).strip()
        or str(api_server.get("extra", {}).get("key", "")).strip()
    )


def _is_wsl() -> bool:
    """Return True when running inside Windows Subsystem for Linux."""
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    osrelease = Path("/proc/sys/kernel/osrelease")
    if not osrelease.exists():
        return False
    try:
        return "microsoft" in osrelease.read_text(encoding="utf-8").lower()
    except OSError:
        return False


def _get_wsl_windows_host() -> str | None:
    """Best-effort Windows host IP for WSL2 -> Windows service access.

    Strategy (in order of reliability):
    1. Default gateway from ``ip route`` — in WSL2 this is *always* the
       Windows host, regardless of Tailscale/VPN DNS overrides.
    2. Nameserver from ``/etc/resolv.conf`` — works in vanilla WSL2 but
       breaks when Tailscale MagicDNS or other DNS proxies are active.
    """
    # Preferred: default gateway — this IS the Windows host in WSL2
    try:
        import subprocess
        result = subprocess.run(
            ["ip", "route"],
            capture_output=True, text=True, timeout=3,
        )
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 3 and parts[0] == "default" and parts[1] == "via":
                return parts[2]
    except Exception:
        pass

    # Fallback: parse /etc/resolv.conf for nameserver
    resolv_conf = Path("/etc/resolv.conf")
    if not resolv_conf.exists():
        return None
    try:
        for raw_line in resolv_conf.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line.startswith("nameserver "):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1]:
                return parts[1]
    except OSError:
        return None
    return None


def get_omnivoice_url_candidates(
    hermes_home: str | Path | None = None,
    port: int = 7861,
) -> list[str]:
    """
    Return preferred OmniVoice URLs for the current runtime.

    Explicit env/.env overrides short-circuit the candidate list.
    """
    explicit = get_env_value("OMNIVOICE_URL", hermes_home=hermes_home, default="").strip()
    if explicit:
        return [explicit]

    candidates: list[str] = []

    def add(url: str) -> None:
        normalized = str(url).strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    if _is_wsl():
        windows_host = _get_wsl_windows_host()
        if windows_host:
            add(f"http://{windows_host}:{port}")
        add(f"http://127.0.0.1:{port}")
        add(f"http://localhost:{port}")
    else:
        add(f"http://127.0.0.1:{port}")
        add(f"http://localhost:{port}")

    return candidates


def get_default_omnivoice_url(
    hermes_home: str | Path | None = None,
    port: int = 7861,
) -> str:
    """
    Resolve the default OmniVoice URL for the current runtime.

    - Honors `OMNIVOICE_URL` from process env or `~/.hermes/.env`
    - Uses the Windows host IP automatically when running in WSL
    - Falls back to localhost everywhere else
    """
    return get_omnivoice_url_candidates(hermes_home=hermes_home, port=port)[0]


# ---------------------------------------------------------------------------
# TTS Provider Detection — reads Hermes config + env to report what's available
# ---------------------------------------------------------------------------

TTS_PROVIDER_META: dict[str, tuple[str, str | None]] = {
    "edge-tts":    ("Edge TTS",          None),              # import edge_tts
    "omnivoice":   ("OmniVoice",         None),              # socket/Gradio check
    "openai":      ("OpenAI TTS",        "OPENAI_API_KEY"),
    "elevenlabs":  ("ElevenLabs",        "ELEVENLABS_API_KEY"),
    "mistral":     ("Mistral Voxtral",   "MISTRAL_API_KEY"),
    "minimax":     ("MiniMax TTS",       "MINIMAX_API_KEY"),
    "xai":         ("xAI TTS",           "XAI_API_KEY"),
    "gemini":      ("Gemini TTS",        None),              # GEMINI_API_KEY | GOOGLE_API_KEY
    "neutts":      ("NeuTTS",            None),              # import neutts
    "kittentts":   ("KittenTTS",         None),              # import kittentts
}

# Map Hermes config provider names → our engine IDs
_HERMES_PROVIDER_TO_ENGINE_ID: dict[str, str] = {
    "edge":      "edge-tts",
    "omnivoice": "omnivoice",
    "openai":    "openai",
    "elevenlabs":"elevenlabs",
    "mistral":   "mistral",
    "minimax":   "minimax",
    "xai":       "xai",
    "gemini":    "gemini",
    "neutts":    "neutts",
    "kittentts": "kittentts",
}


def resolve_tts_providers(
    hermes_home: str | Path | None = None,
) -> list[dict]:
    """Detect available TTS providers by reading Hermes config + .env.

    Returns
        list of ``{"id": str, "name": str, "available": bool}``
        covering all known TTS providers.  The caller should treat
        ``available`` as *plausibly configured* — cloud providers are
        checked by API‑key presence, local engines by importability.
        OmniVoice is returned as *unavailable* here because it needs a
        runtime socket check (see ``companion_server._detect_tts_engines``).
    """
    config = load_yaml(hermes_path("config.yaml", hermes_home=hermes_home), {})
    tts_cfg = config.get("tts", {}) or {}
    env = load_hermes_env(hermes_home=hermes_home)

    def _has_env(key: str) -> bool:
        return bool(os.environ.get(key) or env.get(key))

    def _importable(mod: str) -> bool:
        try:
            import importlib.util
            return importlib.util.find_spec(mod) is not None
        except Exception:
            return False

    providers: list[dict] = []

    for engine_id, (name, env_key) in TTS_PROVIDER_META.items():
        if engine_id == "edge-tts":
            available = _importable("edge_tts")
        elif engine_id == "omnivoice":
            available = False   # socket check done by caller
        elif engine_id == "gemini":
            available = _has_env("GEMINI_API_KEY") or _has_env("GOOGLE_API_KEY")
        elif engine_id in ("neutts", "kittentts"):
            available = _importable(engine_id)
        elif env_key:
            available = _has_env(env_key)
        else:
            available = False

        providers.append({
            "id": engine_id,
            "name": name,
            "available": available,
        })

    return providers


def resolve_activated_tts_provider(
    hermes_home: str | Path | None = None,
) -> str:
    """Read the active TTS provider from Hermes config.

    Returns an engine ID (e.g. ``"edge-tts"``, ``"omnivoice"``) that matches
    the keys returned by :func:`resolve_tts_providers`.
    """
    config = load_yaml(hermes_path("config.yaml", hermes_home=hermes_home), {})
    tts_cfg = config.get("tts", {}) or {}
    raw = (tts_cfg.get("provider") or "edge").strip().lower()
    return _HERMES_PROVIDER_TO_ENGINE_ID.get(raw, "edge-tts")
