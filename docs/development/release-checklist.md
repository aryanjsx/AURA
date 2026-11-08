# Release Checklist

Before tagging a release, run through this checklist on real machines (not just CI containers).

## Manual smoke tests (~30 min total)

For each platform below, start from a fresh user account / VM snapshot. Run the install one-liner and verify the steps in the table.

| Platform | One-liner | Verify |
|---|---|---|
| macOS Intel laptop | `curl -fsSL <url> \| bash` | (1)–(8) below |
| macOS ARM laptop | same | (1)–(8) |
| Ubuntu 22.04 fresh VM | same | (1)–(8) |
| Fedora 40 fresh VM | same | (1)–(8) |
| WSL2 Ubuntu on Windows | same | (1)–(8) |

### Verification steps

1. **Install completes ≤ 5 min** on typical broadband.
2. **`locus` (no args)** drops into a chat session within 2 s.
3. **First chat turn returns a response** from `qwen3.5:2b` via Ollama.
4. **Banner shows background work** ("Setting up in background: …") while it's still going.
5. **Completion notification fires** between turns when the bg work finishes (Rust extension or a model).
6. **`locus doctor`** exits 0 once all bg work completes; shows the Background tasks table.
7. **Re-run `curl … | bash`** on the same machine. It completes ≤ 30 s, says `[ok] step already done` for every step.
8. **`locus-uninstall`** removes `~/.locus/` and `~/.local/bin/locus*`. Verify with `ls`.

## Cloud quick-path verification

On any one platform:

```bash
export ANTHROPIC_API_KEY=test-fake-key
locus init --force
```

Verify init proposes cloud (mentions "anthropic" in the prompt), and the resulting `config.toml` has `[intelligence] provider = "anthropic"`.

## Failure-mode spot checks

Run at least one failure scenario per release; rotate which one.

- Disconnect network mid-install — verify clear error and re-run completes.
- Delete `~/.locus/config.toml` — verify bare `locus` re-runs init.
- Delete `~/.locus/.venv` — verify re-running curl heals it.
- `EUID=0 bash install.sh` — verify hard-fail with "don't run as root".

## CI gates (automated, no manual action)

- All pytest tests pass: `uv run pytest tests/`
- All bats tests pass: see `.github/workflows/bash-tests.yml`
- Container integration matrix is green: see `.github/workflows/installer-integration.yml`

## Code signing

Without signing secrets, `desktop.yml` still releases, but Windows SmartScreen and macOS Gatekeeper warn on first launch. Add the secrets under **Settings > Secrets and variables > Actions** in the repository, and the next `desktop-v*` tag is signed.

### Windows

Use one of these. If both are set, the certificate wins.

- **Code-signing certificate (.pfx).** An OV or EV certificate from a certificate authority.
  - Secret `WINDOWS_CERTIFICATE`: the .pfx file, base64-encoded (`[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert.pfx"))`).
  - Secret `WINDOWS_CERTIFICATE_PASSWORD`: its password.
- **Azure Trusted Signing.** Usually the cheapest option. Create a Trusted Signing account and certificate profile, and an app registration with the *Trusted Signing Certificate Profile Signer* role.
  - Secrets `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET`.
  - Variables `AZURE_SIGNING_ENDPOINT` (for example `https://eus.codesigning.azure.net`), `AZURE_SIGNING_ACCOUNT` and `AZURE_SIGNING_PROFILE`.

The "Configure Windows signing" step adds the certificate's thumbprint, or a `trusted-signing-cli` sign command, to `tauri.release.conf.json`. Installers are signed with SHA-256 and timestamped.

### macOS

Needs an Apple Developer ID Application certificate and notarization credentials:

- Secrets `APPLE_CERTIFICATE` (the .p12, base64-encoded), `APPLE_CERTIFICATE_PASSWORD` and `APPLE_SIGNING_IDENTITY` (for example `Developer ID Application: Name (TEAMID)`).
- Secrets `APPLE_ID`, `APPLE_PASSWORD` (an app-specific password for that Apple ID) and `APPLE_TEAM_ID`.

The workflow checks the notarization credentials before building, so a bad one fails in seconds rather than at the end.
