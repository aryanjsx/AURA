#!/usr/bin/env bash
#
# Build the Python runtime bundled with the desktop app into
# frontend/src-tauri/binaries/runtime/. On first launch the app installs it
# with the bundled uv, so end users need no git, Python, or Rust toolchain.
#
# Usage:
#   ./build-runtime.sh <uv-python-request> [cargo-target]
#   ./build-runtime.sh 3.12
#   ./build-runtime.sh 3.12 universal2-apple-darwin
#   ./build-runtime.sh cpython-3.12-windows-x86_64-none x86_64-pc-windows-msvc
#
# Output:
#   requirements.txt  third-party dependencies, hash-locked from uv.lock
#   locus_assistant-*.whl, locus_rust-*.whl
#   manifest.json     the Python request and file names the app installs
#
# Requires uv, a Rust toolchain for the target, and the repository's git
# history (the Locus version comes from git tags).

set -euo pipefail

PYTHON_REQUEST="${1:?usage: build-runtime.sh <uv-python-request> [cargo-target]}"
CARGO_TARGET="${2:-}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
OUT_DIR="$SCRIPT_DIR/../binaries/runtime"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
cd "$REPO_ROOT"

# The rust/ workspace pins an MSRV toolchain without the cross targets the
# release jobs install on stable.
export RUSTUP_TOOLCHAIN="${RUSTUP_TOOLCHAIN:-stable}"

echo "Exporting locked requirements..."
uv export --frozen --no-dev --no-header --no-emit-project \
    --no-emit-package locus-rust \
    --extra desktop --extra inference-cloud --extra inference-google \
    --format requirements-txt -o "$OUT_DIR/requirements.txt"

echo "Building the Locus wheel..."
uv build --wheel --out-dir "$OUT_DIR"

echo "Building the locus_rust wheel for Python $PYTHON_REQUEST..."
uv python install "$PYTHON_REQUEST"
PYTHON_BIN="$(uv python find --managed-python "$PYTHON_REQUEST")"
maturin_args=(
    build --release
    --manifest-path rust/crates/locus-python/Cargo.toml
    --interpreter "$PYTHON_BIN"
    --out "$OUT_DIR"
)
if [ -n "$CARGO_TARGET" ]; then
    maturin_args+=(--target "$CARGO_TARGET")
fi
uvx --from 'maturin>=1.12.6,<2' maturin "${maturin_args[@]}"

"$PYTHON_BIN" - "$OUT_DIR" "$PYTHON_REQUEST" <<'PY'
import json
import sys
from pathlib import Path

out, python = Path(sys.argv[1]), sys.argv[2]
wheels = sorted(p.name for p in out.glob("*.whl"))
for prefix in ("locus_assistant-", "locus_rust-"):
    found = [w for w in wheels if w.startswith(prefix)]
    if len(found) != 1:
        sys.exit(f"expected one {prefix}*.whl in {out}, found {found}")
manifest = {"python": python, "requirements": "requirements.txt", "wheels": wheels}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps(manifest, indent=2))
PY

ls -lh "$OUT_DIR"
