# Nous Companion Community Release Plan

## Goal

Ship Nous Companion as a normal desktop app for the Hermes community, with source builds kept as a contributor workflow instead of the main user path.

## Recommended Distribution Shape

- Primary user path: prebuilt Tauri releases published on GitHub Releases
- Contributor path: local source run with `python scripts/run_nous_companion.py` plus `cargo tauri dev`
- Backend ownership: the desktop app should eventually start and stop the backend automatically
- Public docs: release-first

## Platform Plan

### Windows

- Ship a native Tauri installer.
- Assume Hermes itself still lives in WSL2, following Hermes upstream guidance.
- Nous Companion should auto-detect the Hermes home when possible and fall back to the Runtime picker in the UI.
- Recommended implementation direction: the app owns startup, while the backend stays aligned with the Hermes environment. The open engineering decision is whether that backend should run natively on Windows against `\\\\wsl.localhost\\...` paths or be launched inside WSL via `wsl.exe`.

### macOS

- Ship a standard Tauri app bundle / DMG.
- Run the backend natively on macOS.
- Expect normal macOS signing and notarization work before public distribution.

### Linux

- Ship an AppImage first, plus `.deb` if the release pipeline is straightforward.
- Run the backend natively on Linux.

## Backend Startup Direction

Current state:

- `scripts/run_nous_companion.py` is the backend entrypoint.
- `scripts/demo_server.py` is development-only.
- The Tauri shell does not yet own backend process startup.

Target state:

1. User launches only the desktop app.
2. The desktop app starts the backend automatically.
3. The desktop app surfaces backend health and runtime detection in the UI.
4. The user never needs to run a backend script manually.

For Tauri process management, the relevant official docs are:

- Shell plugin: https://v2.tauri.app/plugin/shell/
- Distribution: https://v2.tauri.app/distribute/

## Updates

### Short term

- Publish new installers on GitHub Releases.
- Tell users to download the new build when a release is posted.

### Medium term

- Add in-app update detection.
- Use the Tauri updater against GitHub Releases once code signing and release signing are in place.

Relevant official docs:

- Tauri updater: https://v2.tauri.app/plugin/updater/
- Tauri action: https://github.com/tauri-apps/tauri-action

Important note: the Tauri updater requires signed updates. That means updater work should start only after we have a stable release pipeline and secure signing key storage.

## First GitHub Release Checklist

1. Initialize git cleanly and verify the public repo does not contain `src-tauri/target/`, generated caches, or local outputs.
2. Confirm the README is release-first and keeps source-build instructions secondary.
3. Decide the Windows backend strategy for Hermes-in-WSL.
4. Keep the GitHub Actions build workflow healthy for Windows, macOS, and Linux artifacts.
5. Smoke-test one release candidate on each platform.
6. Add release notes and installation notes for Windows + WSL.
7. Only after release builds are stable, wire in updater support.

## Open Questions

- Should the Python backend be bundled, or should releases depend on the user's existing Hermes/Python environment?
- On Windows, is native backend execution against WSL-exposed Hermes paths good enough, or is launching the backend inside WSL more reliable?
- Which Linux formats are worth maintaining beyond AppImage?
