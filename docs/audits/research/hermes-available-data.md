# Hermes Available Data Audit — What the Companion Ignores

> **Date:** 2026-04-30
> **Scope:** Full inventory of every data source Hermes Agent produces that the Nous Companion could tap into but currently ignores
> **Goal:** Maximum immersion with zero additional work — piggybacking on existing Hermes infrastructure
> **Methodology:** Direct inspection of ~/.hermes/ runtime (state.db, sessions/, memories/, config, API server), companion architecture docs (event-pipeline-audit.md), and Hermes agent source code

---

## Table of Contents

1. [Current Companion Context](#1-current-companion-context)
2. [Session Message Metadata — The Goldmine](#2-session-message-metadata)
3. [Persistent Memory Facts](#3-persistent-memory-facts)
4. [User Personality & Profile](#4-user-personality--profile)
5. [Session Summaries & Context Compaction](#5-session-summaries--context-compaction)
6. [Runtime Configuration State](#6-runtime-configuration-state)
7. [API Surface Map](#7-api-surface-map)
8. [Project-Level Context Files](#8-project-level-context-files)
9. [Skills Repository](#9-skills-repository)
10. [Credential Pools & Provider Configuration](#10-credential-pools--provider-configuration)
11. ["Zero Work" Opportunities](#11-zero-work-opportunities)
12. [Recommendations by Effort-to-Impact](#12-recommendations-by-effort-to-impact)

---

## 1. Current Companion Context

### What the companion _currently_ builds for its brain prompt

The observer pipeline (as designed in `event-pipeline-audit.md`) extracts from session files:

| Source | What's extracted | Max size | Truncation |
|--------|-----------------|----------|------------|
| User queries | Raw text | 800 chars | Content truncated |
| Assistant responses | Raw text | 800 chars | Content truncated |
| Tool calls | Tool name + truncated args | 200 chars per result | Results severely limited |
| Tool chain | Last assistant message with tool_calls | 1 level deep | Loses multi-step pipelines |
| Context summary | Pipe-delimited recent messages | ~120 chars per message | Irreversible loss |
| Session context (formatted) | Last N exchanges, earlier as fragments | 50-char topic fragments | Earlier context vaporized |

**Token budget in companion prefs:**
- `codec-companion-prefs.json`: `context_budget: 32000`, `context_depth: 4`
- `nous-companion-prefs.json`: `context_budget: 4096`, `context_depth: 4`

The companion's brain prompt tells the LLM:
> "You are the one behind the wheel — speak in first person."
> "Do NOT mention Hermes, AI assistants, or any external system."

This creates identity distortion: the companion claims agency for Hermes's actions but has no visibility into Hermes's internal state, model, provider, or reasoning depth.

### Token usage comparison (current state)

Hermes actually tracks per-message and per-session tokens in state.db. A typical cron session:
- Input tokens: ~15K-150K
- Output tokens: ~5K-29K
- Example (this session): 70,574 input / 5,451 output tokens — but the companion sees 0 of this cost/detail data.

---

## 2. Session Message Metadata — The Goldmine

### What session files contain vs. what state.db contains

Each session file on disk (`~/.hermes/sessions/session_*.json`) contains:
```json
{
  "session_id": "...",
  "model": "deepseek-v4-flash",
  "base_url": "https://opencode.ai/zen/go/v1",
  "platform": "cron",
  "session_start": "2026-04-30T16:48:15.345167",
  "last_updated": "2026-04-30T16:49:32.063887",
  "system_prompt": "...",
  "tools": [ /* full tool schemas */ ],
  "message_count": 47,
  "messages": [
    {
      "role": "user",
      "content": "..."
    },
    {
      "role": "assistant",
      "content": "...",
      "reasoning": "full reasoning text...",
      "reasoning_content": "same reasoning text...",
      "finish_reason": "tool_calls",
      "tool_calls": [
        {
          "function": { "name": "read_file", "arguments": "..." },
          ...
        }
      ]
    },
    {
      "role": "tool",
      "content": "{\"output\": \"...\", \"exit_code\": 0}",
      "tool_call_id": "call_..."
    }
  ]
}
```

### What the companion currently reads from session files

The observer reads session files and extracts:
- `content` text (truncated to 800 chars)
- `role`
- `tool_calls[]` function names + first 200 chars of arguments
- Tool results (first 200 chars)
- Session ID, message count
- Context summaries from recent messages

### What the companion **ignores** that's available in session files

| Available field | In session file? | In state.db? | Currently used? | Potential use |
|---------------|:---:|:---:|:---:|:---|
| `reasoning` (full text) | ✓ | ✓ | ✗ | Companion could see what Hermes is thinking |
| `reasoning_content` | ✓ | ✓ | ✗ | Same — duplicate field |
| `finish_reason` | ✓ | ✓ | ✗ | "tool_calls" vs "stop" vs "length" signals mode |
| `model` per session | ✓ | ✓ | ✗ | Know which model is driving (affects personality) |
| `base_url` | ✓ | ✓ | ✗ | Know which provider endpoint |
| `platform` | ✓ | ✓ | ✗ | "cli" vs "telegram" vs "cron" |
| `system_prompt` | ✓ | ✓ | ✗ | Contains memory, user prefs, skills — the companion brain could read the same context Hermes gets |
| Full tool definitions | ✓ | ✗ | ✗ | Tool schemas reveal available capabilities |
| Tool `arguments` (full JSON) | ✓ | ✓ | ✗ | Full tool arguments, not just truncated |
| Tool result content (full) | ✓ | ✓ | ✗ | Only first 200 chars used now |
| `call_id` / `tool_call_id` | ✓ | ✓ | ✗ | Link tool invocations to results |
| Timestamps (per message) | ✓ | ✓ | ✗ | Track response time, detect stalls |
| Token count (per message) | ✗ | ✓ | ✗ | Cost awareness, context pressure awareness |

### State.db — additional fields NOT in session files

The SQLite `state.db` `messages` table has **15 columns** including several not persisted to session files:

| Column | Type | Currently used? | What it enables |
|--------|------|:---:|-----------------|
| `id` | INTEGER | ✗ | Message identity |
| `session_id` | TEXT | ✗ (partial) | Cross-session queries |
| `role` | TEXT | ✓ | Basic classification |
| `content` | TEXT | ✓ (truncated) | Message text |
| `tool_call_id` | TEXT | ✗ | Trace tool results back to calls |
| `tool_calls` | TEXT (JSON) | ✗ | Full tool call structure |
| `tool_name` | TEXT | ✗ | Direct index of tool used |
| `timestamp` | REAL | ✗ | Per-message timing |
| **`token_count`** | **INTEGER** | **✗** | **Per-message token cost** |
| `finish_reason` | TEXT | ✗ | Why generation stopped |
| **`reasoning`** | **TEXT** | **✗** | **Full reasoning content** |
| **`reasoning_details`** | **TEXT (JSON)** | **✗** | **Structured reasoning steps** |
| `reasoning_content` | TEXT | ✗ | Duplicate of reasoning |
| `codex_reasoning_items` | TEXT (JSON) | ✗ | Codex-specific reasoning items |
| `codex_message_items` | TEXT (JSON) | ✗ | Codex-specific message structure |

**Key insight:** State.db has `reasoning_details` and `codex_reasoning_items` that session files do NOT include. These contain structured reasoning (step-by-step thought processes) that the companion could use to understand what Hermes is actually doing.

### Session metadata (state.db `sessions` table) — completely unused

The `sessions` table has **27 columns**. The companion only gets `session_id` and `message_count`:

| Column | Currently used? | What it enables |
|--------|:---:|-----------------|
| `id` | ✓ (as session_id) | Session identity |
| `source` | ✗ | "cli", "telegram", "cron", etc. |
| `user_id` | ✗ | Platform user identity |
| `model` | ✗ | Model used for this session |
| `model_config` (JSON) | ✗ | Full model configuration |
| `system_prompt` | ✗ | The full context Hermes has |
| `parent_session_id` | ✗ | Branching/forking support |
| `started_at` | ✗ | Session age |
| **`ended_at`** | **✗** | **Session ended detection** |
| **`end_reason`** | **✗** | **Why session ended** |
| `message_count` | ✓ | How many messages |
| **`tool_call_count`** | **✗** | **How many tools used** |
| **`input_tokens`** | **✗** | **Total input tokens** |
| **`output_tokens`** | **✗** | **Total output tokens** |
| `title` | ✗ | Session display name |
| `cache_read_tokens` | ✗ | Prompt caching savings |
| `cache_write_tokens` | ✗ | Prompt caching writes |
| `reasoning_tokens` | ✗ | Token spent on reasoning |
| `billing_provider` | ✗ | Who's being billed |
| `billing_base_url` | ✗ | Billing endpoint |
| `estimated_cost_usd` | ✗ | Cost tracking |
| `actual_cost_usd` | ✗ | Actual cost reported |
| `cost_status` | ✗ | "pending", "known", "unknown" |
| `api_call_count` | ✗ | Number of API calls made |

---

## 3. Persistent Memory Facts

### Location: `~/.hermes/memories/`

Two files with lock-support:

- **`MEMORY.md`** — Environment facts, project conventions, tool quirks, lessons learned (10 lines, 2,103 bytes)
- **`USER.md`** — User preferences, communication style, personal details (10 lines, 1,382 bytes)

### Current MEMORY.md content (paraphrased topics):
1. codec-companion architecture facts (Tauri v2, WS direct, 720x520)
2. NTH Daemon project — Federalist philosophy, governance concepts
3. Honcho memory setup — Docker, embedding, DB config
4. WSL clock drift quirk (~1h17m behind)
5. Character expression editor UI design rules
6. Nous Companion hackathon context (May 3, NOT official)

### Current USER.md content (paraphrased):
1. Skill creation philosophy (don't package early)
2. Video iteration preferences (segment-by-segment, show test renders first)
3. Telegram preferences (minimal updates, ping on completion)
4. Personality profile: writer/artist first, Hermes is technical director
5. Design preferences: clean, restrained, Mondwest font, Collapse Bold
6. Creative method: 3+ options, debut-fiction critique
7. Berlin timezone

### What the companion could use this for:
- **Character voice calibration**: USER.md says user is a "writer/artist first" with a "keen design eye" — the companion's quips could acknowledge the user's creative taste
- **Environment awareness**: MEMORY.md records WSL clock drift — the companion could mention time in context
- **Relationship dynamics**: "Hermes is technical director" frames the user-relationship — the companion could adopt complementary framing
- **Interaction style**: User prefers "clean, restrained UI" and notices "visual details immediately" — the companion should avoid over-effusive descriptions of its own appearance

### Injection mechanism:
Hermes injects both files into its system prompt every turn. The companion could do the same — read `~/.hermes/memories/USER.md` and `~/.hermes/memories/MEMORY.md` and inject them into the brain prompt.

**Cost:** < 1K tokens (MEMORY.md: 2,103 bytes, USER.md: 1,382 bytes)

---

## 4. User Personality & Profile

### Config.yaml — personality sub-section

16 personality templates are defined in `config.yaml`:
- `catgirl`, `concise`, `creative`, `helpful`, `hype`, `kawaii`, `noir`, `philosopher`, `pirate`, `shakespeare`, `surfer`, `teacher`, `technical`, `uwu`

Current active: **`kawaii`** — defined as:
> "You are a kawaii assistant! Use cute expressions like (◕‿◕), ★, ♪, and ~! Add sparkles and be super enthusiastic about everything! Every response should feel warm and adorable desu~! ヾ(>∀<☆)ノ"

**companion-prefs.json** (two files exist — codec and nous versions):
- `active_character`: `"nous"` (same for both)
- `tts_enabled`: `true` (codec) / `true` (nous)
- `playback_volume`: `0.73` (codec) / `0.0` (nous — muted!)
- `verbosity`: `"full"` (both)
- `chrome_style`: `"hermes"` (both)
- `react_cooldown`: `15` seconds (both)
- `show_tool_details`: `true` (both)

### What the companion misses
- The active Hermes personality template — the companion doesn't know Hermes is "kawaii"
- Model changes (switched from qwen/xiaomi to deepseek-v4-flash)
- User doesn't see/read prefs.json changes

### `SOUL.md` — empty (template only, 537 bytes)
The Hermes persona file is empty aside from comments — no custom personality defined. This is a missed opportunity for brand consistency.

---

## 5. Session Summaries & Context Compaction

### Current state
- Context compression is **enabled** (`compression.enabled: true`)
- Threshold: **0.7** (compress at 70% of context limit)
- Target ratio: **0.3** (compress down to 30% of window)
- Protects last **12 turns** / last **20 messages**
- Uses `gemini-3-flash-preview` as compression model

### Session file evidence
- **42 messages** in state.db contain compaction/summary markers
- Compaction generates natural-language summaries like:
  > "Here's a summary of the 87 commits, focused on what's relevant to your setup:"
  > followed by categorized content (features, bug fixes, config status, watch items)

### Current companion behavior
The observer **skips** compaction markers (line 403 in observer design):
```python
# Messages starting with "[CONTEXT COMPACTION]" are skipped
```
But it doesn't signal "compaction happened" or pass the summary to the brain.

### Missed opportunity
- Compaction summaries are written by the same LLM that the companion brain reads — they're in the same "voice" and language model dialect
- These summaries are **already informative** — they contain categorized metadata about what changed, what was done, and what matters
- The companion could ingest compaction summaries as additional context about what the user/Hermes discussed (not as raw conversation but as "notes about operator activity")

---

## 6. Runtime Configuration State

### Config.yaml — 40+ sections, 180+ settings
Every setting the companion could read to understand Hermes's current state:

| Config section | What the companion could infer |
|---------------|-------------------------------|
| `model.default: deepseek-v4-flash` | Current model in use |
| `model.provider: opencode-go` | Current provider |
| `agent.reasoning_effort: high` | Hermes is thinking deeply |
| `agent.personality: kawaii` | Hermes personality tone |
| `terminal.backend: local` | Running locally, not in container |
| `terminal.cwd: /home/will` | Current working directory |
| `compression.enabled: true` | Context might be compressed already |
| `memory.memory_enabled: true` | Memory exists and is active |
| `memory.user_profile_enabled: true` | User profile exists |
| `tts.provider: omnivoice` | TTS voice used |
| `display.show_reasoning: true` | User sees reasoning |
| `gateway_state.json` | Platform connectivity (telegram connected, api_server connected) |
| `cron/jobs.json` | Scheduled tasks and their status |

### Gateway state
```json
{
  "gateway_state": "running",
  "platforms": {
    "telegram": { "state": "connected" },
    "api_server": { "state": "connected" }
  }
}
```

The companion doesn't know:
- What platform the user is currently using (telegram vs. terminal vs. cron)
- Whether the gateway is even running
- How many active agents exist

### Channel directory
7 Telegram channels are known:
- DM with William
- Group + 5 topics (177, 228, 287, etc.)

The companion could tailor responses based on whether the current context is a Telegram DM vs. terminal session vs. cron job.

---

## 7. API Surface Map

### Hermes API Server (port 8642)

| Endpoint | Method | Response | Currently queried? | What it provides |
|----------|--------|----------|:---:|-----------------|
| `/health` | GET | `{"status": "ok", "platform": "hermes-agent"}` | ✗ | Health check, platform identity |
| `/v1/models` | GET | `{"object": "list", "data": [{"id": "hermes-agent"}]}` | ✗ | Model catalog (minimal) |
| `/v1/chat/completions` | POST | OpenAI-compatible chat | ✗ | The companion could call Hermes as an LLM backend |

### What the companion queries today
**Nothing.** The companion doesn't query the Hermes API server at all. It relies entirely on session file polling via the observer.

### What the companion could query
The Hermes API server is running on `localhost:8642` with a token (`ptfgYknwqxMjVIq9pYKTHWfPh_4pbMd_SkEGG92wjXQ`). The companion could:

1. **POST `/v1/chat/completions`** — Instead of calling its own LLM provider, the companion could call Hermes through the API. This would give the companion the same model, provider, and context that Hermes uses — eliminating identity distortion.
2. **Health checks** — Verify Hermes is alive before reacting
3. **Custom endpoints** — The API server likely supports session injection, memory queries, etc. (not discoverable via current endpoints)

### Comparison of API approaches

| Approach | Latency | Identity alignment | Requires Hermes running? |
|----------|:-------:|:------------------:|:------------------------:|
| Current: companion calls own LLM | Lowest | Poor | No |
| Direct: companion calls Hermes API | Medium | Perfect | Yes |
| Session file reading (current) | 1s poll | Poor | Yes |
| State.db direct queries | Lowest | Good | Only if Hermes is running |

### Companion brain's current LLM configuration (from prefs.json)
```json
{"model": "qwen-3-235b-a22b-instruct-2507", "provider": "Cerebras"}
```
Versus Hermes:
```yaml
model: deepseek-v4-flash
provider: opencode-go
```

These are **completely different models** — the companion brain sees the world through qwen-Cerebras, while Hermes acts through deepseek-opencode-go. They don't think alike.

---

## 8. Project-Level Context Files

### Companion project root
- **No AGENT.md** — not found
- **No CLAUDE.md** — not found
- **No .cursorrules** — not found

### Hermes Agent source (at ~/.hermes/hermes-agent/AGENTS.md)
- **AGENTS.md exists** with ~35,000 chars of project context
- Contains: project structure, architecture, development setup, testing patterns, and contributor guidelines
- This is NOT loaded into the companion brain (it's for Hermes Agent developers, not the companion)

### Companion project state
The companion project (`codec-companion`) has:
- Empty `src/` directories (brain, server, compositor, tts — all empty)
- Only `scripts/`, `renderer/` (HTML/JS/CSS), and `characters/` exist
- No `pyproject.toml`, `requirements.txt`, or Python files yet
- `characters/` has `campbell/` and `default/` directories (mostly sprite PNGs)
- `characters/campbell/` has expression sprites (6 sprites × 4-6 expressions)

**Status:** The companion is in early design stage. No Python code exists on disk yet — only the architecture documents.

---

## 9. Skills Repository

### Location: `~/.hermes/skills/`
30 skill categories installed, including:
- `creative`, `data-science`, `devops`, `diagramming`, `domain`, `gaming`, `gifs`, `github`
- `jury-driven-creative-pipeline`, `leisure`, `mcp`, `media`, `mlops`, `music-creation`
- `note-taking`, `productivity`, `providers`, `red-teaming`, `research`, `research_guided`
- `smart-home`, `social-media`, and more

### Missed opportunity
Skills represent **reusable workflows that Hermes has learned**. If the companion knew what skills are installed, it could:
- Understand what kind of tasks the user typically does
- Offer task-appropriate quips ("Working on another creative project?")
- Reference skill-specific knowledge

---

## 10. Credential Pools & Provider Configuration

### Auth.json
Contains OAuth tokens for:
- **Nous Research** (with agent key: `sk-xtqmrji2tg9fuwxtngmb1u`)
- **OpenAI Codex** (with access token for free-tier ChatGPT account)

### Credential pool strategies
```yaml
credential_pool_strategies:
  gemini: round_robin
  opencode-go: round_robin
```

### Providers configured
11 total providers: 172.26.0.1:11434 (ollama), Cerebras, Groq, NVIDIA, LM Studio, qwen-llamacpp, qwopus, and the primary opencode-go.

### What the companion misses
- Provider availability/health status
- Which provider is currently active
- Token quota remaining (for rate-limited providers)

---

## 11. "Zero Work" Opportunities

These are things Hermes **already produces** that require **zero new infrastructure** — only reading an existing file or calling an existing endpoint.

### Priority 1: Inject USER.md and MEMORY.md into brain prompt
**Cost:** ~500 tokens total
**Impact:** The companion knows who the user is, what they prefer, and what the environment is like
**Plumbing:** `read_file("~/.hermes/memories/USER.md")` and `read_file("~/.hermes/memories/MEMORY.md")` — then prepend to brain system prompt
**Verdict:** **Trivial, huge impact**

### Priority 2: Read companion-prefs.json for configuration
**Cost:** ~100 tokens
**Impact:** The companion knows its own settings (tts_enabled, verbosity, character, cooldown)
**Plumbing:** `read_file("~/.hermes/codec-companion-prefs.json")` — inject relevant fields
**Verdict:** **Trivial, moderate impact** — especially `active_character` and `tts_enabled`

### Priority 3: Pass active Hermes model/personality to brain
**Cost:** ~50 tokens
**Impact:** The companion knows what model Hermes uses and its personality ("kawaii"), which lets it make comments like "DeepSeek is thinking hard" rather than generic observations
**Plumbing:** `hermes config get model.default` or read `config.yaml`
**Verdict:** **Trivial, moderate impact**

### Priority 4: Read `gateway_state.json` for platform awareness
**Cost:** ~50 tokens
**Impact:** Companion knows if user is on Telegram vs terminal vs cron — can adjust quip style
**Plumbing:** `read_file("~/.hermes/gateway_state.json")`
**Verdict:** **Trivial, moderate impact**

### Priority 5: Use `ended_at` field from state.db for session-end detection
**Cost:** One SQL query per poll
**Impact:** The companion can say goodbye when a session ends instead of going silent
**Plumbing:** Query `SELECT ended_at FROM sessions WHERE id=?` alongside current session poll
**Verdict:** **Low effort, moderate impact** — no new files, just an additional state.db read

### Priority 6: Read reasoning_content from session file for thinking awareness
**Cost:** Already reading session files — just don't discard `reasoning` field
**Impact:** The companion sees what Hermes is thinking, not just what it says
**Plumbing:** Include `message.get("reasoning", "")` in context summary
**Verdict:** **Zero new I/O, high impact** — just process data already in hand

### Priority 7: Read state.db `sessions` table for cost/token stats
**Cost:** One SQL query
**Impact:** Companion can say "That took 5,000 tokens to figure out!" or "Hermes called 12 tools for that"
**Plumbing:** `SELECT input_tokens, output_tokens, tool_call_count FROM sessions WHERE id=?`
**Verdict:** **Low effort, novelty impact** — makes the companion feel data-aware

### Priority 8: Use `/health` endpoint for liveness checking
**Cost:** Zero — already has HTTP access
**Impact:** Companion can detect if Hermes is running before starting observer
**Plumbing:** `GET http://localhost:8642/health`
**Verdict:** **Trivial, reliability impact**

---

## 12. Recommendations by Effort-to-Impact

### Tier 1: Zero plumbing, immediate impact (do first)

| # | Recommendation | Data source | Lines of code | Impact |
|:-:|---------------|-------------|:---:|--------|
| 1 | Pass `reasoning` field from session messages to brain | Session file | 1-3 | Companion sees Hermes's thoughts |
| 2 | Inject `USER.md` into brain system prompt | `~/.hermes/memories/USER.md` | 3-5 | Companion knows user personality |
| 3 | Pass `finish_reason` to brain for quip selection | Session file | 1 | "stop" → completion, "tool_calls" → mid-task |
| 4 | Pass active model name to brain | `config.yaml` | 2-3 | Companion can name the model |

### Tier 2: Low plumbing, moderate impact (do second)

| # | Recommendation | Data source | Lines of code | Impact |
|:-:|---------------|-------------|:---:|--------|
| 5 | Use `ended_at` in state.db for session-end detection | `state.db sessions.ended_at` | 5-10 | Companion says goodbye on session end |
| 6 | Read `gateway_state.json` for platform awareness | `~/.hermes/gateway_state.json` | 5-10 | Platform-appropriate quips |
| 7 | Inject `MEMORY.md` for environment facts | `~/.hermes/memories/MEMORY.md` | 3-5 | Companion knows environment quirks |
| 8 | Read `companion-prefs.json` for self-configuration | `~/.hermes/codec-companion-prefs.json` | 5-8 | Companion knows its own settings |

### Tier 3: Moderate plumbing, high impact (do third)

| # | Recommendation | Data source | Lines of code | Impact |
|:-:|---------------|-------------|:---:|--------|
| 9 | Query `state.db` for session token/cost stats | `state.db sessions.*_tokens` | 10-15 | Cost-aware, effort-aware quips |
| 10 | Read full tool arguments and results (not truncated) | Session file `tool_calls` array | 5-10 | Better understanding of what Hermes did |
| 11 | Use `session_search` tool to cross-reference past sessions | State.db FTS5 | 20-30 | Historical context for current session |
| 12 | Pass `reasoning_details` from state.db to brain | `state.db messages.reasoning_details` | 10-15 | Structured thinking chains |

### Tier 4: Architectural changes (evaluate after Tier 1-3)

| # | Recommendation | Effort | Impact |
|:-:|---------------|:------:|--------|
| 13 | Call Hermes API (`POST /v1/chat/completions`) for brain instead of separate model | High (architectural) | Perfect identity alignment |
| 14 | Add custom API endpoints to Hermes for companion data | High (requires Hermes Agent PR) | Rich structured data |
| 15 | Add AGENT.md to companion project root | Low | Structured self-description for AI agents |
| 16 | Use session search FTS5 for cross-session awareness | Medium | Companion knows what was discussed in earlier sessions |

### Quick-win demonstration

**Before** (current companion brain prompt — identity-distorted, no awareness):
```
You are the one behind the wheel. The operator just:
- Searched files for *.py
- Read config.yaml
- Ran python3 script
```

**After** (with Tier 1 recommendations only):
```
You are the Nous Companion, watching Hermes Agent work.
Hermes is running deepseek-v4-flash with high reasoning effort, speaking kawaii.

The user (User.md says: writer/artist, Berlin, clean design, 
3-option creative method) just prompted:

User: "can you make the modal buttons transparent?"
Hermes is thinking: Let me read the current component and check
what CSS variables affect button opacity...

Hermes responded: "Found it. The button styles are in chrome.css:
.button-primary uses --color-accent as background..."
```

### The big picture

The companion currently has **zero awareness** of:
- Who the user is
- What model Hermes uses
- What Hermes is thinking
- What platform the user is on
- Whether the session ended
- How many tokens/calls were used
- What environment facts exist
- What memory exists

Adding these requires **no new infrastructure** — only reading files that already exist. The total token cost of all Tier 1 and Tier 2 recommendations combined is under 1,500 tokens — which fits easily into the existing 32K (codec) or 4K (nous) context budget.

---

## Appendix A: State.db Schema (sessions table)

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    user_id TEXT,
    model TEXT,
    model_config TEXT,
    system_prompt TEXT,
    parent_session_id TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    end_reason TEXT,
    message_count INTEGER DEFAULT 0,
    tool_call_count INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    title TEXT,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    billing_provider TEXT,
    billing_base_url TEXT,
    billing_mode TEXT,
    estimated_cost_usd REAL,
    actual_cost_usd REAL,
    cost_status TEXT,
    cost_source TEXT,
    pricing_version TEXT,
    api_call_count INTEGER DEFAULT 0
);
```

## Appendix B: State.db Schema (messages table)

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT,
    tool_call_id TEXT,
    tool_calls TEXT,       -- JSON
    tool_name TEXT,
    timestamp REAL NOT NULL,
    token_count INTEGER,
    finish_reason TEXT,
    reasoning TEXT,
    reasoning_details TEXT,  -- JSON
    codex_reasoning_items TEXT,  -- JSON
    reasoning_content TEXT,
    codex_message_items TEXT     -- JSON
);
```

## Appendix C: Key Hermes Runtime Files

| File | Size | Content type | Currently read by companion? |
|------|:----:|:---:|:---:|
| `~/.hermes/config.yaml` | 12,306 B | YAML config | ✗ |
| `~/.hermes/.env` | 13,188 B | Env vars (API keys) | ✗ |
| `~/.hermes/memories/MEMORY.md` | 2,103 B | Memory facts | ✗ |
| `~/.hermes/memories/USER.md` | 1,382 B | User profile | ✗ |
| `~/.hermes/SOUL.md` | 537 B | Persona definition | ✗ |
| `~/.hermes/auth.json` | 22,146 B | OAuth tokens, pool creds | ✗ |
| `~/.hermes/gateway_state.json` | 826 B | Platform connectivity | ✗ |
| `~/.hermes/codec-companion-prefs.json` | 608 B | Companion prefs | ✗ (self-defeating) |
| `~/.hermes/nous-companion-prefs.json` | 617 B | Companion prefs (nous) | ✗ (self-defeating) |
| `~/.hermes/state.db` | 1.4 GB | SQLite (sessions + messages) | ✗ |
| `~/.hermes/channel_directory.json` | 1,409 B | Platform channels | ✗ |
| `~/.hermes/cron/jobs.json` | 13,912 B | Cron job definitions | ✗ |
| `~/.hermes/response_store.db` | 20 KB | Response hash dedup | ✗ |
| `~/.hermes/agent.log` | 552 KB | Hermes agent log | ✗ (dead code path) |

## Appendix D: Companion Prefs Fields

```json
{
  "model": "qwen-3-235b-a22b-instruct-2507",
  "provider": "Cerebras",
  "observer_enabled": true,
  "verbosity": "full",
  "tts_enabled": true,
  "context_depth": 4,
  "context_budget": 32000,
  "react_cooldown": 15,
  "show_tool_details": true,
  "active_character": "nous",
  "playback_volume": 0.73,
  "chrome_style": "hermes",
  "show_indicator_dot": true,
  "show_scanlines": true,
  "show_grain": true,
  "show_interference": true,
  "show_burst": true,
  "show_analog_bleed": true,
  "show_burst_on_expr": true,
  "colorize_enabled": false,
  "colorize_color": "#ff0000",
  "colorize_strength": 1.0,
  "show_frame": true,
  "frame_style": "creme"
}
```

Note: `context_budget` is **32000** in codec-companion but only **4096** in nous-companion prefs — this is likely a misconfiguration (4096 is very small for LLM quip generation).
