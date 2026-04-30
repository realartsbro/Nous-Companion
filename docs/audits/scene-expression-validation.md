# Scene File Expression Validation Audit

**Date:** 2026-04-30  
**Auditor:** Cron Job — Hermes Agent  
**Character:** `nous`  
**Valid Expression Names:** `cheerful`, `normal`, `serious`, `standalones`  
**Source of Truth:** `CutoutCompositor` loads directories matching `_*` under `characters/nous/` and strips the leading underscore via `ExpressionGroup.__init__` (line 97 of `cutout_compositor.py`). `expression_names` returns `list(self.groups.keys())`.

---

## 1. Valid Expression Names for `nous`

| Directory | Expression Name | Files |
|-----------|----------------|-------|
| `_cheerful/` | `cheerful` | `base.png`, 6 eye/mouth sprite variants |
| `_normal/` | `normal` | `sprite-base.png`, `normal_eyes_full/half`, 4 mouth variants |
| `_serious/` | `serious` | `base.png`, `serious_eyes_full/half`, 3 mouth variants |
| `_standalones/` | `standalones` | 11 full-face PNGs: cheeky1, cheeky2, eww, happy, munch1, munch2, surprise, u, u2, wink1, wink2 |

No `interested` sprite exists anywhere — not as an expression group directory, not as a standalone PNG.

---

## 2. Variant-by-Variant Expression Validation

### Variant A: "The Witness" (`variant-a-witness.nous-scene.json`)

| # | Time | Expression | Valid? | Effect if Invalid |
|---|------|-----------|--------|-------------------|
| 1 | 0.0 | `normal` | ✅ | — |
| 2 | 2.5 | `normal` | ✅ | — |
| **3** | **7.0** | **`interested`** | **❌** | Expression silently dropped. `set_expression("interested")` logs `WARNING Unknown expression 'interested'` and **does nothing** — the sprite stays on the previous expression (`normal`). The entire segment intended to show an "interested" expression with `look_track` action plays with a neutral `normal` face. |
| 4 | 20.0 | `cheerful` | ✅ | — |
| 5 | 30.0 | `serious` | ✅ | — |
| 6 | 43.0 | `normal` | ✅ | — |

**Impact:** Cue #3 (t=7.0, the longest silent segment descriptor) will render incorrectly — the companion stays on "normal" instead of shifting to "interested." The scene notes explicitly call for a shift "from normal to interested to smirk across the segment," but neither `interested` exists as an expression group, nor does it exist as a standalone PNG file. The expression change will not occur.

### Variant B: "The Teammate" (`variant-b-teammate.nous-scene.json`)

| # | Time | Expression | Valid? | Notes |
|---|------|-----------|--------|-------|
| 1 | 0.0 | `cheerful` | ✅ | |
| 2 | 3.0 | `normal` | ✅ | |
| 3 | 6.5 | `serious` | ✅ | |
| 4 | 9.0 | `normal` | ✅ | |
| 5 | 16.0 | `normal` | ✅ | |
| 6 | 18.0 | `cheerful` | ✅ | |
| 7 | 22.0 | `serious` | ✅ | |
| 8 | 24.5 | `normal` | ✅ | |
| 9 | 29.0 | `cheerful` | ✅ | |
| 10 | 35.0 | `normal` | ✅ | |
| 11 | 41.0 | `cheerful` | ✅ | |

**Verdict:** ✅ All expressions are valid. No issues.

### Variant C: "The Invitation" (`variant-c-invitation.nous-scene.json`)

| # | Time | Expression | Valid? | Notes |
|---|------|-----------|--------|-------|
| 1 | 0.0 | `normal` | ✅ | |
| 2 | 8.0 | `cheerful` | ✅ | |
| 3 | 22.0 | `cheerful` | ✅ | |
| 4 | 40.0 | `serious` | ✅ | |
| 5 | 49.0 | `normal` | ✅ | |
| 6 | 57.0 | `cheerful` | ✅ | |
| 7 | 62.0 | `cheerful` | ✅ | |

**Verdict:** ✅ All expressions are valid. No issues.

---

## 3. Action Field Analysis

### Source: `scene_player.py` — `_playback_loop()` (line 363)

The `action` field is **extracted** from each scene dict (line 375) and **included as metadata** in the `scene_cue` event broadcast to WebSocket clients (lines 393–403):

```python
action = scene.get("action")
# ...
cue_event = {
    "type": "scene_cue",
    "index": i,
    "time": cue_time,
    "elapsed": round(elapsed, 3),
    "expression": expression,
    "line": line,
    "overlay_text": overlay_text,
    "action": action,       # <— metadata only
}
await self._emit(cue_event)
```

**No server-side execution of any action value exists.** The playback loop handles: expression setting, frame pushing, TTS audio playing, and overlay emission — but never branches on `action`.

### Registered Action Values vs. Implementation Status

| Action Value | Used In Scenes | Scene Player Implements? | Any Renderer Implements? | Status |
|-------------|---------------|------------------------|------------------------|--------|
| `blink` | A(t0,t2.5), B(t0,t6.5,t16,t22,t29) | ❌ No | ❌ No evidence found | **Metadata-only — emitted in `scene_cue` event but no code acts on it** |
| `look_track` | A(t7), B(t3), C(t22) | ❌ No | ❌ No | **Metadata-only** |
| `shrink` | A(t43), B(t35), C(t62) | ❌ No | ❌ No | **Metadata-only** |
| `expression_cycle` | A(t20), B(t18), C(t8) | ❌ No | ❌ No | **Metadata-only** |
| `lean_in` | A(t30), B(t9,t24.5), C(t40) | ❌ No | ❌ No | **Metadata-only** |

**Search results:** A grep for `shrink|lean_in|look_track|expression_cycle` across the entire `src/` directory returned zero matches. These strings exist only in scene JSON files and the `scene_cue` broadcast payload — they are never parsed, dispatched, or acted upon anywhere in the codebase.

**Impact:** All `action` directives are effectively documentation/dead code. The renderers receive the event but would need custom client-side logic to interpret and execute actions like blinking, shrinking, or camera leaning. No such logic exists in the current codebase.

---

## 4. TTS Speed Override Analysis

### Source: `scene_player.py` — `load_scene()` (lines 136–177)

Per-cue `speed` values **ARE actually applied** to TTS synthesis. The mechanism works as follows:

```python
scene_speed = scene.get("speed")
if scene_speed is not None:
    speed_val = float(scene_speed)
    speed_restore = self._server._tts_config.get("speed", 1.0)
    self._server._tts_config["speed"] = speed_val  # Override applied

# TTS synthesized with the overridden speed
b64_wav = await self._server._synthesize_tts(line, expression)

# Speed restored after synthesis
if speed_restore is not None:
    self._server._tts_config["speed"] = speed_restore
```

**Finding:** Speed overrides are applied at **load time** (pre-generation phase), not at playback time. Since all TTS is pre-generated in `load_scene()` before `play_scene()` is called, each cue's `speed` correctly affects the audio WAV that gets generated. After synthesis, the original speed is restored so subsequent cues don't inherit the wrong speed.

**This is correct and functional behavior**, not a warning-only situation. The pre-generated WAV files encode the correct speaking rate.

### Speed Values Used in Scenes

| Variant | Speed Values |
|---------|-------------|
| A (Witness) | 0.85, 0.85, 0.9, 0.9, 0.7 |
| B (Teammate) | 1.1, 1.15, 1.1, 1.05, 1.0, 0.95, 1.0, 1.0, 1.05, 0.85, 0.7 |
| C (Invitation) | 0.9, 0.95, 0.95, 0.85, 0.8, 0.9, 0.9 |

**Edge case:** If `_synthesize_tts()` is asynchronous and the TTS engine does not support mid-stream speed changes, the speed override still works because it's set before the call and restored after. However, if multiple scenes were being pre-generated concurrently (they're not — the loop is sequential), there would be a race condition. The sequential loop is safe.

---

## 5. Recommendations

### 🔴 Must Fix

| Issue | File | Severity | Recommendation |
|-------|------|----------|----------------|
| **Invalid expression `interested`** in Variant A, Cue #3 (t=7.0) | `variant-a-witness.nous-scene.json`, line 27 | **High** — The expression transition silently fails; the companion renders the wrong face for a 13-second segment. | Either: (a) Add `_interested` expression group to `nous` character, or (b) Change the cue's expression to `cheerful` or `normal` (the nearest existing expression). The scene notes say "from normal to interested to smirk" — if there's no `interested` sprite, this may require a new sprite sheet. |

### 🟡 Should Fix

| Issue | File | Severity | Recommendation |
|-------|------|----------|----------------|
| **All `action` values are metadata-only** — `blink`, `look_track`, `shrink`, `expression_cycle`, `lean_in` | `scene_player.py` + all 3 scene files | **Medium** — Scene files reference these actions extensively (13 cues across 3 variants), but nothing executes them. The demo render output will lack all intended visual actions. | Either: (a) Implement action dispatching in `_playback_loop()` (e.g., call `self._server.anim.blink()` for `blink`, send `shrink` command to renderer for `shrink`), or (b) Remove `action` from scene files if these are aspirational/later features, or (c) Document in the scene format spec that `action` is reserved for future renderer-side interpretation. |
| **No `_execute_cue` method exists** despite being referenced in audit instructions | `scene_player.py` | **Low** — Cue execution happens inline in `_playback_loop()`. If the codebase intends a future `_execute_cue` factoring, having it would make action dispatching cleaner. | Refactor cue execution into a dedicated `_execute_cue(scene)` method for testability and action-dispatch centralization. |

### 🟢 Nice to Know

| Issue | File | Severity | Recommendation |
|-------|------|----------|----------------|
| **`standalones` expression group exists but is never used** in any scene file | `nous` character dir | **Low** — The `standalones` group contains 11 expressive full-face sprites (wink, surprise, cheeky, etc.) that could add variety. | Consider using standalone expressions in scenes for specific moments (wink at the "pick a face" line in A:t20, or surprised at the lobster fact in B:t9). |
| **Variant B, Cue #11 (t=41.0) has no `action` field** | `variant-b-teammate.nous-scene.json`, line 100-106 | **Info** — All other cues in B have an action; this one is missing it. Intentional (final hold with brand card) or an oversight. | Verify whether a final `blink` action should be present on the closing cue. |
| **Pre-generation of TTS happens at load time** which means loading a scene takes longer as all audio is generated upfront | `scene_player.py` — `load_scene()` | **Info** — Caching is good for playback performance. Speed overrides work correctly in pre-generation. | Ensure this is documented for future maintainers: speed is load-time only, not real-time adjustable during playback. |
| **`manual_expression_cooldown` is hardcoded to 8.0s** in `_playback_loop()` | `scene_player.py`, line 387 | **Info** | Consider making this configurable or deriving it from scene metadata. |

---

## Summary

| Variant | Expressions Valid | Invalid | Actions Used (all unimplemented) | Speed Overrides |
|---------|-----------------|---------|----------------------------------|----------------|
| A — The Witness | 5 of 6 | **1** (`interested`) | blink, look_track, expression_cycle, lean_in, shrink | ✅ Functional |
| B — The Teammate | 11 of 11 | **0** | blink, look_track, expression_cycle, lean_in, shrink | ✅ Functional |
| C — The Invitation | 7 of 7 | **0** | blink, look_track, expression_cycle, lean_in, shrink | ✅ Functional |

**One concrete bug found** (`interested` is not a valid expression for `nous`).  
**One architectural gap found** (all `action` values are metadata-only — nothing executes them).  
**No TTS speed override issues** (they work correctly via pre-generation at load time).
