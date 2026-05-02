---
name: Bug Report
about: Report a problem with Nous Companion
title: "[Bug] "
labels: ["bug"]
assignees: []
---

## Description
A clear and concise description of the bug.

## Steps to Reproduce
1. Go to '...'
2. Click on '...'
3. Observe '...'

## Expected Behavior
What you expected to happen.

## Actual Behavior
What actually happened.

## Environment
- **OS:** (e.g., Windows 11, macOS 14, Ubuntu 22.04)
- **Nous Companion version:** (e.g., v1.2.3 or commit hash)
- **Install method:** (prebuilt binary / browser / Tauri from source / built binary)
- **Hermes Agent version:** (if applicable)

## Component
Which part of the stack is affected?
- [ ] Tauri desktop shell
- [ ] Renderer (HTML/CSS/JS)
- [ ] Python backend / WebSocket server (`companion_server.py`)
- [ ] Hermes observer / session watcher (`hermes_observer.py`)
- [ ] Compositor / animation (`cutout_compositor.py`, `animation_controller.py`)
- [ ] Brain / quip generation (`brain.py`)
- [ ] TTS engine
- [ ] Character system
- [ ] Settings UI
- [ ] Other: ___

## Configuration
- **Model provider:** (e.g., OpenAI, Anthropic, local Ollama, etc.)
- **TTS engine:** (OmniVoice / OpenAI TTS / Edge-TTS / None)
- **Chrome style:** (Hermes / Classic)
- **Character:** (default or custom)

## Logs / Screenshots
If applicable, paste relevant log output or attach screenshots.

- Backend debug log: `~/.nous-companion-debug.log` (or `/tmp/nous-companion-debug.log` on Linux/macOS)
- Browser/Tauri devtools console output

## Additional Context
Add any other context about the problem here (e.g., WSL setup, firewall, custom character, scene file).
