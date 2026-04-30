# Nous Companion — Scripted Performance Scene File Format

The companion loads a JSON scene file and plays through it as a timed performance.
Each scene cue triggers: expression change → TTS line → animation action → hold for audio → next cue.

## File Format (`.nous-scene.json`)

```json
{
  "meta": {
    "title": "Demo: The Witness",
    "character": "nous",
    "duration_seconds": 60,
    "version": "1.0"
  },
  "scenes": [
    {
      "time": 0.0,
      "expression": "normal",
      "line": "So this is where you work.",
      "speed": 0.9,
      "action": "blink",
      "overlay_text": null,
      "notes": "First appearance. Slow fade in. 4s silence before line."
    },
    {
      "time": 8.0,
      "expression": "interested",
      "line": "You move fast when you are in the zone.",
      "speed": 0.85,
      "action": "look_track",
      "overlay_text": null,
      "notes": "Eyes track terminal activity left to right."
    },
    {
      "time": 20.0,
      "expression": "smirking",
      "line": "I can wear any face you give me.",
      "speed": 0.9,
      "action": "expression_cycle",
      "overlay_text": "CHARACTER CREATOR",
      "notes": "Quick cuts through settings — ring selector, expression groups."
    },
    {
      "time": 35.0,
      "expression": "serious",
      "line": "Chainsaws were invented for childbirth. That is the energy I bring.",
      "speed": 0.9,
      "action": "lean_in",
      "overlay_text": null,
      "notes": "Close up portrait. Scanlines visible. Dark facts delivery."
    },
    {
      "time": 48.0,
      "expression": "normal",
      "line": "I stop existing when you stop talking to me. Please do not minimize my window.",
      "speed": 0.75,
      "action": "shrink",
      "overlay_text": "NOUS COMPANION — MIT — OPEN SOURCE",
      "notes": "Slowly resize to SMALL. Final brand card overlay."
    }
  ]
}
```

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `time` | float | yes | Seconds from start when this cue fires |
| `expression` | string | yes | Expression group name (normal, serious, cheerful, etc.) |
| `line` | string | yes | TTS text to speak. Companion speaks this aloud. |
| `speed` | float | no | TTS speed multiplier. Default 1.0. Range 0.5-1.5. |
| `action` | string | no | Animation action: blink, look_track, expression_cycle, lean_in, shrink |
| `overlay_text` | string | no | Text to show as lower third / on-screen overlay in video edit |
| `notes` | string | no | Production note for the video editor. Not used at runtime. |

## Playback Logic

```
for each scene in scenes (sorted by time):
  1. Wait until cue time (elapsed seconds from start)
  2. Set expression
  3. If line: generate TTS audio + play with lip sync
  4. If action: trigger animation action
  5. Wait for audio to finish (or 2s if no audio)
  6. If overlay_text: emit overlay event for video recording
  7. Advance to next cue
```

## TTS Generation

Each `line` is fed through the companion's existing TTS pipeline:
1. Check `pendingExpressionVoiceFiles` for expression-specific voice
2. Generate audio via current TTS engine
3. Play through browser AudioContext with lip-sync tracking
4. On audio end → advance to next scene

## Video Recording Sync

The companion emits timestamped overlay events during playback:
```json
{"type": "scene_overlay", "text": "CHARACTER CREATOR", "time": 20.0}
```

These can be captured by OBS/Recordly via browser source or logged to console for post-production reference.
