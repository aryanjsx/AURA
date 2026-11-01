#!/usr/bin/env bash
#
# Install the bundled runtime the way the desktop app does on first launch,
# then start `locus serve` against a stand-in Ollama API and check /health.
# Keep the uv arguments in step with `install_steps` in src/runtime.rs.
#
# Usage:
#   ./runtime-smoke.sh [uv-binary]
#
# Expects build-runtime.sh to have filled frontend/src-tauri/binaries/runtime.

set -euo pipefail

UV_BIN="${1:-uv}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$SCRIPT_DIR/../binaries/runtime" && pwd)"
HOME_DIR="$(mktemp -d)"
OLLAMA_PORT=11998
SERVE_PORT=8799

cleanup() {
    [ -n "${SERVE_PID:-}" ] && kill "$SERVE_PID" 2>/dev/null || true
    [ -n "${OLLAMA_PID:-}" ] && kill "$OLLAMA_PID" 2>/dev/null || true
    rm -rf "$HOME_DIR"
}
trap cleanup EXIT

case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) BIN_DIR="Scripts"; EXE=".exe" ;;
    *) BIN_DIR="bin"; EXE="" ;;
esac
VENV="$HOME_DIR/venv"
PYTHON="$VENV/$BIN_DIR/python$EXE"

export UV_PYTHON_INSTALL_DIR="$HOME_DIR/python"
export UV_CACHE_DIR="$HOME_DIR/cache"
export UV_NO_CONFIG=1
export UV_PYTHON_DOWNLOADS=automatic

read_manifest() {
    "$UV_BIN" run --no-project --python 3.12 python -c \
        "import json,sys; m=json.load(open(sys.argv[1])); print(m[sys.argv[2]] if isinstance(m[sys.argv[2]], str) else '\n'.join(m[sys.argv[2]]))" \
        "$BUNDLE/manifest.json" "$1" | tr -d '\r'
}
PYTHON_REQUEST="$(read_manifest python)"
REQUIREMENTS="$BUNDLE/$(read_manifest requirements)"
WHEELS=()
while IFS= read -r wheel; do
    WHEELS+=("$BUNDLE/$wheel")
done < <(read_manifest wheels)

echo "== Installing the bundled runtime (Python $PYTHON_REQUEST)"
"$UV_BIN" venv --python "$PYTHON_REQUEST" --managed-python "$VENV"
"$UV_BIN" pip install --python "$PYTHON" --no-deps --require-hashes -r "$REQUIREMENTS"
"$UV_BIN" pip install --python "$PYTHON" --no-deps "${WHEELS[@]}"
"$PYTHON" -c "import locus, locus_rust"
"$VENV/$BIN_DIR/locus$EXE" --version

echo "== Starting locus serve against a stand-in Ollama API"
"$PYTHON" - "$OLLAMA_PORT" <<'PY' &
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

MODEL = {"name": "qwen3:0.6b", "model": "qwen3:0.6b", "size": 1, "details": {"family": "qwen3"}}

class Handler(BaseHTTPRequestHandler):
    def _send(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send({"models": [MODEL]} if self.path.startswith("/api/tags") else {"version": "0.0.0"})

    def do_POST(self):
        self._send({"model": MODEL["name"], "message": {"role": "assistant", "content": "ok"}, "done": True})

    def log_message(self, *args):
        pass

HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
PY
OLLAMA_PID=$!

LOCUS_HOME="$HOME_DIR/locus-home" OLLAMA_HOST="http://127.0.0.1:$OLLAMA_PORT" \
    "$VENV/$BIN_DIR/locus$EXE" serve --port "$SERVE_PORT" \
    --engine ollama --model qwen3:0.6b --agent simple > "$HOME_DIR/serve.log" 2>&1 &
SERVE_PID=$!

for _ in $(seq 1 120); do
    code="$(curl -s -m 2 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$SERVE_PORT/health" || true)"
    if [ "$code" = "200" ]; then
        echo "locus serve is healthy"
        exit 0
    fi
    if ! kill -0 "$SERVE_PID" 2>/dev/null; then
        break
    fi
    sleep 1
done

echo "locus serve did not become healthy (last HTTP status: ${code:-none})"
tail -40 "$HOME_DIR/serve.log"
exit 1
