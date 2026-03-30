# VRM MCP Proxy

An integrated proxy server that controls VRM Agent Host and VOICEVOX through MCP (Model Context Protocol).
The same `vrmah_mcp_proxy.py` works across Claude Code CLI, VS Code extensions, and Codex CLI.

- You need to adapt config.json to your environment first.
- VRM Agent Host (provisional name) is required separately.

## Connection Overview and Terms (Beginner-Friendly)
### Connection diagram
```
VS Code / LLM CLI / other MCP clients <--> vrmah_mcp_proxy <--> backend servers (vrmah, voicevox)
```

If the servers run on your local machine, use `http://localhost:<port>/`.
If they run on another machine, use that machine's IP address.
On Windows 11 + WSL setups, `localhost` may not work depending on the routing path.

In that case, use the host machine IP address directly.
If needed, ask your LLM to read this document and configure MCP based on your environment.

This repository is mainly intended for AI-assisted setup.
Example prompts:

```
Environment: Windows 11, PowerShell + Claude Code
Please configure MCP for VRM Agent Host using vrmah_mcp_proxy/spec/mcp_setup_*.txt.
```

```
Environment: Windows 11, WSL + Codex
Please configure MCP for VRM Agent Host using vrmah_mcp_proxy/spec/mcp_setup_*.txt.
```

```
Environment: Windows 11, VS Code + Claude Code extension
Please configure MCP for VRM Agent Host using vrmah_mcp_proxy/spec/mcp_setup_*.txt.
```

Your AI can usually detect the execution environment. If uncertain, tell it to verify first before changing settings.

When configuring Claude Code MCP from an active Claude Code session, file editing can conflict with the running session.
If this happens, stop with `Ctrl+C`, resume with `claude --resume`, then run a quick test such as:

```
I restarted the session. Please run a greeting test.
```

### Important
To trigger automatic avatar actions and voice output, you usually need to add guidance in `Agents.md` or `CLAUDE.md`.
Add the following block.

#### Example addition to `CLAUDE.md`

```markdown
## Avatar Communication (MCP)

Use MCP tools at key milestones and provide user feedback through the avatar.
**Do not speak every turn**. Only speak at important milestones.

### VOICEVOX language note
- VOICEVOX is primarily designed for Japanese speech synthesis.
- English input may sound unnatural or fail for words not covered by dictionary/pronunciation rules.
- For reliable output, prefer sending Japanese text to `voicevox_speak`.
- If your workflow requires frequent English speech, consider testing another TTS engine better suited for English.

### MCP tools to use

| Tool | Purpose |
|------|---------|
| `voicevox_speak` | Avatar speech via TTS |
| `vrm_command` | Animation playback / expression control |
| `batch_vrm_commands` | Run multiple commands in sequence |

### Timing and speech content

| Timing | Voice (short) | Animation |
|--------|----------------|-----------|
| Start of task | "Got it, I'll try it." | Idle_energetic |
| Task complete | "Done!" | Idle_cute + Layer_nod_once |
| Need confirmation | "Please check this." | Idle_think + Layer_tilt_neck |
| Error occurred | "Looks like there is a problem." | Idle_concern |
| Long-running task | "Still working on it." | Idle_calm |

### Example
On completion:
  voicevox_speak: text="Done! Please check."
  vrm_command: target=animation, cmd=play, params={"id": "Idle_cute", "seamless": "y"}
  vrm_command: target=animation, cmd=play, params={"id": "Layer_nod_once"}

### Rules
- Keep speech to one sentence, roughly 15 characters or fewer
- Put details in normal text output
- During continuous work, summarize and speak once at the end
- If the user is in a hurry, speech can be skipped

Use backups and rollback measures, and proceed at your own responsibility.

### Notes
Before use, start VRM Agent Host and load a VRM model.
(For a quick trial, opening the VRM Agent Host endpoint in a browser provides TEST setup samples.)
Start VOICEVOX before use if speech is needed. Voice settings are configured in `config.json`.

### Terms
- `vrmah`: VRM Agent Host (avatar runtime server)
- `voicevox`: speech synthesis engine (server process)

## Features

| Tool | Description |
|------|-------------|
| `vrm_command` | Send an HTTP command to VRM Agent Host |
| `batch_vrm_commands` | Execute multiple commands in order |
| `voicevox_speak` | Synthesize text and play it through VRM Agent Host |
| `voicevox_speakers` | Get available VOICEVOX speakers |

## Requirements

- Python 3.x (`python`, `python3`, or `py` available in PATH)
- `requests` library (`pip install requests`)
- Running VRM Agent Host
- Running VOICEVOX (if speech synthesis is used)

## Setup

### 1. Configure `config.json`

Edit `vrmah_mcp_proxy/config.json` for your environment:

```json
{
  "vrmah": "http://<ip-address-vrmah>:34560",
  "voice": {
    "type": "voicebox",
    "server": "http://<ip-address-voicevox>:50021",
    "name": "Ouka Miko",
    "speaker_uuid": "0693554c-338e-4790-8982-b9c6d476dc69",
    "style_id": 43
  }
}
```

- `vrmah`: VRM Agent Host address
- `voice.server`: VOICEVOX address
- `voice.style_id`: default speaker ID (check with `voicevox_speakers`)

### 2. Environment-specific setup

Follow the setup guide for your environment:

| Environment | Setup guide | Config file |
|-------------|-------------|-------------|
| VS Code extension | [spec/mcp_setup_for_vscode.txt](spec/mcp_setup_for_vscode.txt) | `.mcp.json` |
| Claude Code CLI | [spec/mcp_setup_for_claude.txt](spec/mcp_setup_for_claude.txt) | `~/.claude.json` |
| Codex CLI | [spec/mcp_setup_for_codex.txt](spec/mcp_setup_for_codex.txt) | `~/.codex/config.toml` |

### 3. Verify connection

After restarting the session in each environment, all four tools should be available.

## Framing support

This server supports both framing formats:
- **Content-Length framing** (LSP style): typically used by VS Code extensions
- **NDJSON framing** (newline-delimited JSON): commonly used by CLI tools

Framing is auto-detected from the first message. No client-side special setting is required.

## Usage examples

### Play an animation

```text
vrm_command: target=animation, cmd=play, params={"id": "Idle_cute", "seamless": "y"}
```

### Speech synthesis

```text
voicevox_speak: text="Hello"
```

### Combined avatar communication

```text
voicevox_speak + animation for speaking with synchronized avatar motion
```

## Troubleshooting

### MCP server cannot connect

1. **Check Python path**: `python --version`
2. **Check requests**: `python -c "import requests"`
3. **Check VRM Agent Host**: open or curl `http://<host>:34560/?target=vrm&cmd=getLoc`

### Tools do not appear

Restart the session completely. Existing sessions may not detect newly registered MCP servers.

## File structure

```
vrmah_mcp_proxy/
├── vrmah_mcp_proxy.py              # MCP server implementation
├── config.json                # Connection settings
├── README.md                  # This file
├── instructions.md            # API quick reference
├── detailed_instructions.md   # Full API reference
├── animation_ids.txt          # Animation ID list
├── voicevox_speaker_list.json # VOICEVOX speaker list
└── spec/
    ├── mcp_setup_for_claude.txt  # Claude Code CLI setup
    ├── mcp_setup_for_codex.txt   # Codex CLI setup
    └── mcp_setup_for_vscode.txt  # VS Code extension setup
```
