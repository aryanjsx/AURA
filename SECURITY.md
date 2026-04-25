# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in AURA, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, contact the maintainer directly:

- **GitHub:** [@aryanjsx](https://github.com/aryanjsx)

Please include:

1. A description of the vulnerability
2. Steps to reproduce it
3. The potential impact
4. Any suggested fix (optional but appreciated)

## Response Timeline

- **Acknowledgement:** within 48 hours
- **Assessment:** within 7 days
- **Fix (if confirmed):** as soon as reasonably possible, with a new release

## Scope

AURA is designed to be fully offline with no network calls. Security concerns most relevant to this project include:

- **Command injection** — bypass of the shell allowlist or argv splitting
- **Path traversal** — escaping the filesystem sandbox or reaching protected system directories
- **Sandbox escape** — symlink chains, keyword expansion, or tilde expansion resolving outside intended boundaries
- **Audit log tampering** — breaking or forging the hash-chained audit log
- **Plugin manifest bypass** — loading unregistered plugins or actions not declared in `plugins_manifest.yaml`
- **Permission escalation** — a low-privilege source (e.g. `llm`, `auto`) executing commands above its cap
- **Rate limiter bypass** — circumventing per-source rate limiting or repeat-threshold protection
- **Sensitive data in logs** — credentials, tokens, or PII appearing in `logs/aura.log` or `logs/audit.log`

## Security Architecture (Phase 1)

AURA's Phase 1 security layer includes:

| Layer | What It Does |
|---|---|
| **Filesystem Sandbox** | All file operations confined to `~/AURA_SANDBOX`; symlink escape detection |
| **Protected Paths** | `C:\Windows`, `/usr`, `/etc`, etc. blocked via full ancestry checking |
| **Shell Allowlist** | Only `git`, `npm`, `docker`, `echo` can be executed; `shell=False` by default |
| **Command Policy** | Denylist of destructive patterns applied before any command reaches the process layer |
| **Permission Validator** | Source-capped permission levels (`cli` = CRITICAL, `llm` = MEDIUM, `auto` = LOW) |
| **Rate Limiter** | Per-source sliding-window rate limiting with repeat-threshold loop protection |
| **Safety Gate** | Interactive confirmation for destructive operations with configurable timeout |
| **Tamper-Evident Audit Log** | Hash-chained audit entries with rotation sidecar; detects tampering on startup |
| **Plugin Manifest Binding** | SHA-256 manifest hash verified at worker startup; unregistered actions rejected |
| **Non-Bypassable Registry** | Single execution entry point (`CommandRegistry.execute`); no reachable dispatcher via reflection |

## Supported Versions

| Version | Supported |
|---|---|
| 2.0.x (current) | Yes |
| 0.1.x – 0.2.x | No |

## Acknowledgements

We appreciate responsible disclosure and will credit reporters in the CHANGELOG (with permission).
