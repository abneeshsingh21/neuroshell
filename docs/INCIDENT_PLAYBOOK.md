# NeuroShell Incident Playbook

## Severity Levels

- SEV-1: Data loss, RCE risk, or production outage.
- SEV-2: Partial outage, elevated error rates, policy bypass.
- SEV-3: Non-critical degradation or tooling instability.

## Response Flow

1. Detect: alert from SLO monitor, CI, or manual report.
2. Triage: classify severity and impacted components.
3. Contain: disable risky paths (policy profile production + viewer/operator where needed).
4. Eradicate: patch root cause and verify with tests.
5. Recover: rollback/deploy fixed version and validate health.
6. Review: postmortem with timeline, actions, and prevention items.

## Immediate Commands

- `policy`
- `policy profile production`
- `policy role operator`
- `policy audit`
- `policy audit export ./audit.json`
- `policy audit verify ./audit.json`

## Evidence Collection

- Export audit logs (JSON/CSV + sha256 sidecar).
- Preserve CI logs and failing test output.
- Snapshot current deployment state file.

## Recovery Checklist

- Confirm rollback target is clean.
- Validate config hash matches approved stage profile.
- Run targeted regression suites before reopening traffic.
