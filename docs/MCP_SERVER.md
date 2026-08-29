# NeuroShell MCP Server Mode

NeuroShell can run as a **Model Context Protocol (MCP) tool provider**, so AI
clients — Claude Desktop, Cursor, agent frameworks — execute shell commands
**through** NeuroShell's safety stack instead of a raw shell:

```
MCP client → stdio JSON-RPC → PolicyEngine (RBAC)
           → 4-layer SafetyChecker → two-phase confirmation
           → ShellExecutor → PII/DLP scrubbing
           → hash-chained audit log → MCP client
```

No extra dependencies are required — the transport is newline-delimited
JSON-RPC 2.0 over stdio, implemented natively.

## Tools

| Tool | What it does | Executes? |
|---|---|---|
| `neuroshell_execute` | Run a command through the full safety pipeline | Yes (gated) |
| `neuroshell_translate` | Natural language → shell command + risk grade | No |
| `neuroshell_explain` | Explain a command (summary, flags, risks) | No |
| `neuroshell_safety_check` | Grade risk without running anything | No |

### Execution gating

- **SAFE / CAUTION** commands run immediately.
- **DANGER** commands are refused with a structured reason; the client must
  re-call with `confirm: true` after the human approves (two-phase confirm).
- **BLOCKED** commands (e.g. `rm -rf /`, raw disk writes, fork bombs) can
  **never** be executed through this server — there is no override parameter.
- All stdout/stderr is scrubbed for secrets (AWS keys, tokens, PEM keys,
  connection strings, …) before it is returned to the client.
- Every decision — executed, refused, confirmation-required — is appended to
  `~/.neuroshell/mcp_audit.jsonl`, where each entry embeds the SHA-256 of the
  previous one. Tampering with any line breaks verification of the chain from
  that point forward.

## Claude Desktop setup

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "neuroshell": {
      "command": "neuroshell-mcp",
      "env": {
        "NEUROSHELL_MCP_ROLE": "developer"
      }
    }
  }
}
```

(Or `"command": "python3", "args": ["-m", "core.mcp_server"]` with `"cwd"`
pointing at a source checkout.)

## Cursor setup

`.cursor/mcp.json` in your project (or global settings):

```json
{
  "mcpServers": {
    "neuroshell": {
      "command": "neuroshell-mcp"
    }
  }
}
```

## Per-client policy scope

Set in the client's server config `env` block:

| Variable | Values | Effect |
|---|---|---|
| `NEUROSHELL_MCP_ROLE` | `admin` `devops` `developer` `contractor` `guest` | RBAC role for the PolicyEngine. Unknown values degrade to `guest` (least privilege). |
| `NEUROSHELL_MCP_READONLY` | `1` | Disables `neuroshell_execute` entirely; translate / explain / safety_check stay available. Ideal for "advisor" deployments. |

## Verifying the audit chain

```python
from core.mcp_server import MCPAuditLog
from pathlib import Path
ok, entries = MCPAuditLog(Path.home() / ".neuroshell" / "mcp_audit.jsonl").verify()
print("intact:", ok, "entries:", entries)
```

## Manual smoke test

```bash
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"cli","version":"1"}}}' \
 '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
 | neuroshell-mcp
```
