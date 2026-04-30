# Reaction Trigger Map — Nous Companion

> **Date:** 2026-04-30  
> **Scope:** Complete catalog of companion speech/silence conditions, false claim risks, settings respect audit, and post-completion event handling.  
> **Files analyzed:**
> - `src/server/companion_server.py` (4,348 lines)
> - `src/server/hermes_observer.py` (1,116 lines)
> - `src/brain/brain.py` (179 lines)
> - `src/brain/character_manager.py` (901 lines)
> - `renderer/settings.html` (7152 lines)

---

## 1. Complete Trigger Catalog — Every Condition That Produces a Companion Reaction

Every companion speech event ultimately flows through `_synthesize_and_play()` (line 3801 of `companion_server.py`). The six entry points are listed below in priority order (higher = speaks sooner/more reliably).

### 1A. Approval Reaction (`_do_approval_react`) — Priority: HIGHEST

| Property | Detail |
|----------|--------|
| **Trigger event** | `EVENT_TOOL_USE` with `approval_pending=True` or `significance >= 10` |
| **Observer emission** | 3 paths in `_poll_once()`: (1) `clarify` tool call detected (line 740-750), (2) `_is_approval_request()` matches on assistant content <300 chars (line 770-789), (3) tool result with approval keywords (line 815-824) |
| **Companion entry** | Line 2756-2775 in `_on_hermes_event()` |
| **Bypasses** | `_is_reacting` guard, all cooldowns, semantic dedup, verbosity setting |
| **Cancels** | Pending prompt ack (line 2760), pending tool cluster (line 2765-2769) |
| **LLM prompt** | Explosive: "You just attempted a maneuver that REQUIRES USER APPROVAL. React URGENTLY." Forces `serious_shouting` expression (fallback to `serious`). |
| **Fires** | **Immediately** — `asyncio.create_task()` (line 2772), no buffering, no delay |
| **Conditions to actually speak** | LLM returns valid non-empty quip (line 3457-3458) |

### 1B. Prompt Acknowledgment (`_do_prompt_react`) — Priority: HIGH

| Property | Detail |
|----------|--------|
| **Trigger event** | `EVENT_THINKING` — new user message (role == "user") detected by observer |
| **Observer emission** | Line 705-711 in `_poll_once()` |
| **Companion entry** | Line 2699-2727 in `_on_hermes_event()` |
| **Bypasses** | `_is_reacting` guard (line 2701: "MUST be instant"), all cooldowns, all semantic checks |
| **Cancels** | Idle timer (line 2708), current TTS if user interjected (line 2710-2716) |
| **Delay** | `_prompt_ack_delay` = 0.0s (line 212). Sleeps in `_delayed_prompt_react()` then calls `_do_prompt_react()`. |
| **LLM path** | Attempts `_generate_quip()` with 5-second timeout (line 3524-3527). If timeout, falls back to pre-canned acks from shuffle bag. |
| **Conditions to speak** | `len(query) >= 2` (line 2720). Observer enabled, verbosity not "silent". Not during startup grace period. LLM returns valid quip OR fallback acks are non-repetitive. |

### 1C. Completion Reaction (`_do_contextual_react`) — Priority: HIGH

| Property | Detail |
|----------|--------|
| **Trigger event** | `EVENT_COMPLETE` — final assistant response (no tool_calls, not approval) |
| **Observer emission** | Line 794-800 in `_poll_once()` |
| **Companion entry** | Line 2805-2882 in `_on_hermes_event()` |
| **Bypasses** | `_is_reacting` guard (line 2829: "escalated — they bypass _is_reacting") |
| **Respects** | `react_cooldown` setting (15s default) — BUT only if `_prompt_reacted_this_turn` is False (line 2834-2838). If the companion already ack'd the prompt this turn, completion fires regardless of cooldown. |
| **Cancels** | Pending tool cluster (line 2812-2816), pending prompt ack (line 2821-2827) |
| **Verbosity split** | `"brief"` → pre-canned brief quip from shuffle bag, no LLM (line 2847-2860). `"full"` → LLM via `_generate_quip()` with full session context (line 2862-2879). |
| **Dedup** | `_is_duplicate_reaction()` checks hash of response + tool_chain against last 5 reactions (line 2870). Also `_is_redundant_with_recent_comments()` checks structural/semantic repetition (line 3300). |
| **Startup idle timer** | Always starts after completion (line 2859 or 2882) |
| **Conditions to NOT speak** | Response <10 chars (line 2844-2845), duplicate hash, redundant text, LLM returns "..." or empty |

### 1D. Tool Cluster Reaction (`_do_tool_react`) — Priority: MEDIUM

| Property | Detail |
|----------|--------|
| **Trigger event** | `EVENT_TOOL_USE` with significance 3-9 (not approval) |
| **Observer emission** | Line 756-767 or 817-824 in `_poll_once()` |
| **Companion entry** | Line 2733-2803 in `_on_hermes_event()` |
| **Buffering** | Events with sig >= 3 are appended to `_tool_cluster_buffer` (line 2788-2795). 2-second flush timer via `_flush_tool_cluster_after()` (line 2798-2802). Multiple tools within window are aggregated. |
| **Respects** | `_is_reacting` guard (line 2778-2780): if companion is already speaking, non-urgent tool events are silently dropped. Tool cooldown (line 3379-3382): uses `react_cooldown` setting. Semantic dedup (line 3371-3374): same semantic type ("reading", "writing", etc.) within `_semantic_cooldown` (15s) is blocked. |
| **Bypasses when** | Significance >= 10 or approval_pending → escalated to approval path (bypasses all guards) |
| **LLM prompt** | "You just handled something — a fix, a find, or just a look around." First-person framing. |
| **Conditions to speak** | sig >= 3, NOT _is_reacting, NOT within tool cooldown, NOT semantically duplicate, LLM returns valid quip |

### 1E. Idle Line (`_fire_idle_line`) — Priority: LOW (Internal Timer)

| Property | Detail |
|----------|--------|
| **Trigger** | `_start_idle_timer()` called after completion reaction (line 2859, 2882) |
| **Delay** | Random: 600-3600 seconds (10-60 minutes) — line 3994 |
| **Source** | No LLM. Picks from character's `idle_lines` shuffle bag (pre-written lines). |
| **Conditions to speak** | `idle_lines_enabled=True` (line 3989), character has idle lines (line 3991-3993, 4010-4011) |
| **Cancelled by** | Any user interaction: EVENT_THINKING (line 2708), EVENT_TOOL_USE (line 2735) |
| **Restarts** | Always restarts after firing (line 4038) |

### 1F. Manual / Click-Triggered Lines (`_speak_random_line`) — Priority: MEDIUM

| Property | Detail |
|----------|--------|
| **Trigger** | WebSocket command (user clicks speak button in UI) |
| **Priority** | `priority=True` — cancels current TTS (line 4062) |
| **Source** | Same shuffle bag as idle lines |
| **Conditions** | Character must have idle lines |

---

## 2. Silence Catalog — Every Condition Where the Companion Sees an Event but Stays Silent

### 2A. Event-Level Silences (event received, no speech produced)

| # | Condition | Code Location | Impact |
|---|-----------|---------------|--------|
| 1 | **Startup grace period** (first 5 seconds after boot) | `companion_server.py` line 2662-2669 | Expression changes + status broadcasts only. ALL speech suppressed. |
| 2 | **`observer_enabled = False`** | `companion_server.py` line 2683-2697 | Expression changes + status broadcasts only. ALL speech suppressed. Observer still polls — just handler ignores. |
| 3 | **`verbosity = "silent"`** | `companion_server.py` line 2683-2697 | Same as observer_enabled=False. |
| 4 | **`EVENT_SESSION_SWITCHED`** — always silent | `companion_server.py` line 2884-2891 | Status broadcast only. No quip mechanism at all. |
| 5 | **`EVENT_RESPONDING`** — dead constant | `hermes_observer.py` line 26, never emitted by `_poll_once()` | Not imported by companion (line 51 only imports 4 types). Complete dead path. |
| 6 | **`EVENT_IDLE`** — dead constant | `hermes_observer.py` line 29, never emitted by `_poll_once()` | Not imported by companion. Complete dead path. |
| 7 | **`watch_logs()`** — dead method | `hermes_observer.py` line 1044-1094 | Full implementation but never called. `start()` launches `_watch_loop()` → `_poll_once()`, not `watch_logs()`. |

### 2B. Tool Event Silences (sig-based gating)

| # | Condition | Code Location | Impact |
|---|-----------|---------------|--------|
| 8 | **Significance < 3** | `companion_server.py` line 2783-2785 | Silent drop. Status broadcast still happens ("using tools..."). |
| 9 | **`_is_reacting = True`** (non-urgent tools only) | `companion_server.py` line 2778-2780 | Tool events with sig < 10 while companion is speaking are silently dropped. The tool is **lost forever** — not buffered, not retried. |
| 10 | **Tool cooldown active** (cluster flush) | `companion_server.py` line 3379-3382 | Entire cluster dropped silently if within `react_cooldown` since last tool reaction. Uses wall-clock, not per-tool. |
| 11 | **Semantic dedup** (cluster flush) | `companion_server.py` line 3371-3374 | Same semantic type ("reading", "writing", etc.) within `_semantic_cooldown` (15s) → cluster dropped. |
| 12 | **Empty tool_args** (cluster flush) | `companion_server.py` line 3342-3343 | If `_tool_cluster_buffer` is empty when flush fires, no-op. |
| 13 | **Buffer cancelled by COMPLETE** | `companion_server.py` line 2812-2816 | All buffered tools cleared when final response arrives. |
| 14 | **Buffer cancelled by new tool arrival** | `companion_server.py` line 2798-2799 | Old flush task cancelled, new one started. Tools aren't lost — they're re-buffered. |

### 2C. Completion Reaction Silences

| # | Condition | Code Location | Impact |
|---|-----------|---------------|--------|
| 15 | **Response < 10 characters** | `companion_server.py` line 2844-2845 | Empty/minimal responses produce no reaction. |
| 16 | **Duplicate reaction** (same response hash in last 5) | `companion_server.py` line 2870-2874 | Hash of response + tool_chain matched against 5 most recent. |
| 17 | **LLM returns empty/"..."** | `companion_server.py` line 3295-3296 | Quip text is "..." or empty → no speech |
| 18 | **Redundant with recent comments** (structural/pattern check) | `companion_server.py` line 3300-3302 | `_is_redundant_with_recent_comments()` checks last 6 comments within 180s window. |
| 19 | **Cooldown active AND no prompt ack this turn** | `companion_server.py` line 2834-2838 | If prompt didn't ack this turn, cooldown (default 15s) applies. |

### 2D. Prompt Acknowledgment Silences

| # | Condition | Code Location | Impact |
|---|-----------|---------------|--------|
| 20 | **Query too short** (< 2 chars) | `companion_server.py` line 2720 | No prompt ack for empty/tiny messages. |
| 21 | **LLM timeout** (>5s) + fallback is repetitive | `companion_server.py` line 3546-3547, 3572-3574 | If LLM takes too long AND the fallback ack is structurally redundant, silence. |
| 22 | **Superseded by completion** | `companion_server.py` line 2821-2827 | Pending prompt ack cancelled if response arrives first. |
| 23 | **Superseded by approval** | `companion_server.py` line 2760-2764 | Pending prompt ack cancelled if approval needed. |

### 2E. Idle Line Silences

| # | Condition | Code Location | Impact |
|---|-----------|---------------|--------|
| 24 | **`idle_lines_enabled = False`** | `companion_server.py` line 3989-3990 | Timer never starts. |
| 25 | **Character has no idle_lines** | `companion_server.py` line 3991-3993, 4010-4011 | Timer starts? No — checked before timer starts AND before firing. |
| 26 | **User interacts during idle delay** | `companion_server.py` line 2708, 2735 | Any THINKING or TOOL_USE cancels the idle timer. |

### 2F. Speech Delivery Silences

| # | Condition | Code Location | Impact |
|---|-----------|---------------|--------|
| 27 | **`tts_enabled = False`** | `companion_server.py` line 3885-3886 | Text is still broadcast to UI, but no TTS synthesis occurs. |
| 28 | **Stale reaction sequence** (out-of-order LLM completion) | `companion_server.py` line 3864-3866 | If a newer reaction already played audio, older one is dropped via sequence counter. |
| 29 | **Expression not in character's set** | `companion_server.py` line 1024-1025, 105 | LLM-chosen expression validated against available expressions; falls back to "normal" silently. |

---

## 3. False Claim Risk Assessment — Where the Companion Could Say It "Did" Something It Didn't

### 3.1 The Core Problem: Identity Distortion

The brain prompt contains three contradictory signals:

| Signal | Text | Effect |
|--------|------|--------|
| **Agency framing** | "You are the one behind the wheel — speak in first person." (line 3281) | Pushes the LLM to claim ownership of all actions |
| **Honesty disclaimer** | "If you only READ or SEARCHED a file, do NOT claim you edited, modified, or changed it." (line 3283) | Attempts to limit false claims, but is a negative constraint in an agentic prompt |
| **Sanitization** | `_sanitize_text()` replaces "Hermes" → "the system", "AI assistant" → "I", "language model" → "" (line 3067-3085) | Erases any trace of an external agent, reinforcing the fiction that the companion IS the actor |

The combination is dangerous: the LLM is told "you are the one doing everything" and then "but don't say you did X if you only did Y." LLMs are notoriously bad at negative constraints in the presence of strong positive framing.

### 3.2 Specific False Claim Vectors

#### Vector A: "I edited a file" when Hermes only read it

**Risk: HIGH**

- The tool chain labels (line 3021-3034) are clear: `read_file` → "File read", `write_file` → "File edited"
- BUT the context also includes assistant reasoning text that may say things like "I need to modify the config"
- The LLM sees: "File read: read_file (reading config.yaml)" AND "The assistant just responded: 'I'll need to update the config.yaml to fix this bug'"
- The brain has no way to distinguish "Hermes read the file to understand it" from "Hermes read the file AND then modified it" from "Hermes read the file AND thought about modifying it but didn't"
- The tool chain only shows the LAST assistant's tool calls — if there were multiple rounds, earlier writes are invisible

#### Vector B: "I fixed the bug" when the issue remains

**Risk: HIGH**

- The companion reacts to EVENT_TOOL_USE which fires BEFORE the tool result is available (line 715-767 in observer)
- The companion sees: "terminal: command: cargo build" and says "Build fixed!"
- But the build might fail — the tool RESULT event arrives separately (line 802-824)
- The cluster buffer (2s window) may batch call + result, BUT:
  - Results are truncated to 200 chars (line 818)
  - No structured error detection — the companion can't tell PASS from FAIL
- The companion's completion reaction sees only the final successful-appearing response text

#### Vector C: "I completed that task" when tools are still running

**Risk: MEDIUM**

- `EVENT_COMPLETE` fires on the first assistant response without tool_calls
- But Hermes often emits multiple assistant messages: one with thinking, one with tool calls, one with response
- If the final response says "Let me do that now" but has no tool_calls, the companion says "Task done!" while Hermes is about to start working

#### Vector D: "I understood the codebase" when only seeing fragments

**Risk: MEDIUM**

- All content is truncated: user messages to 400 chars (line 2979), assistant responses to 200 chars (line 2989), tool results to 200 chars (line 818)
- The brain context is concatenated from fragments, losing structure
- The LLM hallucinates understanding from incomplete data

#### Vector E: "The user said X" — quoting from truncated context

**Risk: LOW-MEDIUM**

- User messages in context are truncated to 400 chars and concatenated with topic summaries for older exchanges (line 2982)
- The brain reconstructs what it thinks the user said from fragments

#### Vector F: False approval detection

**Risk: MEDIUM**

- `_is_approval_request()` uses regex keywords (line 985-993): "are you sure", "need you to", "proceed?"
- Pattern: `r"need you to"` — matches "I need you to know that..." which is NOT an approval request
- False positive → companion interrupts to urgently ask for approval when Hermes is just explaining

#### Vector G: Companion reacts to ITS OWN quip generation sessions

**Risk: LOW but dangerous**

- `_is_companion_session()` (observer line 494-510) checks for "Available expressions:" or `"{\"quip\":"` in system messages
- This is a HEURISTIC — if a user session happens to contain these strings (e.g., user asks the LLM to write a JSON schema), the session could be misclassified
- If a companion session is NOT filtered (false negative), the observer could follow it and emit events about the companion's own quip generations, creating an infinite reaction loop

### 3.3 How the Context Actually Looks to the LLM Brain

The formatted context (line 2956-3057) produces something like:

```
The conversation so far:
 · User asked about config · User wanted to fix timeout

Recent context:
User asked: Can you look at the config.yaml and fix the timeout issue?
Assistant: I'll check the config file first

Current query: I found a section called timeout: 30. Should I change it?

File edited: write_file (writing config.yaml)
File read: read_file (reading config.yaml)
Command: terminal (command: cat config.yaml)
Result: Done. Changed timeout to 60.
```

**Problems:**
1. "File edited" and "File read" appear in REVERSE chronological order (tool_chain is from last assistant only)
2. The brain can't tell which happened first — reading led to editing, or editing was reverted by reading?
3. The "Result" field (from `_sanitize_text`) replaces "Hermes" with "the system" and "AI assistant" with "I"
4. The tool chain is one level deep — if there's a sequence read→edit→test→edit→test, only the last edit+test appear
5. No tool OUTPUT (what the command printed, what the file contained) — only labels

### 3.4 Brain Prompts Compared

| Reaction Type | Prompt | First-Person? | Caveat about read vs write? |
|---------------|--------|---------------|---------------------------|
| **Completion** (line 3280) | "You are the one behind the wheel — speak in first person" | ✅ Strong | ✅ "If you only READ or SEARCHED a file, do NOT claim you edited..." |
| **Tool** (line 3600) | "You just handled something — a fix, a find, or just a look around" | ✅ Moderate | ❌ None — just "Summarize it in one short sentence" |
| **Approval** (line 3435) | "You just attempted a maneuver... YOU are the one who needs clearance" | ✅ Strong | ❌ None — urgency overrides accuracy |
| **System prompt** (line 854) | "React to the SPECIFIC context. If a file was written/modified... If a file was only read..." | ✅ Moderate | ✅ Present but buried in rules |

The **tool reaction prompt** (3600-3608) is the most risky: it says "You just handled something" (presumes completion) and "Speak in first person — you're the one in control." There is NO caveat about read vs. write. The companion will confidently say "I patched that file" even when it only called `read_file`.

---

## 4. Settings Respect — Tracing Actual vs. Intended Behavior

### 4.1 `observer_enabled` (master toggle)

| Claimed behavior | Actual behavior |
|-----------------|-----------------|
| "Disable Hermes watching" | ✅ Respected at event handler level (line 2683) |
| "Observer stops polling" | ❌ **NOT respected** — the observer loop continues polling session files. Only the reaction handler checks this flag. CPU/battery cost continues. |
| **Where checked** | `_on_hermes_event()` line 2657, checked every event |
| **Default** | `True` |
| **UI control** | Sidebar footer toggle in settings.html (line 36-42) — always visible on all pages |

### 4.2 `verbosity` (full / brief / silent)

| Setting | Completion | Tool Use | Prompt Ack | Approval | Status Broadcasts |
|---------|-----------|----------|------------|----------|-------------------|
| **full** (default) | LLM contextual quip | LLM quip (if sig>=3) | LLM prompt ack | LLM approval react | ✅ Full details |
| **brief** | Pre-canned quip only | LLM quip (if sig>=3) | LLM prompt ack | LLM approval react | ✅ Full details |
| **silent** | Expression only | Expression only | Expression only | ❌ All blocked | ✅ Status still sent |

**Discrepancies:**
- `verbosity = "brief"` only affects EVENT_COMPLETE (pre-canned vs LLM). Tool reactions still use LLM even in "brief" mode. This is undocumented behavior.
- `verbosity = "silent"` vs `observer_enabled = False` are functionally IDENTICAL (line 2683 checks both with `or`). Two settings with same effect is confusing.
- Status broadcasts are NEVER suppressed by verbosity settings — the UI always sees "watching..."/"using tools..."/"idle" regardless.

### 4.3 `context_budget` (1-4 depth tiers)

| Tier | Label | max_messages | max_detailed | Brain exchanges | Token ceiling |
|------|-------|-------------|-------------|----------------|--------------|
| 1 | Brief | 25 | 4 | 2 | ~2K tok |
| 2 | Normal | 50 | 8 | 8 | ~4K tok |
| 3 | Deep (default) | 120 | 14 | 12 | ~9.6K tok |
| 4 | Chaos | 200 | 22 | 22 | ~16K tok |

**Where used:**
1. `_format_session_context()` (line 2964) — `max_messages` limits how many messages to scan, `max_detailed` limits detailed pairs (older exchanges become topic-only 50-char fragments)
2. `_get_brain_history_exchanges()` (line 2919) — controls how many companion quip exchanges are fed as LLM conversation history
3. `_record_quip()` (line 2929-2930) — prunes quip history to fit

**Respected?** ✅ Fully respected. Depth controls ALL three context dimensions consistently.

**Old settings migration:** ✅ Handles old 1-8 depth values and token budgets >8000 (line 1406-1423).

### 4.4 `react_cooldown` (5-60s)

| Claimed | Actual |
|---------|--------|
| "Seconds between completion reactions" | ✅ Applied to completion reactions (line 2836, unless prompt acked this turn) |
| "Also applies to tool reactions" | ✅ Tool cluster flush also checks this (line 3379) |
| "Does NOT apply to approval/prompt" | ✅ Approval bypasses all cooldowns. Prompt bypasses (line 2720: "bypasses all cooldowns"). |

**Respected?** ✅ Fully respected for its documented scope.

### 4.5 `tts_enabled`

| Claimed | Actual |
|---------|--------|
| "Speak reactions aloud" | ✅ Checked at line 3885 in `_do_synthesize_and_play()` |
| "Text-only when disabled" | ✅ Text is still broadcast to UI (line 3877-3881), TTS synthesis skipped. |

**Respected?** ✅ Fully respected.

### 4.6 `show_tool_details`

| Claimed | Actual |
|---------|--------|
| "Show 'reading file.py' vs just 'working...'" | ✅ Controls status broadcast content (line 2673-2675) |
| "Also affects brain context?" | ❌ NOT respected — brain ALWAYS gets full context regardless of this setting. The setting only affects what's shown in the UI status bar. |

### 4.7 `idle_lines_enabled`

| Claimed | Actual |
|---------|--------|
| "Enable spontaneous idle lines" | ✅ Checked before starting idle timer (line 3989) |
| "Disable without restart" | ✅ Setting change takes effect on next timer start (no in-flight cancellation) |

**Respected?** ✅ Fully respected.

### 4.8 `godmode` (companion-side)

- **Toggle**: settings.html line 78-83 (QUICK page), WebSocket command `set_godmode` (line 2318)
- **Effect**: Loads Hermes's jailbreak system prompt and prepends it to the brain prompt (line 869-875)
- **Respected?** ✅ The `_godmode` flag is read every time `_generate_quip()` or `_generate_tool_quip()` is called.
- **Note**: Godmode affects the LLM's constraints but does NOT change which events trigger reactions. It's purely a prompt-level modification.

### 4.9 Settings Synchronization Summary

| Setting | Persistence | Used where | Real-time apply? |
|---------|------------|-----------|-----------------|
| `observer_enabled` | `nous-companion-prefs.json` | `_on_hermes_event()` | ✅ Instant |
| `verbosity` | Same | `_on_hermes_event()` | ✅ Instant |
| `context_budget` | Same | `_format_session_context()`, `_get_brain_history_exchanges()` | ✅ Instant (prune on read) |
| `react_cooldown` | Same | `_on_hermes_event()`, `_flush_tool_cluster()` | ✅ Instant |
| `tts_enabled` | Same | `_do_synthesize_and_play()` | ✅ Instant |
| `show_tool_details` | Same | Status broadcast only | ✅ Instant |
| `idle_lines_enabled` | Same | `_start_idle_timer()` | ✅ On next timer cycle |

**All settings are loaded from `~/.hermes/nous-companion-prefs.json` at startup (line 1398-1428) and saved on change (line 1430-1438).** The UI sends WebSocket command `set_prefs` which triggers immediate save and in-memory update (line 2430-2441).

---

## 5. Post-Completion Events — What Happens After the "Complete" Signal

### 5.1 The Normal Flow

```
User message → EVENT_THINKING (prompt ack)
  → Assistant(tool_calls) → EVENT_TOOL_USE (tool reaction, buffered)
  → Tool result → EVENT_TOOL_USE (potentially clustered)
  → Assistant(tool_calls) → EVENT_TOOL_USE (more tools, clustered)
  → Tool result → EVENT_TOOL_USE
  → Assistant(response, no tool_calls) → EVENT_COMPLETE (final quip)
    → Cancel tool cluster buffer
    → Cancel pending prompt ack
    → Generate completion quip
    → Start idle timer (10-60 min)
```

### 5.2 Post-Completion Tool Events

**Scenario: Hermes does post-processing after its final response**

Hermes sessions are append-only JSON files. The observer polls every 1 second for mtime changes. If after `EVENT_COMPLETE` fires:

1. **Skill creations**: Hermes generates a skill file using `write_file` or `patch` → new messages appear in session → observer detects them as "new messages" on next poll → `EVENT_TOOL_USE` fires for the tool call → if sig >= 3 and companion is NOT currently speaking (`_is_reacting = False`), the tool reaction fires.

2. **Background rewrites**: Same pattern — tool events arrive, get buffered, flushed after 2s, generate quips.

3. **Follow-up tool calls in the same session**: The observer's sequential processing (line 695-826) catches ALL messages after the last known count. If the session contains assistant messages after the "final" response (e.g., Hermes edits files after responding), they are processed in the same or subsequent poll cycles.

**Result: The companion WILL react to post-completion events**

The relevant code path:
- Observer `_poll_once()` (line 688-826): processes all messages with `index >= self._last_count()`
- After `EVENT_COMPLETE` is emitted for the response message, the `_last_count` is updated to the current message count (line 826)
- New messages (skill writes, rewrites, etc.) have HIGHER indices → detected on next poll
- These generate fresh `EVENT_TOOL_USE` events
- The companion's `_on_hermes_event` receives them as NEW tool events

**The confusing case**: If post-completion tools arrive while the completion quip is still being spoken (TTS active, `_is_reacting = True`), they are **silently dropped** (line 2778-2780) if significance < 10. Only approvals would bypass.

### 5.3 No "Session Ended" Notification

| Problem | Detail |
|---------|--------|
| **What's missing** | When a session ends (`ended_at` field set in state.db), the observer detects it via `_is_ended_session()` (observer line 648), forces a switch on next poll, but the companion gets no event about the ENDING. |
| **Current behavior** | `EVENT_SESSION_SWITCHED` fires for the new session, but the old session's death is invisible. |
| **Impact** | Companion can't say "Goodbye" or "Session wrapped up." It just jumps to reacting to the next session. |

### 5.4 Reactions to Companion's Own Sessions

**Risk of infinite loops:**

- The companion's LLM quip calls create Hermes API calls → Hermes writes companion quip sessions to disk
- If `_is_companion_session()` (observer line 494-510) fails to detect these, the observer follows the companion session
- The companion then sees messages containing its own personality prompt and "Available expressions: ..."
- It reacts to ITS OWN quips as if they were user/Hermes activity
- Each reaction creates ANOTHER quip session → infinite loop

**Mitigation:** The `_is_companion_session()` check looks for `"Available expressions:"` in system messages (line 505) and `"{\"quip\":"` in content (line 508). These are robust markers but:
- `_is_companion_session()` is only called during `_get_session_inventory()` and `_find_active_session()`
- It is NOT checked per-message in `_poll_once()`
- A companion session that sneaks through (e.g., if the file scan picks it up and inventory filtering misses it) WILL be polled and reacted to

### 5.5 The "Always Speaking" Problem

**Scenario:** If the companion generates a reaction that takes a long time (TTS synthesis + playback duration), `_is_reacting` is True during `_synthesize_and_play` (set at line 3306 for completion, line 3254 for brief, line 3468 for approval, line 3631 for tool).

The timing:
- `_do_contextual_react` (line 3268): LLM generation is OUTSIDE `_is_reacting` (good), but the broadcast inside is guarded (line 3306-3314, briefly)
- `_synthesize_and_play` (line 3801): acquires `_tts_lock`, creates task, awaits it — this can take seconds (TTS synthesis + audio playback)
- During TTS playback, the companion is NOT in `_is_reacting` — only during the brief broadcast window

**Actual guard duration:** `_is_reacting = True` for a few milliseconds at most (just the broadcast) — not during TTS playback. Line 3254-3259 for brief reactions is a no-op (sleep(0) inside guard). Line 3306-3314 for completion is also just recording metadata.

**This means:** Tool events CAN fire during TTS playback, because `_is_reacting` is False. The 2-second cluster buffer means tools are aggregated and reacted to after 2s, potentially INTERRUPTING the companion's own speech (line 3822-3831: priority reactions cancel current TTS).

### 5.6 Sequence Counter for Stale Reactions

Line 3864-3866: `_do_synthesize_and_play` checks `seq` against `_last_played_seq`. If a newer reaction already played, the older one is dropped.

This correctly handles:
- Tool reaction starts (seq=5) → Completion reaction starts (seq=6) → Tool reaction finishes → checks seq=5 < 6 → DROPPED
- Completion reaction finishes first (last_played=6) → Tool reaction finishes → DROPPED

**Problem:** The sequence counter only protects audio playback order. Text is already broadcast (line 3877-3881) before the seq check. If a tool reaction is stale, the text already reached the UI before being dropped. Users see text but no audio.

---

## Appendix A: Code Path Summary

```
Observer._poll_once()
  │
  ├─ New user msg ────────────────────────────── EVENT_THINKING
  │   └─ _on_hermes_event()
  │       └─ _delayed_prompt_react() → _do_prompt_react()
  │           ├─ _generate_quip() [LLM, 5s timeout]
  │           └─ Fallback: shuffle bag prompt_acks
  │           └─ _synthesize_and_play()
  │
  ├─ Assistant msg with tool_calls ───────────── EVENT_TOOL_USE
  │   └─ _on_hermes_event()
  │       ├─ sig>=10 or approval ──→ _do_approval_react()
  │       │                           └─ _generate_tool_quip() [LLM]
  │       │                           └─ _synthesize_and_play(priority=True)
  │       ├─ sig>=3 ──→ buffer → 2s → _flush_tool_cluster()
  │       │                             └─ _do_tool_react()
  │       │                                 └─ _generate_tool_quip() [LLM]
  │       │                                 └─ _synthesize_and_play()
  │       └─ sig<3 ──→ SILENT DROP
  │
  ├─ Tool result msg ────────────────────────── EVENT_TOOL_USE (same as above)
  │
  ├─ Assistant msg without tool_calls ────────── EVENT_COMPLETE
  │   └─ _on_hermes_event()
  │       ├─ Cancel tool cluster
  │       ├─ Cancel prompt ack
  │       ├─ verbosity="brief" ──→ shuffle bag brief quip
  │       │                        └─ _synthesize_and_play()
  │       └─ verbosity="full" ──→ _format_session_context()
  │                                └─ _do_contextual_react()
  │                                    └─ _generate_quip() [LLM]
  │                                    └─ _synthesize_and_play()
  │       └─ _start_idle_timer()
  │
  └─ Session switched ────────────────────────── EVENT_SESSION_SWITCHED
      └─ _on_hermes_event()
          └─ Broadcast status only ──→ SILENT

INTERNAL TIMER:
  _start_idle_timer() (after completion)
    └─ 10-60 min → _fire_idle_line()
        └─ Shuffle bag idle_lines
        └─ _synthesize_and_play()
```

## Appendix B: Data Loss Risk Summary

| Risk | Impact | Likelihood | Mitigated? |
|------|--------|------------|------------|
| Tool events during `_is_reacting` | Silent drop, never retried | High (frequent during busy sequences) | ❌ No |
| Low-sig tools (browser, poll, reads) | Never produce speech | By design (sig<3) | ✅ Intentional |
| Post-completion tools during speech | Silent drop | Low (completion quip is brief) | ❌ No |
| Tool results truncated to 200 chars | Brain sees fragment | Always | ❌ No |
| Companion session false negative | Infinite reaction loop | Very low (robust heuristic) | ❌ Single heuristic |
| Stale audio played | Confusing timing | Medium (race with priority reactions) | ✅ Seq counter |
| Same response hash within 5 reactions | Missed reaction | Low (rarely identical) | ✅ By design |

---

*Report generated by research cron Job 4 of 5 — read-only analysis. No files were modified.*
