# Nous Companion — Source Code Surface Audit

**Generated:** 2026-04-30  
**Scope:** Every .py, .js, .html, .css, .rs file (excluding `src-tauri/target/`)

---

## 1. Complete File Manifest

### Python — `src/` (14 files, 8,911 lines)

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `src/server/companion_server.py` | 4,305 | Main WebSocket server: handles client connections, settings, LLM quip generation, TTS orchestration, event broadcasting, animation state, and reaction logic |
| 2 | `src/server/hermes_observer.py` | 1,116 | Polls Hermes session files for state changes (thinking, responding, tool_use, complete), emits companion events |
| 3 | `src/brain/character_manager.py` | 901 | Loads/saves/switches/manages multiple characters from the filesystem; handles character import/export as ZIP archives |
| 4 | `src/compositor/animation_controller.py` | 404 | Orchestrates animation timing: audio-reactive mouth flopping, blink cycles, expression switching, idle motion |
| 5 | `src/hermes_runtime.py` | 395 | Hermes home detection (WSL-aware), env/config loaders, OmniVoice URL resolution, TTS provider discovery |
| 6 | `src/compositor/cutout_compositor.py` | 429 | Composites cut-out sprite layers (eyes, mouths, base) from per-expression-group directories |
| 7 | `src/tts/engine.py` | 210 | TTS engine abstraction: OmniVoice (Gradio), edge-tts, OpenAI TTS, NoOp for silent mode |
| 8 | `src/brain/brain.py` | 179 | Standalone LLM quip generator using character personality + expression selection (legacy/deprecated) |
| 9 | `src/brain/character_loader.py` | 138 | Legacy character loader with expression PNG loading (v1 character format) |
| 10 | `src/compositor/sprite_compositor.py` | 154 | Sprite layout compositor: positions character portrait frames by name and expression |
| 11 | `src/compositor/audio_analyzer.py` | 149 | Extracts RMS energy from WAV audio for mouth-open/close threshold animation |
| 12 | `src/server/scene_player.py` | 508 | Plays `.nous-scene.json` scripted performances with timed TTS, expressions, and cue callbacks |
| 13 | `src/compositor/__init__.py` | 12 | Package exports: SpriteCompositor, CutoutCompositor, ExpressionGroup, AudioAnalyzer, AnimationController |
| 14 | `src/server/__init__.py` | 4 | Package exports: CompanionServer, HermesObserver |
| 15 | `src/brain/__init__.py` | 4 | Package exports: Character, load_character, Brain, Quip |
| 16 | `src/tts/__init__.py` | 3 | Package exports: TTSEngine, NoOpTTS, OpenAITTS, OmniVoiceTTS, create_engine |

### Python — `scripts/` (15 files, 1,068 lines)

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `scripts/detect_offsets.py` | 120 | Detects optimal eye/mouth sprite offsets for cut-out compositing |
| 2 | `scripts/debug_composite.py` | 94 | Debug composite rendering preview for character sprites |
| 3 | `scripts/debug_lipsync.py` | 99 | Debug audio-driven lip-sync visualization |
| 4 | `scripts/preview_animation.py` | 92 | Local animation preview without full server |
| 5 | `scripts/gen_expressions.py` | 99 | Generates expression variant sprites from a base sprite |
| 6 | `scripts/gen_placeholders.py` | 89 | Creates placeholder sprite files for new character templates |
| 7 | `scripts/demo_server.py` | 84 | Launch script for development demo server |
| 8 | `scripts/run_nous_companion.py` | 75 | Production launch script that starts the companion server |
| 9 | `scripts/sprite_sheet.py` | 64 | Generates sprite sheets from individual expression PNGs |
| 10 | `scripts/omnivoice_tts.py` | 56 | Standalone OmniVoice TTS test |
| 11 | `scripts/inspect_hermes.py` | 40 | Inspects Hermes home directory structure |
| 12 | `scripts/test_audio_direct.py` | 33 | Direct audio playback test |
| 13 | `scripts/test_imports.py` | 32 | Verifies all Python imports resolve correctly |
| 14 | `scripts/test_compositor.py` | 78 | Unit tests for the cut-out compositor |
| 15 | `scripts/check_sprites.py` | 13 | Validates sprite file consistency |

### JavaScript (1 app file + 1 vendor file)

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `renderer/js/renderer.js` | 2,666 | Main renderer: WebSocket client, portrait rendering, audio playback, visual effects (grain, scanlines, interference, burst, colorize), settings bridge, canvas compositing |
| 2 | `renderer/assets/vendor/lucide-lite.js` | 105 | Vendor: Lucide icon library (lite/minified) |

### HTML (6 files, 8,336 lines)

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `renderer/settings.html` | 7,152 | Settings popup: all UI controls (toggles, sliders, selects), character editor, model/session/TTS dropdowns, audio player, character ring 3D carousel |
| 2 | `renderer/font-preview.html` | 368 | Standalone page to preview all loaded fonts |
| 3 | `renderer/splash-preview.html` | 324 | Standalone page to preview splash screen appearance |
| 4 | `renderer/hover-test.html` | 266 | Standalone test for chrome overlay hover interactions |
| 5 | `renderer/arc-effect-test.html` | 169 | Standalone test for arc-like visual effects |
| 6 | `renderer/index.html` | 57 | Main app window layout: portrait canvas, scanlines, grain, burst overlay, chrome overlay, startup splash |

### CSS (2 files, 1,175 lines)

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `renderer/css/chrome.css` | 874 | Main window styles: portrait container, scanlines, grain, burst, splash screen, chrome overlay, brand label, wave viz, hermes mode layout, font faces |
| 2 | `renderer/css/style.css` | 301 | Settings window styles (included via settings.html `<style>` block — style.css appears to be legacy/unused) |

### Rust (1 file)

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `src-tauri/src/main.rs` | 1,336 | Tauri v2 backend: window management, settings window, file dialogs, filesystem ops (read/write), external URL opener, backend process lifecycle |
| 2 | `src-tauri/build.rs` | (build script) | Tauri build configuration (standard) |

### Other Python (test files, root)

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `test_structural.py` | 104 | Structural integrity tests for source tree |
| 2 | `test_idle_load.py` | 41 | Tests idle line loading from character files |
| 3 | `test_scene_player_basic.py` | 36 | Basic scene player unit test |
| 4 | `test_scene_player_import.py` | 4 | Scene player import verification |

---

## 2. Settings Key Cross-Reference

Settings flow: **Server defaults** (`companion_server.py` lines 233-254) → **Prefs file** (persisted JSON) → **Settings UI** (`settings.html` controls + JS event handlers) → **Renderer** (`renderer.js` `handleEvent('settings')` branch).

### Complete Settings Table

| Key | Server Default | UI Element(s) | UI Default | Renderer Handler | 3 Layers? |
|-----|---------------|---------------|------------|-------------------|-----------|
| `observer_enabled` | `True` | `#observer-enabled-toggle` (checkbox in sidebar footer) | `checked` | — (server-side only, controls observer loop) | ✅ Server + UI |
| `verbosity` | `"full"` | `#verbosity-select` (select: full/brief/silent) | `"full"` | — (server-side reaction length control) | ✅ Server + UI |
| `tts_enabled` | `True` | `#tts-enabled-toggle` (checkbox, SYSTEM page) | `checked` | — (server-side TTS gate, checked by scene_player) | ✅ Server + UI |
| `context_budget` | `3` (Deep) | `#context-memory-select` (select: 1=Brief/2=Normal/3=Deep/4=Chaos) | `"3"` | — (server-side, controls prompt depth) | ✅ Server + UI |
| `react_cooldown` | `15` | `#cooldown-select` (select: 5/10/15/30/60s) | `"15"` | — (server-side cooldown timer) | ✅ Server + UI |
| `show_tool_details` | `True` | `#tool-details-toggle` (checkbox, SYSTEM page) | `checked` | — (server-side, controls tool event verbosity) | ✅ Server + UI |
| `idle_lines_enabled` | `True` | `#idle-lines-toggle` (checkbox, SYSTEM page) | `checked` | — (server-side, enables/disables idle line generation) | ✅ Server + UI |
| `playback_volume` | `0.8` | `#volume-slider` (range 0-100) | `80` → `0.8` | ✅ `applyPlaybackVolume(data.settings.playback_volume)` at line 1273 | ✅ All 3 |
| `chrome_style` | `"hermes"` | `#chrome-style-select` (select: hermes/classic) | `"hermes"` | ✅ `applyChromeStyle(currentChromeStyle)` at line 1276 | ✅ All 3 |
| `show_indicator_dot` | `False` | `#indicator-dot-toggle` (checkbox) | unchecked | ✅ Toggles `#status-dot` display at line 1282 | ✅ All 3 |
| `show_scanlines` | `True` | `#scanlines-toggle` (checkbox, DISPLAY page) | `checked` | ✅ EffectMap `["show_scanlines", ".scanlines"]` at line 1290 | ✅ All 3 |
| `show_grain` | `True` | `#grain-toggle` (checkbox) | `checked` | ✅ EffectMap `["show_grain", "#grain-canvas"]` at line 1291 | ✅ All 3 |
| `show_interference` | `True` | `#interference-toggle` (checkbox) | `checked` | ✅ EffectMap `["show_interference", "#interference-bars"]` at line 1292 | ✅ All 3 |
| `show_burst` | `True` | `#burst-toggle` (checkbox) | `checked` | ✅ EffectMap `["show_burst", "#burst-overlay"]` at line 1293 | ✅ All 3 |
| `show_burst_on_expr` | `False` | `#burst-expr-toggle` (checkbox) | unchecked | ✅ `showBurstOnExpr = data.settings.show_burst_on_expr` at line 1324 | ✅ All 3 |
| `show_analog_bleed` | `True` | `#analog-bleed-toggle` (checkbox) | `checked` | ✅ `analogBleedEnabled = data.settings.show_analog_bleed` at line 1302 | ✅ All 3 |
| `frame_style` | `"creme"` | `#frame-style-select` (select: none/creme/white/black/brackets) | `"creme"` | ✅ `frameStyle = data.settings.frame_style` + `redrawFrameOverlay()` at line 1314 | ✅ All 3 |
| `colorize_enabled` | `False` | `#colorize-toggle` (checkbox) | unchecked | ✅ `colorizeEnabled = data.settings.colorize_enabled` at line 1329 | ✅ All 3 |
| `colorize_color` | `"#ff0000"` | `#colorize-picker` (color input) | `#ff0000` | ✅ `colorizeColor = hexToRgb(data.settings.colorize_color)` at line 1337 | ✅ All 3 |
| `colorize_strength` | `1.0` | `#colorize-strength` (range 0-1) | `1.0` → `100%` | ✅ `colorizeStrength = Math.max(0, Math.min(1, data.settings.colorize_strength))` at line 1346 | ✅ All 3 |

### Settings Flow Notes

- **All 20 server-defaulted settings** are persisted via `_save_settings()`/`_load_settings()` in `companion_server.py`
- **9 keys have full 3-layer coverage** (server default → UI element → renderer handler): `playback_volume`, `chrome_style`, `show_indicator_dot`, `show_scanlines`, `show_grain`, `show_interference`, `show_burst`, `show_burst_on_expr`, `show_analog_bleed`, `frame_style`, `colorize_enabled`, `colorize_color`, `colorize_strength`
- **Settings-specific UI wiring** is in `initObserverSettings()` (settings.html lines 3717-3754) and `applySettings()` (lines 3596-3668)
- **The volume slider** uses its own `sendSetting("playback_volume", ...)` call (line 4537) rather than the generic effect listeners
- **Settings UI query on connect**: `send("get_settings", {})` sent by renderer.js at line 721, received at server handler `handle_get_settings` which broadcasts `{"type": "settings", "settings": {...}}`

---

## 3. Dead / Dormant Code

### 3.1 Stale "codec" Prefix Logging (should be "nc")

Found these `console.log/warn/error` calls still using a `[codec]` prefix instead of the renamed `[nc]`:

- **None found.** All console output in `renderer.js` uses `[nc]` consistently.
- `settings.html` uses `[settings]` prefix (consistent, no cleanup needed).
- **HermesObserver** uses `CODEC_DEBUG_POLL` env var (line 67-69) — this is the last remaining "codec" reference in the Python backend:
  ```python
  self._debug_poll: bool = os.environ.get("CODEC_DEBUG_POLL", "").strip().lower()
  ```
  This is used internally for debug tracing; low cleanup priority.

### 3.2 Diagnostic Environment Variables

Found in `companion_server.py` lines 216-230:

| Env Var | Used? | Notes |
|---------|-------|-------|
| `CODEC_DIAG_DISABLE_FRAME_STREAM` | ✅ Used at line 281 | Disables continuous frame streaming |
| `CODEC_DIAG_DISABLE_ALL_RENDERER_FRAMES` | ✅ Used at line 283, checked at line 670 | Disables ALL frame messages |
| `CODEC_DIAG_SWITCH_CONTROL_FIRST` | ✅ Used at line 285 | Switches control order |
| `CODEC_DIAG_DISABLE_OBSERVER` | ✅ Used at line 287, checked at line 468 | Disables Hermes observer |
| `CODEC_DIAG_DISABLE_SESSION_REFRESH` | ✅ Used at line 289 | Disables session refresh loop |

**All 5 diagnostic flags are wired but remain prefixed with "CODEC"**. They work, just have legacy naming.

### 3.3 Commented-Out Settings or Features

- **`settings.html` line 117**: The `<input>` for character import accepts `.codec-character.zip` as a legacy extension — intentionally retained for backward compatibility.
- **`renderer.js` line 10-17**: `CHARACTER_CODEC_FREQUENCIES` object references old "codec" naming for codec frequencies. This is cosmetic display data, not a code path.
- **`character_manager.py` line 25**: `LEGACY_CHARACTER_ARCHIVE_MANIFEST = "codec-companion-character.json"` — retained for backward compatibility with old character exports.
- **`renderer.js` line 1935**: Falls back to reading `localStorage.getItem('codec-sprite-size')` for backward compatibility.
- **`companion_server.py` line 339**: `_legacy_prefs_path = hermes_path("codec-companion-prefs.json")` — reads old prefs filename, writes to new `nous-companion-prefs.json`.

### 3.4 Unreferenced JS Functions / CSS Classes

- **`style.css` (301 lines)** — The `<link>` in `settings.html` references `css/chrome.css?v=1` (correct). But `settings.html` contains all its styles inline within `<style>` blocks (lines 502-5001). `style.css` (301 lines in `renderer/css/style.css`) is **loaded by neither `index.html` nor `settings.html`** — this file is completely unreferenced and dead code.
- **`applyFrameBorder()`** (settings.html line 3590-3594) — Called from `applySettings()` line 3660. Active code.
- **`applyRuntimeState()`** (settings.html line 3684) — Used in `handleEvent` for `runtime_config` data type. Active.
- **`preview_animation.py` series of test HTML files**: `arc-effect-test.html`, `font-preview.html`, `hover-test.html`, `splash-preview.html` — These are dev/test pages not linked from any production code. Possibly referenced by the user manually.

### 3.5 Legacy/Backward-Compatibility Bridges

| Location | Legacy Reference | Migration |
|----------|-----------------|-----------|
| `companion_server.py:339` | `codec-companion-prefs.json` → `nous-companion-prefs.json` | Read from legacy, write to new |
| `character_manager.py:25-28` | `codec-companion-character.json` + `.codec-character.zip` | Accept both on import, export as new |
| `renderer.js:1935` | `localStorage('codec-sprite-size')` | Read legacy on migration |
| `settings.html:117` | `.codec-character.zip` in file accept attr | Accept legacy archives |

---

## 4. Dependency Chain

### 4.1 Python Imports (src/ directory)

```
src/server/companion_server.py
  ├── compositor.cutout_compositor
  ├── compositor.animation_controller
  ├── hermes_runtime (all major functions)
  ├── server.hermes_observer
  ├── brain.character_manager (late import, inside __init__)
  └── aiohttp, numpy, soundfile, websockets, gradio_client (runtime TTS)

src/server/hermes_observer.py
  └── (stdlib only: asyncio, json, os, re, time, datetime, pathlib, sqlite3)

src/server/scene_player.py
  └── src/server/companion_server (via server arg, loose coupling)

src/brain/brain.py
  ├── brain.character_loader (Character)
  └── hermes_runtime (get_api_server_key, get_api_server_url)

src/brain/character_manager.py
  ├── compositor.cutout_compositor (CutoutCompositor)
  └── (PyYAML, PIL for image processing)

src/brain/character_loader.py
  └── PIL (Image)

src/compositor/__init__.py → exports: SpriteCompositor, CutoutCompositor, ExpressionGroup, AudioAnalyzer, AnimationController

src/compositor/cutout_compositor.py
  └── PIL (Image)

src/compositor/animation_controller.py
  ├── compositor.cutout_compositor
  └── compositor.audio_analyzer

src/compositor/audio_analyzer.py
  └── numpy

src/compositor/sprite_compositor.py
  └── PIL (Image)

src/tts/engine.py
  └── (edge_tts, gradio_client loaded lazily)

src/hermes_runtime.py
  └── (stdlib: json, os, subprocess, pathlib)
```

**Import graph (simplified):**
```
brain/brain.py → brain/character_loader.py → (PIL)
                → hermes_runtime.py

brain/character_manager.py → compositor/cutout_compositor.py → (PIL)

server/companion_server.py → compositor/cutout_compositor.py
                           → compositor/animation_controller.py → audio_analyzer.py → numpy
                           → hermes_runtime.py
                           → server/hermes_observer.py
                           → brain/character_manager.py

compositor/sprite_compositor.py → (PIL) - standalone
tts/engine.py → standalone
server/scene_player.py → standalone
```

### 4.2 JS Script Load Order

**index.html** (main window, line 55):
```html
<script src="js/renderer.js?v=20260430-splash-rotation"></script>
```
→ Single script. All renderer logic is IIFE-wrapped in `renderer.js`.

**settings.html** (settings popup):
```html
<script src="assets/vendor/lucide-lite.js"></script>   <!-- line 8 -->
<script> /* inline lucide DOMContentLoaded init */ </script>  <!-- lines 9-12 -->
<style> ... </style>  <!-- lines 502-5001: all CSS inline -->
<script> /* entire settings JS application (~2150 lines) */ </script>  <!-- lines ~5000-7150 -->
```
→ All settings JS is in a single inline `<script>` block at the bottom, after the inline styles.

### 4.3 External Dependencies

**Python (requirements.txt):**
```
aiohttp>=3.9          → HTTP client for LLM API calls
edge-tts>=6.1         → Free TTS fallback
gradio_client>=1.10   → OmniVoice TTS API client
numpy>=1.26           → Audio RMS analysis
Pillow>=10.0          → Image compositing (sprite layers)
PyYAML>=6.0           → Config file parsing
soundfile>=0.12       → Audio file reading
websockets>=12.0      → WebSocket server
```
+ **aiohttp** required for LLM calls.
+ **sqlite3** used by hermes_observer to query state.db (stdlib).
+ **edge_tts** requires ffmpeg for WAV conversion (runtime dependency).

**Rust (Cargo.toml):**
```
tauri = { version = "2", features = ["unstable"] }   → Desktop app framework
serde = { version = "1", features = ["derive"] }     → JSON serialization
serde_json = "1"                                      → JSON parsing
base64 = "0.22"                                       → File base64 encoding
rfd = "0.15"                                          → Native file dialogs
tauri-build = "2" (build dep)                         → Build configuration
```

**Vendor JS:**
- `lucide-lite.js` (105 lines) — SVG icon system for settings UI buttons

---

## 5. Total Lines of Code

| Language | Scope | Files | Lines |
|----------|-------|-------|-------|
| **Python** | `src/` | 16 files | 8,911 |
| **Python** | `scripts/` | 15 files | 1,068 |
| **Python** | root test files | 4 files | 185 |
| **Python** | **Total** | **35 files** | **10,164** |
| **JavaScript** | `renderer/js/` (app) | 1 file | 2,666 |
| **JavaScript** | `renderer/assets/vendor/` | 1 file | 105 |
| **JavaScript** | **Total** | **2 files** | **2,771** |
| **HTML** | `renderer/` | 6 files | 8,336 |
| **CSS** | `renderer/css/` | 2 files | 1,175 |
| **Rust** | `src-tauri/src/` | 1 file | 1,336 |

### Grand Total by Source Type

| Category | Files | Lines |
|----------|-------|-------|
| Application Python (src/) | 16 | 8,911 |
| Utility Python (scripts/ + tests/) | 19 | 1,253 |
| JavaScript (app + vendor) | 2 | 2,771 |
| HTML | 6 | 8,336 |
| CSS | 2 | 1,175 |
| Rust | 1 | 1,336 |
| **Grand Total** | **46** | **23,782** |

### By Functional Area

| Area | Lines | % |
|------|-------|---|
| Python backend (server, observer, character mgmt) | 8,911 | 37.5% |
| HTML (settings UI heavy at 7,152 lines) | 8,336 | 35.0% |
| JavaScript renderer | 2,666 | 11.2% |
| Rust Tauri shell | 1,336 | 5.6% |
| CSS styles | 1,175 | 4.9% |
| Scripts + tests | 1,253 | 5.3% |
| Vendor JS | 105 | 0.4% |

---

## 6. Notable Findings

1. **`renderer/css/style.css` is dead code** — 301 lines loaded by neither HTML page. All settings styles are inlined in `settings.html`'s `<style>` block, and main window styles are in `chrome.css`.

2. **Settings HTML is extremely large** — `settings.html` at 7,152 lines is the single largest file. ~5,200 lines are inline CSS (lines 502-5,000) and ~2,150 lines are inline JS (lines ~5,000-7,150). This file would benefit from extracting CSS and JS into separate files.

3. **5 CODEC_DIAG_* env vars** remain with legacy "CODEC" prefix while the main codebase has been renamed to "nous-companion". They still function but should be renamed for consistency.

4. **Legacy backward compatibility is well-handled** — 4 migration bridges exist (prefs, character archives, localStorage keys, file accept patterns) that gracefully read old `codec-*` formats while writing the new `nous-*` format.

5. **All 20 settings keys defined in the server have UI representations** — coverage is complete from server defaults through to the settings UI. 12 of 20 keys additionally have renderer-side handlers (visual effects that need immediate DOM updates).

6. **`brain/brain.py` (179 lines) appears dormant** — The `CompanionServer` no longer uses `Brain` directly; all quip generation is done inline via `_generate_quip()` in `companion_server.py`. The standalone `Brain` class may have been superseded.

7. **The `splash-preview.html` and test HTML pages** are not referenced by any production code — they are developer tooling for visual testing.
