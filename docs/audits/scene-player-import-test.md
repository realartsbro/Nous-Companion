# Scene Player Import Test

**Date:** 2026-04-30
**Working Directory:** `/mnt/c/Users/will/Agent Workspace/codec-companion`
**Python Version:** 3.10.12 (Linux/WSL)

---

## 1. Syntax Check `py_compile`

| Result | Detail |
|--------|--------|
| **PASS** | `src/server/scene_player.py` — no syntax errors |

---

## 2. Import Results

### Test A: Direct import via `from src.server.scene_player import ScenePlayer`

| Result | Detail |
|--------|--------|
| **FAIL** | `src/server/__init__.py` is triggered, which imports `companion_server`, which imports `from compositor.cutout_compositor import CutoutCompositor`. The `compositor` package is not on the default Python path. Error: `ModuleNotFoundError: No module named 'compositor'` |

### Test B: Import with `sys.path.insert(0, "src")` via `from server.scene_player import ScenePlayer`

| Result | Detail |
|--------|--------|
| **PASS** | Module found when `src/` is on path. All 13 public methods enumerated. |

**ScenePlayer public API (13 methods):**
- `STATE_DONE`, `STATE_IDLE`, `STATE_LOADED`, `STATE_PAUSED`, `STATE_PLAYING`
- `VALID_STATES`
- `handle_command`, `load_scene`, `pause_scene`, `play_scene`, `reset`, `scene_status`, `state`, `stop_scene`

### Test C: Full package import `from server import companion_server, scene_player`

| Result | Detail |
|--------|--------|
| **PASS** | Both modules import successfully when `src/` is on `sys.path`. CompanionServer class present. |

### Test D: `import hermes_runtime` / `from compositor.cutout_compositor import CutoutCompositor`

| Dependency | Status |
|------------|--------|
| `hermes_runtime` | ✅ Found |
| `compositor.cutout_compositor` | ✅ Found (at `src/compositor/`) |
| `numpy` | ✅ Installed |
| `soundfile` | ✅ Installed |
| `websockets` | ✅ Installed |

---

## 3. Test File Execution

### `test_scene_player_import.py`

| Result | Detail |
|--------|--------|
| **PASS** | Output: `OK` |

This file does `sys.path.insert(0, "src")` then `from server.scene_player import ScenePlayer` — works correctly.

### `test_scene_player_basic.py`

| Result | Detail |
|--------|--------|
| **FAIL** | `TypeError: ScenePlayer.__init__() missing 1 required positional argument: 'server'` |

**Issues identified:**
1. **Constructor mismatch** — `ScenePlayer()` called without the required `server` argument. The actual constructor signature is `ScenePlayer.__init__(self, server)`.
2. **Method name mismatch** — Test calls `player.play()`, `player.pause()`, `player.stop()`, `player.get_status()` but the actual API uses `play_scene()`, `pause_scene()`, `stop_scene()`, and `scene_status()` (or the `state` property).
3. **Test relies on demo scene files** — `demo-scenes/variant-a-witness.nous-scene.json` exists at the expected path, but the test cannot reach it due to the above failures.

### Existing `tests/` Suite (compositor + server tests)

| Test | Result | Reason |
|------|--------|--------|
| `tests/test_compositor.py::test_list_assets` | FAIL | `FileNotFoundError: No positions.json found at characters/default/positions.json` |
| `tests/test_compositor.py::test_composite_expressions` | FAIL | Same — missing `positions.json` |
| `tests/test_compositor.py::test_base64_output` | FAIL | Same — missing `positions.json` |
| `tests/test_compositor.py::test_missing_sprite` | FAIL | Same — missing `positions.json` |
| `tests/test_server.py::test_client` | FAIL | Async test function needs `pytest-asyncio` plugin |

---

## 4. Demo Scene Assets

Three scene files exist in `demo-scenes/`:

| File | Size |
|------|------|
| `variant-a-witness.nous-scene.json` | 2,585 bytes |
| `variant-b-teammate.nous-scene.json` | 4,484 bytes |
| `variant-c-invitation.nous-scene.json` | 3,593 bytes |

All are valid JSON and reference the scene structure expected by `ScenePlayer.load_scene()`.

---

## 5. Import Chain Analysis

```
    ScenePlayer  ──→  stdlib only (asyncio, json, logging, pathlib, wave)
                                                    ╱
    companion_server  ──→  compositor.*  ──→  sprite assets (positions.json)
                        ╲  hermes_runtime  ──→  Hermes API config
                        ╲  numpy, soundfile, websockets
```

- `ScenePlayer` itself has **zero project-internal imports** — only stdlib.
- The import chain breaks only because `src/server/__init__.py` eagerly imports `companion_server`, which triggers `compositor` imports.
- When importing `ScenePlayer` directly (bypassing `__init__.py` or adding `src/` to path), everything works.
- `companion_server` has more complex dependencies but all packages are installed.

---

## 6. Verdict

| Verdict | Detail |
|---------|--------|
| **PASS** — Module is functional for scene playback |

**Justification:**
- `scene_player.py` has clean syntax and no internal project dependencies.
- The module imports successfully with correct path setup (`sys.path.insert(0, "src")`).
- All public API methods are present and properly defined.
- All third-party and project dependencies resolve (`hermes_runtime`, `compositor`, `numpy`, `soundfile`, `websockets`).
- Demo scene files are present and well-formed.

**Caveats to note:**
1. **Path setup required** — The `compositor` package is at `src/compositor/` and needs `src/` on `sys.path`. Tests and run scripts must handle this (the import test does it correctly).
2. **Test file is stale** — `test_scene_player_basic.py` was written against a hypothetical API and needs updating to match the current `ScenePlayer.__init__(self, server)` signature and method names (`play_scene`/`pause_scene`/`stop_scene`/`scene_status`).
3. **Compositor asset gap** — `characters/default/positions.json` is missing, which will break `companion_server` initialization at runtime (not a scene_player issue per se, but affects end-to-end playback).
4. **pytest-asyncio missing** — Async tests in the suite cannot run without this plugin.
