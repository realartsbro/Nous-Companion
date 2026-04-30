# Tauri Main Window Lag Investigation

Last updated: 2026-04-25

## Symptom

The main Tauri renderer window intermittently delays character switches, expression changes, and lip-sync by roughly 1-5 seconds.

Important nuance:
- once the main window receives a switch event, it paints quickly
- the delay is before or during message handling in the main window

## Confirmed Observations

1. `switch_to_first_frame` is consistently tiny.
   - Typical values: about `0.3ms` to `2ms`
   - Conclusion: drawing after receipt is not the primary bottleneck

2. Both sockets in the main window get delayed together.
   - `message_age` on the renderer socket and `main_control_message_age` on the separate command socket were both about `2.3s`
   - Conclusion: this is not just one clogged websocket

3. Continuous frame streaming is not the sole root cause.
   - Diagnostic run used:
     - `CODEC_DIAG_DISABLE_FRAME_STREAM=1 python3 scripts/demo_server.py`
   - Startup confirmed:
     - `Diagnostic mode: continuous renderer frame stream disabled`
   - Character switching was still randomly laggy

4. The mouth analyzer itself is broadly healthy now.
   - Example diagnostics:
     - `loaded frames=138 mean=0.409 max=1.000 above_open=78 above_close=99`
     - `complete frames=138 non_closed_frames=23 mouth_changes=8`
   - Conclusion: mouth thresholds are no longer the main suspect

5. Audio readiness is usually fast enough.
   - `audio_ready` typically around `50-80ms`
   - `audio_path_failed` still occurs in Tauri, but fallback audio succeeds
   - Conclusion: audio decode/start is not the main explanation for 2-5 second UI lag

6. Disabling Hermes observer + session refresh removes the lag.
   - Diagnostic run used:
     - `CODEC_DIAG_DISABLE_OBSERVER=1 CODEC_DIAG_DISABLE_SESSION_REFRESH=1 python3 scripts/demo_server.py`
   - Result:
     - character switching became effectively instant again
     - mouth movement and general main-window responsiveness recovered
   - Conclusion: the regression is in the Hermes session-follow / session-list subsystem

## Ruled Out Or De-Prioritized

- Server-side character switch logic as the main bottleneck
- One bad websocket as the only cause
- Mouth threshold logic as the main cause
- Continuous renderer frame stream as the only cause
- Decorative grain / scanline effects as the main cause
- PNG transport as the primary root cause
- Websocket topology as the primary root cause

## Current Working Theory

The server's Hermes session work was blocking the asyncio loop often enough to make
all websocket clients look delayed.

The most suspicious hot spots were:
- repeated full session-directory scans
- repeated JSON parsing of session files
- reparsing the current session file on every observer poll just to check ended state
- rebroadcasting unchanged session lists every 10 seconds

## Instrumentation Caveat Resolved

Earlier `server_sent_at_ms` values for `character_switched` and `expressions` were being stamped too early in the switch path.

That meant `message_age` could accidentally include:
- server-side work after the switch was already decided
- renderer queueing time
- and client-side receive delay

This has now been tightened so switch-related messages are stamped at the actual renderer/control dispatch points instead of reusing one earlier timestamp.

## Fix Direction

The current implementation work is:
- cache session inventory metadata by file mtime/size
- avoid reparsing the current Hermes session file on every poll
- use cached inventory for auto-follow and ended-session checks
- only broadcast refreshed session lists when the payload actually changes
- skip session refresh work entirely when no control clients are connected

## Next Validation

Run the server normally again, without diagnostic disable flags, and verify:
- character switching remains fast
- session lists still update in settings
- Hermes auto-follow still reacts to live sessions
