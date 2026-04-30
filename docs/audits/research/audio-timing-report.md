# Audio Pipeline Research Report

**Date:** 2026-04-30  
**Scope:** End-to-end TTS pipeline — quip generation to speaker output  
**Files analyzed:** `companion_server.py`, `engine.py`, `audio_analyzer.py`, `animation_controller.py`, `scene_player.py`, `renderer.js`, `settings.html`  
**Author:** Cron Job 3/5 — Nous Companion Research Audit

---

## 1. Complete Audio Pipeline

### 1.1 Pipeline Overview (source → sink)

```
Hermes Event (observer)
       │
       ▼
  _on_hermes_event()              [companion_server.py:2644]
       │
       ├── EVENT_THINKING ──→ _delayed_prompt_react()  [line 2724]
       ├── EVENT_TOOL_USE ──→ _flush_tool_cluster()    [line 2800]
       │                        └── _do_tool_react()   [line 3587]
       ├── EVENT_COMPLETE ──→ _do_contextual_react()   [line 2879]
       │                 └── _speak_brief()             [line 2857]
       └── Approval ──────→ _do_approval_react()       [line 2772]
                                (priority=true)
                                      │
                                      ▼
                           _synthesize_and_play()
                           [companion_server.py:3801]
                                      │
                           ┌──────────┴──────────┐
                           │                     │
                     priority=true         normal path
                     cancels current       acquires _tts_lock
                     utterance, awaits     [line 3833]
                     its cancellation
                           │                     │
                           └──────────┬──────────┘
                                      ▼
                         _do_synthesize_and_play()
                         [companion_server.py:3853]
                                      │
                                      ├── broadcast text (type:"text")
                                      ├── _synthesize_tts() [line 3888]
                                      │       │
                                      │       ├── OmniVoice (voice clone via Gradio) [line 1048]
                                      │       └── edge-tts (free, fallback) [line 1055]
                                      │
                                      ├── anim.load_audio(path) [line 3897]
                                      │       └── AudioAnalyzer reads WAV → RMS frames [audio_analyzer.py]
                                      │
                                      ├── _broadcast_audio_to_renderers() [line 3914]
                                      │       └── WebSocket message type:"audio" + base64 WAV or path
                                      │
                                      └── wait loop (polls anim._audio_playing) [line 3924-3933]
                                                  │
                                                  ▼
                                          Renderer (browser JS)
                                          handleAudio() [renderer.js:1490]
                                                  │
                                                  ├── path mode: HTMLAudioElement
                                                  └── base64 mode: AudioContext.decodeAudioData()
                                                          │
                                                          ▼
                                                  startPlaybackFrom(0) [renderer.js:1624]
                                                          │
                                                          ├── AudioBufferSourceNode.start()
                                                          └── reports playback_started to server
```

### 1.2 Event Sources

There are **five** distinct paths that can trigger synthesized speech:

| Trigger | Entry Point | Priority | Notes |
|---------|------------|----------|-------|
| User sends a new message | `EVENT_THINKING` → `_delayed_prompt_react` | **Non-blocking** | Delayed by `_prompt_ack_delay` (0s), cancellable by approval |
| Hermes uses tools | `EVENT_TOOL_USE` → clustering → `_do_tool_react` | Best-effort | 2s cluster window, min significance threshold of 3 |
| Hermes completes response | `EVENT_COMPLETE` → `_do_contextual_react` | Escalated | Bypasses `_is_reacting` guard |
| Approval request | `EVENT_TOOL_USE` (approval flag) → `_do_approval_react` | **Priority=true** | Cancels current speech |
| Click/shortcut | `_speak_random_line` / `_fire_idle_line` | priority=true (click) / false (timer) | Uses shuffle bag |

### 1.3 Quip Generation (LLM call)

`_generate_quip()` [line 837] calls the user's configured provider (Cerebras/Groq fast path preferred, Hermes fallback) with:
- System prompt: character personality + available expressions + formatting rules
- Context: formatted session history + tool data
- JSON schema enforcement: `{"quip": string, "expression": string}`
- 15s timeout (fast provider) or 30s (Hermes fallback)
- 3 retries on 429 (1s, 2s, 4s backoff)

---

## 2. Queuing Behaviour

### 2.1 TTS Lock — Single Serialized Utterance

The system uses an **`asyncio.Lock`** (`_tts_lock`) to ensure only one TTS utterance executes at a time [line 180, 3833]:

```python
self._tts_lock = asyncio.Lock()  # Only one utterance plays at a time
```

Inside `_synthesize_and_play()`:
```python
async with self._tts_lock:
    task = asyncio.create_task(self._do_synthesize_and_play(...))
    self._current_tts_task = task
    await task
```

### 2.2 Can Multiple TTS Requests Queue Up?

**No — they do not queue.** The `_tts_lock` causes callers to **block (wait)** for the current utterance to finish. While waiting, the caller is suspended at the `async with self._tts_lock:` line. There is no queue data structure — just the lock.

Consider the scenario:
1. Tool reaction starts, acquires `_tts_lock`, begins `_do_synthesize_and_play`
2. Completion event arrives while #1 is still synthesizing/playing
3. Completion calls `_synthesize_and_play()` → blocks on `_tts_lock`
4. When #1 finishes, #2 acquires the lock and starts

**Since there is no queue, one caller blocks while the second waits. If a third caller arrives, it also blocks — but none are dropped.**

### 2.3 What Happens When a New Reaction Arrives During Speech?

**It depends on the reaction type:**

| Incoming Reaction | Current speech behaviour |
|------------------|--------------------------|
| **Approval** (`priority=True`) | **Immediate interruption**: cancels current `_current_tts_task`, stops audio, broadcasts `audio_stop`, then takes over [line 3822-3831] |
| **Prompt ack** (no priority) | Cancels current TTS (user interjection) [line 2710-2716] but only inside `EVENT_THINKING` handler |
| **Completion** (escalated) | Blocks on `_tts_lock` — waits for current speech to finish, then plays |
| **Tool reaction** (non-urgent) | Blocks on `_tts_lock` — waits for current speech to finish |
| **Idle line** (timer, no priority) | Blocks on `_tts_lock` — waits for current speech to finish |

### 2.4 Sequence Number Staleness Detection

Each reaction gets an incrementing `_reaction_seq_counter` [line 3818]. In `_do_synthesize_and_play`, stale out-of-order completions are dropped:

```python
if seq and seq < self._last_played_seq:
    print(f"[TTS] Stale reaction seq={seq}, last_played={self._last_played_seq} → skip")
    return
```

This prevents a slow LLM call from delivering audio after a newer, faster reaction already played.

---

## 3. Interruption Logic

### 3.1 Priority-Based Interruption

Only **approval reactions** use `priority=True` [line 3822]:

```python
if priority and self._current_tts_task and not self._current_tts_task.done():
    self._current_tts_task.cancel()
    try:
        await self._current_tts_task
    except asyncio.CancelledError:
        pass
    self._current_tts_task = None
    self.anim.stop_audio()
    self._invalidate_frame_signature()
    await self._broadcast(json.dumps({"type": "audio_stop"}), roles={"renderer"})
```

This performs:
1. Cancel the current `asyncio.Task` (which raises `CancelledError` inside the synthesise loop)
2. Wait for the cancelled task to finish
3. Stop the animation controller's audio state
4. Force a frame refresh (invalidates signature)
5. Broadcast `audio_stop` to the renderer (which calls `stopPlayback()` in JS)

### 3.2 User Interjection

When the user sends a new message (`EVENT_THINKING`), the observer **cancels** current TTS unconditionally [line 2710]:

```python
if self._current_tts_task and not self._current_tts_task.done():
    print("[TTS] Cancelling current speech (user interjected)")
    self._current_tts_task.cancel()
    self._current_tts_task = None
    self.anim.stop_audio()
    self._invalidate_frame_signature()
    await self._broadcast(json.dumps({"type": "audio_stop"}), roles={"renderer"})
```

### 3.3 What Gets Interrupted?

Cancelling `_current_tts_task` raises `asyncio.CancelledError` inside `_do_synthesize_and_play` [line 3935], which is caught in the `finally` block:

```python
except asyncio.CancelledError:
    interrupted = True
    raise
finally:
    self._is_speaking = False
    if not interrupted:
        await self._broadcast(json.dumps({"type": "status", "status": "idle"}))
```

Key: **"idle" status is NOT broadcast on interruption** — the caller that interrupted it becomes responsible for setting the next status. Cleanup of the temp WAV file still happens (via a background task with 2s delay).

### 3.4 Renderer-Side Interruption

When the backend broadcasts `audio_stop`, the JS `handleEvent` [renderer.js:1240] does:

```javascript
case "audio_stop":
    stopPlayback();
    updateStatus("connected");
    setCursorVisible(false);
    isSpeaking = false;
    break;
```

`stopPlayback()` [line 1704]:
```javascript
function stopPlayback() {
    stopWaveViz();
    if (currentSource) { try { currentSource.stop(); } catch(e) {} currentSource = null; }
    if (currentAudioElement) {
        try { currentAudioElement.pause(); } catch(e) {}
        currentAudioElement = null;
    }
    isPlaying = false;
    if (btnPlayPause) btnPlayPause.textContent = "▶";
    if (playbackTimer) { clearInterval(playbackTimer); playbackTimer = null; }
}
```

This **abruptly cuts audio** — no cross-fade, no fade-out. For maximum immersion, this is a pain point.

---

## 4. Event Collision Handling

### 4.1 Rapid-Fire Tool Events (<1s apart)

Tools are **buffered in a cluster** [line 2788]:
- `_tool_cluster_buffer: list[dict]` accumulates tool events
- A 2-second flush timer (`_tool_cluster_window = 2.0`) is **reset on each new event**
- When the timer fires, all buffered events are aggregated into a single reaction

```python
self._tool_cluster_buffer.append({"tools": tools, ...})
# Reset/restart the 2-second flush timer
if self._tool_cluster_task and not self._tool_cluster_task.done():
    self._tool_cluster_task.cancel()
self._tool_cluster_task = asyncio.create_task(
    self._flush_tool_cluster_after(self._tool_cluster_window)
)
```

**Effect:** If 10 tool events arrive in 500ms, they produce at most 1 reaction (after 2s of silence). Only the aggregated, unique tools are mentioned.

### 4.2 Completion Arriving During Tool Clustering

When `EVENT_COMPLETE` arrives while tool events are buffered:
1. The pending cluster flush task is cancelled [line 2812]
2. The cluster buffer is cleared [line 2816]
3. The completion reaction fires instead [line 2879]

**Result:** No duplicate "working on it" + "done" — just the completion reaction.

### 4.3 Approval Superseding Prompt Ack

If approval arrives during the prompt ack delay window (`_prompt_ack_delay = 0.0` but the LLM generation can take time):
1. The prompt ack task is cancelled [line 2760]
2. The approval reaction fires immediately [line 2772]
3. Approval is the **single speech event** for that turn

### 4.4 Completion Superseding Prompt Ack

If the LLM responds before the prompt ack finishes generating:
1. The prompt ack task is cancelled [line 2821-2825]
2. The completion reaction fires as the sole response

### 4.5 Renderer-Side Deduplication

The renderer has a 500ms dedup window in `handleAudio()` [line 1494]:

```javascript
if (now - _lastAudioCall < 500) {
    void frontendLog(`audio dedup skip (${Math.round(now - _lastAudioCall)}ms)`);
    return;
}
```

This prevents double-play when a base64 audio message arrives while fallback path loading is also in progress.

### 4.6 Anti-Repetition System

Multiple layers prevent the same thing being said twice:

| Layer | Mechanism | Scope |
|-------|-----------|-------|
| Hash-based dedup | `_hash_reaction_trigger()` + `_recent_reactions` ring buffer (last 5) | Exact same trigger text |
| Semantic cooldown | `_last_reaction_semantic` + 15s `_semantic_cooldown` | Same type (reading, searching, etc.) |
| Fuzzy match | `SequenceMatcher` ratio ≥ 0.85 | Similar quip text |
| Recent comment window | Last 6 comments in 180s window | Similar content |
| LLM instruction | Prompt says "VARY YOUR SENTENCE STRUCTURE" | Generated variety |

---

## 5. TTS Failure Modes

### 5.1 `_synthesize_tts()` Flow [line 1038]

```python
async def _synthesize_tts(self, text, expression):
    # 1. Try OmniVoice (if configured engine == "omnivoice")
    if engine == "omnivoice":
        result = await self._tts_omnivoice(text)
        if result:
            return result
        print("[TTS] OmniVoice unavailable, falling back to edge-tts")
    # 2. Fall back to edge-tts
    return await self._tts_edge(text)
```

### 5.2 OmniVoice Failure

`_tts_omnivoice()` returns `None` if:
- Gradio client can't connect to any candidate URL (connection refused, timeout)
- Reference audio path doesn't exist or is empty
- Gradio `predict()` throws any exception
- Returned result has no valid audio file path
- The server simply doesn't respond

**Key detail:** `_ov_client` (Gradio client) is cached once connected. If the network drops mid-session, the next `predict()` will throw, and `None` is returned — **but the client is NOT retried or reconnected** in the same call. Only the next call to `_synthesize_tts()` would try again.

### 5.3 edge-tts Failure

`_tts_edge()` [line 1137] retries once with 1s delay. Returns `None` if:
- `edge_tts.Communicate.save()` fails (no network)
- `ffmpeg` conversion fails (but falls back to MP3 bytes)
- Resulting file is < 100 bytes

### 5.4 Both Engines Unavailable

If **both** OmniVoice and edge-tts fail (no network):
1. `_synthesize_tts` returns `None`
2. `_do_synthesize_and_play` sees `audio_b64` is falsy and `return`s early [line 3889]
3. **Result: text is still displayed** (broadcast `type:"text"` at line 3877), **status says "speaking..." briefly, then "idle"** — but no audio plays
4. The animation controller loads no audio, so lip-sync stays idle (mouth closed)
5. The wait loop at line 3924-3933 is never reached (early return)

**There is no user-visible error** — just silence where audio would be. The system degrades silently.

### 5.5 Audio Analyzer Failure

If `anim.load_audio()` fails (corrupt WAV, unsupported format), lip-sync breaks but audio still plays:

```python
except Exception as e:
    print(f"[TTS] Audio load failed (lip-sync disabled): {e}")
```

---

## 6. Immersion Analysis

### 6.1 Immersion Break Points

#### 🔴 CRITICAL: Audio Abruptly Cut on Interruption
When a priority reaction or user interjection interrupts current speech:
- Server: `audio_stop` broadcast → no fade-out
- Renderer: `stopPlayback()` → `currentSource.stop()` → **instant cutoff**
- **Impact:** Any immersion built by the TTS is shattered by an abrupt mid-word silence

#### 🔴 CRITICAL: No Gap Fill During TTS Synthesis
Between the time a reaction is triggered and audio starts playing:
1. LLM quip generation (0.5-5s depending on provider)
2. TTS synthesis (1-3s for OmniVoice, 0.5-2s for edge-tts)
3. Browser decode + playback start

During this window: the character's expression changes immediately (set at line 3873), and text is broadcast, but **no audio plays**. For a reaction like "Found it" (0.5s of speech), the 3s of silence before it plays creates a disjointed experience.

#### 🔴 CRITICAL: Scene Player vs Live Reaction Collision
The scene player has **no mechanism to prevent live reactions from firing during a performance**. The docstring says "live reactions arriving during a scene are queued and play after the performance completes" — but this is **not implemented**. The `_tts_lock` would cause live reactions to block, but the observer is not paused during scene playback.

#### 🟡 HIGH: Audio Gap Between Consecutive Utterances
When one utterance completes and the next starts:
1. `_is_speaking` is set to False [line 3939]
2. If not interrupted, "idle" status is broadcast
3. Next reaction's `_synthesize_and_play` sets `_is_speaking = True` again

There is an **observable gap** where the "idle" status flickers between utterances. The animation loop at line 4126 checks `not self._is_speaking and not self.anim._audio_playing` before reverting to normal expression — so during the gap, the character might return to idle expression briefly.

#### 🟡 HIGH: Lip-Sync Tail May Cause Visible "Ghost" Movement
The animation controller adds a 250ms tail after the audio analyzer's last frame [line 168]:
```python
tail_frames = max(6, int(self.fps * 0.25))  # ~250ms tail
```
But the renderer's audio playback may end slightly before or after this tail, causing visible mouth movement on a silent character.

#### 🟡 HIGH: No Audio Progress Tracking on Server
The server's wait loop [line 3924-3933] polls `anim._audio_playing` with a generous deadline: `end_deadline = duration_s + 2.0`. If the renderer finishes early (e.g., decode delay, clock drift), the server waits up to 2 extra seconds doing nothing.

#### 🟡 HIGH: Browser AudioContext Suspend/Resume
On mobile browsers or after prolonged idle, `AudioContext` may be in "suspended" state. `handleAudio()` calls `audioCtx.resume()` [line 1587/1601], but this is an async operation that introduces jitter. If resume fails, audio silently fails.

#### 🟡 MEDIUM: Scene Player — Silently Failed TTS
If a scene's TTS pre-generation fails, the scene still plays (text displays) but with a 0.5s gap instead of audio [line 415]:
```python
elif line:
    await self._wait_duration(0.5)  # brief pause instead of speech
```

#### 🟡 MEDIUM: Frame Suppression During Audio Broadcast
Lines 3910 and 482-489 show `self._suppress_frames = True` during audio broadcasts. This suppresses ALL animation frames during the audio push. For a 2-second audio clip with a 300ms broadcast time, there's a 300ms visual freeze.

#### 🟡 MEDIUM: Idle Line Timing
Idle lines [line 3994] fire at random intervals (10-60 min) regardless of whether the user is actively listening. An idle line mid-conversation would interrupt the user's flow.

#### 🟢 LOW: No Audio Compression
WAV audio is sent base64-encoded over WebSocket. A 2-second mono 24kHz WAV is ~96KB, base64-encoded is ~128KB. This contributes to WebSocket congestion and frame suppression delays.

#### 🟢 LOW: edge-tts Voice Mismatch
The fallback edge-tts uses a fixed `en-US-GuyNeural` voice, which may not match the cloned OmniVoice reference voice. The character suddenly sounds different.

### 6.2 Does the System Support "Maximum Immersion"?

**No — not in its current state.** Critical gaps:

1. **No cross-fade** during audio transitions — speech is cut or started abruptly
2. **No predictive pre-loading** — TTS is synthesized on-demand, adding latency
3. **No audio ducking** — background/interference effects continue at full volume during speech
4. **No conversation pacing** — the companion can interrupt itself mid-sentence
5. **Observable status flickers** — "speaking..." / "idle" transitions are broadcast to the UI
6. **Frame suppression** causes visual stutter during audio broadcast
7. **No queuing discipline** — the `_tts_lock` blocks callers arbitrarily, with no priority queue

For "maximum immersion" (where the companion feels like a seamless radio presence), the system needs:
- Proactive pre-generation of common reactions
- Audio cross-fading during interruption
- A proper priority queue instead of a lock
- Concealed silence during synthesis (environmental filler sound)
- Pausing the observer during scene playback

---

## 7. Scene Player Audio (Comparison with Live Reactions)

### 7.1 Architecture Difference

| Aspect | Live Reactions | Scene Player |
|--------|---------------|--------------|
| TTS timing | On-demand, waits for LLM + synthesis | **Pre-generated at load time** |
| Synchronization | Fire-and-forget | Timed cues (`"time": 1.5`) |
| Audio loading | `anim.load_audio()` + broadcast in same task | Same, but from pre-generated cache |
| Status events | Emitted as things happen | Emitted at cue times |
| Interruptibility | Interruptible (priority/user) | Pausable/Stoppable by command |

### 7.2 Scene Player Internal Flow

```
load_scene(path) [line 71]
  ├── Validate JSON, sort by time
  ├── For each scene: _synthesize_tts() → cache {base64, bytes, path, duration_s}
  └── → state = STATE_LOADED

play_scene() [line 200]
  └── _playback_loop() [line 363]
        for each scene:
          ├── _wait_until(cue_time)  # sleeps in 100ms increments
          ├── anim.set_expression(expr)
          ├── _send_current_frame_to_renderers()
          ├── emit scene_cue event
          ├── _play_audio_block(audio_info) [line 469]
          │     ├── anim.load_audio(path)
          │     ├── _cache_last_audio()
          │     ├── _suppress_frames = True
          │     ├── _broadcast_audio_to_renderers(wav_bytes, duration_s)
          │     ├── _suppress_frames = False
          │     └── await _wait_duration(duration_s)
          └── emit overlay event (if any)
```

### 7.3 Key Differences

1. **Pre-generation:** Scene player synthesizes ALL audio at load time. Live reactions synthesize on-demand. This means scene playback has zero TTS latency but can be slow to load (10 scenes × 3s each = 30s load time).

2. **Timing precision:** Scene player uses `time.time()` based wall-clock timing with 100ms resolution. Live reactions have no timing — they play as soon as the LLM responds.

3. **Interruption model:** Scene player can be paused/stopped via WebSocket commands. Live reactions can be interrupted by priority events.

4. **Frame suppression:** Both use `_suppress_frames = True` during audio broadcast, causing visual freezes. For scene player, this happens per-cue.

5. **State machine:** Scene player has explicit states (IDLE → LOADED → PLAYING → PAUSED → DONE). Live reactions have no state machine — they're a series of fire-and-forget calls.

---

## Summary Table

| Property | Status |
|----------|--------|
| TTS lock | ✅ Single utterance at a time |
| Queue | ❌ No queue — callers block on `asyncio.Lock()` |
| Priority interruption | ✅ Approval requests can interrupt |
| User interjection | ✅ User message cancels current speech |
| Staleness protection | ✅ Sequence counter drops out-of-order audio |
| Tool event clustering | ✅ 2s buffer window |
| Event deduplication | ✅ 5-layer anti-repetition system |
| Silent TTS failure | ❌ No user-visible error on TTS failure |
| Audio cross-fade | ❌ Abrupt cut on stop |
| Lip-sync accuracy | ✅ Smoothed RMS with hysteresis + tail |
| Overlapping audio prevention | ✅ Lock + cancel + stale detection |
| Observer paused during scene | ❌ Not implemented — live reactions can fire during scenes |
| Predictive audio loading | ❌ Everything is on-demand |
| Compression | ❌ Raw WAV over WebSocket (no Opus/MP3) |
