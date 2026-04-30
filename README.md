# ⬡ NOUS COMPANION

> _a desktop friend that sits next to your Hermes_
> _animated portraits · lip-synced TTS · reactive quips_
> _a community project for Hermes Agent ✦_

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform: Windows | macOS | Linux](https://img.shields.io/badge/platform-windows%20%7C%20macos%20%7C%20linux-lightgrey)]()

---

**Nous Companion** is a small always-on companion window for [Hermes Agent](https://hermes-agent.nousresearch.com). She watches your Hermes sessions, reacts in character with a pixel-animated portrait, speaks with lip-sync, and keeps you company while you work.

She runs entirely locally — no cloud dependency for the core loop. TTS and LLM calls go through whatever providers you already have configured in Hermes.

---

## ✨ Features

- **🎭 Animated Portrait** — layered sprites (base + eyes + mouth) composited at 30 fps. Scanlines, grain, interference bars, analog bleed — full CRT aesthetic.
- **🎤 Lip-Synced TTS** — hears what your Hermes is doing and voices reactions through OmniVoice, Edge-TTS, or your setup of choice. Per-expression voice references (serious voice for serious expressions).
- **💬 Reactive Quips** — generates in-character one-liners based on what Hermes is doing. Varies sentence structure, uses the character's voice.
- **🔄 Weighted Idle Expressions** — expressions cycle at random with configurable rarity. Standalone idle frames drop in occasionally for variety.
- **🎮 Godmode Live Feed** — opens a live text stream of every reaction so you can see her "thinking."
- **🪟 Borderless Always-on-Top** — sits discreetly on your desktop. Three size tiers: BIG (267px), MEDIUM (150px), SMALL (89px).
- **🎨 Hermes Mode Chrome** — full-height teal overlay with sweeping brand spotlight, EKG-style audio wave viz, and status animations.
- **🖼️ Classic (MGS1) Mode** — green-codec bars, MGS1 Codec font, retro frequency display.
- **🔌 Multi-Character System** — switch between character profiles, each with their own expressions, voice references, and personality.
- **📦 Character Export/Import** — shareable `.nous-companion-character.zip` bundles. Legacy `.codec-character.zip` imports still supported.

---

## 🖥️ Quick Start

### Prerequisites

- Python 3.11+
- **Hermes Agent** installed and configured (for reactive quips). Without Hermes, the companion still runs — you'll see the character portrait and can explore the settings UI, but she won't react to sessions.

### Option 1 — Browser (for testing only)

> **Note:** The browser tab works for quick testing, but the companion is designed as a desktop app. Use Option 3 or 4 for the full experience (always-on-top, borderless, edge snapping).

```bash
pip install -r requirements.txt
python scripts/run_nous_companion.py
```

Then open **http://localhost:8766** in your browser.

### Option 2 — Tauri Desktop App (development)

For contributors who want to run from source with the full desktop experience:

```bash
python scripts/run_nous_companion.py &
cd src-tauri
cargo tauri dev
```

> On Windows with Hermes in WSL:
> ```powershell
> $env:NOUS_COMPANION_BACKEND_MODE='wsl'
> cargo tauri dev
> ```

### Option 3 — Prebuilt Binary (recommended for most users)

Coming soon. Prebuilt installers will be published here once CI builds are set up.

### Option 4 — Build Your Own Binary

```bash
cargo tauri build
```

The binary lands in `src-tauri/target/release/`. On Windows: `nous-companion.exe`. On macOS: `Nous-Companion.app`. On Linux: `nous-companion` AppImage.

---

## 🎯 Hackathon: Creative Track + Kimi Track

Nous Companion is built for the **Hermes Agent Creative Hackathon**. Here's how we qualify:

For the **Kimi Track**, the companion's LLM provider can be set to any Kimi model via the System → Model dropdown in settings. The companion routes LLM calls directly (bypassing Hermes proxy) for lower latency — just select a Kimi model and your submission video shows it in action.

---

## 🎨 Visual Style

```
┌──────────────────────┐
│  ⬡ NOUS              │  ← Collapse Bold, cream spotlight
│  ⬡ COMPANION         │  ← sweeping diagonal stroke animation
│                       │
│  SETTINGS / CLOSE     │  ← Mondwest action text
│                       │
│  [  ﹏﹏﹏﹏﹏﹏ ]      │  ← EKG wave viz (audio-reactive)
│                       │
│  ⬤                   │  ← status dot (speaking/thinking/idle)
└──────────────────────┘
```

Dark teal (`#041c1c`) backgrounds. Cream text (`#ffe6cb`). Collapse Bold for the brand. Mondwest for UI. MGS1 Codec for the retro classic skin.

---

## 🧩 Architecture

```
┌─────────────────────────────────────────────────────┐
│  Tauri Shell (Rust)                                 │
│  ┌─────────────────────────────────────────────────┐│
│  │  Renderer (HTML/CSS/JS)  ◀──── WebSocket ────  ││
│  │  - portrait compositing                         ││
│  │  - audio playback with lip sync                 ││
│  │  - chrome overlay + effects                     ││
│  └─────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────┐│
│  │  Python Backend                                 ││
│  │  - companion_server.py (WS host)                ││
│  │  - compositor (PIL cutout animation)            ││
│  │  - brain (LLM quip generation)                  ││
│  │  - TTS engine (OmniVoice / Edge-TTS)            ││
│  │  - hermes_observer.py (session watcher)         ││
│  └─────────────────────────────────────────────────┘│
│         │ reads Hermes state from                   │
│         ▼                                           │
│  ~/.hermes/  (config, API keys, model cache)        │
└─────────────────────────────────────────────────────┘
```

**Key design decisions:**
- **No bundled API keys** — reads everything from your existing Hermes install
- **Direct provider routing** — calls LLM APIs directly when possible (avoids Hermes proxy overhead)
- **Local-first** — Python backend runs on your machine, WebSocket connects to 127.0.0.1
- **Character system** — each character is a directory with config, sprites, personality, and voice references

---

## 🎭 Character System

Characters live in `characters/<name>/`:

```
characters/nous/
├── config.yaml            # sprite ordering, voice settings, idle rarity
├── personality.md         # LLM system prompt for quip generation
├── nous_normal.wav        # default voice reference
├── voice_cheerful.wav     # expression-specific voice
├── voice_serious.wav
├── _normal/               # expression group
│   ├── sprite-base.png    # base head
│   ├── sprite-eyes-open.png
│   ├── sprite-eyes-closed.png
│   ├── sprite-mouth-closed.png
│   └── sprite-mouth-open.png
├── _cheerful/             # another expression
└── _standalones/          # idle-only full frames (no compositing)
```

---

## 🛠️ For Hermes Users: Skills Integration

If you use Hermes Agent, load the **nous-companion** skill to give your Hermes full context about the companion's architecture, settings, and debugging:

```bash
hermes skill view nous-companion
```

The skill covers:
- WebSocket protocol and concurrent-send pitfalls
- Provider routing and model cache management
- Character editor UI and idle rarity system
- Chrome overlay styles (Hermes + Classic)
- All visual effects (scanlines, grain, interference, burst, analog bleed)
- Debugging guide for frame decode starvation, Tauri bridge relay, and more

---

## 📦 Stack

| Layer | Technology |
|-------|-----------|
| Desktop shell | Tauri 2 (Rust) |
| Renderer | Plain HTML/CSS/JS, Canvas2D, WebGL |
| Backend | Python 3.11+, asyncio |
| Animation | Pillow, NumPy |
| Audio | SoundFile, WebAudio API |
| Comms | WebSockets, AioHTTP |
| LLM routing | Direct provider API calls via Hermes config |
| TTS | OmniVoice, Edge-TTS, or your Hermes TTS setup |

---

## 🧪 Development

```bash
# Run tests
pytest tests/

# Run the backend standalone (for debugging)
python scripts/run_nous_companion.py

# Debug compositing
python scripts/debug_composite.py

# Preview animation
python scripts/preview_animation.py
```

---

## 🤝 Contributing

PRs welcome! A few guidelines:
- Keep API keys out of the repo — they belong in `~/.hermes/.env`
- Test your changes with `pytest tests/` before opening a PR
- If you add a setting, wire it through the full WebSocket loop (server default → renderer handler → settings UI)

---

## 📜 License

MIT — see [LICENSE](LICENSE).

---

## ⬡

_Built with ∎ for the Hermes Agent community._
