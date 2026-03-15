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

- Command injection through the dispatcher
- Unsafe file path handling
- Process management privilege escalation
- Exposure of sensitive data in logs

## Supported Versions

| Version | Supported |
|---|---|
| 0.1.x (current) | ✅ Yes |

## Acknowledgements

We appreciate responsible disclosure and will credit reporters in the CHANGELOG (with permission).
