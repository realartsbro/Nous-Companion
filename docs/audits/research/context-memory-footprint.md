# Context & Memory Footprint Audit

> **Cron Job 2 of 5** — READ-ONLY analysis  
> **Date:** 2026-04-30  
> **Scope:** Every source the companion pulls from for quip context, how far back it reaches, and what Hermes-side data is available but unused.

---

## 1. Current Context Sources (all that feed quip generation)

The companion assembles quip context from **11 distinct sources**, loaded at different layers:

| # | Source | Where Loaded | How Used |
|---|--------|-------------|----------|
| 1 | **personality.md** | `character_loader.py:39` → `character.build_system_prompt()` | Baked into the LLM system prompt as the character's identity |
| 2 | **idle_lines.txt** (137 lines) | `character_manager.py:70-78` | Shuffled and spoken after `_idle_timer` fires (no LLM call) |
| 3 | **prompt_acks.txt** (27 lines) | `character_manager.py:83-102` | Shuffled and spoken instantly when a user message arrives (`_delayed_prompt_react`) |
| 4 | **brief_quips.txt** (36 lines) | `character_manager.py:107-123` | Shuffled and spoken after completion in "brief" verbosity mode |
| 5 | **Session messages** (last N) | `hermes_observer.py:428-438` via `get_current_context(max_messages=50)` | `_format_session_context` builds a bullet list of user queries, assistant responses, tool chain, and the latest response |
| 6 | **Tool chain** (recent tools) | `hermes_observer.py:793-800` → `_poll_once` | Extracted from assistant messages with tool_calls, enriched with `_extract_recent_tool_chain` |
| 7 | **Quip history** (companion's own past) | `companion_server.py:888-893` → `_quip_history` ring buffer | Injected as `user`/`assistant` message pairs before current context (depth-tiered, 2-22 exchanges) |
| 8 | **Recent comment history** | `companion_server.py:3155-3168` → `_recent_comment_context()` | Appended to the "Current event" context as a continuity block (last 6 comments, 180s window) |
| 9 | **Expression names** | `character_loader.py:112-117` → `build_system_prompt()` | Listed in system prompt so the LLM can pick an appropriate expression |
| 10 | **Godmode system prompt** (optional) | `companion_server.py:869-875` → `_load_godmode_system_prompt()` | Prepended to system prompt when godmode is enabled |
| 11 | **speech_allowed config** | `companion_server.py:848-851` | Filters expression list to only speech-permitted expressions |

### How context is assembled end-to-end (completion reaction flow):

```
Hermes session file (.json)  ──poll─►  HermesObserver._poll_once()
                                             │
                                    detects new messages ──► emit(EVENT_COMPLETE, {...})
                                             │
                                    CompanionServer._on_hermes_event()
                                             │
                                    get_current_context(max_messages=50) ──► raw messages
                                             │
                                    _format_session_context(raw_msgs, response, tool_chain)
                                             │
                                    builds: [earlier topics] + [recent exchanges] + [tool chain] + [result]
                                             │
                                    _recent_comment_context() adds continuity block
                                             │
                                    _generate_quip(assembled_context, reaction_kind)
                                             │
                                    system = personality.md + expression list + CRITICAL RULES
                                    messages = system + quip_history + user_context
                                             │
                                    ──► LLM call (via Hermes API server or fast provider)
```

---

## 2. How Far Context Actually Reaches

### Depth Tiers (controlled by `context_budget` setting)

| Tier | Label | Session msgs scanned | Detailed exchanges | Earlier topics | Quip history exchanges | Token ceiling |
|------|-------|---------------------|-------------------|----------------|----------------------|--------------|
| 1 | Brief | 25 | 4 | compacted to topic lines | 2 (4 msgs) | 50K |
| 2 | Normal | 50 | 8 | compacted to topic lines | 8 (16 msgs) | 50K |
| 3 | Deep (default) | 120 | 14 | compacted to topic lines | 12 (24 msgs) | 50K |
| 4 | Chaos | 200 | 22 | compacted to topic lines | 22 (44 msgs) | 50K |

### What "detailed exchanges" means

- `max_messages=120` means the observer reads the **last 120 raw messages** from the session file (line 2865)
- `max_detailed=14` means the **last 14 user+assistant pairs** are shown verbatim (with 400-char user query, 200-char assistant response truncation)
- Exchanges beyond 14 are compacted to single-topic lines (first 50 chars of user query only)
- The 50K token ceiling is a generous safety cap — actual size is much smaller (depth-controlled)

### Time window

- **No time-based window on context.** It's purely count-based: "last N messages."
- **Session liveness:** Only sessions modified within `LIVE_SESSION_CUTOFF_S` (1800s = 30 min) of the most recent session are considered "live" (observer line 376)
- **Comment history:** 180-second window for companion-to-companion continuity
- **Dedup window:** 5-minute window for reaction hash deduplication

### Key limitation: single-session isolation

- Quip history (`_quip_history`) is an **in-memory ring buffer** — it resets when the companion server restarts
- On session switch (`EVENT_SESSION_SWITCHED`), the companion's Brain `clear_history()` is NOT called (only the observer updates its tracking)
- There is **no cross-session memory** — each Hermes session is treated as isolated

---

## 3. What Hermes Produces That the Companion Ignores

### 3.1 Hermes Memory System (MEMORY.md + USER.md) ⭐⭐⭐ Biggest miss

**Location:** `~/.hermes/memories/MEMORY.md` and `~/.hermes/memories/USER.md`

Hermes maintains two persistent memory stores that are **injected into every Hermes turn** but completely invisible to the companion:

**MEMORY.md** (currently ~1,971 chars / 2,200 cap):  
Contains project-level facts, environment quirks, and technical conventions:
- `codec-companion: Tauri v2, WS direct, 720x520…`
- `Time quirks: WSL clock drifts ~1h17m behind…`
- `Nous Companion: Tauri v2, hackathon project…`
- NTH research project pipeline stages and methodology
- OmniVoice, Ollama, Honcho configuration details

**USER.md** (currently ~1,112 chars / 1,375 cap):  
Contains user identity, preferences, and behavioral patterns:
- `User prefers…` (preferences, working style)
- Communication patterns (Telegram, design review process)
- Creative method, tools, and quality standards
- Personal details (Berlin timezone, Windows+WSL+Tauri stack)

**Why this is the biggest miss:** If the companion read USER.md, it could:
- Address the user by name or role
- Reference their preferred working style ("I know you like one change at a time…")
- Understand their design preferences without being told
- Adapt its tone to match the user's communication style
- Know about the Telegram home channel, Berlin tz, etc.

### 3.2 Context Compaction Summaries 🟡 Moderate miss

**Location:** Session JSON files, injected as user/assistant messages

Hermes compacts old conversation turns when approaching context limit (config: `compression.threshold=0.7`, `compression.target_ratio=0.3`). Compacted content is stored as:
```
[CONTEXT COMPACTION — earlier conversation summarized]
```

The observer explicitly **strips these markers** (line 2978 & line 403):
```python
if role == "user" and not content.startswith("[CONTEXT COMPACTION"):
```

**What's lost:** The compaction summaries contain high-level summaries of what was discussed earlier in the session. These could give the companion a "bigger picture" view without consuming token budget.

### 3.3 User Personality Profiles 🟡 Moderate miss

**Location:** `~/.hermes/profiles/{business,debut-fiction}/`

Hermes has profile directories with their own:
- `config.yaml` — profile-specific settings
- `sessions/` — isolated session files per profile
- `memories/` — profile-specific memory
- `skills/` — profile-specific skills

The companion doesn't:
- Detect which Hermes profile is active
- Adjust behavior based on profile (business vs creative)
- Read profile-level config or personality data

### 3.4 SOUL.md System Prompt 🟢 Minor miss

**Location:** `~/.hermes/SOUL.md`

Currently just a template file (15 lines, mostly HTML comments). The companion doesn't read it at all. Since it's currently empty, this is a minor miss, but if populated it would be valuable.

### 3.5 Project AGENT.md / CLAUDE.md / .cursorrules 🟢 No current loss

The companion project has **no AGENT.md or CLAUDE.md** file. It has:
- `README.md` (227 lines, general project info)
- `DEVELOPER_BRIEF.md` (9 lines, mostly placeholder)

So there's nothing to read here. If these are added in the future, the companion should consume them.

### 3.6 Full Session History 🟡 Moderate miss

**Location:** `~/.hermes/sessions/session_*.json`

Each session file contains:
- `session_id`, `model`, `platform`, `system_prompt`, `tools` (full schemas)
- All messages with `role`, `content`, `tool_calls`, `finish_reason`, `reasoning`, `reasoning_content`
- Up to hundreds of messages (one examined: 196 messages, 1592 "role" entries)

**What the companion ignores:**
- **Reasoning content** — Hermes stores reasoning blocks in `reasoning` and `reasoning_content` fields, but the observer only extracts `content`. Reasoning contains the model's step-by-step thought process, which could give the companion insight into *why* Hermes did something, not just *what* it did.
- **Tool call IDs and response chains** — The observer only uses tool_call_id to map tool results to names; it doesn't track the full request/response chain
- **Message metadata** — Token counts, finish reasons, response_item_ids are all ignored
- **System prompt** — The full Hermes system prompt (thousands of bytes with memory injection, skills list, tool definitions) is never read by the companion

### 3.7 Hermes API Endpoints 🟢 Minor miss

**Location:** `http://127.0.0.1:8642/v1/`

The companion uses only `/v1/chat/completions` for quip generation. Available but unused:
- `/v1/session_search` — full-text search across past sessions
- `/v1/memory` — read/write memory entries
- `/v1/models` — model listing and capability detection
- Hermes-side memory injection is **not mirrored** to the companion

### 3.8 Hermes Configuration 🟢 Minor miss

**Location:** `~/.hermes/config.yaml` (502 lines), `~/.hermes/.env` (292 lines)

Contains:
- Active model, provider, TTS settings
- Available skills list (97+ descriptive skills)
- Platform configurations (Telegram, email, etc.)
- User preferences (display, streaming, terminal config)

The companion reads only `API_SERVER_KEY` and `API_SERVER_URL` from `.env` and `platforms.api_server` from config. It doesn't use the active model, skill inventory, or TTS provider info to inform its behavior.

### 3.9 Multi-Session Continuity 🟠 Significant miss

**The companion has NO cross-session awareness.** Each Hermes session is treated independently:
- When Hermes switches to a new session (user starts a new conversation), the companion loses all quip history context
- The observer tracks `_session_last_counts` per filename, but doesn't carry context between sessions
- No mechanism exists to inject "things we discussed 2 sessions ago" into the quip prompt
- Hermes itself has this capability via memory injection — the companion mirrors none of it

---

## 4. Specific Recommendations (What Could Be "Grabbed for Free")

### P0 — Implement Now (Zero Code Change, Pure Data Read)

**4.1 Inject MEMORY.md into quip system prompt**
- *File:* `~/.hermes/memories/MEMORY.md`
- *Effort:* Read the file in `_generate_quip()`, append a "## Hermes's Notes\n{content}" section to the system prompt (or a compacted 500-char version)
- *Impact:* Companion suddenly knows about project details, environment quirks, conventions. It would know it's a Tauri v2 app, WSL clock drifts, which TTS engine is preferred, etc.
- *Risk:* None — read-only, bounded file size (2,200 chars max)

**4.2 Inject USER.md into quip system prompt**
- *File:* `~/.hermes/memories/USER.md`
- *Effort:* Same as 4.1. Compact to 400 chars or inject as-is.
- *Impact:* Companion knows who it's talking to — their preferences, working style, creative process, design taste. Enables personalized quips: "One-thing-at-a-time, got it, boss."
- *Risk:* None — read-only, bounded (1,375 chars max)

**4.3 Feed reasoning content to the quip LLM**
- *Source:* `msg.get("reasoning", "")` and `msg.get("reasoning_content", "")` in session messages
- *Effort:* In `_poll_once()`, when building tool_use events, append reasoning to the context. The observer already has `assistant_reasoning` (line 761) but only gets the first 400 chars of `content`, not `reasoning`.
- *Impact:* Companion would know *why* Hermes is doing something, not just *what* tools it called. Enables smarter contextual reactions.
- *Risk:* Token budget increase. Cap at 200 chars of reasoning.

### P1 — Important But Needs Minor Plumbing

**4.4 Session search for recent context**
- *Mechanism:* When a session starts, call Hermes API `/v1/session_search` or read the last 2-3 session files
- *Effort:* Add a `_load_previous_session_context()` method that reads the previous session's last few exchanges
- *Impact:* Companion could reference "Last time we talked about [topic]" — creates continuity illusion
- *Risk:* Token budget. Limit to 2-3 topic lines.

**4.5 Expose tool chain as structured data, not just text**
- *Source:* The observer already extracts `tool_args` with `name` and `summary` in `_score_tool_cluster`
- *Effort:* In `_generate_quip()`, format tool chain as labeled action blocks (reads vs writes vs searches) instead of dumping raw text
- *Impact:* Better factual accuracy — companion can distinguish "Hermes read a file" from "Hermes wrote to a file"
- *Risk:* None — restructuring existing data

**4.6 Read profile info for context-appropriate behavior**
- *Source:* `~/.hermes/profiles/{active}/`
- *Effort:* Detect which profile Hermes is using (from config or session file platform field). Adjust companion tone/topics accordingly.
- *Impact:* Companion could be more technical in "business" profile, more creative in "debut-fiction" profile
- *Risk:* Profile detection logic needed

### P2 — Nice to Have

**4.7 Feed SOUL.md into system prompt**
- *Effort:* If SOUL.md has content, append it to character personality as "System context: {soul_content}"
- *Impact:* The companion would understand the meta-instructions Hermes is following

**4.8 Use Hermes model info to calibrate expectations**
- *Source:* `config.yaml` → `model.default` or session file `model` field
- *Effort:* Read active model in `_generate_quip()`; if model is slow (local GGUF), adjust timing or verbosity
- *Impact:* Companion wouldn't quip "That was fast!" when Hermes uses a slow local model

---

## 5. Summary: Current Context Depth vs. Available Data

```
Current companion context window:
┌─────────────────────────────────────────┐
│  Last 120 session messages (max)        │ ← purely count-based, no time window
│  Last 14 detailed exchanges             │
│  Earlier topics: 1-line summaries       │
│  Quip history: 12 previous exchanges    │
│  Comment history: 6 entries / 180s      │
└─────────────────────────────────────────┘


Available but unused (in ~/.hermes/):
┌─────────────────────────────────────────┐
│  MEMORY.md (1,971 chars)               │ ← project facts, conventions, quirks
│  USER.md (1,112 chars)                 │ ← user preferences, identity, style
│  Reasoning from all tool calls          │ ← why Hermes did what it did
│  Previous session summaries             │ ← cross-session narrative
│  Compacted conversation summaries       │ ← high-level "bigger picture"
│  Profile personalities                  │ ← role-specific behavior config
│  SOUL.md (if populated)                │ ← meta-instructions
└─────────────────────────────────────────┘
```

### Verdict

The companion has **decent short-term memory** (up to ~120 messages deep) but **zero persistent/long-term context**. The top two Hermes memory stores (MEMORY.md and USER.md) would cost ~100 bytes of system prompt to inject and would give the companion more personality awareness than everything else combined. Both are bounded, read-only, already-structured files that are updated by Hermes itself — the companion gets ongoing memory updates "for free" just by reading them at quip time.
