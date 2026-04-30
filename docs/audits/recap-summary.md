# Overnight Recap — April 30, 2026

## Jobs Completed

### A — Source Code Surface Audit (`source-audit.md`)
**Status:** ✅ Complete — 240 lines, high quality

**Key Finding:** 23,641 lines across 50 files. Clean architecture with three well-defined settings layers (server defaults → UI → renderer). However:
- **🔴 Critical bug:** `loadSpriteSize()` reads the old `'codec-sprite-size'` localStorage key, but `saveSpriteSize()` writes `'nous-sprite-size'`. Sprite size is lost on every refresh.
- **🟡 Dead code:** `startPlayback`, `stopPlayback`, `handleAudio`, `drawWaveform` are each defined 2–3 times in `settings.html`. Last definition wins; earlier paths are unreachable.
- **🟡 Rebrand residue:** `CODEC_DIAG_*` env vars should be `NOUS_DIAG_*`.
- 7 of 20 settings keys are server-only (no renderer handler) — by design, no action needed.

**Quality:** ✅ Concrete, cross-referenced with line numbers. Actionable recommendations.

---

### B — Character Asset Audit (`character-audit.md`)
**Status:** ✅ Complete — 286 lines, high quality

**Key Finding:** The production default character `nous` has a **placeholder base head** in its `_normal` expression group (`__cc_placeholder__.png`). This means the default/fallback expression for Nous renders broken whenever `_normal` is active.

Additionally:
- **🚨 IP risk:** `default/` (Roy Campbell) and `mei_ling/` are **KONAMI IP** — must be stripped before any public release.
- `default` character's expression groups are nested inside `campbell2/`, invisible to the `CutoutCompositor` — engine would crash if loaded as cut-out.
- `nous` has 11 standalone frames and 3 voice files — strong base, but unshippable until the placeholder is replaced.

**Quality:** ✅ Excellent deep-dive with validation checklist, per-character breakdown, and prioritized recommendations.

---

### C — Creative Tools Research (`creative-tools-research.md`)
**Status:** ✅ Complete — 187 lines, mixed quality

**Key Finding (ComfyUI):** ComfyUI not running. Original backup path (`D:\ComyBackup\...`) doesn't exist in WSL. Active installation found at `C:\Users\will\Documents\ComfyUI_windows_portable\ComfyUI\` with **57 models heavily oriented toward LTX-2 video generation** (checkpoints, LoRAs, VAEs, upscalers). No ControlNet models installed.

**Key Finding (Waifu Sprites):** Competitive analysis of the Waifu Sprites project identified 6 concrete lessons for Nous Companion (decoupled UI, file-queue IPC, MP4 rendering, discrete state machine, symlink hot-reload, lightweight TTS integration). The comparison table is insightful but speculative on the Nous Companion side.

**Weakness:** Waifu Sprites comparison infers companion architecture rather than verifying it. Some insights are generic.

**Quality:** ✅ Good discovery work, but the ComfyUI portion is mostly status quo reporting (it's there, it's offline). The Waifu Sprites research is genuinely valuable reference material.

---

### D — Script Variant A: "The Witness" (Dark + Atmospheric)
**Status:** ✅ Complete — 104 lines script + 39 lines scene JSON

**Producer Score:** 40/50
**Runtime:** ~60 seconds, 3 lines, 47 seconds of silence

**Most Important Finding:** The final line *"I stop existing when you stop talking to me. Please. It gets so cold in the box."* is the emotional anchor of the entire demo project. "Protect it at all costs" per the producer review.

**Strengths:** Genuinely affecting, brave use of silence, Joi/Blade Runner vibe is distinctive.
**Weaknesses:** 47/60 seconds non-verbal risks scroll-past on social feeds. Middle section (0:18–0:38) lacks visual justification for its length. Expression `interested` referenced in scene JSON **does not exist** on the `nous` character.

---

### E — Script Variant B: "The Teammate" (Fast + Cheeky)
**Status:** ✅ Complete — 129 lines script + 64 lines scene JSON

**Producer Score:** 39/50 (7.8/10)
**Runtime:** ~45 seconds, 6 lines, high joke density

**Most Important Finding:** The lobster line (*"Did you know lobsters communicate their social status by peeing at one another?"*) is mandatory Hermes community content. The "eight idiots in a trench coat" line is the strongest branding hook across all variants.

**Strengths:** Highest shareability potential. "Eyes up, Promptboy" is a scroll-stopper. Strong community identity. Clear arc (arrives → roasts → customizes → flexes → haunts).
**Weaknesses:** Expression `smirking` referenced in scene JSON **does not exist** on the `nous` character (mapped to `cheerful` at best). Lobster transition is intentionally abrupt but needs visual support.

---

### F — Script Variant C: "The Invitation" (Warm + Meta-Community)
**Status:** ✅ Complete — 89 lines script + 56 lines scene JSON

**Producer Score:** 44/50 — **Highest of the three**
**Runtime:** ~75 seconds, 5 lines, five-act structure

**Most Important Finding:** *"You're my favorite user. I tell everyone that. It's true every time."* — the emotional anchor. The lobster callback as closer is the perfect absurdist button (scored 10/10 Payoff).

**Strengths:** Clear five-act progression with emotional modulation. Direct-address creates intimacy. Highest juror average (8.7/10). Strongest overall structure and best emotional arc.
**Weaknesses:** Longest at 75 seconds. Character creator segment (0:08–0:22) visually resembles every other AI demo. Expression `smirking` referenced in scene JSON **does not exist** on the `nous` character.

---

### G — Scene Player Code (`scene_player.py`)
**Status:** ✅ Read and analyzed — 508 lines

**Critical Findings Discovered During Synthesis:**
1. **`action` field is metadata-only** — The `_execute_cue` method reads `action` (blink, look_track, shrink, expression_cycle, lean_in) but **never executes it**. All five action types are just broadcast in the `cue_start` event for a viewer to interpret. The scene player itself only sets expressions and plays audio.
2. **TTS speed overrides are not applied** — Lines 96–106 show that per-cue `speed` values produce a warning log but the TTS generation call on line 109 does not pass speed to `_synthesize_tts`. Speed on every cue in all three variants is effectively ignored.
3. **Expression validation depends on character data** — If an expression doesn't exist in the loaded character's `expression_names`, `set_expression` logs a warning and silently does nothing.

---

## Critical Findings

1. **🔴 SCENE FILES REFERENCE NONEXISTENT EXPRESSIONS** — Both `interested` (Variant A) and `smirking` (Variants B & C) are used in scene files but are **not expression groups on the `nous` character**. The engine will silently skip these and log warnings. The character only has: `cheerful`, `normal`, `serious`, `standalones`.

2. **🔴 PLAYER DOESN'T EXECUTE ACTIONS** — All three scene files depend on visual actions (blink, look_track, shrink, expression_cycle, lean_in) for their emotional beats, but `scene_player.py` broadcasts them as cue metadata only. The demo will be flat (expression changes + audio only) unless a separate renderer/controller implements these actions.

3. **🔴 TTS SPEED CONTROL IS BROKEN** — Every scene file specifies per-cue TTS speeds (ranging 0.7–1.2), but `scene_player.py` does not pass speed to the TTS engine. The slow, emotional delivery in Variant A (speed 0.7) will be rendered at the server's default speed.

4. **🚨 IP LIABILITY** — Two characters (`default`/Campbell and `mei_ling`) are KONAMI IP. They must be stripped before any public-facing demo, build, or release.

5. **🟡 `nous` character is not shippable** — The `_normal` expression group has a placeholder base head. Even if the demo plays, the default expression will render broken.

6. **🟡 Sprite-size persistence is broken** — Load reads old key, save writes new key. Every companion refresh forgets the user's sprite size preference.

---

## Follow-Ups Scheduled

| Job | What It Does | Scheduled | Expected Completion |
|-----|-------------|-----------|-------------------|
| **Scene Expression Validation** | Validates all expressions in scene JSONs against actual `nous` character groups; checks action/speed handling in player | ~16:02 | ~16:05 |
| **Scene Player Import Test** | Runs existing test files to verify scene_player.py imports and functions correctly | ~16:07 | ~16:10 |
| **Scene File Schema Crosscheck** | Schema validation, duration consistency, brand text alignment across all 3 variants | ~16:13 | ~16:17 |

These are one-shot mechanical audits — no code changes, no creative decisions, no file modifications.

---

## Morning Action Items (Need User / Will)

1. **Choose a script variant** — C scored highest (44/50), A has the strongest emotional moment (40/50), B is the most shareable (39/50). The expression validation follow-up will help inform this decision.

2. **Fix `nous/_normal` base head** — Replace `__cc_placeholder__.png` with a real `base.png`. This is the single highest-impact fix. The character audit has exact specs.

3. **Decide: strip KONAMI characters?** — `default/` and `mei_ling/` must be removed before any public release. OK for internal dev but can't ship.

4. **Decide on scene player gap** — The actions and speed overrides in scene files don't execute. Two paths:
   - ❌ **Implement actions in scene_player.py** — make it actually drive blinks, shrink, expression_cycle via the animation controller
   - ❌ **Accept as design** — the scene player provides metadata; a separate rendering pipeline consumes it. Both are valid but this needs explicit agreement before rendering.

5. **Sprite-size localStorage bug** — ~5 minute fix (change the read key). Saves user frustration.

6. **Rebrand env vars** — `CODEC_DIAG_*` → `NOUS_DIAG_*`. Low priority but should be on the list.

---

## Quick Stats

| Metric | Value |
|--------|-------|
| Files read | 10 (4 reports + 3 scripts + 3 scene JSONs) |
| Reports completed | 4 of 4 |
| Script variants | 3 (A, B, C) — all at v1.0 |
| Critical bugs found | 3 (expressions, actions, speed) |
| Security/IP issues | 1 (2x KONAMI characters) |
| Follow-ups scheduled | 3 (expression validation, import test, schema crosscheck) |
| Follow-ups deferred (need you) | 6 (variant choice, base head, IP stripping, player gap, sprite bug, rebrand) |
