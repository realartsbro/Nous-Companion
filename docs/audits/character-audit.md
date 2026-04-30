# Nous Companion — Character Asset Audit
**Date:** 2025-04-30
**Auditor:** Hermes Agent (cron job)
**Scope:** All character directories under `characters/` and `characters-private/`

---

## 1. Executive Summary

| Character | Real Name | Location | Status | IP Risk | Critical Issues |
|-----------|-----------|----------|--------|---------|-----------------|
| `nous` | Nous | `characters/nous/` | **✅ READY** | ✅ Original (Nous Research) | None |
| `campbell` | Roy Campbell | `characters-private/default/campbell/` | **LEGACY / BROKEN** | 🚨 KONAMI — MUST NOT SHIP | Flat old-format sprites; no separated eye/mouth layers |
| `campbell2` | Roy Campbell | `characters-private/default/campbell2/` | **FUNCTIONAL** | 🚨 KONAMI — MUST NOT SHIP | No config.yaml; relies on parent `default/config.yaml` |
| `mei_ling` | Mei Ling | `characters-private/mei_ling/` | **FUNCTIONAL** | 🚨 KONAMI — MUST NOT SHIP | None critical |

**Key Finding:** The production default character (`nous`) is COMPLETE and READY TO SHIP. All sprites are valid, voice files exist, personality fits the brand. The two KONAMI IP characters (`campbell`, `mei_ling`) live in `characters-private/` and are already excluded from the public build. This is the correct arrangement — they will not ship unless explicitly moved to `characters/`.

---

## 2. Character Directory Inventory

### Public (`characters/`) — Ships with the product
```
characters/
└── nous/          ← Nous (intended default, original IP)
```

### Private (`characters-private/`) — Development/archive only
```
characters-private/
├── default/
│   ├── campbell/     ← Campbell flat sprites (old format)
│   ├── campbell2/    ← Campbell expression-group sprites (new format)
│   ├── base_heads/   ← Old-style flat head assets
│   ├── eyes/         ← Old-style eye sprites
│   ├── mouths/       ← Old-style mouth sprites
│   ├── expressions/  ← Old-style pre-composited expressions
│   ├── config.yaml   ← Shared config for Campbell
│   ├── personality.md
│   └── positions.json
└── mei_ling/
    ├── config.yaml
    ├── personality.md
    ├── mei_ling.wav
    ├── _normal/
    ├── _serious/
    ├── _smiling/
    └── _standalones/
```

---

## 3. Per-Character Deep Dive

### 3.1 `nous` — Nous (Intended Default) ✅

**Location:** `characters/nous/`

**Config (`config.yaml`)**
- `name`: Nous
- `description`: *(empty string)*
- `voice.engine`: omnivoice
- `voice.reference_audio`: `nous_normal.wav`
- `expression_voices`: cheerful → `voice_cheerful.wav`, serious → `voice_serious.wav`
- `animation`: `speaking_cycle: [speaking]`, `flap_interval_ms: 180`, `mouth_open_threshold: 0.35`, `mouth_close_threshold: 0.18`
- `display_mode`: `cover`
- `sprite_order`: Fully defined for all 3 expression groups (base, eyes list, mouths list)
- `idle_rarity`: `_cheerful: 5`, `_normal: 5`, `_serious: 5`; `_standalones: 11 entries × 1`
- `speech_allowed`: `_cheerful: true`, `_normal: true`, `_serious: true`, `_standalones: false`
- `offsets`: All `[0, 0]` — works because all sprites share same full-canvas dimensions (342×512) and are pre-aligned
- **YAML validity:** ✅ Valid, well-formed

**Personality (`personality.md`)**
- **Tone:** Kawaii-cheeky, hyper-competent, affectionately teasing, playfully arrogant
- **Character brief:** Digital companion "Nous" who lives in the user's systems. Speaks in first person, uses nicknames (boss/chief/darling), celebrates wins, mocks typos. Delivers punchy 15-25 word responses in JSON.
- **Available expressions:** normal, serious, cheerful
- **Fit for brand:** ✅ Strong match — explicitly built as the "kawaii Nous girl" companion

**Supporting text files:**
- `idle_lines.txt`: 138 lines — excellent variety of idle banter, memes, and historical trivia quips ✅
- `brief_quips.txt`: 37 lines — quick completion acknowledgments ✅
- `prompt_acks.txt`: 28 lines — thoughtful prompt receipt acknowledgments ✅

**Voice Files**
| File | Size | Purpose |
|------|------|---------|
| `nous_normal.wav` | 433 KB | Default voice reference |
| `voice_cheerful.wav` | 393 KB | Cheerful expression voice reference |
| `voice_serious.wav` | 436 KB | Serious expression voice reference |
| **Total** | **3 files** | ✅ All present, all above 300 KB (good quality) |

**Expression Groups**

| Group | Sprites | Base | Eyes | Mouths | Notes |
|-------|---------|------|------|--------|-------|
| `_normal` | 7 | `sprite-base.png` (342×512, 214 KB) | 2 (`normal_eyes_full.png`, `normal_eyes_half.png`) | 4 (`normal_mouth_1.png` .. `normal_mouth_4.png`) | ✅ Fully functional |
| `_cheerful` | 7 | `base.png` (342×512, 205 KB) | 3 (`cheerful_eyes_closed1-3.png`) | 3 (`cheerful_mouth_open1-3.png`) | ✅ Fully functional |
| `_serious` | 6 | `base.png` (342×512, 208 KB) | 2 (`serious_eyes_full.png`, `serious_eyes_half.png`) | 3 (`serious_mouth_1-3.png`) | ✅ Fully functional |
| `_standalones` | 11 | `cheeky1.png`, `cheeky2.png`, `eww.png`, `happy.png`, `munch1.png`, `munch2.png`, `surprise.png`, `u.png`, `u2.png`, `wink1.png`, `wink2.png` | — | — | ✅ All full-frame sprites |

**`_standalones` count:** 11 frames ✅

**Critical Validation:**
- All sprites are 342×512 RGBA PNGs (will be downscaled to ≈133×200 by the compositor's `MAX_SPRITE_DIMENSION=200`)
- No zero-byte files ✅
- `sprite-base.png` in `_normal` is a REAL asset (219 KB), **not a placeholder** ✅
- Every expression group has a base head + eyes + mouths ✅
- Config references (sprite filenames) all match actual files on disk ✅
- `idle_lines.txt` uses Windows line endings (`\r\n`) — functionally fine but worth normalizing for cross-platform consistency ⚠️

---

### 3.2 `campbell` / `campbell2` — Roy Campbell 🚨 KONAMI IP

**Location:** `characters-private/default/` (config at `default/config.yaml`)

**Config (`config.yaml`)**
- `name`: "Roy Campbell"
- `description`: "Former FOXHOUND commanding officer. Tactical advisor via Codec frequency."
- `voice.engine`: omnivoice
- `voice.reference_audio`: `campbell2/vc115902.wav`
- `animation`: `speaking_cycle: [speaking]`, `flap_interval_ms: 180`
- **Missing fields:** `idle_rarity`, `sprite_order`, `display_mode`, `offsets`, `speech_allowed`, `mouth_open_threshold`, `mouth_close_threshold`
- **YAML validity:** ✅ Valid but minimal

**Personality (`personality.md`)**
- **Tone:** Melodramatically serious, authoritative, military briefing style
- **Character brief:** Colonel Campbell from Metal Gear Solid. Issues tactical commentary over a "Codec" cadence. Military jargon for everything.
- **Available expressions:** normal, serious, serious_shouting, smiling, looking_down
- **Fit for brand:** ❌ KONAMI IP — not for public release

**Voice Files**
- `default/campbell2/vc115902.wav`: 1.6 MB ✅ (good quality clip)
- `default/campbell2/audio_test.wav`: 197 KB (likely a test file)

**`positions.json`:** Present at `default/positions.json` with offsets for "neutral", "thinking", "surprised" — but this is a **legacy format** not used by the current `CutoutCompositor` (which reads offsets from `config.yaml`).

#### Campbell (Old Format — LEGACY)
**Location:** `default/campbell/`

23 flat PNG sprites, all 52×89 px. These are **pre-composited** frames (not layered eye/mouth overlays). Each sprite is a complete character pose:
- Normal variants (full, half-closed, closed eyes)
- Serious variants (normal, half-squinched, fully squinched eyes)
- Mouth variants (fully open, half open)
- Looking down animation frames
- Smiling variants

This format is **NOT compatible** with `CutoutCompositor` — there are no `_expression` group directories and no separated eye/mouth layers.

#### Campbell2 (New Format — FUNCTIONAL but headless)
**Location:** `default/campbell2/`

5 expression groups + 1 standalones group with separated eye/mouth layers:

| Group | Sprites | Base (52×89) | Eyes | Mouths | Notes |
|-------|---------|------|------|--------|-------|
| `_normal` | 5 | `sprite-1-4.png` (8.5 KB) | 2 (`sprite-1-5`, `sprite-1-6`: 44×11) | 2 (`sprite-1-7`, `sprite-1-8`: 34×34) | ✅ Works with auto-classification |
| `_serious` | 5 | `sprite-10-2.png` (8.5 KB) | 2 (`sprite-10-3`, `sprite-10-4`: 44×11) | 2 (`sprite-10-5`, `sprite-10-6`: 34×34) | ✅ Works |
| `_serious_shouting` | 5 | `sprite-13-2.png` (8.5 KB) | 2 (`sprite-13-3`, `sprite-13-4`: 44×11) | 2 (`sprite-13-5`, `sprite-13-6`: 42×34) | ✅ Works |
| `_smiling` | 5 | `sprite-3-7.png` (8.5 KB) | 2 (`sprite-3-8`, `sprite-3-9`: 44×11) | 2 (`sprite-3-10`, `sprite-3-11`: 34×34) | ✅ Works |
| `_looking_down` | 5 | `sprite-15-1.png` (8.5 KB) | 2 (`sprite-17-2`, `sprite-17-3`: 48×15) | 2 (`sprite-18-1`, `sprite-18-2`: 34×30) | ✅ Works |
| `_standalones` | 3 | `concerned.png`, `serious_nod.png`, `thinking.png` (all 52×89) | — | — | ✅ 3 frames |

**Key issue:** `campbell2/` has **no `config.yaml`** of its own. It relies on the parent `default/config.yaml` for its config. The `CutoutCompositor` expects config to be at the character's root directory. Since `default/` uses the old flat sprite format, loading `default/` directly would fail (old `base_heads/` + `eyes/` + `mouths/` cannot be interpreted by `CutoutCompositor`). Loading `default/campbell2/` would work **if** it had its own `config.yaml`.

**`_standalones` count:** 3 frames

---

### 3.3 `mei_ling` — Mei Ling 🚨 KONAMI IP

**Location:** `characters-private/mei_ling/`

**Config (`config.yaml`)**
- `name`: "Mei Ling"
- `description`: "Codec frequency operator. Provides mission intel and saves your progress."
- `voice.engine`: omnivoice
- `voice.reference_audio`: `mei_ling.wav`
- `animation`: `speaking_cycle: [speaking]`, `flap_interval_ms: 180`, `mouth_open_threshold: 0.40`, `mouth_close_threshold: 0.22`
- `offsets`: Defined for `_normal`, `_serious`, `_smiling` — eyes `[4, 33]`, mouth `[14, 51]`
- **Missing fields:** `idle_rarity`, `sprite_order`, `display_mode`, `speech_allowed`
- **YAML validity:** ✅ Valid

**Personality (`personality.md`)**
- **Tone:** Sweet, cheerful, encouraging, proudly nerdy, philosophical
- **Character brief:** Mei Ling from Metal Gear Solid. MIT graduate, tech prodigy. Quotes Chinese proverbs, worries about the user working too hard.
- **Available expressions:** normal, serious, smiling
- **Fit for brand:** ❌ KONAMI IP — not for public release

**Voice Files**
| File | Size |
|------|------|
| `mei_ling.wav` | 429 KB ✅ |

**Expression Groups**

| Group | Sprites | Base (52×89) | Eyes | Mouths | Notes |
|-------|---------|------|------|--------|-------|
| `_normal` | 5 | `sprite-3-12.png` (9.0 KB) | 2 (`sprite-3-13`, `sprite-3-14`: 44×14) | 2 (`sprite-4-5`, `sprite-4-6`: 24×14) | ✅ Works with auto-classification |
| `_serious` | 5 | `sprite-12-10.png` (9.0 KB) | 2 (`sprite-12-11`, `sprite-12-12`: 44×14) | 2 (`sprite-13-3`, `sprite-13-4`: 22×15) | ✅ Works |
| `_smiling` | 5 | `sprite-9-5.png` (9.1 KB) | 2 (`sprite-9-6`, `sprite-9-7`: 44×14) | 2 (`sprite-10-3`, `sprite-10-4`: 24×14) | ✅ Works |
| `_standalones` | 3 | `concerned.png`, `tongue.png`, `wink.png` (all 52×89) | — | — | ✅ 3 frames |

**`_standalones` count:** 3 frames

**Validation:**
- All expression groups have base + eyes + mouth ✅
- Config has offset info ✅ (no `positions.json` needed — offsets are in config.yaml)
- No `idle_lines.txt`, `brief_quips.txt`, or `prompt_acks.txt` — would use hardcoded defaults from `CharacterManager` ⚠️

---

## 4. Copyright / IP Flags

| Character | IP Owner | Source Material | Flag | Location | Action Required |
|-----------|----------|----------------|------|----------|-----------------|
| Roy Campbell (`campbell`/`campbell2`) | KONAMI | Metal Gear Solid | 🚨 **MUST NOT SHIP** | `characters-private/default/` | ✅ Already isolated — purge before any public build |
| Mei Ling (`mei_ling`) | KONAMI | Metal Gear Solid | 🚨 **MUST NOT SHIP** | `characters-private/mei_ling/` | ✅ Already isolated — purge before any public build |
| Nous (`nous`) | Nous Research | Original | ✅ **Safe to ship** | `characters/nous/` | No action needed |

The KONAMI characters are already stored in `characters-private/`, which is **not loaded** by `CharacterManager` (it scans `characters/` only). This is the correct security boundary. When preparing a release build:
1. Delete `characters-private/` entirely
2. Verify no references to "campbell", "mei_ling", "metal gear", "FOXHOUND", or "codec" remain in `characters/` or scene files

---

## 5. Validation Checklist

### 5.1 At least one expression group with base head + eyes + mouth

| Character | Pass? | Details |
|-----------|-------|---------|
| `nous` | ✅ **PASS** | 3 functional groups (`_normal`, `_cheerful`, `_serious`) each with base + eyes + mouths |
| `campbell` (old) | ❌ **FAIL** | No expression group structure; flat pre-composited sprites only |
| `campbell2` | ✅ **PASS** | 5 groups with proper base + eyes + mouth layers |
| `mei_ling` | ✅ **PASS** | 3 groups with proper base + eyes + mouth layers |

### 5.2 Valid YAML in `config.yaml`

| Character | Pass? | Details |
|-----------|-------|---------|
| `nous` | ✅ **PASS** | Full config with all fields |
| `default` (Campbell) | ✅ **PASS** | Minimal but valid |
| `mei_ling` | ✅ **PASS** | Valid with offset info |

### 5.3 `personality.md` exists

| Character | Pass? | Details |
|-----------|-------|---------|
| `nous` | ✅ **PASS** | Full personality profile (32 lines) |
| `default` (Campbell) | ✅ **PASS** | Full personality profile (58 lines) |
| `mei_ling` | ✅ **PASS** | Full personality profile (36 lines) |

### 5.4 Voice files present

| Character | Pass? | Voice Files |
|-----------|-------|-------------|
| `nous` | ✅ **PASS** | 3 files (normal, cheerful, serious) |
| `default` (Campbell) | ✅ **PASS** | 2 files (vc115902.wav, audio_test.wav) |
| `mei_ling` | ✅ **PASS** | 1 file (mei_ling.wav) |

### 5.5 `positions.json` or config offset info

| Character | Pass? | Details |
|-----------|-------|---------|
| `nous` | ✅ **PASS** | Offsets in `config.yaml` (all `[0,0]` — works due to full-canvas sprites) |
| `default` (Campbell) | ✅ **PASS** | `positions.json` present (legacy format); no offsets in config.yaml |
| `mei_ling` | ✅ **PASS** | Offsets in `config.yaml` for all 3 groups |

---

## 6. Broken Characters & Asset Issues

### 🔴 Critical — None

No critical issues found in the public `characters/` directory. The `nous` character is fully functional.

### 🟡 Moderate

1. **`campbell` old-format sprites are incompatible with `CutoutCompositor`**
   - `default/campbell/` contains flat pre-composited 52×89 PNGs
   - `CutoutCompositor` requires `_expression` group directories with separated base/eyes/mouth layers
   - Impact: Cannot load Campbell from old format
   - Status: ✅ Already handled — `campbell` is in `characters-private/` and the new-format `campbell2` exists alongside it

2. **`campbell2` lacks its own `config.yaml`**
   - Config lives at `default/config.yaml` with `voice.reference_audio: campbell2/vc115902.wav`
   - If `campbell2/` is loaded as a standalone character, it has no config
   - Impact: Would use defaults for everything (no voice reference, no character name)
   - Status: Mitigated because Campbell is KONAMI IP and won't ship

3. **`nous` all sprites are full-canvas (342×512) transparent PNGs**
   - The compositor downscales uniformly by `200/512 ≈ 0.39×` to ~133×200
   - Impact: File sizes are larger than necessary. 11 standalone PNGs × 342×512 = ~2.2 MB for standalones alone
   - Suggestion: Pre-crop to content bounding boxes and update offsets to save ~60% file size

4. **`nous` offsets are all `[0, 0]`**
   - Works because all sprites are same full-canvas size and pre-aligned
   - Fragile — any change to sprite dimensions will break alignment
   - Suggestion: Use actual eye/mouth offset coordinates for robustness

### 🟢 Minor / Observations

5. **`nous/_standalones` auto-classification:** The `ExpressionGroup` engine classifies non-base sprites as eyes or mouths based on size heuristics. For standalones, `is_standalone=True` bypasses this at render time — no functional impact, but the log messages may be confusing.

6. **`mei_ling` and `campbell2` have no `idle_lines.txt`, `brief_quips.txt`, or `prompt_acks.txt`** — they rely on hardcoded defaults from `CharacterManager`. Functional, but less character-specific.

7. **`mei_ling` uses `sprite-` prefix naming scheme** while `nous` uses descriptive names (`normal_eyes_full.png`, etc.). The engine works with both, but descriptive names make manual troubleshooting easier.

8. **`nous/idle_lines.txt` uses Windows line endings (`\r\n`)** — the `Character.__init__` method splits by `\n` only, which leaves trailing `\r` on each line. The `.strip()` call handles this, but it's worth normalizing for cross-platform consistency.

---

## 7. Default Character `nous` Readiness Check

| Criterion | Status | Notes |
|-----------|--------|-------|
| Complete expression set | ✅ **READY** | 3 expressions (`_normal`, `_cheerful`, `_serious`) + 11 standalones |
| Base head present in all groups | ✅ **READY** | `sprite-base.png` (real asset, 219 KB) in `_normal`, `base.png` in `_cheerful` and `_serious` |
| Voice files | ✅ **READY** | 3 files covering normal, cheerful, serious |
| Personality fits "kawaii Nous girl" brand | ✅ **READY** | Explicitly designed as cheeky, teasing digital companion |
| Valid YAML config | ✅ **READY** | All fields present: sprite_order, idle_rarity, display_mode, speech_allowed, offsets |
| Prompt acks | ✅ **READY** | 28 personalized prompt acknowledgment lines |
| Idle lines | ✅ **READY** | 138 idle lines with memes, trivia, and banter |
| Brief quips | ✅ **READY** | 37 completion acknowledgments |
| No zero-byte sprites | ✅ **PASS** | All files have valid content |
| No empty expression groups | ✅ **PASS** | Every group contains sprites |
| Config references match actual files | ✅ **PASS** | Every filename in `sprite_order` exists on disk |
| Windows line endings in idle_lines.txt | ⚠️ **Minor** | `\r\n` instead of `\n` — `.strip()` handles it, but should be normalized |

**Verdict: `nous` IS READY TO SHIP.** No critical blockers. The previous audit flagged `__cc_placeholder__.png` as the base head — that file no longer exists. It has been replaced with a real `sprite-base.png` asset.

---

## 8. What Happens When `characters/` Is Empty?

**Analysis of `CharacterManager._load_all()` and `CompanionServer.__init__()`:**

1. If `characters/` does not exist: `CharacterManager.active_id` is set to `""` (empty string)
2. If `characters/` exists but has no valid character directories: `self.characters` will be an empty dict, `self.active_id` will remain as `"default"` (the initial value in `__init__`)
3. `CompanionServer.__init__` then calls `_infer_initial_character_id()` which checks if the requested character exists in `self.char_manager.characters`. If not, it returns `self.char_manager.active_id` — which is `"default"` (an empty string if dir doesn't exist)
4. After `__init__`, `self.char_manager.active` would be `None` if no characters loaded
5. `self.compositor` would be `None`, causing errors when `AnimationController` tries to composite frames
6. `self._brain_prompt` falls back to `self._load_personality(character_dir)` — loads from the path passed as `--character-dir`

**Fallback behavior on first launch with empty `characters/`:**
- The server starts but has no compositor → animation cannot render
- TTS may still work (falls back to edge-tts)
- LLM quips may still generate text responses
- The WebSocket server accepts connections but cannot serve frames
- Renderer clients would show an empty/black window or error state

**Mitigation factors:**
- The default `--character-dir` argument points to `characters/nous/` specifically, not the whole `characters/` directory
- If `characters/nous/` exists but `characters/` is empty, `CompanionServer` still loads Nous correctly because it receives the full path
- The `CharacterManager` scans `characters/` root (parent of the character dir) — so even if only `nous/` exists, it will find and load it

**Bottom line:** On first launch with the default config, if `characters/nous/` exists (which it always should, as it ships with the product), the server works fine. If someone manually deletes ALL characters, the server degrades gracefully (no animation, but doesn't crash).

---

## 9. Recommendations

### Immediate (Pre-Launch)
1. **None required** — `nous` is ready to ship. No critical issues.

### Before Public Release
2. **Purge `characters-private/` from any build artifacts**
   - Delete `characters-private/` to eliminate any risk of KONAMI IP leaking
   - Audit scene files, docs, and test scripts for Campbell/Mei Ling references

### Quality-of-Life Improvements
3. **Normalize line endings in `nous/idle_lines.txt`**
   - Convert `\r\n` → `\n` for cross-platform consistency

4. **Crop Nous sprites to content bounding boxes**
   - Currently 342×512 full-canvas with large transparent areas
   - Cropping to ~200×267 (or similar) would reduce file sizes by ~60%
   - Update `offsets` in `config.yaml` to match new coordinates

5. **Add `sprite_order` for standalones** (optional)
   - Currently standalones are ordered alphabetically by filename
   - Explicit ordering would make the idle rotation predictable

---

## Appendix A: Sprite Dimensional Summary

### Nous (`characters/nous/`)
All sprites: **342×512 px** (downscaled to ~133×200 at load time)

| Group | Base | Eyes | Mouths |
|-------|------|------|--------|
| `_normal` | 342×512 | 2 × 342×512 | 4 × 342×512 |
| `_cheerful` | 342×512 | 3 × 342×512 | 3 × 342×512 |
| `_serious` | 342×512 | 2 × 342×512 | 3 × 342×512 |
| `_standalones` | 11 × 342×512 | — | — |

### Campbell2 (`characters-private/default/campbell2/`)
All bases: **52×89 px** (no downscaling needed — under MAX_SPRITE_DIMENSION)

| Group | Base | Eyes | Mouths |
|-------|------|------|--------|
| `_normal` | 52×89 | 2 × 44×11 | 2 × 34×34 |
| `_serious` | 52×89 | 2 × 44×11 | 2 × 34×34 |
| `_serious_shouting` | 52×89 | 2 × 44×11 | 2 × 42×34 |
| `_smiling` | 52×89 | 2 × 44×11 | 2 × 34×34 |
| `_looking_down` | 52×89 | 2 × 48×15 | 2 × 34×30 |

### Mei Ling (`characters-private/mei_ling/`)
All bases: **52×89 px** (no downscaling needed)

| Group | Base | Eyes | Mouths |
|-------|------|------|--------|
| `_normal` | 52×89 | 2 × 44×14 | 2 × 24×14 |
| `_serious` | 52×89 | 2 × 44×14 | 2 × 22×15 |
| `_smiling` | 52×89 | 2 × 44×14 | 2 × 24×14 |

---

## Appendix B: File Integrity Check

**Zero-byte files found:** None ✅
**Total characters audited:** 3 (1 public, 2 private)
**Total expression groups scanned:** 14 (3 Nous + 6 Campbell2 + 3 Mei Ling + 2 legacy)
**Total standalone frames:** 17 (11 Nous + 3 Campbell2 + 3 Mei Ling)
**Config files inspected:** 3 (nous/config.yaml, default/config.yaml, mei_ling/config.yaml)
**Personality files inspected:** 3 (nous, default, mei_ling)
**Voice files inspected:** 6 (3 Nous, 2 Campbell, 1 Mei Ling)
**`positions.json` files found:** 1 (default/positions.json — legacy format)

---

## Appendix C: Change Log from Previous Audit

This audit supersedes the previous `character-audit.md` from 2025-04-30. Key differences:

1. **`characters/` now contains only `nous/`** — `default/` and `mei_ling/` have been moved to `characters-private/`
2. **`nous/_normal/` base head is now `sprite-base.png`** (real asset, 219 KB) — the `__cc_placeholder__.png` placeholder has been removed
3. **Previous "PARTIALLY BROKEN" status is now "READY"** — the critical blocker (placeholder base head) is fixed
4. **`campbell` is confirmed LEGACY** — flat sprites only, no expression group structure
5. **`nous` now has `display_mode: cover`** and full `sprite_order` definitions — both were flagged as missing in the previous audit
