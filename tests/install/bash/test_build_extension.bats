#!/usr/bin/env bats

setup() {
    TEST_TMPDIR=$(mktemp -d)
    export LOCUS_HOME="$TEST_TMPDIR/.locus"
    mkdir -p "$LOCUS_HOME/.state"
    mkdir -p "$LOCUS_HOME/src/rust/crates/locus-python"
    touch "$LOCUS_HOME/src/rust/crates/locus-python/Cargo.toml"
    export UV_STUB_LOG="$TEST_TMPDIR/uv.log"
    : > "$UV_STUB_LOG"
    export PATH="$BATS_TEST_DIRNAME/stubs:$PATH"
    export SCRIPT="$BATS_TEST_DIRNAME/../../../scripts/install/build-extension.sh"
}

teardown() {
    [[ -n "${TEST_TMPDIR:-}" ]] && rm -rf "$TEST_TMPDIR"
}

@test "writes extension-built marker on success" {
    UV_STUB_EXIT=0 run bash "$SCRIPT"
    [ "$status" -eq 0 ]
    [ -f "$LOCUS_HOME/.state/extension-built" ]
}

@test "writes extension-failed marker on failure" {
    UV_STUB_EXIT=1 run bash "$SCRIPT"
    [ "$status" -ne 0 ]
    [ -f "$LOCUS_HOME/.state/extension-failed" ]
    [ -s "$LOCUS_HOME/.state/extension-failed" ]
}

@test "removes prior failed marker on success" {
    touch "$LOCUS_HOME/.state/extension-failed"
    UV_STUB_EXIT=0 run bash "$SCRIPT"
    [ ! -f "$LOCUS_HOME/.state/extension-failed" ]
    [ -f "$LOCUS_HOME/.state/extension-built" ]
}

@test "calls uv run maturin develop with the right manifest" {
    UV_STUB_EXIT=0 run bash "$SCRIPT"
    grep -q "run maturin develop -m" "$UV_STUB_LOG"
    grep -q "rust/crates/locus-python/Cargo.toml" "$UV_STUB_LOG"
}

@test "atomic rename — no .tmp file left behind" {
    UV_STUB_EXIT=0 run bash "$SCRIPT"
    leftover=$(find "$LOCUS_HOME/.state" -name "*.tmp" 2>/dev/null | wc -l)
    [ "$leftover" -eq 0 ]
}
