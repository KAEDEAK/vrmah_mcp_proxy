## Common Preparation
1. Configure each server endpoint and voice settings in `config.json`.
2. Start VRM Agent Host and load a VRM model.
3. Start VOICEVOX if you plan to use speech.

## Windows 11 + PowerShell, Claude Code CLI

### Register
`claude mcp add vrm_proxy_claude -- py mcp_proxy/mcp_server.py`

### Verify registration
`claude mcp list`
`claude mcp get vrm_proxy_claude`

### Try it
After restarting Claude Code:
Ask it to do a greeting through VRM Agent Host MCP.

### Remove registration
`claude mcp remove vrm_proxy_claude`

### Add to `CLAUDE.md`
See the "Example addition to CLAUDE.md" section in `README.md` and add avatar-integration guidance.

## Windows 11 + VS Code (Claude Code extension)

### Register (basic)
Create `.mcp.json` in the project root:

```json
{
  "mcpServers": {
    "vrm_proxy": {
      "command": "python",
      "args": ["mcp_proxy/mcp_server.py"]
    }
  }
}
```

If `python` is unavailable, replace it with `py` or `python3`.

### Register (separate config per agent)
Use the `--config` option to specify a different config file.
Useful when you want different connection targets or voices per agent:

```json
{
  "mcpServers": {
    "vrm_proxy_for_claude": {
      "command": "python",
      "args": ["mcp_proxy/mcp_server.py"]
    },
    "vrm_proxy_for_codex": {
      "command": "python",
      "args": [
        "mcp_proxy/mcp_server.py",
        "--config", "config_for_codex.json"
      ]
    }
  }
}
```

Since server names differ, tool name prefixes also change:
- `mcp__vrm_proxy_for_claude__voicevox_speak`
- `mcp__vrm_proxy_for_codex__voicevox_speak`

Update ToolSearch queries in CLAUDE.md or CODEX.md to match the corresponding prefix.

### Verify
Reload the VS Code window (`Ctrl+Shift+P` -> `Developer: Reload Window`).
Then confirm MCP connection status in the Claude Code extension.

### Try it
Do a greeting test through VRM Agent Host MCP.

### Remove registration
Delete the corresponding entry from `.mcp.json`.

### Note: GitHub Copilot extension
Use `.vscode/mcp.json` instead of `.mcp.json`, and use the key `servers`:

```json
{
  "servers": {
    "vrm_proxy": {
      "command": "python",
      "args": ["mcp_proxy/mcp_server.py"]
    }
  }
}
```

## Windows 11 + WSL + Codex CLI

### Register
`codex mcp add vrm_proxy_codex -- python3 mcp_proxy/mcp_server.py --base-url http://<ip-address-vrmah>:34560`

### Verify registration
`codex mcp list`
`codex mcp get vrm_proxy_codex`

### Try it
Run a greeting test through VRM Agent Host MCP.

### Remove registration
`codex mcp remove vrm_proxy_codex`

## MCP Resource URIs and File Mapping

LLMs read documentation via MCP resource URIs.

| MCP Resource URI | Source File | Content |
|---|---|---|
| `vrm-proxy://instructions` | (hardcoded in mcp_server.py) | Brief tool usage description |
| `vrm-proxy://api-spec` | `instructions.md` | API Quick Reference |
| `vrm-proxy://api-spec-detailed` | `detailed_instructions.md` | API Detailed Reference (all commands) |

Cross-references within documents use MCP resource URIs instead of file names.

## Common Notes
- If `CLAUDE.md` / `Agents.md` recommends avatar integration, the assistant can use it automatically (see `README.md`).
- For animation IDs, see `animation_ids.txt`.
- Speaker IDs can be checked with the `voicevox_speakers` tool.
- See `README.md` for full details.

### Useful CLI shortcuts
- `CTRL+C`: interrupt
- `CTRL+Z`: suspend temporarily, resume with `fg $1`
