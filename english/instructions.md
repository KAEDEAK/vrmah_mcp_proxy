# VRM Agent Host API Quick Reference

This document covers only the core commands.
For advanced parameters and extended features, see `vrm-proxy://api-spec-detailed` resource.

## When controlling directly via HTTP (not via MCP)
Listening endpoint: `http://localhost:34560/` (or the server/port specified by the user)
Request format: `GET /?target=<target>&cmd=<command>&<params...>`

---
## Initial Setup
The following scripts can batch-load the VRM model, adjust menus, configure Lipsync, adjust position, and more:
- setup/setup_example.bat
- setup/setup_example.sh1
- setup/setup_example.ps1

## VRM Model

### Load
```text
?target=vrm&cmd=load&file=model.vrm
```

### Get position / rotation
```text
?target=vrm&cmd=getLoc
?target=vrm&cmd=getRot
```

---

## Animation

### Play
```text
?target=animation&cmd=play&id=Idle_generic&seamless=y
```

Main animation IDs:
- `Idle_generic` / `Idle_cute` / `Idle_calm`: idle states
- `Angry_01` / `Brave_01` / `Shy_01`: emotional expressions
- `Layer_look_away`: look-away layer

### Stop / resume / reset
```text
?target=animation&cmd=stop
?target=animation&cmd=resume
?target=animation&cmd=reset
```

### Get status
```text
?target=animation&cmd=getstatus
```

---

## Expression, Mouth, Blink

### Expression
```text
?target=animation&cmd=shape&word=Relaxed&seamless=y
?target=animation&cmd=shape&word=Angry&seamless=y
```
Expressions: `Relaxed`, `Angry`, `Aa`, `Ih`, `Ou`, `Ee`, `Oh`

### Mouth shape
```text
?target=animation&cmd=mouth&word=A&seamless=y
?target=animation&cmd=reset_mouth&seamless=y
```

### Blink
```text
?target=animation&cmd=shape&blink=0,1&seamless=y
?target=animation&cmd=reset_blink&seamless=y
```
`blink=left,right` (`0=open`, `1=closed`)

### Auto blink
```text
?target=animation&cmd=auto_blink&enable=true&freq=2000
?target=animation&cmd=auto_blink&enable=false
```

---

## Gaze Control

### Enable / disable automatic gaze control
```text
?target=vrm&cmd=gaze_control&enable=true
?target=vrm&cmd=gaze_control&enable=false
```

### Look at camera
```text
?target=vrm&cmd=look_at_camera
```

### Set gaze angles directly
```text
?target=vrm&cmd=look&mode=deg&yaw=30&pitch=-15
```

---

## Lip Sync

### Start audio-synced lip sync (output audio)
```text
?target=lipSync&cmd=audiosync&channel=1&scale=3
```
`channel`: `0=WavePlayback`, `1=ExternalAudio(WASAPI)`, `2=Microphone`

### Stop
```text
?target=lipSync&cmd=audiosync_off
```

### Get status
```text
?target=lipSync&cmd=getstatus
```

---

## Wing Menu (`wingsys`)

### Show / hide
```text
?target=wingsys&cmd=menus_show
?target=wingsys&cmd=menus_hide
?target=wingsys&cmd=menus_show&side=left
?target=wingsys&cmd=menus_hide&side=right
```

### Get status
```text
?target=wingsys&cmd=menus_status
```

### Labels
```text
?target=wingsys&cmd=labels&enable=true&face=camera
?target=wingsys&cmd=labels&enable=false
```

---

## Background

### Fill with solid color
```text
?target=background&cmd=fill&color=FF0000
?target=background&cmd=fill&color=00FF00
```

### Transparent window
```text
?target=background&cmd=transparent&enable=true
?target=background&cmd=transparent&enable=false
```

---

## Server / Window

### Server status
```text
?target=server&cmd=getstatus
```

### Always on top
```text
?target=server&cmd=stay_on_top&enable=true
```

### Mouse event pass-through
```text
?target=server&cmd=pointer_events_none&enable=true
```

### Server diagnostics
Run a bundled diagnostics check for current server settings.
```text
?target=server&cmd=diagnostics
```
- No parameters required
- Checked categories: WavePlayback, image receiver, Body Interaction, network, config override, system state
- Response fields: `threat_level` (0-4), `threat_label` (SAFE/NOTICE/CAUTION/WARNING/DANGER), `score`, `findings`, `sections`
- Use this to verify whether the current runtime settings match your intent

### File integrity verification
Verify runtime files against the manifest (`runtime_files.json`, or `runtime_files_linux.json` on Linux).
```text
?target=server&cmd=verify
```
- No parameters required
- Response fields: `total_checked`, `skipped_permission`, `issue_count`, `unknown_files`, `modified_files`, `missing_files`, `type_mismatch`
- Quick check: `issue_count=0` means no issues detected

---

## Audio Playback

### Wave playback (POST)
```text
POST /waveplay/
Content-Type: application/octet-stream
(RIFF/WAVE mono 16-bit 48kHz binary)
```

### Playback control
```text
?target=server&cmd=waveplay_start
?target=server&cmd=waveplay_stop
?target=server&cmd=waveplay_volume&value=1.0
```

---

## Camera

### Auto-adjust to VRM
```text
?target=camera&cmd=adjust
```

### Look at VRM
```text
?target=camera&cmd=look_at_vrm
```

---

## VOICEVOX Speech Synthesis

If VOICEVOX is configured, text can be synthesized and played through VRM Agent Host.

### Synthesize and play
```text
Use tool: voicevox_speak
  text: "Hello"
  speaker_id: 43 (optional)
  speed_scale: 1.0 (optional)
  volume_scale: 1.0 (optional)
```

### List speakers
```text
Use tool: voicevox_speakers
```

Configure in `mcp_proxy/config.json`:
```json
{
  "version": 2.0,
  "vrmah": {
    "host": "http://<ip-address-vrmah>:34560",
    "candidates": ["http://<ip-address-vrmah-candidate>:34560"]
  },
  "voice": {
    "type": "voicebox",
    "server": "http://<ip-address-voicevox>:50021",
    "candidates": ["http://<ip-address-voicevox-candidate>:50021", "http://<ip-address-vrmah>:50021"],
    "name": "Ouka Miko",
    "speaker_uuid": "...",
    "style_id": 43
  }
}
```

---

## Detailed Reference

See `vrm-proxy://api-spec-detailed` resource for:

- Body Interaction (click/drag detection, Face Poke, SpringBone)
- Body Partitioning (custom sub-part definitions)
- IK/FK control (limb position/rotation and animation)
- Per-eye blink control (`blink_left` / `blink_right`)
- Image overlay (`image` target)
- Gravity and SpringBone physics controls
- Advanced Wing Menu settings (colors, geometry, highlights)
- Detailed `config.json` settings
- Debug Telemetry / Debug Status
