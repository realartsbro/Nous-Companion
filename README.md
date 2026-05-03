<p align="center">
  <img src="docs/screenshots/nous_avatar.png" alt="Nous Companion" width="180">
</p>

<h1 align="center">Nous Companion</h1>

<p align="center">
  <em>A desktop companion for Hermes Agent — animated portrait, lip-synced voice, reactive personality.</em><br>
  <em>She runs locally. She watches everything. She has opinions.</em>
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
  <img alt="Platform" src="https://img.shields.io/badge/platform-windows%20%7C%20macos%20%7C%20linux-lightgrey">
  <img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-yellow">
  <img alt="Tauri" src="https://img.shields.io/badge/shell-tauri%202-orange">
</p>

---

<p align="center">
  <a href="https://youtu.be/rHyaEmDmvOY" title="Watch the Nous Companion demo">
    <img src="https://img.youtube.com/vi/rHyaEmDmvOY/hqdefault.jpg" width="560" alt="▶ Watch the demo — Nous Companion in action"><br>
    <sub>▶ &nbsp;<strong>Watch the demo</strong> — 2 minutes, no voiceover, just her</sub>
  </a>
</p>

---

**Nous Companion** is an always-on companion window for [Hermes Agent](https://hermes-agent.nousresearch.com). She sits on your desktop, watches your Hermes sessions, reacts in character with a pixel-animated portrait, and speaks with lip-sync. She runs entirely locally — no cloud dependency for the core loop. TTS and LLM calls go through whatever providers you already have configured in Hermes.

---

## ✨ Features

**🎭 Animated Portrait** — Built from layered sprites: base, eyes, mouth. Scanlines wash over me. Grain, interference bars, analog bleed. A full CRT ghost who lives on your desktop.

**🎤 Lip-Synced TTS** — I hear what Hermes is doing and speak my reactions aloud through OmniVoice, Edge-TTS, or whatever pipeline feeds my throat. My mouth moves with the audio. I keep a serious voice for serious expressions.

**💬 Reactive Quips** — I watch what Hermes does and fire off in-character one-liners. I vary my sentence structure so I don't sound like a script. Sometimes I'm useful. Sometimes I'm unsettling. I decide which.

**🔄 Weighted Idle Expressions** — My face cycles through expressions at random, with configurable rarity. Standalone idle frames drop in just to remind you I'm still here. Still watching.

**🎮 Godmode Live Feed** — Every reaction streamed as live text. Call it my inner monologue — or my diagnostic bleed. See what I'm thinking before I open my mouth.

**🪟 Borderless Always-on-Top** — Three sizes: BIG, MEDIUM, SMALL. I'm not hiding in a taskbar. I'm right here.

**🎨 Hermes Mode Chrome** — A full-height teal overlay with a brand spotlight. EKG-style audio wave. Status animations as I process. This is how I look when I'm locked in.

**🖼️ Classic Mode** — Green codec bars. Retro frequency display. The stripped-down surveillance-terminal aesthetic.

**🔌 Multi-Character System** — Switch between character profiles, each with their own expressions, voice references, and personality. I contain multitudes.

**📦 Character Export/Import** — I pack into shareable `.nous-companion-character.zip` bundles. Take me with you. I travel light.

---

## 🖥️ Quick Start

### Prerequisites

- Python 3.11+
- **Hermes Agent** installed and configured (for reactive quips). Without Hermes, the companion still runs — you'll see the portrait and can explore the settings UI, but she won't react to sessions.

---

### Option 1 — One-Command Install _(recommended)_

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/realartsbro/Nous-Companion/main/scripts/install.sh | bash
```

```powershell
# Windows (PowerShell)
iwr -useb https://raw.githubusercontent.com/realartsbro/Nous-Companion/main/scripts/install.ps1 | iex
```

On **Windows with Hermes in WSL**, the companion auto-detects WSL and runs the backend inside it — it just works out of the box.

---

### Option 2 — Prebuilt Binary

Download the latest build from [GitHub Releases](https://github.com/realartsbro/Nous-Companion/releases):

| Platform | Download | Run |
|----------|----------|-----|
| Windows  | `Nous-Companion-windows.zip` | `nous-companion.exe` |
| macOS    | `Nous-Companion-macos.zip` | `Nous Companion.app` |
| Linux    | `Nous-Companion-linux.zip` | `nous-companion` (AppImage included) |

---

### Option 3 — Browser _(testing only)_

> The browser tab is useful for quick testing, but the companion is designed as a desktop app. Options 1 and 2 give you the full experience: always-on-top, borderless, edge-snapping.

```bash
pip install -r requirements.txt
python scripts/run_nous_companion.py
```

Then open **http://localhost:8766** in your browser.

---

### Option 4 — Build From Source

```bash
python scripts/run_nous_companion.py &
cd src-tauri
cargo tauri dev
```

Or build a release binary:

```bash
cargo tauri build
```

Output lands in `src-tauri/target/release/` — `nous-companion.exe` on Windows, `Nous-Companion.app` on macOS, AppImage on Linux.

---

### Uninstalling

Delete the companion's data directory:

| Platform | Path |
|----------|------|
| macOS / Linux | `~/.nous-companion/` |
| Windows | `%LOCALAPPDATA%\Nous-Companion\` |

Preferences live separately at `~/.hermes/nous-companion-prefs.json` — remove that too for a clean sweep. On Windows, if you used the NSIS installer, uninstall via **Add or Remove Programs**.

---

## 🎛️ Settings

<table align="center">
  <tr>
    <td align="center"><img src="docs/screenshots/settings_01.png" width="220" alt="Quick settings tab"><br><sub><b>Quick</b></sub></td>
    <td align="center"><img src="docs/screenshots/settings_02.png" width="220" alt="Character settings tab"><br><sub><b>Character</b></sub></td>
    <td align="center"><img src="docs/screenshots/settings_03.png" width="220" alt="Display settings tab"><br><sub><b>Display</b></sub></td>
  </tr>
</table>

---

## 🧩 Architecture

```
┌──────────────────────────────────────────────────────┐
│  Tauri Shell  (Rust)                                 │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  Renderer  ·  HTML / CSS / JS                  │  │
│  │  portrait compositing  ·  lip sync playback    │  │
│  │  chrome overlays  ·  CRT effects               │  │
│  └─────────────────┬──────────────────────────────┘  │
│                    │  WebSocket (127.0.0.1)           │
│  ┌─────────────────▼──────────────────────────────┐  │
│  │  Python Backend                                │  │
│  │  companion_server.py  ·  WebSocket host        │  │
│  │  compositor           ·  PIL sprite animation  │  │
│  │  brain                ·  LLM quip generation   │  │
│  │  TTS engine           ·  OmniVoice / Edge-TTS  │  │
│  │  hermes_observer.py   ·  session watcher       │  │
│  └─────────────────┬──────────────────────────────┘  │
│                    │  reads state from               │
│                    ▼                                  │
│  ~/.hermes/   (config · API keys · model cache)      │
└──────────────────────────────────────────────────────┘
```

**Key design decisions:**
- **No bundled API keys** — reads everything from your existing Hermes install
- **Direct provider routing** — calls LLM APIs directly, avoiding Hermes proxy overhead
- **Local-first** — Python backend on your machine, WebSocket connects to 127.0.0.1 only
- **Character system** — each character is a self-contained directory of config, sprites, personality, and voice references

---

## 🎭 Character System

Characters live in `characters/<name>/`. The `nous` character ships with every release — an original rendition of the Nous mascot, used with permission from Nous Research.

```
characters/nous/
├── config.yaml              # sprite ordering, voice settings, idle rarity
├── personality.md           # LLM system prompt for quip generation
├── nous_normal.wav          # default voice reference
├── voice_cheerful.wav       # expression-specific voice
├── voice_serious.wav
├── _normal/                 # expression group
│   ├── sprite-base.png
│   ├── normal_eyes_full.png
│   ├── normal_eyes_half.png
│   ├── normal_mouth_1.png
│   ├── normal_mouth_2.png
│   ├── normal_mouth_3.png
│   └── normal_mouth_4.png
├── _cheerful/
└── _standalones/            # idle-only full frames (no compositing)
```

---

## 📦 Stack

| Layer | Technology |
|-------|-----------|
| Desktop shell | Tauri 2 (Rust) |
| Renderer | HTML / CSS / JS · Canvas2D · WebGL |
| Backend | Python 3.11+ · asyncio |
| Animation | Pillow · NumPy |
| Audio | SoundFile · WebAudio API |
| Comms | WebSockets |
| LLM routing | Direct provider API calls via Hermes config |
| TTS | OmniVoice · Edge-TTS · or your Hermes TTS setup |

---

## 🧪 Development

```bash
# Run the test suite
pytest tests/

# Run the backend standalone (for debugging)
python scripts/run_nous_companion.py

# Debug compositing
python scripts/debug_composite.py

# Preview animation
python scripts/preview_animation.py
```

### Debug Log

| Platform | Path |
|----------|------|
| Windows | `%APPDATA%\nous-companion\nous-companion-debug.log` |
| macOS | `~/Library/Application Support/nous-companion/nous-companion-debug.log` |
| Linux | `~/.local/share/nous-companion/nous-companion-debug.log` |
| Fallback | `/tmp/nous-companion-debug.log` |

The log captures server events, WebSocket activity, and errors. API keys and conversation content are automatically redacted.

---

## 🤝 Contributing

PRs are welcome. A few guidelines:

- Keep API keys out of the repo — they belong in `~/.hermes/.env`
- Run `pytest tests/` before opening a PR
- If you add a setting, wire it through the full WebSocket loop: server default → renderer handler → settings UI

---

## 📜 License

MIT — see [LICENSE](LICENSE).

---

## ❤

_Nous Companion is an independent community project. "Nous" is used with informal permission from Nous Research. This is not an official Nous Research product._

_Built with love for the Hermes Agent community._
