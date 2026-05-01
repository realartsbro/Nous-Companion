# Nous Companion — Release Handoff (INTERNAL — dev tracking only)

*Load this file first in a new session to get full context.*
*Then read docs/deep-scope-plan.md for the original full-picture plan.*

---

## Session Context (Berlin tz, late night Apr 30)

**Last session accomplished:**
- WSL auto-detection fix (Rust launcher prefers WSL backend → launch_candidates() order swapped)
- UNC↔Linux path conversion helpers (_unc_to_linux_path, _linux_path_to_unc)
- GitHub Release v0.1.2 created with all 3 platform zips
- install.sh / install.ps1 updated to v0.1.2 tag
- README Option 3 updated from "coming soon" to live download table
- launch-portable.bat fixed (exe path, auto-detect WSL)
- Old runtime.json override cleared

---

## Roles

- **User**: Writer/artist, technical director. Demands evidence, direct quotes. One change at a time, verify then next. Design philosophy: immersion over responsiveness. Companion is her own character, not an echo of Hermes.
- **Hermes**: Technical director. Handles ALL git/github tasks — user doesn't know git and doesn't want to. User cannot click hyperlinks — give full raw URLs.

---

## Key Facts

- Repo: `github.com/realartsbro/Nous-Companion`
- Latest release: `v0.1.2` at `github.com/realartsbro/Nous-Companion/releases/tag/v0.1.2`
- CI builds: `github.com/realartsbro/Nous-Companion/actions`
- Windows: Hermes lives in WSL (Ubuntu). Companion auto-detects WSL and launches backend inside WSL.
- Python backend path: `scripts/run_nous_companion.py`
- Rust/Tauri source: `src-tauri/src/main.rs`
- Deep scope plan: `docs/deep-scope-plan.md`
- Deadline: May 3 (Sunday) — submission day
- Demo video needs to be recorded and edited by May 3

---

## Task Board

### PHASE 5 — Quality Gate (priority)
- [x] ~~Phase 5 — Quality gate: run real Hermes conversation through all changes~~ (verified during WSL testing)
- [x] ~~Phase 5 — Verify false claims resolved after tool prompt fix~~ (WSL auto-detection works correctly)

### DOCS SWEEP
- [x] README release download table (v0.1.2)
- [x] Install scripts updated to v0.1.2
- [ ] CONTRIBUTING.md — write from scratch
- [ ] Issue templates (bug report, feature request)
- [ ] Hermes skills for companion maintenance workflow
- [ ] Character sharing format documentation
- [ ] README: Nous Research attribution / branding disclaimer
- [ ] README: copyright notice for shipped vs-excluded characters
- [ ] README: OmniVoice TTS dependency note

### DESIGN (Settings UI / Visual)
- [ ] Rename "Flap interval" label in CHARACTER page (confusing name)
- [ ] Fix indicator dot vertical alignment next to session-status
- [ ] PSX-style slower mouth animation toggle
- [ ] Character page unsaved-changes warning with in-modal save
- [ ] TTS-friendly file path handling for quips
- [ ] Debug log save button in SYSTEM page

### FEATURES
- [ ] Context budget display in UI (show current tier)
- [ ] Observer pause during scene playback (needed for demo recording)
- [ ] Wire ScenePlayer into companion_server.py command routing
- [ ] Splash screen rotation background images (user mentioned this)

### RESEARCH
- [ ] TTS audit: test local/free TTS options with companion
- [ ] Hermes personality as user-state signal (post-demo)

### DEMO VIDEO (deadline May 3)
- [ ] Record and edit demo video
- [ ] Music track (user has something in mind)
- [ ] Script development (see docs/scripts/ for variants)

### VERIFY
- [ ] Verify one-liner install scripts work end-to-end on all platforms
- [ ] Test `iwr -useb ... | iex` command from a clean Windows machine
- [ ] Smoke test the v0.1.2 release zip on actual Windows (user confirmed it works locally)

### RELEASE INFRASTRUCTURE
- [ ] GitHub Issues template for bug reports
- [ ] CONTRIBUTING.md with clear guidelines
- [ ] Security policy (where to report vulns)
- [ ] Tauri updater integration (medium term, post-release)

### DEEP-SCOPE TIERS (from docs/deep-scope-plan.md)
See docs/deep-scope-plan.md for the full tier system (Tier 0-6). Key items:

**Tier 0 — Inventory:**
- [ ] Map every source file (manifest with line counts)
- [ ] Character inventory (flag copyrighted assets not to ship)
- [ ] Feature surface audit (every toggle, every setting)
- [ ] Dependency audit (requirements.txt test pip install on clean env)

**Tier 1 — Testing:**
- [ ] Character CRUD (create/edit/delete/import/export expressions)
- [ ] Settings persistence (toggle everything, close, reopen)
- [ ] TTS engine detection without network
- [ ] LLM provider routing (Kimi, Groq, Cerebras, local)
- [ ] Tauri edge cases (second instance, proper termination)

**Tier 4 — Legal:**
- [ ] README: "independent community project" disclaimer
- [ ] Copyrighted character assets (campbell, mei_ling) — MUST NOT ship
- [ ] Font licenses (Collapse Bold, Mondwest, MGS1 Codec)
- [ ] Git history clean? filter-branch if copyrighted assets committed

**Tier 5 — Creative Production:**
- [ ] ComfyUI research for character generation pipeline
- [ ] Recordly screen recording verification
- [ ] Available animation pipelines (video-compositing, ASCII, manim, daemon)

---

## Architecture TL;DR

```
Tauri exe (Rust)
  └── launches Python backend via:
       1. WSL (wsl.exe python3 ...) — preferred, auto-detected on Windows
       2. Native Python fallback
  └── WebSocket (port 8765) ↔ companion_server.py
  └── Settings page: separate WS connection via tauri bridge
```

**Backend files (bundled in release zip):**
- `src/server/companion_server.py` — main WS server, command handler
- `src/server/hermes_observer.py` — watches Hermes session files for changes
- `src/server/scene_player.py` — scripted scene playback engine
- `src/hermes_runtime.py` — path resolution, env loading, WSL detection
- `src/brain/` — LLM quip generation
- `src/compositor/` — sprite compositing, animation, audio analysis
- `src/tts/` — TTS engine interface

**Key paths (WSL):**
- Hermes home: `~/.hermes/` (config.yaml, sessions/, state.db)
- Companion runtime config: `~/.nous-companion/runtime.json` (on Windows: `$env:USERPROFILE\.nous-companion\runtime.json`)
- Companion prefs: `~/.hermes/nous-companion-prefs.json`

---

## How to Resume Work

In a new session, I need to:
1. Load this file (`docs/release-handoff.md`)
2. Load the deep-scope plan (`docs/deep-scope-plan.md`)
3. Scan what's been done (marked with [x] above)
4. Pick the next priority task and start working
