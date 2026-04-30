# Nous Companion — Deep-Scope Research & Launch Plan

**Status:** Scoping document — not execution. Every tier feeds into the next.
**Timeline:** Submit EOD May 3 (Sun). Today is Apr 30 (Thu 2:20 AM Berlin).
**Approach:** Inventory → Test → Tell → Ship

---

## ⚠️ Critical Context

1. **Not an official Nous Research product** — the name "Nous" is used with permission, casually. The README, social posts, and presentation must make this clear.
2. **Copyrighted characters** — Mei Ling and Roy Campbell are Konami IP. They're for private use. The public release must ship with an original character (e.g., the `nous` character) and a clear BYO-character workflow.
3. **Kimi track qualification** — does NOT need to show Kimi inside the companion itself. Running Hermes with a Kimi model in the terminal + noting "powered by Kimi" in the writeup suffices.

---

## TIER 0 — INVENTORY & TRUTH (foundation, do first)

*Goal: Know exactly what we have, what ships, what's broken.*

### 0.1 Source File Inventory
- [ ] Map every `.py`, `.js`, `.html`, `.css`, `.rs` file — create a manifest with line counts and purpose
- [ ] Identify all config files (`config.yaml`, `positions.json`, `personality.md`, `tauri.conf.json`, `Cargo.toml`)
- [ ] Document the dependency chain: what imports what (Python → Python, renderer.js internal deps)

### 0.2 Character Inventory
- [ ] List every character directory, its sprites, config, voice files
- [ ] Flag copyrighted assets (Campbell sprites = Konami, Mei Ling = Konami)
- [ ] Document the `nous` character (original, ships with the release)
- [ ] Check: does the default character have a valid expression set that won't break on first launch?
- [ ] Check: what happens if `characters/` is empty on first run?

### 0.3 Feature Surface Audit
- [ ] List every settings page, every toggle, every dropdown — exhaustive map
- [ ] Mark which settings are persisted vs ephemeral
- [ ] Mark which settings are wired through the full WS loop vs broken
- [ ] Identify "dead" toggles (UI control with no server-side handler)

### 0.4 Dependency Audit
- [ ] `requirements.txt` — test `pip install` on a clean environment
- [ ] Tauri build — verify `cargo tauri build` still works (CI was green but needs confirmation)
- [ ] Node/frontend deps — identify any implicit JS dependencies (Lucide icons, etc.)
- [ ] Edge-TTS detection — does it work without network?
- [ ] OmniVoice detection — what imports are tested? (Omnivoice is my preferred choice, but must run local, not everyone will be able to run it, we can say it works nicely with it due to its speed, but should make it clear what users will need to run this, otherwise we want to encourage them to pipe in any TTS they wish)

---

## TIER 1 — TESTING (no changes, just discover what works)

*Goal: Know our stability posture. Every test is a probe, not a fix.*

### 1.1 Character CRUD
- [ ] **Create:** Add a new expression group via settings → does it save? Does the compositor pick it up?
- [ ] **Edit:** Change expression offsets → do they persist after reload?
- [ ] **Delete:** Remove an expression group → clean cleanup?
- [ ] **Import character** (.nous-companion-character.zip) → end-to-end, error states for invalid zips
- [ ] **Export character** → does the zip contain all required files? Does re-import work?
- [ ] **Switch characters** → does the burst flash fire? Does the voice reference switch?
- [ ] **Idle rarity system** → set weights 0-5 → does the pool respect them? Does speech_allowed filter work?
- [ ] **Per-expression voice** → upload voice for "cheerful" → does it play when that expression is active?

### 1.2 Settings Persistence
- [ ] Toggle every visual effect ON → close settings → reopen → are they still ON?
- [ ] Change chrome style to Classic → close → reopen → stays?
- [ ] Change sprite size → close → reopen → stays?
- [ ] Change volume → close → reopen → stays?
- [ ] Check `nous-companion-prefs.json` — is every setting written correctly?
- [ ] Check legacy read path (`codec-companion-prefs.json`) — does it migrate old prefs?

### 1.3 TTS Engine Detection & Playback
- [x] Start backend without OmniVoice → does it fall back to Edge-TTS?
- [ ] Start backend without either → graceful error or crash?
- [x] Play a TTS reaction → audio plays, lip sync works?
- [ ] Interrupt playback (new reaction arrives during speech) → clean transition?
- [x] Volume slider → affects playback volume?
- [x] Per-expression voice → switch to expression with custom voice file → correct ref loaded?

### 1.4 LLM Provider Routing
- [ ] Select a Kimi model → does `_get_fast_provider_config()` resolve it correctly? 
- [ ] Select Groq → quip generated?
- [ ] Select Cerebras → quip generated?
- [ ] Select local provider (Ollama/LM Studio) → resolved without api_key gate?
- [ ] Select a model → navigate away → back → model still selected?
- [ ] Click refresh (⟳) → model list updates without removing cache-only providers?
- [ ] Provider name mismatch test: select model → does the UI send the cached `name` or the config key?

### 1.5 WebSocket & Network Resilience
- [ ] Disconnect backend → renderer shows "disconnected" state (red dot)?
- [ ] Reconnect backend → renderer recovers?
- [x] Concurrent WS sends (frame loop + command responses) → no lost messages?
- [ ] Settings page connects independently → both windows receive broadcasts?
- [x] Rapid character switching → no frame decode starvation (5s timeout rescue)?

### 1.6 Tauri Desktop Shell
- [x] Window appears borderless, always-on-top, correct size
- [x] Sprite size change → window resizes correctly
- [ ] Settings window opens → positioned correctly (QUESTION: Is it possible to make the app with the main window launch perfectly  center on screen when started for the first time, and after that, remember the last position the user had it?)
- [ ] Close app → backend process terminates?
- [ ] Second instance → behavior?
- [x] Edge snapping test (if implemented) → dock to screen edge? (only implemented for the main window)

### 1.7 Visual Effect Correctness
- [ ] Scanlines — visible at all sizes? Consistent with portrait canvas?
- [ ] Grain — visible, animated, performance acceptable?
- [ ] Interference bars — scroll correctly, composite with character pixels?
- [ ] Analog bleed — drawImage ghost copies at correct offset?
- [ ] Burst flash on character switch — timing correct (no CSS transition eating the animation)?
- [x] Frame overlays (creme/white/black/brackets) — draw correctly on overlay canvas?
- [x] Colorize WebGL shader — toggle, pick color, adjust strength → all work?
- [x] EKG wave viz — appears during speech, fades after stop?

### 1.8 Edge Cases
- [ ] Empty characters directory → graceful fallback or crash?
- [ ] Corrupted config.yaml → handled?
- [ ] Very long personality prompt → truncation?
- [ ] Multiple rapid settings changes → broadcast throttle?
- [x] Window at smallest size (52x89) → all controls still reachable?
- [x] Window at biggest size → all controls properly positioned?

---

## TIER 2 — FEATURE PRESENTATION (what do we show?)

*Goal: Categorize every feature as "cool," "ridiculous," or "technical" — decide the demo arc.*

### 2.1 Genuinely Cool Features (lead with these)
| Feature | Why It's Cool | Demo Angle |
|---------|--------------|------------|
| Character creator / expression editor | Community can make their own companion — extends the Hermes ecosystem | "Your Hermes, your companion" |
| Per-expression voice cloning | Different emotions have different voices — serious voice for serious expressions | Quick switch: normal → serious → cheerful |
| Weighted idle expression system | Characters feel alive between interactions | Watch the portrait cycle naturally |
| Godmode live feed | See the companion "thinking" in real-time | Overlay text streaming |
| Lip-synced TTS playback | Audio-driven mouth animation, not random | Pinpoint sync |
| Import/export character bundles | Shareable community characters | Show a quick import |
| Direct LLM provider routing | No Hermes proxy overhead — fast quips | "Bypasses the middleman" |

### 2.2 Ridiculous / Cheeky Features (for the demo personality)
| Feature | Why It's Ridiculous | Demo Angle |
|---------|-------------------|------------|
| Analog bleed (SCART RGB ghosting) | Emulating bad cable connections from 1990s | "We brought back the worst part of CRT" |
| Classic MGS1 green-codec mode | Pure nostalgic indulgence | "For the old heads" |
| Burst flash on character switch | Over-the-top noise transition | Flash edit in video |
| Status dot that shines through the overlay | Because why not | "She's always watching" |
| EKG wave viz | A heartbeat for a desktop companion | Living pulse |
| Interference bars | Simulating signal degradation | "Building character through interference" |

### 2.3 Technical Depth Features (for the GitHub repo / community power users)
| Feature | Why Technical |
|---------|--------------|
| WebGL colorize shader | Real-time GPU-powered recolor of portrait |
| Frame overlay system with 5 styles | CSS+Canvas dual rendering pipeline |
| Configurable CSP in Tauri | Security-aware architecture |
| PID-file-based backend lifecycle | Clean process management |
| Dual WS client architecture (settings + main) | Proper concurrent connection handling |

---

## TIER 3 — STORYTELLING FRAMEWORK (debut-fiction methodology)

*Goal: Apply the debut-fiction probing/critique model to shape our demo narrative.*

### 3.1 Core Question
*Before writing a single line of script, answer:*
> What is this video saying?
> What is the sub-text (never spoken)?
> What does the viewer feel after watching?

**Draft core:** "Hermes Agent is powerful but invisible — a mind without a face. Nous Companion gives it eyes, a voice, a personality. Your terminal just got a friend."

### 3.2 Story Segments (from debut-fiction's "philosophical core" method)

Each segment needs a CLEAR core stated before writing:

**Segment 1 — "The Missing Face"**
- Core: Hermes works in the background. You never see it. Until now.
- Sub-text: Agent interfaces are boring terminals. We fixed that.
- Viewer feels: Recognition ("I use Hermes, I know what this means")

**Segment 2 — "Personality is an Invitation"**
- Core: The character creator means anyone can build a companion.
- Sub-text: This isn't a closed app — it's a platform for the community.
- Viewer feels: Ownership ("I could make mine look like...")

**Segment 3 — "The Ridiculous Detail"**
- Core: The interference bars, analog bleed, and CRT noise aren't bugs — they're love letters.
- Sub-text: We cared about the experience, not just the feature list.
- Viewer feels: Delight ("They put SCART ghosting in a desktop app")

**Segment 4 — "Built on Hermes"**
- Core: Zero extra config. Reads your Hermes setup and goes.
- Sub-text: Nous Companion makes the Hermes ecosystem stronger, not more complex.
- Viewer feels: Trust ("It just works with what I already have")

**Segment 5 — "Yours to Shape"**
- Core: Open source, MIT license, shareable characters.
- Sub-text: This isn't a product launch — it's a gift to the community.
- Viewer feels: Invitation ("I can contribute")

### 3.3 Anti-Patterns (from debut-fiction voice contract)
- ❌ "Not just a companion, but a friend" — "Not X, but Y" template
- ❌ "You'll never work alone again" — slogan language
- ❌ "The companion that's always there" — generic truism
- ❌ Telling the viewer how to feel ("Isn't that adorable?")
- ✅ Write from inside the argument: "She reads your terminal. She reacts. That's it."

### 3.4 Tone Check
| Right | Wrong |
|-------|-------|
| "A small window that sits on your desktop. A character that reacts." | "Revolutionize your Hermes experience" |
| "Made for people who like their terminal to have a face." | "The AI companion you deserve" |
| "MIT. Go make something." | "Join the future of agent interaction" |

---

## TIER 4 — LEGAL & COMMUNITY READINESS

*Goal: Ship without getting sued, invite contribution without confusion.*

### 4.1 Licensing & Attribution
- [ ] README needs: "Nous Companion is an independent community project. 'Nous' is used with permission from Nous Research."
- [ ] LICENSE: MIT (already in place)
- [ ] Character assets license: what license applies to the `nous` character art?
- [ ] If using community art: attribution guidelines (specific character belongs to nous, this image however I created myself, we'll be fine)

### 4.2 Copyrighted Content Removal
- [ ] `characters/campbell/` — all sprites are Konami IP. MUST NOT ship.
- [ ] `characters/mei_ling/` — same. MUST NOT ship.
- [ ] Do we have a git history that includes these? If so, consider `git filter-branch` or start fresh.
- [ ] The splash screen background (`renderer/bg.jpg`) — is this original or sourced? (It also belongs to nous, however it'll be fine if we credit them and we'll even use some others in rotation, so the splash screen has different ones, remind me of this)
- [ ] Fonts: Collapse, Mondwest, MGS1 Codec — what are the licenses? Ship them in the repo? (nous ships them hermes itself, not sure if that's an oversight on their part, excluding MGS1 Codec, they don't ship that)
- [x] Replace the default character with an original one (`characters/nous/`) as the shipped default. (we keep "Nous")

### 4.3 Branding
- [ ] The MGS1 Codec font is named after Metal Gear Solid — this is fine in the app (easter egg mode) but don't market it as "MGS mode" in tweets. Call it "Classic" or "Retro codec."
- [x] The `nous` character's personality/presence should be distinct enough that she's an original creation. (branding is specifically nous girl and that's absolutely adored by the team)
- [ ] README should not imply any official Nous Research endorsement.

### 4.4 Community Infrastructure
- [ ] GitHub Issues template for bug reports
- [ ] CONTRIBUTING.md with clear guidelines
- [ ] Character sharing format documentation (how to build a character)
- [ ] Security policy (where to report vulns)
- [ ] Starring/engagement plan

---

## TIER 5 — CREATIVE PRODUCTION TOOLS

*Goal: Know what we CAN use for the video and assets.*

### 5.1 ComfyUI Integration (NOTE: YOU DON'T WANT TO GENERATE ANYTHING, YOU WANT TO RESEARCH WHAT WE HAVE AVAILABLE, WHAT WE COULD DO AND FOCUS ON THE POSSIBILITIES THAT REALLY MATTER, YOU CAN ALSO SEARCH ONLINE, BE FOCUSED NOT TO WASTE TIME WITH CREATING STUFF I CANNOT APPROVE IN CREATIVE TERMS)
- [ ] Check if ComfyUI is installed and running on this machine (we have portable comfy, D:\ComyBackup\ComfyUI-Easy-Install)
- [ ] If yes: what models are available? Flux? SDXL? AnimateDiff? (you can research what's capable with ltx2.3, as I only have an older version HOWEVER, make sure that's even useful for us. We could think in terms of i2v for the demo, but you go and research what's new, what's still the best, what the options are.)
- [ ] Potential uses:
  - Generate custom character portraits for the `nous` character (Flux img2img from sketch?)
  - Generate background art for the demo video (dark atmospheric scenes)
  - Generate expression variants (different moods for the same base head)
  - Generate the video thumbnail (only interesting if you find out a really well done and easy to use workflow, so people can create their own character with their own pipeline. What makes this difficult is that we need inpainting, so you'd have to see what state of the art models for local use are best for that, if that could be automated, so pixel-perfection remains and only eyes/mouths, as per our "nous companion" compatibility could be changed, this is more of a heavy research task)
- [x] Risk: ComfyUI generation takes time — factor this into our overnight window (don't generate anything overnight, just research, but extensively so, especially finding workflows and the plotting out a comfy-workflow that go extremely well with our companion. It'd be amazing if we'd be able to ship a "create your character" kind of skill as all hermes users will now be able to use comfyui natively in hermes from now on, so even non-artsy types will be able to send a message to their hermes and if we can manage a workflow that can actually return a full character with animations for them, that'd be insane, I know that is possible. Probably a lot of info online already we can use and stitch together to piggybank of other or even official workflows.)

### 5.2 Recordly (Screen Recording)
- [ ] Verify Recordly is available on this machine
- [ ] Test capture of: borderless Tauri window, settings window, terminal activity
- [ ] Plan: record all RAW footage in one batch, edit later (don't record anything we wanna use for the final edit, you can test of course)

### 5.3 Music & Audio
- [ ] No copyright concerns for hackathon demo
- [ ] Sources: royalty-free libraries, generated music, self-composed (it's just a demo video, we can use whatever, but perhaps a really nice locally generated track, that vibes with the music nous research uses in their release demos, that'd  be cool, but no sweat, I already have something in mind for a track)
- [ ] The companion's own TTS can serve as voiceover, which is thematically perfect
- [ ] Music should match the dark teal / CRT aesthetic — ambient electronic, low-fi, or synthwave

### 5.4 Available Pipelines (from skills inventory)
| Pipeline | Use Case | Ready? |
|----------|----------|--------|
| `video-compositing-production` | Cinematic title cards, image compositing | ✅ Yes (PIL/Python) |
| `ascii-video` | Retro ASCII art for transition effects | ✅ Yes |
| `daemon-video-pipeline` | Atmospheric procedural backgrounds | ✅ Yes |
| `manim-video` | Animated diagrams of architecture | ✅ Yes |
| `comfyui` | Generate character art / backgrounds | ⚠️ Needs verification |

---

## TIER 6 — OVERNIGHT AUTOMATION (runs while we sleep)

*Goal: Parallel research that produces actionable output by morning.*

### 6.1 What CAN Run Unsupervised
- ✅ Source code audits (searching for patterns, counting lines, mapping dependencies)
- ✅ Settings surface extraction (parsing HTML for all toggles, IDs, defaults)
- ✅ Character asset inventory (walking directories, extracting metadata)
- ✅ Config consistency checks (comparing settings.html defaults vs companion_server.py defaults)
- ✅ FFmpeg/encoding verification
- ✅ Requirements.txt pip install test (in a temp venv)
- ✅ Character ZIP export validation (structural check without importing)

### 6.2 What Needs Human Supervision
- ❌ Actual feature testing (UI interaction, TTS playback, LLM routing)
- ❌ Import/export of characters (needs backend running)
- ❌ Visual effect correctness (needs human eyes)
- ❌ Window snapping / edge behavior (needs display)
- ❌ ComfyUI generation (needs GPU, may take time)

### 6.3 Suggested Cron Jobs

**Job A: Source Code Audit**
- Runs: once overnight
- Produces: full file manifest, dependency graph, dead code candidates
- Tools: `find`, `grep`, Python static analysis

**Job B: Config Consistency Check**
- Runs: once overnight
- Compares: settings.html defaults vs companion_server.py defaults vs renderer.js handler coverage
- Produces: table of every setting key, its 3 states (UI, server, renderer), and whether all 3 are wired
- Flags: settings with UI controls but no server handler, or server defaults with no UI

**Job C: Character Asset Validation**
- Runs: once overnight
- Checks: every character folder for required files, valid YAML, valid PNG dimensions, voice files exist
- Produces: per-character health report

**Job D: Git State Snapshot**
- Runs: after all other jobs
- Produces: `git status` summary, diff of any changes, list of files not yet tracked
- Purpose: know exactly what state the repo is in before we start working tomorrow

---

## EXECUTION ORDER

```
                       ┌──────────────────┐
                       │   TIER 0          │
                       │   Inventory       │ ← Start here, do first
                       └────────┬─────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                  ▼
     ┌────────────────┐ ┌──────────────┐ ┌────────────────┐
     │   TIER 1        │ │   TIER 4      │ │   TIER 5        │
     │   Testing       │ │   Legal       │ │   Production    │
     │ (parallel w/   │ │ (do early,    │ │ (probe what    │
     │  Tier 0 output) │ │  catch late)  │ │  tools work)   │
     └────────┬────────┘ └──────┬───────┘ └────────┬───────┘
              │                 │                   │
              └─────────────────┼───────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   TIER 2          │
                       │   Presentation   │ ← Depends on Tier 1 results
                       └────────┬─────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   TIER 3          │
                       │   Storytelling   │ ← Writes the script
                       └────────┬─────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   RECORD & EDIT  │ ← May 2-3
                       └──────────────────┘
```

---

## NEXT STEP FOR US

1. **You review this plan** — add/remove/modify tiers and tasks
2. **We agree on the overnight cron jobs** — which audits to automate
3. **I set up the cron jobs** — they run while you sleep
4. **Tomorrow morning** — we review the overnight output, then start executing Tier 1

Ready for your additions, cuts, and direction.
