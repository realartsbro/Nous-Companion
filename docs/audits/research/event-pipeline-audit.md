# Event Pipeline Audit — Nous Companion

> **Date:** 2026-04-30  
> **Scope:** Full trace of every event type from Hermes session → observer → brain → quip → TTS  
> **Files analyzed:**
> - `src/server/hermes_observer.py` (1,117 lines)
> - `src/server/companion_server.py` (4,348 lines)
> - `src/brain/brain.py` (180 lines)
> - `src/tts/engine.py` (211 lines)
> - `src/compositor/animation_controller.py` (405 lines)
> - `src/compositor/audio_analyzer.py` (150 lines)
> - `src/server/scene_player.py` (535 lines)
> - `src/brain/character_loader.py` (139 lines)

---

## 1. Complete Event Catalog

### A. Observer-Emitted Events (Hermes Observer → Companion Server)

These events are dispatched by `HermesObserver._poll_once()` after detecting changes in Hermes session files. The observer polls every 1 second.

#### 1. `EVENT_SESSION_SWITCHED` ("session_switched")

| Property | Detail |
|----------|--------|
| **Trigger** | Observer's auto-follow detects a different session file is now the most recently modified live session, and the cooldown (3s) has elapsed. |
| **Where emitted** | `_poll_once()`, line 626 |
| **Conditions** | `current != self._current_session_file` AND switch cooldown elapsed AND current session not actively receiving new messages. |
| **Data payload** | `{session_id, message_count, model}` |
| **Companion action** | Resets session broadcast cache, broadcasts `{"type": "sessions"}` to control clients, broadcasts `{"type": "status", "status": "session: {id}"}`. |
| **Reaction?** | No quip generated. Silent status-only update. |

#### 2. `EVENT_THINKING` ("thinking")

| Property | Detail |
|----------|--------|
| **Trigger** | New user message detected in the session file (message with `role == "user"`). |
| **Where emitted** | `_poll_once()`, line 705 |
| **Conditions** | `role == "user"` AND `message_count > self._last_count()`. |
| **Data payload** | `{query, context, session, session_id, message_count}` |
| **Companion action** | Cancels idle timer, cancels current TTS (user interjected), schedules a delayed prompt reaction via `_delayed_prompt_react()`. Broadcasts `{"type": "status", "status": "watching..."}` and `{"type": "hermes_event"}`. |
| **Reaction?** | Yes — fires `_do_prompt_react(query)` after `_prompt_ack_delay` (0.0s). Falls back to pre-canned acks if LLM times out (>5s). |

#### 3. `EVENT_TOOL_USE` ("tool_use")

| Property | Detail |
|----------|--------|
| **Trigger** — **Assistant with tool_calls** | Assistant message with `tool_calls` array (line 715). |
| **Trigger** — **Approval content** | Assistant message without tool_calls but content matches `_is_approval_request()` (line 771). |
| **Trigger** — **Tool result** | Tool role message with result content (line 817). |
| **Where emitted** | `_poll_once()`, lines 756, 778, 817 |
| **Data payload** | Varies by sub-type, includes: `{tool_count, tools[], tool_args[], trigger_query, assistant_reasoning, session, message_count, significance, approval_pending, clarify_questions[]}` |
| **Companion action** | (1) **Approval/sig>=10**: Immediate `_do_approval_react()`. (2) **sig >= 3**: Buffer into `_tool_cluster_buffer`, flush after 2s via `_flush_tool_cluster_after()`. (3) **sig < 3**: Silently dropped. Always broadcasts status `"using {tools}..."`. |
| **Reaction?** | Yes for approval/sig≥10 (immediate). Yes for sig≥3 (buffered, delayed 2s). No for sig<3. |

#### 4. `EVENT_COMPLETE` ("complete")

| Property | Detail |
|----------|--------|
| **Trigger** | Assistant message without tool_calls AND not an approval request (line 794). |
| **Where emitted** | `_poll_once()`, line 794 |
| **Conditions** | `role == "assistant"`, no `tool_calls`, `content` is NOT an approval request (or content >= 300 chars). |
| **Data payload** | `{response, tool_chain[], session, session_id, message_count}` |
| **Companion action** | Cancels any pending tool cluster. Cancels any pending prompt ack (superseded). Checks cooldown (unless prompt already reacted this turn). Checks verbosity: "brief" → pre-canned completion quip; "full" → formats session context, calls LLM via `_do_contextual_react()`. Starts idle timer. |
| **Reaction?** | Yes, always (subject to cooldown/duplicate checks). |

#### 5. `EVENT_RESPONDING` ("responding")

| Property | Detail |
|----------|--------|
| **Trigger** | Defined as constant (line 27) but **never emitted by `_poll_once()`**. Only available via manual API (`hermes_observer.py` line 1102-1104: `trigger_responding()`). |
| **Where emitted** | Only from `trigger_responding()` — manual API. |
| **Companion action** | **None**. Companion server never subscribes or acts on this event. |
| **Reaction?** | Dead path. |

#### 6. `EVENT_IDLE` ("idle")

| Property | Detail |
|----------|--------|
| **Trigger** | Defined as constant (line 29). Only available via `trigger_idle()` manual API (line 1114-1116). |
| **Where emitted** | Only from manual API. |
| **Companion action** | **None**. Not imported or handled by companion server. |
| **Reaction?** | Dead path. |

#### 7. Additional from `watch_logs()` (Legacy)

| Property | Detail |
|----------|--------|
| **Method** | `watch_logs()` (line 1044-1094) watches `~/.hermes/logs/agent.log` for regex patterns matching `EVENT_THINKING`, `EVENT_TOOL_USE`, `EVENT_COMPLETE`. |
| **Used?** | **Never called.** The observer uses session-file polling (`start()` → `_watch_loop()`), not log watching. Dead code path. |

---

### B. Companion-Initiated Events (not from observer)

#### 8. `EVENT_IDLE` — Idle line (internal timer)

| Property | Detail |
|----------|--------|
| **Trigger** | `_start_idle_timer()` called after completion reactions start a timer with random delay (10-60 min). When timer fires, `_fire_idle_line()` picks the next line from the character's shuffle bag. |
| **Where originated** | `companion_server.py` line 4006-4035 |
| **Data payload** | Character-defined idle line text (pre-written, no LLM). |
| **Reaction?** | Text + optional TTS. No event emitted through observer. |

#### 9. `EVENT_SCENE` — Scene player events

| Property | Detail |
|----------|--------|
| **Types** | `scene_loaded`, `scene_cue`, `scene_overlay`, `scene_complete`, `scene_error` |
| **Trigger** | Scripted `.nous-scene.json` file loaded and played via WebSocket command. |
| **Reaction?** | Scene player drives expression + TTS directly. Not a quip. |

---

### C. Companion WebSocket Outbound Events (to renderer/control clients)

These are broadcast by the companion server to connected WebSocket clients:

| Type | When sent | Payload |
|------|-----------|---------|
| `frame` | Every animation tick (30 fps) | `{type, frame(base64), text, expression, mouth_open, server_sent_at_ms}` |
| `status` | On state changes | `{type: "status", status: "watching..."/"working..."/"speaking..."/"idle"}` |
| `hermes_event` | Every observer event received | `{type: "hermes_event", event_type, message_count, context}` |
| `text` | When companion speaks | `{type: "text", text, expression}` |
| `audio` | When TTS audio ready | `{type: "audio", audio(base64), duration_s, server_sent_at_ms}` |
| `audio_stop` | When speech cancelled | `{type: "audio_stop"}` |
| `sessions` | Periodically or on switch | `{type: "sessions", sessions[], active}` |
| `characters` | On demand | `{type: "characters", characters[], active}` |
| `character_switched` | On character change | `{type: "character_switched", character, name, ...}` |
| `expressions` | On character switch | `{type: "expressions", expressions[]}` |
| `scene_loaded` | Scene loaded | `{type: "scene_loaded", ...}` |
| `scene_cue` | Scene cue fires | `{type: "scene_cue", index, time, expression, line, ...}` |
| `scene_overlay` | Scene overlay text | `{type: "scene_overlay", text, time, ...}` |
| `scene_complete` | Scene finishes | `{type: "scene_complete", elapsed, scene_count}` |
| `scene_error` | Scene error | `{type: "scene_error", error}` |

---

## 2. Data Flow Diagram (ASCII)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Hermes Agent Process                             │
│                                                                         │
│  User Query → LLM → Tool Calls → Tool Results → Final Response          │
│                  (writes session_*.json after each step)                 │
└─────────────────────────────────────────────────────────────────────────┘
                              │ poll (1s)
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     HermesObserver._poll_once()                         │
│                                                                         │
│  Read session_*.json → diff message_count vs last_count                 │
│                                                                         │
│  New user msg?   ──→ emit EVENT_THINKING(query, context)               │
│  New assistant   ──→ has tool_calls? → emit EVENT_TOOL_USE(tools, args) │
│  msg?                no tool_calls, approval? → emit EVENT_TOOL_USE     │
│                      no tool_calls, !approval → emit EVENT_COMPLETE     │
│  Session file     ──→ emit EVENT_SESSION_SWITCHED(id)                  │
│  changed?                                                                │
└─────────────────────────────────────────────────────────────────────────┘
                              │ callback
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   CompanionServer._on_hermes_event()                    │
│                                                                         │
│  EVENT_THINKING:                                                        │
│   ├─ Cancel idle timer, cancel current TTS                             │
│   └─ Schedule _delayed_prompt_react(query)                             │
│                                                                         │
│  EVENT_TOOL_USE:                                                        │
│   ├─ approval/sig≥10 → _do_approval_react() [immediate]                │
│   ├─ sig≥3 → buffer → 2s flush → _do_tool_react()                     │
│   └─ sig<3 → silent drop                                               │
│                                                                         │
│  EVENT_COMPLETE:                                                        │
│   ├─ Cancel tool cluster, cancel pending prompt ack                    │
│   ├─ Check cooldown & verbosity                                         │
│   ├─ "brief" → pre-canned quip                                         │
│   └─ "full" → _do_contextual_react(context)                            │
│                                                                │
│  EVENT_SESSION_SWITCHED: broadcast status update only                   │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Reaction Methods                                                       │
│                                                                         │
│  _do_prompt_react(query):                                               │
│   ├─ Try LLM via _generate_quip(prompt, "prompt") [5s timeout]         │
│   └─ Fallback: pre-canned prompt acks (shuffle bag)                     │
│                                                                         │
│  _do_approval_react():                                                  │
│   └─ LLM via _generate_tool_quip(prompt, "approval")                   │
│                                                                         │
│  _do_tool_react():                                                      │
│   └─ LLM via _generate_tool_quip(prompt, "tool")                       │
│                                                                         │
│  _do_contextual_react(context):                                         │
│   └─ LLM via _generate_quip(prompt, "completion")                      │
│                                                                         │
│  All → _synthesize_and_play(quip, expression)                           │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  _synthesize_and_play → _do_synthesize_and_play                         │
│                                                                         │
│  1. Broadcast {"type": "text", text, expression}                        │
│  2. Broadcast {"type": "status", "status": "speaking..."}              │
│  3. _synthesize_tts(text, expression):                                  │
│     ├─ OmniVoice (voice clone via Gradio) OR                           │
│     ├─ edge-tts (free fallback) OR                                      │
│     └─ NoOp (silent)                                                    │
│  4. anim.load_audio(tmp_wav) → AudioAnalyzer computes per-frame RMS    │
│  5. Broadcast {"type": "audio", audio(base64), duration_s}              │
│  6. Animation loop drives lip-sync from RMS values                      │
│  7. Wait for audio duration, then status = "idle"                       │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Post-Speech                                                           │
│                                                                         │
│  _start_idle_timer():                                                   │
│   └─ Schedule random idle line in 10-60 min                             │
│                                                                         │
│  AnimationController.run_loop():                                        │
│   └─ 30fps: _update_mouth(dt) + _update_eyes(dt) + _update_transition  │
│      → build_event("frame") → send to renderer                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Where Misleading Claims Could Originate

This section enumerates the gap between what Hermes actually did and what the companion "thinks" happened — each is a potential source of hallucinations or misleading reactions.

### 3.1 Session-File Polling (Fundamental Architectural Gap)

The observer reads **serialized session files**, not live Hermes state. This creates several distortions:

| Issue | Detail |
|-------|--------|
| **Stale data** | Poll interval is 1s. If multiple messages arrive within that window, they're batched. The companion sees an atomic view of what happened, not the sequence. |
| **File mid-write** | `_poll_once()` catches `json.JSONDecodeError` (line 833) and silently retries. If writes are frequent, events can be lost. |
| **Truncated content** | All message content is truncated to 800 chars when emitted (line 697). The companion never sees full context. |
| **No streaming visibility** | The companion has no idea if Hermes is currently generating a response — it only sees the final persisted state. |

### 3.2 Tool-Use Event Ambiguity

The observer emits `EVENT_TOOL_USE` for **three different situations**, but the companion reacts to all of them with the same code path (just different significance scores):

| Observer source | Companion receives | Risk |
|-----------------|-------------------|------|
| Assistant message with `tool_calls` (line 715) | `{tools[], tool_args[], trigger_query, assistant_reasoning, significance}` | Companion sees what Hermes *planned* to do, not what *actually happened*. If a tool call fails, the companion already reacted to it. |
| Tool result message (line 817) | `{tool_result, tool_name, significance}` | The companion sees only the first 200 chars of the result. Critical output is truncated. |
| Assistant content that looks like an approval request (line 771) | `{approval_pending: True, clarify_questions[]}` | This is **heuristic-based** (`_is_approval_request()` regex match). False positives cause the companion to interrupt and react urgently when Hermes was just discussing options. |

### 3.3 Tool Chain Extraction — Only One Level Deep

`_extract_recent_tool_chain()` (observer line 1024-1040) only looks at the **last** assistant message with tool_calls. If Hermes used multiple tool calls in sequence, only the final batch appears in the EVENT_COMPLETE `tool_chain`. The companion's completion reaction then says things like "Found it in the config" when in reality it was a 10-tool pipeline.

### 3.4 Significance Scoring — Heuristic + Lossy

The significance scoring system (`_score_tool_significance`, observer line 906-983) is a **static heuristic** that categorizes tool names and crude argument patterns:

| Heuristic | Problem |
|-----------|---------|
| `_NOISY_TOOLS = {"process", "browser_snapshot", ...}` | A `process(wait)` that just polled is treated as noise. But a `process(wait)` that completed a critical build is also noise. Context loss. |
| `_LOW_SIG_PATHS` regex | Writes to `config.yaml` or `settings.json` get score 3 (low). But modifying `config.yaml` is highly significant. |
| `_ACTION_TOOLS` | A `terminal` running `ls` gets score 3 (reading), while a `terminal` running `git push` gets score 6. But the companion only sees "terminal: command: ..." — it doesn't see the output. |
| Approval keyword regex | `_APPROVAL_KEYWORDS` catches phrases like "are you sure" but also catches "I need you to know that..." — false positives. |

### 3.5 Context Summarization — Irreversible Information Loss

| Loss point | Detail |
|------------|--------|
| **`_build_context_summary()`** (observer line 842) | Concatenates recent messages into a pipe-delimited string, each truncated to 120 chars. Original structure and full meaning lost. |
| **`_format_session_context()`** (companion line 2956) | Further truncates: only last N exchanges are detailed; earlier exchanges reduced to 50-char topic fragments. |
| **`_sanitize_text()`** (companion line 3067) | Replaces "Hermes" → "the system", "AI assistant" → "I", "language model" → "". The LLM brain is told it's the one doing the work ("I"), creating an explicit identity distortion. |
| **Tool chain prefixing** (companion line 3021-3034) | `read_file` → "File read", `write_file` → "File edited", `terminal` → "Command". The LLM brain gets these labels but not the actual content or output. |

### 3.6 Brain Prompt — Critical Identity Distortion

The companion brain's system prompt (companion line 854-867, and the `_do_contextual_react` prompt at line 3280-3285) explicitly tells the LLM:

> *"You are the one behind the wheel — speak in first person. Reference specific tools or files if they matter. Do NOT mention Hermes, AI assistants, or any external system."*
>
> *"If you only READ or SEARCHED a file, do NOT claim you edited, modified, or changed it."*

Despite the disclaimer about read vs. write, the prompt pushes the LLM to **claim agency** over Hermes's actions. The combination of:
1. Sanitized context (Hermes → "the system")
2. First-person framing ("You are the one behind the wheel")
3. Truncated tool summaries (only seeing file paths, not outputs)
4. No visibility into Hermes's actual model, provider, or reasoning

...makes it very likely the companion **hallucinates details** about what was accomplished. The LLM brain has no way to verify it actually changed a file — it only sees the label "File edited: write_file (writing src/foo.py)".

### 3.7 Tool Cluster Flushing — Temporal Blindness

When multiple tools fire within 2 seconds, they're buffered and reacted to as one cluster. The companion sees:

```
- terminal: command: git push origin main
- terminal: command: npm run build
```

...but has no idea which order they happened, whether one failed, or whether the second depended on the first. The LLM might say "Pushed and built" when in reality the push failed and the build ran on old code.

### 3.8 Completion Irreversibility

Once `EVENT_COMPLETE` fires, the companion reacts **even if Hermes subsequently edits its response** (session files are immutable append-only, but Hermes sometimes regenerates). The companion's reaction is based on the response at capture time.

---

## 4. Dead Paths — Events Observed But Never Resulting in a Reaction

### 4.1 `EVENT_RESPONDING` ("responding")

- **Defined** in `hermes_observer.py` line 27
- **Never emitted** by `_poll_once()` — the primary detection loop
- **Only available** via manual API `trigger_responding()` (line 1102)
- **Not imported** in `companion_server.py` (line 51 only imports `EVENT_THINKING`, `EVENT_COMPLETE`, `EVENT_TOOL_USE`, `EVENT_SESSION_SWITCHED`)
- **Result:** Code weight with zero runtime effect

### 4.2 `EVENT_IDLE` ("idle")

- **Defined** in `hermes_observer.py` line 29
- **Never emitted** by `_poll_once()`
- **Only available** via manual API `trigger_idle()` (line 1115)
- **Not imported** in `companion_server.py`
- **Result:** Dead constant

### 4.3 Legacy Log Watcher (`watch_logs()`)

- **Full implementation** at observer line 1044-1094
- **Never called** — observer only starts `_watch_loop()` which calls `_poll_once()`, not `watch_logs()`
- **Result:** Dead code path. If someone mistakenly calls `watch_logs()` instead of `start()`, they'd get log-based events that duplicate or conflict with file-polling events.

### 4.4 Significance Score 0-2 (below `_tool_min_significance = 3`)

- **Observed:** Tool events with significance < 3 are received by `_on_hermes_event()`
- **Action:** Buffering is skipped, no reaction generated
- **Status broadcast still happens** (line 2750) — the client sees "using tools..." but companion says nothing
- **Common low-sig tools lost:** `browser_snapshot` (score 1), `process(poll/list)` (score 0), file reads on cache/temp paths (score 2), `browser_navigate` (score 1)

### 4.5 Tool Events During `_is_reacting`

- **Observed:** Non-urgent tool events (significance < 10) while `_is_reacting == True` are simply dropped
- **Line 2778:** `if self._is_reacting: return`
- **Result:** If a tool event arrives while the companion is speaking, it's silently lost

### 4.6 Duplicate Completion Reactions

- **Observed:** `EVENT_COMPLETE` events where `_is_duplicate_reaction()` returns True (same response hash within the last 5 reactions)
- **Line 2870:** `if self._is_duplicate_reaction(trigger_hash): return`
- **Result:** Identical responses (e.g., same error message, same "Let me know what you think") are silently deduplicated

---

## 5. Missing Coverage — Hermes Events NOT Observed That Should Be

### 5.1 Model Call Stream (No Streaming Awareness)

| What's missing | Impact |
|----------------|--------|
| Hermes can stream text (token by token) via the API server. The companion has **zero visibility** into streaming. | The companion can't show real-time transcription, can't display "thinking" dots during generation, and has to wait for the full response to be written to disk. |
| The observer's `EVENT_RESPONDING` was designed for this but **never implemented** in `_poll_once()`. | A huge UX gap: the companion sits in "watching..." state while Hermes is actively generating a multi-paragraph response with tool calls. |

### 5.2 Tool Execution Results (Output, Not Just Invocation)

| What's missing | Impact |
|----------------|--------|
| The observer captures `tool_call_id` and links tool results to tool names (observer line 804-813), but only sends the first 200 chars of the result. | The companion never sees what a command actually printed. A `terminal` running `ls` returns the file listing, but the companion only sees `tool_name: "terminal"`. |
| No structured parsing of common tool outputs (test results, build output, search snippets). | The companion can't say "3 tests passed" — it sees "Result: ..." truncated. |

### 5.3 Hermes Internal State Changes

| What's missing | Impact |
|----------------|--------|
| Model switching (`EVENT_MODEL_SWITCHED`) | If the user switches models mid-conversation, the companion stays silent. |
| Godmode toggle | The companion has its own godmode logic (line 869-875) but doesn't react to Hermes entering/exiting godmode. |
| Session ended naturally | `EVENT_SESSION_SWITCHED` fires when auto-follow picks a new session, but there's no "session ended" event for the old one. The companion just drops it silently. |
| Provider errors / API outages | If Hermes's API provider goes down, the companion sits in "watching..." and never knows why no further events arrive. |

### 5.4 Concurrent Session Activity

| What's missing | Impact |
|----------------|--------|
| The observer auto-follows the **single most recent** live session. If the user switches between two concurrently active Hermes sessions (e.g., one in the terminal, one in chat), the companion only sees the latest one. | The companion may be reacting to the wrong conversation entirely. |
| The 3-second session switch cooldown (line 59) means rapid toggling between sessions is delayed. | The companion can miss events during rapid session switching. |

### 5.5 Context Compaction Awareness

| What's missing | Impact |
|----------------|--------|
| Hermes performs context compaction when conversations grow long, inserting `[CONTEXT COMPACTION]` markers. The observer skips compaction markers (line 403, line 2978) but doesn't signal "compaction happened" to the companion. | The companion's brain might reference conversation details that Hermes has already compacted away — the companion thinks the conversation is longer than it actually is from Hermes's perspective. |

### 5.6 User Presence / Idle Detection

| What's missing | Impact |
|----------------|--------|
| The companion has its own idle line timer (10-60 min), but it's purely time-based. It doesn't know if the user is actually present. | The companion might deliver idle lines when no one's there, or stay silent when the user is waiting. |
| No integration with screen lock, window focus, or system idle. | Wasted quips for absent users. |

---

## 6. Summary: Event Type Coverage Matrix

| Event | Defined in Observer | Emitted by Observer | Handled by Companion | Produces Speech |
|-------|:---:|:---:|:---:|:---:|
| `thinking` | ✓ | ✓ (file poll) | ✓ | ✓ (prompt ack) |
| `responding` | ✓ | ✗ (manual only) | ✗ (not imported) | ✗ (dead path) |
| `complete` | ✓ | ✓ (file poll) | ✓ | ✓ |
| `tool_use` | ✓ | ✓ (file poll) | ✓ | ✓ (conditional on sig) |
| `idle` | ✓ | ✗ (manual only) | ✗ (not imported) | ✗ (dead path) |
| `session_switched` | ✓ | ✓ (file poll) | ✓ (status only) | ✗ |
| Idle lines (internal) | ✗ | N/A (internal timer) | ✓ | ✓ |
| Scene events (internal) | ✗ | N/A (scripted) | ✓ | ✓ (pre-generated TTS) |

---

## 7. Recommendations

1. **Add streaming awareness** — Implement `EVENT_RESPONDING` emission in `_poll_once()` to detect pending assistant messages (messages with content="", indicating Hermes is generating). This lets the companion show real-time "thinking..." state.

2. **Add tool output parsing** — Extract structured data from common tool results (test counts, file paths, error messages) and pass it to the brain for more specific reactions.

3. **Add model/provider change events** — Watch `state.db` for model/provider changes in the active session and emit events so the companion can acknowledge them.

4. **Fix the identity distortion** — The brain prompt tells the LLM "you are the one behind the wheel" but the companion has no actual agency. A more honest framing (e.g., "Your operator just did X") would reduce hallucination risk.

5. **Add end-of-session detection** — Emit a dedicated event when the current session's `ended_at` field changes from null to a timestamp, so the companion can acknowledge the conversation ended.

6. **Prune dead code** — Remove `EVENT_RESPONDING`, `EVENT_IDLE` if they're truly unused, or implement their emission in the poll loop. Remove the legacy log watcher `watch_logs()` or document it as deprecated.
