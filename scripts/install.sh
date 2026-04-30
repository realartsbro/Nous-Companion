#!/usr/bin/env bash
# Nous Companion — install script
# Usage: curl -fsSL https://git.io/nous-companion-install | bash
# Or:   curl -fsSL https://raw.githubusercontent.com/realartsbro/Nous-Companion/main/scripts/install.sh | bash

set -euo pipefail

REPO="realartsbro/Nous-Companion"
TAG="v0.1.2"
INSTALL_DIR="${NOUS_COMPANION_DIR:-"$HOME/.nous-companion"}"
BIN_DIR="$HOME/.local/bin"

# --- Platform detection ---
detect_platform() {
    local arch
    arch="$(uname -m)"
    case "$(uname -s)" in
        Linux)
            case "$arch" in
                x86_64)  echo "linux" ;;
                aarch64|arm64) echo "linux-arm64" ;;
                *) echo "unsupported-arch:$arch" ;;
            esac
            ;;
        Darwin)
            case "$arch" in
                x86_64)  echo "macos" ;;
                arm64)   echo "macos" ;;
                *) echo "unsupported-arch:$arch" ;;
            esac
            ;;
        *)
            echo "unsupported-os:$(uname -s)"
            ;;
    esac
}

# --- Fetch latest release ---
fetch_release() {
    local platform="$1"
    local asset_name
    case "$platform" in
        linux)       asset_name="Nous-Companion-linux.zip" ;;
        macos)       asset_name="Nous-Companion-macos.zip" ;;
        windows)     asset_name="Nous-Companion-windows.zip" ;;
        *)           echo "unknown-platform:$platform"; exit 1 ;;
    esac
    echo "https://github.com/$REPO/releases/download/$TAG/$asset_name"
}

# --- Install ---
install_platform() {
    local platform="$1"
    local url
    url="$(fetch_release "$platform")"

    echo "⬡ Nous Companion"
    echo "  Platform: $platform"
    echo "  Installing to: $INSTALL_DIR"
    echo "  Downloading..."

    mkdir -p "$INSTALL_DIR"
    local tmpzip
    tmpzip="$(mktemp)"
    # Clean up on exit
    trap 'rm -f "$tmpzip"' EXIT

    if command -v curl &>/dev/null; then
        curl -fsSL "$url" -o "$tmpzip"
    elif command -v wget &>/dev/null; then
        wget -q "$url" -O "$tmpzip"
    else
        echo "ERROR: need curl or wget"
        exit 1
    fi

    if ! command -v unzip &>/dev/null; then
        echo "ERROR: need 'unzip' command"
        exit 1
    fi

    unzip -qo "$tmpzip" -d "$INSTALL_DIR"
    echo "  Extracted to $INSTALL_DIR"

    # Find and set up the portable binary
    case "$platform" in
        linux)
            local exe
            exe="$(find "$INSTALL_DIR" -maxdepth 2 -name 'nous-companion' -type f 2>/dev/null | head -1)"
            if [ -z "$exe" ]; then
                # Fall back to AppImage
                exe="$(find "$INSTALL_DIR" -maxdepth 2 -name '*.AppImage' -type f 2>/dev/null | head -1)"
            fi
            ;;
        macos)
            # Look for .app bundle
            local app
            app="$(find "$INSTALL_DIR" -maxdepth 3 -name '*.app' -type d 2>/dev/null | head -1)"
            if [ -n "$app" ]; then
                ln -sf "$app" "$BIN_DIR/Nous-Companion.app" 2>/dev/null || true
                echo "  App bundle: $app"
            else
                echo "  WARNING: Could not find .app bundle"
            fi
            ;;
    esac

    # Add bin dir to PATH instruction
    if [ -d "$BIN_DIR" ]; then
        echo ""
        echo "  ✅ Installed to $INSTALL_DIR"
        echo "  📍 Binary linked in $BIN_DIR"
        echo "  Run: nous-companion"
        echo ""
        echo "  If 'nous-companion' is not found, add to your PATH:"
        echo "    export PATH=\"\$PATH:$BIN_DIR\""
        echo "  (add that line to ~/.bashrc or ~/.zshrc)"
    fi
}

# --- Main ---
main() {
    local platform
    platform="$(detect_platform)"

    case "$platform" in
        unsupported-*)
            echo "ERROR: Unsupported platform: $platform"
            echo "  Nous Companion supports: Linux (x86_64, arm64), macOS (Intel, Apple Silicon)"
            echo "  For Windows, download the installer from the GitHub Releases page."
            exit 1
            ;;
    esac

    install_platform "$platform"
}

main "$@"
