#!/usr/bin/env bash
#
# Download the uv binary for the target platform and place it in the Tauri
# binaries/ directory so it can be bundled as an externalBin sidecar. The
# desktop app uses it on first launch to install its Python runtime.
#
# Usage:
#   ./download-uv.sh x86_64-pc-windows-msvc
#   ./download-uv.sh aarch64-pc-windows-msvc
#   ./download-uv.sh x86_64-unknown-linux-gnu
#   ./download-uv.sh universal-apple-darwin
#
# Each archive is checked against the .sha256 file published with the release.

set -euo pipefail

# Keep in step with the uv the release workflow builds the runtime with.
UV_VERSION="${UV_VERSION:-0.13.6}"
RELEASE_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}"

BINARIES_DIR="$(cd "$(dirname "$0")/../binaries" 2>/dev/null && pwd || echo "$(dirname "$0")/../binaries")"
mkdir -p "$BINARIES_DIR"

TARGET="${1:?usage: download-uv.sh <target-triple>}"
echo "Target triple: $TARGET"

UV_TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$UV_TMP_DIR"' EXIT

sha256_of() {
    if command -v sha256sum &>/dev/null; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

# Download, verify and extract the uv binary for one target triple.
# Prints the path of the extracted binary.
fetch_uv() {
    local triple="$1" ext="tar.gz" exe=""
    case "$triple" in
        *windows*) ext="zip"; exe=".exe" ;;
    esac
    local asset="uv-${triple}.${ext}"
    local dir="$UV_TMP_DIR/$triple"
    mkdir -p "$dir"

    echo "Downloading: $RELEASE_URL/$asset" >&2
    curl -fsSL "$RELEASE_URL/$asset" -o "$dir/$asset"
    curl -fsSL "$RELEASE_URL/$asset.sha256" -o "$dir/$asset.sha256"
    local expected actual
    expected="$(awk '{print $1}' "$dir/$asset.sha256")"
    actual="$(sha256_of "$dir/$asset")"
    if [ "$expected" != "$actual" ]; then
        echo "Checksum mismatch for $asset: expected $expected, got $actual" >&2
        exit 1
    fi

    case "$ext" in
        zip) unzip -q "$dir/$asset" -d "$dir" ;;
        *) tar xzf "$dir/$asset" -C "$dir" ;;
    esac
    local bin
    bin="$(find "$dir" -type f -name "uv${exe}" | head -1)"
    if [ -z "$bin" ]; then
        echo "Could not find uv${exe} in $asset" >&2
        exit 1
    fi
    echo "$bin"
}

# Tauri externalBin naming: <name>-<target-triple>[.exe]
case "$TARGET" in
    universal-apple-darwin)
        # Tauri's universal macOS bundle needs both architectures in one file.
        arm="$(fetch_uv aarch64-apple-darwin)"
        x64="$(fetch_uv x86_64-apple-darwin)"
        OUT_FILE="$BINARIES_DIR/uv-universal-apple-darwin"
        lipo -create "$arm" "$x64" -output "$OUT_FILE"
        lipo "$OUT_FILE" -verify_arch arm64 x86_64
        ;;
    *windows*)
        OUT_FILE="$BINARIES_DIR/uv-${TARGET}.exe"
        cp "$(fetch_uv "$TARGET")" "$OUT_FILE"
        ;;
    *)
        OUT_FILE="$BINARIES_DIR/uv-${TARGET}"
        cp "$(fetch_uv "$TARGET")" "$OUT_FILE"
        ;;
esac

chmod +x "$OUT_FILE"
echo "Saved to: $OUT_FILE"
ls -lh "$OUT_FILE"
