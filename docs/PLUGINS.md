# NeuroShell WASM Plugin Runtime

NeuroShell plugins are **WebAssembly/WASI modules** executed inside a
capability-scoped sandbox (wasmtime embedding). Unlike classic shell
plugins, a NeuroShell plugin has **zero ambient authority**:

| Capability | Default | How it's granted |
|---|---|---|
| Filesystem | **none** | `permissions.fs_read` / `fs_write` dirs in the manifest (WASI preopens) |
| Environment | **none** | `permissions.env` allowlist of variable names |
| Network | **none** | never available — nothing is linked |
| CPU | fuel budget | `limits.fuel` (host cap: 500M) — runaway loops trap, they can't hang NeuroShell |
| Memory | 64 MiB | `limits.memory_bytes` (host cap: 256 MiB) |
| stdout/stderr | captured | size-capped at 1 MB |

## Manifest (`plugin.json`)

```json
{
  "schema": 1,
  "name": "wordcount",
  "version": "1.0.0",
  "description": "Counts words on stdin",
  "entry": "_start",
  "permissions": {
    "fs_read":  ["./data"],
    "fs_write": [],
    "env":      ["LANG"]
  },
  "limits": {
    "fuel": 50000000,
    "memory_bytes": 67108864
  }
}
```

- `name`: lowercase letters/digits/`-`/`_`, 2–64 chars.
- `version`: strict semver `X.Y.Z`.
- Manifest limits are requests — **host ceilings always win**.
- At most 8 preopened dirs and 16 env vars.

## Security model

1. **Informed consent** — installation always shows the full permission
   surface and requires explicit approval (`--yes`). There is no silent
   install path.
2. **SHA-256 pinning** — the module hash is recorded at install and
   re-verified before *every* run. If `plugin.wasm` changes on disk, the
   plugin refuses to run until it is reinstalled (re-approved).
3. **Validation before approval** — the module must compile in wasmtime
   before the consent prompt is even shown.
4. **Hash-chained audit** — installs, runs, hash mismatches, and
   uninstalls land in `~/.neuroshell/plugin_audit.jsonl`, where each
   entry embeds the SHA-256 of the previous one (same tamper-evident
   scheme as the MCP and remote-execution logs).
5. **Crash-safe installs** — files are tmp-written then renamed; a
   half-installed plugin is never runnable.

## CLI

```bash
# Show the permission surface (refuses without --yes)
neuroshell-plugin install wordcount.wasm plugin.json

# Approve and install
neuroshell-plugin install wordcount.wasm plugin.json --yes

neuroshell-plugin list
neuroshell-plugin info wordcount
neuroshell-plugin run wordcount -- --max 10   # args after -- go to the plugin
neuroshell-plugin run wordcount --stdin "some input text"
neuroshell-plugin uninstall wordcount
```

## Authoring plugins

Any language that compiles to `wasm32-wasi` works:

- **Rust**: `cargo build --target wasm32-wasip1`
- **C/C++**: `clang --target=wasm32-wasi` (wasi-sdk)
- **Go**: `GOOS=wasip1 GOARCH=wasm go build`
- **WAT** (text format) is accepted directly for tiny plugins/tests.

The module must export the entry function (default `_start`, the WASI
command convention). Read stdin, write stdout — NeuroShell wires both.

## Install the runtime dependency

```bash
pip install "neuroshell[plugins]"     # or: pip install wasmtime
```

Without wasmtime installed, plugin commands fail with a clear message
and the rest of NeuroShell is unaffected.
