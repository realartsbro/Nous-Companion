# Scene File Schema & Duration Crosscheck Audit

**Date:** 2026-04-30
**Scope:** All three `.nous-scene.json` demo variants + `scene_player.py` capabilities
**Player source:** `src/server/scene_player.py`

---

## 1. Per-Variant Schema Validation

### Variant A — "The Witness" (`variant-a-witness.nous-scene.json`)

| Check | Result |
|-------|--------|
| Valid JSON | ✅ |
| Meta fields present (`title`, `character`, `duration_seconds`, `version`) | ✅ |
| Required fields per scene (`time`, `expression`, `line`) | ✅ All 6 scenes |
| Times monotonically increasing | ✅ 0.0, 2.5, 7.0, 20.0, 30.0, 43.0 |
| Duplicate times | ✅ None |
| Speed values in range 0.5–2.0 | ✅ [0.7, 0.85, 0.9] |
| Character = `nous` only | ✅ |

**⚠ Issues found:**

1. **Scene 0 (t=0.0) is structurally incomplete:**
   - Missing `speed` field entirely (other scenes have it)
   - Missing `overlay_text` field entirely (other scenes have it as `null` or a string)
   - Has only: `time`, `expression`, `line`, `action`, `notes` — only 5 of 7 expected fields

2. **Audio overlap (scene 1 → scene 2):**
   - Scene 1 (t=2.5): "So this is where you work…" (56 chars, speed 0.85) → est. audio ~5.3s, ends ~7.8s
   - Next cue at 7.0s — audio will still be playing when next cue fires (~0.8s overlap)

3. **Audio overlap (scene 4 → scene 5):**
   - Scene 4 (t=30.0): "Chainsaws were invented…" (152 chars, speed 0.9) → est. audio ~13.5s, ends ~43.5s
   - Next cue at 43.0s — ripple overlap (~0.5s)

### Variant B — "The Teammate" (`variant-b-teammate.nous-scene.json`)

| Check | Result |
|-------|--------|
| Valid JSON | ✅ |
| Meta fields present | ✅ |
| Required fields per scene | ✅ All 11 scenes |
| Times monotonically increasing | ✅ 0.0, 3.0, 6.5, 9.0, 16.0, 18.0, 22.0, 24.5, 29.0, 35.0, 41.0 |
| Duplicate times | ✅ None |
| Speed values in range 0.5–2.0 | ✅ [0.7, 0.85, 0.95, 1.0, 1.05, 1.1, 1.15] |
| Character = `nous` only | ✅ |

**⚠ Issues found:**

1. **Scene 10 (t=41.0) is missing `action` field:**
   - This is the final brand-card scene with line "I'm in."
   - All other 10 scenes have `action` — this one lacks it entirely
   - Consequence: no action event fires during the final beat
   - The scene_player reads `action` via `.get("action")` so this won't crash, but the `scene_cue` WebSocket payload will have `"action": null`

2. **Pervasive audio overlaps (9 of 10 inter-cue gaps):**
   - Every single gap between cues is shorter than the estimated TTS audio duration of the preceding scene:
     - Scene 1 (t=3.0, ~9.3s audio) → next at 6.5s, overlap ~2.8s
     - Scene 2 (t=6.5, ~10.1s audio) → next at 9.0s, overlap ~1.1s
     - Scene 3 (t=9.0, ~19.7s audio) → next at 16.0s, overlap ~3.7s
     - Scene 4 (t=16.0, ~18.6s audio) → next at 18.0s, overlap ~0.6s
     - Scene 5 (t=18.0, ~24.1s audio) → next at 22.0s, overlap ~2.1s
     - Scene 6 (t=22.0, ~25.4s audio) → next at 24.5s, overlap ~0.9s
     - Scene 7 (t=24.5, ~31.1s audio) → next at 29.0s, overlap ~2.1s
     - Scene 8 (t=29.0, ~37.8s audio) → next at 35.0s, overlap ~2.8s
     - Scene 9 (t=35.0, ~41.5s audio) → next at 41.0s, overlap ~0.5s
   - **This is a structural feature, not necessarily a bug** — the scene_player's `_play_audio_block` waits for the full duration before advancing to the next cue. The cascade means every cue after the first will fire late, and the final cue will drift by several seconds.
   - Variant B is the most severely affected due to its rapid-fire pacing and dense dialog.

### Variant C — "The Invitation" (`variant-c-invitation.nous-scene.json`)

| Check | Result |
|-------|--------|
| Valid JSON | ✅ |
| Meta fields present | ✅ |
| Required fields per scene | ✅ All 7 scenes |
| Times monotonically increasing | ✅ 0.0, 8.0, 22.0, 40.0, 49.0, 57.0, 62.0 |
| Duplicate times | ✅ None |
| Speed values in range 0.5–2.0 | ✅ [0.8, 0.85, 0.9, 0.95] |
| Character = `nous` only | ✅ |

**⚠ Issues found:**

1. **No schema issues** — all optional fields present on all scenes. ✅

2. **Duration budget may be tight:**
   - Last cue at 62.0s, line = 175 chars at speed 0.9 → est. audio ~15.6s → end ~77.6s
   - Declared `duration_seconds`: 75
   - This is ~2.6s over budget using the 0.08 s/chr heuristic; actual TTS timing may vary

3. **Audio overlaps (2 of 6 gaps):**
   - Scene 2 (t=22.0, ~41.3s audio) → next at 40.0s, overlap ~1.3s
   - Scene 3 (t=40.0, ~49.5s audio) → next at 49.0s, overlap ~0.5s

---

## 2. Duration Consistency Analysis

| Variant | Declared | Last Cue | Last Line Chars | Last Speed | Est. Audio End | Assessment |
|---------|----------|----------|----------------|------------|----------------|------------|
| A | 60s | 43.0s | 105 | 0.7 | ~55.0s | ✅ Comfortably within budget (~5s buffer) |
| B | 45s | 41.0s | 7 | 0.7 | ~41.8s | ✅ Well within budget (~3s buffer) |
| C | 75s | 62.0s | 175 | 0.9 | ~77.6s | ⚠ **~2.6s over budget** (heuristic estimate) |

**⚠ Cascade delay effect:** Due to the audio-blocking playback model (`_play_audio_block` waits for full TTS duration before advancing), every overlap cascades into later cues. In practice:

- **Variant B** will be most affected: the rapid-fire cues mean the final cue at 41.0s may actually fire at ~45–48s real time, making the actual performance 3–7s longer than declared.
- **Variant A** and **C** have fewer overlaps, so drift should be under 2s.

**Recommendation:** The `meta.duration_seconds` value in each file should be updated to reflect realistic total duration including the cascade effect, OR the scene player should pre-compute expected total duration from TTS audio lengths and cache it in the meta.

---

## 3. Brand Text Inconsistency (⚠ High Severity)

Three different brand overlay texts for what should be the same closing brand card:

| Variant | Actual Overlay Text | Arch Doc Text |
|---------|-------------------|---------------|
| A | `NOUS COMPANION — MIT · OPEN SOURCE · POWERED BY HERMES AGENT` | `NOUS COMPANION / MIT · OPEN SOURCE · HERMES AGENT` |
| B | `NOUS COMPANION — HERMES AGENT · MIT` | `NOUS COMPANION / HERMES AGENT · MIT` |
| C | `NOUS COMPANION · HERMES AGENT · MIT OPEN SOURCE` | `NOUS COMPANION / MIT · GITHUB` |

**Key problems:**

1. **Three different texts across three variants** — no unified brand closing. A viewer watching all three demos would see a different brand message each time.
2. **Vendor/org ordering differs:**
   - A: `MIT · OPEN SOURCE · POWERED BY HERMES AGENT`
   - B: `HERMES AGENT · MIT`
   - C: `HERMES AGENT · MIT OPEN SOURCE`
3. **Variant C arch doc vs. actual mismatch:** Architecture doc says `MIT · GITHUB` but actual JSON says `HERMES AGENT · MIT OPEN SOURCE`. These communicate entirely different messages (GitHub-as-CTA vs. Hermes Agent branding).
4. **Punctuation inconsistent:** em-dashes (`—`) vs. middle-dots (`·`) vs. spaces — three different separator styles.

**Recommendation:** Standardize on a single brand closing string. Suggested candidate: `"NOUS COMPANION · MIT · OPEN SOURCE · POWERED BY HERMES AGENT"` (combines all desired elements in a consistent order). Update all three scene files and the architecture doc.

---

## 4. Schema & Structural Differences Between Variants

| Dimension | A | B | C |
|-----------|---|---|---|
| Version | 1.1 | **2.0** | 1.1 |
| Scene count | 6 (lowest) | **11 (highest)** | 7 |
| Speed range | 0.7–0.9 (slower) | **0.7–1.15 (widest)** | 0.8–0.95 |
| Missing optional fields | Scene 0 missing speed + overlay_text | Scene 10 missing action | ✅ All complete |
| Line diversity | 1 silent, 5 spoken | All 11 spoken | All 7 spoken |
| `overlay_text: null` style | Mixed (some missing key, some explicit null) | ✅ Consistent (all have key, null or string) | ✅ Consistent |

**Key structural observations:**

- **Variant B is at version 2.0** while A and C are at 1.1, suggesting B received a revision that A/C may not have. This is consistent with B having the most cues, the widest speed range, and the most refined optional-field completeness.
- **Variant A's scene 0** is the only silent opening cue and is missing both `speed` (acceptable, since no TTS) and `overlay_text` (acceptable, since no overlay) — but it's inconsistent with the other files and with A's own later scenes which explicitly set these to `null`.
- **All three variants use the same set of action values**: `blink`, `expression_cycle`, `lean_in`, `look_track`, `shrink`. Good consistency.
- **No scene file references characters other than `nous`** — all meta blocks have `"character": "nous"` and no per-scene character field exists. ✅

---

## 5. Architecture Document Discrepancies

The `/docs/3-variant-script-architecture.md` contains dialog and segment mapping that differs significantly from the actual JSON files.

| Variant | Arch Doc Line vs. JSON Actual |
|---------|-------------------------------|
| A seg 2 | Arch: *"Ever wonder who's watching you back?"* → JSON: *"I'm not a stalker — I'm an observer."* |
| A seg 3 | Arch: *"I can wear any face… Serious. Cheerful. Stare into your soul."* → JSON: *"Pick a face. I don't need attention — I just prefer it."* |
| B seg 3 | Arch: *"Pick my face. My voice. My existential dread…"* → JSON: *"I can wear any face you give me. Serious. Cheerful. Stare-into-your-soul."* (plus extra bridge scenes not in arch doc) |
| C seg 3 | Arch: *"Someone made me this. You can too…"* → JSON: extensively reworked with community framing |
| C seg 5 | Arch overlay: `MIT · GITHUB` → JSON overlay: `HERMES AGENT · MIT OPEN SOURCE` |

These are essentially different drafts. The architecture doc reads like an earlier pass that was refined during implementation. If the architecture doc is meant to be the source of truth for the JSON files, it needs updating.

---

## 6. Recommendations by Severity

### 🔴 High
1. **Standardize brand closing text** across all three variants. Current three-way inconsistency dilutes brand identity. Pick one canonical text and update all files + architecture doc.
2. **Update architecture doc** (`3-variant-script-architecture.md`) to match the actual JSON content, or tag it as an "initial draft" with a note that the JSON files are the current versions.

### 🟡 Medium
3. **Add missing `action` field** to Variant B scene 10 (t=41.0) for consistency. Suggested value: `"blink"` or `"shrink"` based on context.
4. **Add missing optional fields** to Variant A scene 0 (t=0.0) — explicitly set `"speed": 0.85` (default match) and `"overlay_text": null` to match the pattern used by other scenes.
5. **Review `duration_seconds`** for Variant C: estimated actual runtime ~77.6s, declared 75s. Bump to 80s or 85s to provide realistic headroom given the dense final scene.
6. **Review cascade delay** for Variant B: the dense overlap pattern means all 10 gaps have audio-overlapping-next-cue issues. If precise cue timing matters, either increase gaps or switch to pre-computed TTS durations mapped to cue times (alternative: the scene player fires overlay/cue events immediately and doesn't wait for audio to finish — file as feature request).

### 🟢 Low
7. **Version alignment**: Variant B is at 2.0 while A and C are at 1.1. Bump A/C to match or document that version numbers are independent per variant.
8. **Consider adding `notes` to the required fields schema** or removing it from all scenes — currently every scene has it but the player never reads it. It's valuable documentation but should be a documented convention.
9. **Consider adding a `duration_seconds` precompute step** to the scene player so it emits actual expected duration (from TTS audio lengths) rather than relying on a manually-entered meta value.
