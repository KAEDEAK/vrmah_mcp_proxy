#!/usr/bin/env python3
"""
Minimum MCP proxy for VRM Agent Host.
Simple named tools for local LLMs that struggle with generic schemas.

Tools:
  vrm_animation  - Play a named animation / expression preset
  voicevox_speak - Synthesize text and play via VRM Agent Host
"""
from __future__ import annotations

import io
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

# Windows UTF-8 fix (must be early)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="surrogateescape")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="surrogateescape")
    sys.stdin  = io.TextIOWrapper(sys.stdin.buffer,  encoding="utf-8", errors="surrogateescape")

# ---------------------------------------------------------------------------
# Animation mappings
# ---------------------------------------------------------------------------

# vrm_animation: name -> list of query-param dicts for GET /?...
# Each dict is sent as a separate HTTP request to the VRM Agent Host.
_P = Dict[str, str]
ANIMATIONS: Dict[str, List[_P]] = {
    "reset_shape": [{"target": "animation", "cmd": "shape", "word": "reset",    "seamless": "y"}],
    "reset_pose":  [{"target": "animation", "cmd": "reset"}],
    "generic":     [{"target": "animation", "cmd": "play",  "id": "Idle_generic",      "seamless": "y"}],
    "dance":       [{"target": "animation", "cmd": "play",  "file": "VRMA_01.vrma",    "continue": "false"}],
    "giggle":      [{"target": "animation", "cmd": "shape", "word": "Happy",    "seamless": "y", "continue": "false", "next": "Idle_classy"}],
    "v-sign":      [{"target": "animation", "cmd": "play",  "id": "Idle_energetic_02", "seamless": "y"}],
    "nice":        [{"target": "animation", "cmd": "play",  "id": "Idle_surprise",     "seamless": "y"},
                    {"target": "animation", "cmd": "shape", "word": "Happy",    "seamless": "y"}],
    "cool":        [{"target": "animation", "cmd": "play",  "id": "Idle_energetic_02", "seamless": "y"}],
    "greetings":   [{"target": "animation", "cmd": "play",  "id": "Idle_energetic_02", "seamless": "y"}],
    "happy":       [{"target": "animation", "cmd": "shape", "word": "Happy",    "seamless": "y"}],
    "victory":     [{"target": "animation", "cmd": "play",  "id": "Idle_brave",        "seamless": "y"}],
    "laugh_down":  [{"target": "animation", "cmd": "play",  "id": "Layer_laugh_down",  "seamless": "y"}],
    "relaxed":     [{"target": "animation", "cmd": "shape", "word": "Relaxed",  "seamless": "y"}],
    "sad":         [{"target": "animation", "cmd": "shape", "word": "Sad",      "seamless": "y"}],
    "surprised":   [{"target": "animation", "cmd": "shape", "word": "Surprised","seamless": "y"},
                    {"target": "animation", "cmd": "play",  "id": "Idle_surprise",     "seamless": "y"}],
    "angry":       [{"target": "animation", "cmd": "shape", "word": "Angry",    "seamless": "y"},
                    {"target": "animation", "cmd": "play",  "id": "Idle_angry",        "seamless": "y"}],
    "brave":       [{"target": "animation", "cmd": "play",  "id": "Idle_brave",        "seamless": "y"}],
    "calm":        [{"target": "animation", "cmd": "play",  "id": "Idle_calm",         "seamless": "y"}],
    "concern":     [{"target": "animation", "cmd": "play",  "id": "Idle_concern",      "seamless": "y"}],
    "classy":      [{"target": "animation", "cmd": "play",  "id": "Idle_classy",       "seamless": "y"}],
    "cute":        [{"target": "animation", "cmd": "play",  "id": "Idle_cute",         "seamless": "y"}],
    "denying":     [{"target": "animation", "cmd": "play",  "id": "Idle_denying",      "seamless": "y"}],
    "energetic":   [{"target": "animation", "cmd": "play",  "id": "Idle_energetic",    "seamless": "y"}],
    "sexy":        [{"target": "animation", "cmd": "play",  "id": "Idle_sexy",         "seamless": "y"}],
    "pitiable":    [{"target": "animation", "cmd": "play",  "id": "Idle_pitiable",     "seamless": "y"}],
    "stressed":    [{"target": "animation", "cmd": "play",  "id": "Idle_stressed",     "seamless": "y"}],
    "think":       [{"target": "animation", "cmd": "play",  "id": "Idle_think",        "seamless": "y"}],
    "what":        [{"target": "animation", "cmd": "play",  "id": "Idle_what",         "seamless": "y"}],
    "boyish":      [{"target": "animation", "cmd": "play",  "id": "Idle_boyish",       "seamless": "y"}],
    "cry":         [{"target": "animation", "cmd": "shape", "word": "Sad"},
                    {"target": "animation", "cmd": "play",  "id": "Idle_cry",          "seamless": "y"}],
    "laugh":       [{"target": "animation", "cmd": "play",  "id": "Idle_laugh",        "seamless": "y"},
                    {"target": "animation", "cmd": "shape", "word": "Happy",    "seamless": "y"}],
    "fedup":       [{"target": "animation", "cmd": "play",  "id": "Idle_fedup",        "seamless": "y"}],
    "cat":         [{"target": "animation", "cmd": "play",  "id": "Idle_cat",          "seamless": "y"}],
    "walk":        [{"target": "animation", "cmd": "play",  "id": "Other_walk",        "seamless": "y"}],
    "run":         [{"target": "animation", "cmd": "play",  "id": "Other_run",         "seamless": "y"}],
    "bye":         [{"target": "animation", "cmd": "play",  "id": "Other_WaveArm_01",  "seamless": "n"}],
    "secret":      [{"target": "animation", "cmd": "play",  "id": "Idle_sexy",         "seamless": "y"}],
}

ANIMATION_ENUM = sorted(ANIMATIONS.keys())

# ---------------------------------------------------------------------------
# URL helpers (same logic as vrmah_mcp_proxy.py)
# ---------------------------------------------------------------------------

def _normalize_base_url(value: Any, default: str) -> str:
    if not isinstance(value, str):
        return default
    normalized = value.strip().rstrip("/")
    return normalized or default


def _normalize_url_candidates(values: Any, primary_url: str) -> List[str]:
    if not isinstance(values, list):
        return []
    normalized: List[str] = []
    for item in values:
        if not isinstance(item, str):
            continue
        url = item.strip().rstrip("/")
        if not url or url == primary_url or url in normalized:
            continue
        normalized.append(url)
    return normalized


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, (requests.ConnectionError, requests.Timeout))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_config() -> Dict[str, Any]:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

# ---------------------------------------------------------------------------
# VRM Agent Host client (animation GET + waveplay POST with fallback)
# ---------------------------------------------------------------------------

class VrmahClient:
    def __init__(self, base_url: str, candidates: Optional[List[str]] = None) -> None:
        self.base_url = base_url
        self.base_urls = [base_url]
        for c in candidates or []:
            if c not in self.base_urls:
                self.base_urls.append(c)

    def _promote(self, idx: int) -> None:
        if idx <= 0 or idx >= len(self.base_urls):
            return
        promoted = self.base_urls.pop(idx)
        self.base_urls.insert(0, promoted)
        self.base_url = self.base_urls[0]

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        normalized = path if path.startswith("/") else f"/{path}"
        last_exc: Optional[Exception] = None
        for idx, base in enumerate(list(self.base_urls)):
            try:
                r = requests.request(method, f"{base}{normalized}", **kwargs)
                r.raise_for_status()
                if idx > 0:
                    self._promote(idx)
                return r
            except requests.HTTPError:
                raise
            except requests.RequestException as exc:
                if idx == len(self.base_urls) - 1 or not _is_retryable(exc):
                    raise
                last_exc = exc
        raise last_exc or RuntimeError("No VRMAH endpoint available")

    def vrm_get(self, params: Dict[str, str]) -> str:
        try:
            r = self._request("GET", "/", params=params, timeout=5)
            return r.text.strip() or "ok"
        except Exception as exc:
            return f"error: {exc}"

    def waveplay(self, wav_bytes: bytes) -> None:
        self._request(
            "POST", "/waveplay/",
            data=wav_bytes,
            headers={"Content-Type": "audio/wav"},
            timeout=30,
        )

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "VrmahClient":
        default_url = "http://localhost:34560"
        vrmah = config.get("vrmah", {})
        if isinstance(vrmah, str):
            base_url = _normalize_base_url(vrmah, default_url)
            return cls(base_url)
        if isinstance(vrmah, dict):
            base_url = _normalize_base_url(
                vrmah.get("host") or vrmah.get("server"), default_url
            )
            candidates = _normalize_url_candidates(vrmah.get("candidates"), base_url)
            return cls(base_url, candidates)
        return cls(default_url)

# ---------------------------------------------------------------------------
# VOICEVOX client (same config + fallback logic as vrmah_mcp_proxy.py)
# ---------------------------------------------------------------------------

@dataclass
class VoicevoxConfig:
    server: str
    candidates: List[str]
    name: str
    speaker_uuid: str
    style_id: int

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> Optional["VoicevoxConfig"]:
        voice = config.get("voice", {})
        if voice.get("type") != "voicebox":
            return None
        server = _normalize_base_url(voice.get("server"), "http://localhost:50021")
        candidates = _normalize_url_candidates(voice.get("candidates"), server)
        return cls(
            server=server,
            candidates=candidates,
            name=voice.get("name", ""),
            speaker_uuid=voice.get("speaker_uuid", ""),
            style_id=voice.get("style_id", 0),
        )


class VoicevoxClient:
    def __init__(self, cfg: VoicevoxConfig) -> None:
        self.default_speaker_id = cfg.style_id
        self.server_urls = [cfg.server]
        for c in cfg.candidates:
            if c not in self.server_urls:
                self.server_urls.append(c)

    def _promote(self, idx: int) -> None:
        if idx <= 0 or idx >= len(self.server_urls):
            return
        promoted = self.server_urls.pop(idx)
        self.server_urls.insert(0, promoted)

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        normalized = path if path.startswith("/") else f"/{path}"
        last_exc: Optional[Exception] = None
        for idx, base in enumerate(list(self.server_urls)):
            try:
                r = requests.request(method, f"{base}{normalized}", **kwargs)
                r.raise_for_status()
                if idx > 0:
                    self._promote(idx)
                return r
            except requests.HTTPError:
                raise
            except requests.RequestException as exc:
                if idx == len(self.server_urls) - 1 or not _is_retryable(exc):
                    raise
                last_exc = exc
        raise last_exc or RuntimeError("No VOICEVOX endpoint available")

    def synthesize(
        self,
        text: str,
        speaker_id: Optional[int] = None,
        speed_scale: float = 1.0,
        volume_scale: float = 1.0,
    ) -> bytes:
        speaker = speaker_id if speaker_id is not None else self.default_speaker_id
        query_data = self._request(
            "POST", "/audio_query",
            params={"text": text, "speaker": speaker},
            timeout=30,
        ).json()
        query_data["speedScale"] = speed_scale
        query_data["volumeScale"] = max(0.0, min(2.0, float(volume_scale)))
        return self._request(
            "POST", "/synthesis",
            params={"speaker": speaker},
            json=query_data,
            timeout=60,
        ).content

# ---------------------------------------------------------------------------
# MCP stdio (Content-Length + NDJSON auto-detect)
# ---------------------------------------------------------------------------

class MinimumMcpServer:
    def __init__(self, vrmah: VrmahClient, voicevox_cfg: Optional[VoicevoxConfig]) -> None:
        self.vrmah = vrmah
        self.voicevox_cfg = voicevox_cfg
        self.voicevox = VoicevoxClient(voicevox_cfg) if voicevox_cfg else None
        self._framing: Optional[str] = None
        self._running = True

    # --- I/O ---------------------------------------------------------------

    def _write_message(self, msg: Dict[str, Any]) -> None:
        payload = json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if self._framing == "ndjson":
            sys.stdout.buffer.write(payload + b"\n")
        else:
            sys.stdout.buffer.write(
                f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload
            )
        sys.stdout.buffer.flush()

    def _read_message(self) -> Optional[Dict[str, Any]]:
        first_line = sys.stdin.buffer.readline()
        if not first_line:
            return None
        stripped = first_line.strip()
        if not stripped:
            return self._read_message()

        if stripped.startswith(b"{"):
            if self._framing is None:
                self._framing = "ndjson"
            return json.loads(stripped.decode("utf-8"))

        if self._framing is None:
            self._framing = "content-length"

        headers: Dict[str, str] = {}
        for chunk in first_line.decode("ascii", errors="replace").split("\r\n"):
            if ":" in chunk:
                k, v = chunk.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        while True:
            line = sys.stdin.buffer.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            text = line.decode("ascii", errors="replace").strip()
            if ":" in text:
                k, v = text.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        length = int(headers.get("content-length", 0))
        body = sys.stdin.buffer.read(length)
        return json.loads(body.decode("utf-8"))

    def _result(self, req_id: Any, result: Any) -> None:
        self._write_message({"jsonrpc": "2.0", "id": req_id, "result": result})

    def _error(self, req_id: Any, code: int, message: str) -> None:
        self._write_message({"jsonrpc": "2.0", "id": req_id,
                              "error": {"code": code, "message": message}})

    # --- Main loop ---------------------------------------------------------

    def run(self) -> None:
        while self._running:
            try:
                msg = self._read_message()
            except Exception as exc:
                self._error(None, -32700, f"Read error: {exc}")
                continue
            if msg is None:
                break
            try:
                self._handle(msg)
            except Exception as exc:
                self._error(msg.get("id"), -32603, f"Internal error: {exc}")

    def _handle(self, msg: Dict[str, Any]) -> None:
        if "id" not in msg:
            return  # notification, ignore
        method = msg.get("method", "")
        req_id = msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            self._result(req_id, {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "vrm-minimum-proxy", "version": "0.1.0"},
            })
        elif method == "ping":
            self._result(req_id, {})
        elif method == "shutdown":
            self._result(req_id, {})
            self._running = False
        elif method == "tools/list":
            self._result(req_id, {"tools": self._tool_defs()})
        elif method == "tools/call":
            self._handle_tool_call(req_id, params)
        else:
            self._error(req_id, -32601, f"Method not found: {method}")

    # --- Tool definitions --------------------------------------------------

    def _tool_defs(self) -> List[Dict[str, Any]]:
        tools = [
            {
                "name": "vrm_animation",
                "description": (
                    "Play a named animation on the VRM avatar. "
                    "Choose from: " + ", ".join(ANIMATION_ENUM)
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "enum": ANIMATION_ENUM,
                            "description": "Animation name",
                        }
                    },
                    "required": ["name"],
                },
            },
        ]

        if self.voicevox_cfg:
            tools.append({
                "name": "voicevox_speak",
                "description": (
                    f"Synthesize text with VOICEVOX and play through the VRM avatar. "
                    f"Default speaker: {self.voicevox_cfg.name} (ID: {self.voicevox_cfg.style_id})"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text":         {"type": "string",  "description": "Text to speak"},
                        "speaker_id":   {"type": "integer", "description": f"Speaker style ID (default: {self.voicevox_cfg.style_id})"},
                        "speed_scale":  {"type": "number",  "description": "Speech speed 0.5-2.0 (default: 1.0)"},
                        "volume_scale": {"type": "number",  "description": "Volume 0.0-2.0 (default: 1.0)"},
                    },
                    "required": ["text"],
                },
            })

        return tools

    # --- Tool execution ----------------------------------------------------

    def _handle_tool_call(self, req_id: Any, params: Dict[str, Any]) -> None:
        name = params.get("name")
        args = params.get("arguments") or {}

        if name == "vrm_animation":
            anim_name = args.get("name", "generic")
            steps = ANIMATIONS.get(anim_name, [{"target": "animation", "cmd": "play", "id": "Idle_generic", "seamless": "y"}])
            results = [self.vrmah.vrm_get(params) for params in steps]
            result_text = ", ".join(results)

        elif name == "voicevox_speak":
            if not self.voicevox:
                result_text = "error: VOICEVOX not configured"
            else:
                try:
                    wav = self.voicevox.synthesize(
                        text         = args.get("text", ""),
                        speaker_id   = args.get("speaker_id"),
                        speed_scale  = float(args.get("speed_scale", 1.0)),
                        volume_scale = float(args.get("volume_scale", 1.0)),
                    )
                    self.vrmah.waveplay(wav)
                    result_text = f"ok ({len(wav)} bytes)"
                except Exception as exc:
                    result_text = f"error: {exc}"

        else:
            self._error(req_id, -32602, f"Unknown tool: {name}")
            return

        self._result(req_id, {
            "content": [{"type": "text", "text": result_text}],
            "isError": result_text.startswith("error:"),
        })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    config       = _load_config()
    vrmah        = VrmahClient.from_config(config)
    voicevox_cfg = VoicevoxConfig.from_config(config)
    MinimumMcpServer(vrmah=vrmah, voicevox_cfg=voicevox_cfg).run()


if __name__ == "__main__":
    main()
