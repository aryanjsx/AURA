#!/usr/bin/env bash
# locus-wrapper.sh — symlinked to ~/.local/bin/locus.
# Activates the managed venv and execs the real locus CLI.

LOCUS_HOME="${LOCUS_HOME:-$HOME/.locus}"
VENV="$LOCUS_HOME/.venv"

if [[ ! -d "$VENV" ]]; then
    echo "locus: venv not found at $VENV" >&2
    echo "Re-run the installer: curl -fsSL https://aryanjsx.github.io/Locus/install.sh | bash" >&2
    exit 1
fi

exec "$VENV/bin/locus" "$@"
