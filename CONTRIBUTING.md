# Contributing to Nous Companion

Thanks for wanting to help! A few guidelines:

## Before You Start

- The companion integrates tightly with Hermes Agent's session files and config. Changes that assume a specific Hermes version should be tested against the current release.
- If you're adding a visual effect or setting, wire it through the full loop: server default → WebSocket broadcast → renderer handler → settings UI.

## Pull Requests

- Keep API keys out of the repo — they belong in `~/.hermes/.env`
- Pin dependency versions in `requirements.txt` (see existing entries for format)
- If your change touches the Tauri shell, test with `cargo tauri dev` on your platform

## Code of Conduct

Be respectful. This is a community project.

## Questions

Open a [GitHub Issue](https://github.com/realartsbro/Nous-Companion/issues).
