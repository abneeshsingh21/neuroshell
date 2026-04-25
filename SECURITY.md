# Security Policy

> **Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.**
> **Proprietary Software — see LICENSE.txt**

## Supported Versions

| Version | Supported |
|---------|-----------|
| 5.0.x   | ✅ Active security patches |
| 4.2.x   | ⚠️ Critical fixes only     |
| < 4.2   | ❌ End of life             |

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Report security issues to: **singhabneesh250@gmail.com**

Include in your report:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (optional)

We will acknowledge reports within **48 hours** and aim to release a patch within **14 days** for critical issues.

## Security Architecture

NeuroShell implements the following security controls:

### Zero-Trust Privacy (PII Scrubbing)
- All terminal output is scanned for sensitive data **before** transmission to any cloud LLM
- Automatic redaction of: AWS keys, OpenAI/Anthropic tokens, GitHub tokens, passwords, private keys, database connection strings, Bearer tokens
- PII scrubbing runs **entirely locally** — no data leaves the machine unfiltered
- Raw Shell Mode disables all cloud communication entirely

### Secret Management
- All API keys and secrets are encrypted with **AES-128-CBC (Fernet)** using a machine-derived PBKDF2HMAC-SHA256 key
- Secrets are **never written to disk in plaintext** and never logged
- Key derivation uses 390,000 PBKDF2 iterations — compliant with OWASP recommendations
- Secret files receive `chmod 600` on Unix

### Command Safety
- Four-layer safety system: pattern match → regex analysis → LLM check → user confirmation
- **Injection guard** blocks null bytes, newlines, subshell operators in user input
- **Prompt injection sanitizer** strips LLM control tokens (`[INST]`, `<<SYS>>`, etc.) from AI outputs
- Fork bombs, `rm -rf /`, `format C:`, and `dd if=/dev/` are **hard-blocked**

### Supply-Chain
- SHA-256 hash verification of all NLP model files
- Dependencies scanned with `pip-audit` on every CI push
- SAST scan with `bandit` on every CI push
- No eval(), exec() of untrusted input

### Network
- All LLM calls default to **local Ollama** (no internet required)
- Smart Offline Fallback: if cloud drops, auto-pivots to local Ollama
- Raw Shell Mode: zero network activity guaranteed
- Cloud providers only activated if explicitly configured by user

### Data Privacy
- No telemetry, analytics, or phone-home by default
- Optional crash reporting is anonymized and opt-in only
- All local data (history, config, learning) stored exclusively on user's machine
- NLP Fast-Dictionary operates 100% offline with zero API calls

## Responsible Disclosure

We follow a **90-day coordinated disclosure** policy. We will credit researchers in the release notes unless they request anonymity.
