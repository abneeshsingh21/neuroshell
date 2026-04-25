# NeuroShell Threat Model

## Scope

- User command input and translation pipeline.
- Safety policy, audit logs, and plugin execution paths.
- Local secrets, environment variables, and release artifacts.

## Primary Assets

- User filesystem integrity.
- Secrets and API credentials.
- Audit logs and provenance data.
- Release artifacts and deployment state.

## Threats

- Command injection through translation paths.
- Plugin abuse via untrusted code or excessive capabilities.
- Secret leakage in source, logs, or CI output.
- Artifact tampering between build and deploy.
- Config drift causing unsafe runtime behavior.

## Controls Implemented

- Safety policy profiles/roles with command risk gating.
- Trust-gated plugin loading with capability checks.
- Audit hash chaining and export verification.
- CI secret scanning and dependency/security checks.
- Deployment state tracking with rollback and drift checks.

## Residual Risks

- Host compromise can bypass local controls.
- Optional cloud integrations can increase exfiltration risk.
- Manual operations outside CI can skip controls if not enforced.

## Mitigations Roadmap

- Enforce signed artifact verification at startup.
- Expand chaos testing to network and storage failures.
- Add periodic tabletop incident exercises.
