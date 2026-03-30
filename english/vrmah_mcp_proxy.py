#!/usr/bin/env python3
"""
MCP proxy server for VRM Agent Host.

This server exposes the VRM Agent Host HTTP API (e.g. http://<ip-address-vrmah>:34560)
as Model Context Protocol (MCP) tools via the stdio transport.

Usage:
    python3 vrmah_mcp_proxy/vrmah_mcp_proxy.py

Connection settings are loaded from config.json in the same directory.
The process reads/writes MCP stdio messages using Content-Length framing.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

import requests

# Force UTF-8 encoding for Windows (must be done early, before any I/O)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="surrogateescape")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="surrogateescape")
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="surrogateescape")

JSONRPC_VERSION = "2.0"
LATEST_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = [
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
    "2024-10-07",
]

DEFAULT_SERVER_INFO = {
    "name": "vrm-mcp-proxy",
    "version": "0.1.0",
}

INSTRUCTION_TEXT = (
    "VRM MCP Proxy exposes the VRM Agent Host HTTP API and VOICEVOX TTS as MCP tools.\n\n"
    "VRM Agent Host commands:\n"
    "- vrm/getLoc - Get avatar position\n"
    "- vrm/getRot - Get avatar rotation\n"
    "- vrm/gaze_control - Control gaze (enable=true/false)\n"
    "- animation/play - Play animation (id=Idle_generic&seamless=y)\n"
    "- background/fill - Set background color (color=FF0000)\n\n"
    "Use `vrm_command` with target and cmd parameters.\n\n"
    "VOICEVOX TTS:\n"
    "- voicevox_speak - Synthesize text and play through VRM Agent Host\n"
    "- voicevox_speakers - List available speakers\n\n"
    "See vrm-proxy://api-spec resource for documentation."
)


def _load_config() -> Dict[str, Any]:
    """Load configuration from config.json in the same directory."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning("config.json not found at %s, using defaults", config_path)
        return {}
    except json.JSONDecodeError as e:
        logging.error("Failed to parse config.json: %s", e)
        return {}


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


def _is_retryable_connection_error(exc: Exception) -> bool:
    return isinstance(exc, (requests.ConnectionError, requests.Timeout))


def _resolve_vrmah_endpoints(config: Dict[str, Any]) -> Tuple[str, List[str]]:
    default_base_url = "http://localhost:34560"
    vrmah_value = config.get("vrmah")

    if isinstance(vrmah_value, str):
        base_url = _normalize_base_url(vrmah_value, default_base_url)
        return base_url, []

    if isinstance(vrmah_value, dict):
        base_url = _normalize_base_url(
            vrmah_value.get("host", vrmah_value.get("server")),
            default_base_url,
        )
        candidates = _normalize_url_candidates(vrmah_value.get("candidates"), base_url)
        return base_url, candidates

    return default_base_url, []


@dataclass
class VoicevoxConfig:
    """VOICEVOX configuration from config.json."""
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
    """Simple VOICEVOX HTTP client (no session to avoid encoding issues)."""

    def __init__(
        self,
        base_url: str,
        default_speaker_id: int = 0,
        candidates: Optional[List[str]] = None,
    ) -> None:
        self.base_url = _normalize_base_url(base_url, "http://localhost:50021")
        self.default_speaker_id = default_speaker_id
        self.server_urls = [self.base_url]
        for candidate in candidates or []:
            if candidate not in self.server_urls:
                self.server_urls.append(candidate)

    def close(self) -> None:
        pass  # No session to close

    def _promote_server_url(self, url_index: int) -> None:
        if url_index <= 0 or url_index >= len(self.server_urls):
            return
        promoted = self.server_urls.pop(url_index)
        self.server_urls.insert(0, promoted)
        self.base_url = self.server_urls[0]

    def _request_with_fallback(
        self,
        method: str,
        path: str,
        **request_kwargs: Any,
    ) -> requests.Response:
        normalized_path = path if path.startswith("/") else f"/{path}"
        urls = list(self.server_urls)
        last_error: Optional[Exception] = None
        for idx, base_url in enumerate(urls):
            url = f"{base_url}{normalized_path}"
            try:
                response = requests.request(method, url, **request_kwargs)
                response.raise_for_status()
                if idx > 0:
                    logging.warning("VOICEVOX fallback succeeded: %s", base_url)
                    self._promote_server_url(idx)
                return response
            except requests.HTTPError:
                raise
            except requests.RequestException as exc:
                if idx == len(urls) - 1 or not _is_retryable_connection_error(exc):
                    raise
                logging.warning(
                    "VOICEVOX endpoint failed: %s (%s). Trying fallback.",
                    base_url,
                    exc,
                )
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("No VOICEVOX endpoint available")

    def get_speakers(self) -> List[Dict[str, Any]]:
        """Get list of available speakers."""
        response = self._request_with_fallback("GET", "/speakers", timeout=10)
        return response.json()

    def synthesize(self, text: str, speaker_id: Optional[int] = None,
                   speed_scale: float = 1.0, volume_scale: float = 1.0) -> bytes:
        """Synthesize text to WAV audio."""
        speaker = speaker_id if speaker_id is not None else self.default_speaker_id

        # Step 1: Create audio query
        query_resp = self._request_with_fallback(
            "POST",
            "/audio_query",
            params={"text": text, "speaker": speaker},
            timeout=30,
        )
        query_data = query_resp.json()

        # Apply speed and volume
        query_data["speedScale"] = speed_scale
        query_data["volumeScale"] = max(min(float(volume_scale), 2.0), 0.0)

        # Step 2: Synthesize audio
        synth_resp = self._request_with_fallback(
            "POST",
            "/synthesis",
            params={"speaker": speaker},
            json=query_data,
            timeout=60,
        )
        return synth_resp.content


def _json_dumps(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    except UnicodeEncodeError:
        # Fallback: encode with ASCII escaping for non-ASCII characters
        return json.dumps(data, ensure_ascii=True, separators=(",", ":"))


def _now_ms() -> int:
    return int(time.time() * 1000)


def _stringify(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return _json_dumps(value)
    return str(value)


def _normalize_pairs(values: Dict[str, Any]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for key, raw in values.items():
        if raw is None:
            continue
        if isinstance(raw, (list, tuple)):
            for item in raw:
                if item is None:
                    continue
                pairs.append((key, _stringify(item)))
        else:
            pairs.append((key, _stringify(raw)))
    return pairs


@dataclass
class VRMCommandResult:
    ok: bool
    method: str
    url: str
    status_code: Optional[int]
    elapsed_ms: Optional[float]
    response_excerpt: Optional[str]
    response_json: Optional[Any]
    error: Optional[str] = None

    def structured(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "method": self.method,
            "url": self.url,
            "status_code": self.status_code,
            "elapsed_ms": self.elapsed_ms,
            "response_excerpt": self.response_excerpt,
            "response_json": self.response_json,
            "error": self.error,
        }


class VRMHttpBridge:
    """Simple HTTP bridge for the VRM Agent Host API."""

    def __init__(
        self,
        base_url: str,
        default_timeout: float = 10.0,
        candidates: Optional[List[str]] = None,
    ) -> None:
        self.base_url = _normalize_base_url(base_url, "http://localhost:34560")
        self.default_timeout = default_timeout
        self.session = requests.Session()
        self.base_urls = [self.base_url]
        for candidate in candidates or []:
            if candidate not in self.base_urls:
                self.base_urls.append(candidate)

    def close(self) -> None:
        self.session.close()

    def _promote_base_url(self, url_index: int) -> None:
        if url_index <= 0 or url_index >= len(self.base_urls):
            return
        promoted = self.base_urls.pop(url_index)
        self.base_urls.insert(0, promoted)
        self.base_url = self.base_urls[0]

    def _request_with_base_fallback(
        self,
        *,
        method: str,
        path: str,
        timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
        json_payload: Optional[Any] = None,
        text_payload: Optional[str] = None,
    ) -> requests.Response:
        timeout_value = timeout or self.default_timeout
        normalized_path = path if path.startswith("/") else f"/{path}"
        request_kwargs: Dict[str, Any] = {"timeout": timeout_value}
        if headers:
            request_kwargs["headers"] = {str(k): str(v) for k, v in headers.items()}
        if json_payload is not None:
            request_kwargs["json"] = json_payload
        if text_payload is not None:
            request_kwargs["data"] = text_payload

        urls = list(self.base_urls)
        last_error: Optional[Exception] = None
        for idx, base_url in enumerate(urls):
            url = f"{base_url}{normalized_path}"
            try:
                response = self.session.request(method, url, **request_kwargs)
                if idx > 0:
                    logging.warning("VRM fallback succeeded: %s", base_url)
                    self._promote_base_url(idx)
                return response
            except requests.RequestException as exc:
                if idx == len(urls) - 1 or not _is_retryable_connection_error(exc):
                    raise
                logging.warning(
                    "VRM endpoint failed: %s (%s). Trying fallback.",
                    base_url,
                    exc,
                )
                last_error = exc

        if last_error is not None:
            raise last_error
        raise RuntimeError("No VRM endpoint available")

    def perform_call(
        self,
        *,
        target: str,
        cmd: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "GET",
        timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
        json_payload: Optional[Any] = None,
        text_payload: Optional[str] = None,
        absolute_url: Optional[str] = None,
    ) -> VRMCommandResult:
        method = (method or "GET").upper()
        timeout_value = timeout or self.default_timeout
        query_pairs: List[Tuple[str, str]] = [
            ("target", target),
            ("cmd", cmd),
        ]
        if params:
            query_pairs.extend(_normalize_pairs(params))
        request_kwargs: Dict[str, Any] = {"timeout": timeout_value}
        if headers:
            request_kwargs["headers"] = {str(k): str(v) for k, v in headers.items()}
        if json_payload is not None:
            request_kwargs["json"] = json_payload
        if text_payload is not None:
            request_kwargs["data"] = text_payload

        if absolute_url:
            url = f"{absolute_url.rstrip('/')}?{urlencode(query_pairs)}"
            logging.debug("VRM HTTP %s %s", method, url)
            started = _now_ms()
            try:
                response = self.session.request(method, url, **request_kwargs)
            except requests.RequestException as exc:
                elapsed = (_now_ms() - started)
                return VRMCommandResult(
                    ok=False,
                    method=method,
                    url=url,
                    status_code=None,
                    elapsed_ms=elapsed,
                    response_excerpt=None,
                    response_json=None,
                    error=str(exc),
                )
        else:
            response = None
            url = ""
            started = _now_ms()
            urls = list(self.base_urls)
            for idx, base_url in enumerate(urls):
                attempt_url = f"{base_url}?{urlencode(query_pairs)}"
                logging.debug("VRM HTTP %s %s", method, attempt_url)
                try:
                    response = self.session.request(method, attempt_url, **request_kwargs)
                    url = attempt_url
                    if idx > 0:
                        logging.warning("VRM fallback succeeded: %s", base_url)
                        self._promote_base_url(idx)
                    break
                except requests.RequestException as exc:
                    if idx == len(urls) - 1 or not _is_retryable_connection_error(exc):
                        elapsed = (_now_ms() - started)
                        return VRMCommandResult(
                            ok=False,
                            method=method,
                            url=attempt_url,
                            status_code=None,
                            elapsed_ms=elapsed,
                            response_excerpt=None,
                            response_json=None,
                            error=str(exc),
                        )
                    logging.warning(
                        "VRM endpoint failed: %s (%s). Trying fallback.",
                        base_url,
                        exc,
                    )
            if response is None:
                elapsed = (_now_ms() - started)
                return VRMCommandResult(
                    ok=False,
                    method=method,
                    url=url,
                    status_code=None,
                    elapsed_ms=elapsed,
                    response_excerpt=None,
                    response_json=None,
                    error="No VRM endpoint available",
                )

        excerpt: Optional[str] = None
        parsed_json: Optional[Any] = None
        text = response.text or ""
        if text:
            excerpt = text[:2000]
        try:
            parsed_json = response.json()
        except ValueError:
            parsed_json = None

        elapsed_ms = ((_now_ms() - started)
                      if response.elapsed is None
                      else response.elapsed.total_seconds() * 1000.0)

        return VRMCommandResult(
            ok=response.ok,
            method=method,
            url=url,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            response_excerpt=excerpt,
            response_json=parsed_json,
        )


class MCPProxyServer:
    """Minimal MCP server that exposes VRM HTTP operations and VOICEVOX TTS as tools."""

    def __init__(
        self,
        base_url: str,
        *,
        vrmah_candidates: Optional[List[str]] = None,
        default_timeout: float = 10.0,
        instructions: str = INSTRUCTION_TEXT,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.bridge = VRMHttpBridge(
            base_url,
            default_timeout=default_timeout,
            candidates=vrmah_candidates,
        )
        self.instructions = instructions
        self.protocol_version = LATEST_PROTOCOL_VERSION
        self.initialized = False
        self._lock = threading.Lock()
        self._running = True

        # VOICEVOX setup
        self.voicevox_client: Optional[VoicevoxClient] = None
        self.voicevox_config: Optional[VoicevoxConfig] = None
        if config:
            self.voicevox_config = VoicevoxConfig.from_config(config)
            if self.voicevox_config:
                self.voicevox_client = VoicevoxClient(
                    self.voicevox_config.server,
                    self.voicevox_config.style_id,
                    candidates=self.voicevox_config.candidates,
                )
                logging.info("VOICEVOX client initialized: %s (speaker: %s)",
                             self.voicevox_config.server, self.voicevox_config.name)

    def shutdown(self) -> None:
        self._running = False
        self.bridge.close()
        if self.voicevox_client:
            self.voicevox_client.close()

    # JSON-RPC helpers -------------------------------------------------
    # Auto-detect framing: Content-Length (LSP-style) or NDJSON (line-delimited).
    # The first message determines the mode for the session.
    _framing: Optional[str] = None  # "content-length" or "ndjson"

    def _write_message(self, message: Dict[str, Any]) -> None:
        payload = _json_dumps(message).encode("utf-8")
        if self._framing == "ndjson":
            sys.stdout.buffer.write(payload + b"\n")
        else:
            header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
            sys.stdout.buffer.write(header)
            sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()

    def _read_message(self) -> Optional[Dict[str, Any]]:
        # Read the first line to determine framing mode
        first_line = sys.stdin.buffer.readline()
        if not first_line:
            return None

        stripped = first_line.strip()
        if not stripped:
            # Empty line; skip and retry
            return self._read_message()

        # Auto-detect: if line starts with '{', it's NDJSON
        if stripped.startswith(b"{"):
            if self._framing is None:
                self._framing = "ndjson"
                logging.info("Detected NDJSON framing")
            return json.loads(stripped.decode("utf-8"))

        # Otherwise treat as Content-Length header
        if self._framing is None:
            self._framing = "content-length"
            logging.info("Detected Content-Length framing")

        # Parse remaining headers
        headers: Dict[str, str] = {}
        try:
            line_text = first_line.decode("ascii", errors="replace").strip()
        except Exception:
            line_text = ""
        if ":" in line_text:
            key, value = line_text.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            try:
                line_text = line.decode("ascii", errors="replace").strip()
            except Exception:
                line_text = ""
            if ":" not in line_text:
                continue
            key, value = line_text.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        if "content-length" not in headers:
            raise ValueError("Missing Content-Length header")
        body_length = int(headers["content-length"])
        if body_length < 0:
            raise ValueError("Negative Content-Length")

        body = sys.stdin.buffer.read(body_length)
        if body is None or len(body) != body_length:
            raise ValueError("Unexpected EOF while reading message body")
        return json.loads(body.decode("utf-8"))

    def _send_result(self, request_id: Any, result: Dict[str, Any]) -> None:
        payload = {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "result": result,
        }
        self._write_message(payload)

    def _send_error(self, request_id: Any, code: int, message: str, data: Any = None) -> None:
        payload: Dict[str, Any] = {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
        if data is not None:
            payload["error"]["data"] = data
        self._write_message(payload)

    def run_stdio_loop(self) -> None:
        logging.info("Starting MCP proxy on stdio transport")
        while self._running:
            try:
                message = self._read_message()
            except json.JSONDecodeError as exc:
                logging.error("Failed to parse JSON: %s", exc)
                self._send_error(None, -32700, f"Parse error: {exc}")
                continue
            except Exception as exc:
                logging.error("Failed to read MCP stdio message: %s", exc)
                self._send_error(None, -32700, f"Invalid message framing: {exc}")
                continue

            if message is None:
                break
            try:
                self._handle_message(message)
            except Exception as exc:  # pylint: disable=broad-except
                logging.exception("Unhandled exception while handling message")
                request_id = message.get("id")
                self._send_error(request_id, -32603, f"Internal error: {exc}")
        logging.info("MCP proxy loop finished")

    # Message handling --------------------------------------------------
    def _handle_message(self, message: Dict[str, Any]) -> None:
        if "method" in message:
            if "id" in message:
                self._handle_request(message)
            else:
                self._handle_notification(message)
        else:
            logging.debug("Ignoring message without method: %s", message)

    def _handle_notification(self, message: Dict[str, Any]) -> None:
        method = message.get("method")
        if method == "notifications/initialized":
            logging.info("Client completed initialization")
            return
        logging.debug("Notification received: %s", method)

    def _handle_request(self, message: Dict[str, Any]) -> None:
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}
        logging.debug("Handling request %s (id=%s)", method, request_id)

        if method == "initialize":
            self._handle_initialize(request_id, params)
        elif method == "ping":
            self._send_result(request_id, {})
        elif method == "shutdown":
            self._send_result(request_id, {})
            self.shutdown()
        elif method == "tools/list":
            self._handle_tools_list(request_id)
        elif method == "tools/call":
            self._handle_tool_call(request_id, params)
        elif method == "resources/list":
            self._handle_resources_list(request_id)
        elif method == "resources/templates/list":
            self._handle_resource_templates_list(request_id)
        elif method == "resources/read":
            self._handle_resource_read(request_id, params)
        else:
            self._send_error(request_id, -32601, f"Method not found: {method}")

    # Initialize --------------------------------------------------------
    def _handle_initialize(self, request_id: Any, params: Dict[str, Any]) -> None:
        protocol_version = params.get("protocolVersion")
        if protocol_version in SUPPORTED_PROTOCOL_VERSIONS:
            negotiated = protocol_version
        else:
            negotiated = LATEST_PROTOCOL_VERSION
        self.protocol_version = negotiated
        with self._lock:
            self.initialized = True

        capabilities = {
            "tools": {"listChanged": False},
            "resources": {"listChanged": False},
        }

        result = {
            "protocolVersion": negotiated,
            "capabilities": capabilities,
            "serverInfo": DEFAULT_SERVER_INFO,
            "instructions": self.instructions,
        }
        self._send_result(request_id, result)

    # Tools --------------------------------------------------------------
    def _tool_definitions(self) -> List[Dict[str, Any]]:
        base_url = self.bridge.base_url
        vrm_command_tool = {
            "name": "vrm_command",
            "title": "VRM HTTP command",
            "description": (
                "Send a single HTTP request to the VRM Agent Host. "
                f"Base URL: {base_url}"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Value for target= query"},
                    "cmd": {"type": "string", "description": "Value for cmd= query"},
                    "params": {
                        "type": "object",
                        "description": "Additional query parameters",
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "DELETE"],
                        "default": "GET",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Request timeout in seconds",
                        "default": self.bridge.default_timeout,
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers",
                    },
                    "json_payload": {
                        "type": "object",
                        "description": "JSON body for POST/PUT",
                    },
                    "text_payload": {
                        "type": "string",
                        "description": "Plain text body for POST/PUT",
                    },
                    "absolute_url": {
                        "type": "string",
                        "description": "Override base URL completely (advanced)",
                    },
                },
                "required": ["target", "cmd"],
                "additionalProperties": True,
            },
        }

        batch_tool = {
            "name": "batch_vrm_commands",
            "title": "Batch VRM HTTP commands",
            "description": (
                "Execute multiple VRM HTTP operations sequentially. "
                "Each entry mirrors vrm_command arguments."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "commands": {
                        "type": "array",
                        "items": vrm_command_tool["inputSchema"],
                        "minItems": 1,
                    }
                },
                "required": ["commands"],
            },
        }

        tools = [vrm_command_tool, batch_tool]

        # Add VOICEVOX tools if configured
        if self.voicevox_client:
            voicevox_speak_tool = {
                "name": "voicevox_speak",
                "title": "VOICEVOX Text-to-Speech",
                "description": (
                    "Synthesize text using VOICEVOX and play through VRM Agent Host. "
                    f"Default speaker: {self.voicevox_config.name} (ID: {self.voicevox_config.style_id})"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to synthesize and speak",
                        },
                        "speaker_id": {
                            "type": "integer",
                            "description": f"Speaker style ID (default: {self.voicevox_config.style_id})",
                        },
                        "speed_scale": {
                            "type": "number",
                            "description": "Speech speed (default: 1.0, range: 0.5-2.0)",
                            "default": 1.0,
                        },
                        "volume_scale": {
                            "type": "number",
                            "description": "Volume (default: 1.0, range: 0.0-2.0)",
                            "default": 1.0,
                        },
                    },
                    "required": ["text"],
                },
            }

            voicevox_speakers_tool = {
                "name": "voicevox_speakers",
                "title": "List VOICEVOX speakers",
                "description": "Get list of available VOICEVOX speakers and their style IDs.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            }

            tools.extend([voicevox_speak_tool, voicevox_speakers_tool])

        return tools

    def _handle_tools_list(self, request_id: Any) -> None:
        result = {
            "tools": self._tool_definitions(),
        }
        self._send_result(request_id, result)

    def _handle_tool_call(self, request_id: Any, params: Dict[str, Any]) -> None:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        logging.debug("Tool call %s args=%s", name, arguments)
        if name == "vrm_command":
            result = self._execute_single_command(arguments)
            self._send_result(request_id, result)
        elif name == "batch_vrm_commands":
            result = self._execute_batch(arguments)
            self._send_result(request_id, result)
        elif name == "voicevox_speak":
            result = self._execute_voicevox_speak(arguments)
            self._send_result(request_id, result)
        elif name == "voicevox_speakers":
            result = self._execute_voicevox_speakers(arguments)
            self._send_result(request_id, result)
        else:
            self._send_error(request_id, -32602, f"Unknown tool: {name}")

    def _execute_single_command(self, args: Dict[str, Any]) -> Dict[str, Any]:
        missing = [key for key in ("target", "cmd") if not args.get(key)]
        if missing:
            message = f"Missing required arguments: {', '.join(missing)}"
            return {
                "content": [
                    {
                        "type": "text",
                        "text": message,
                    }
                ],
                "structuredContent": {
                    "ok": False,
                    "method": None,
                    "url": None,
                    "status_code": None,
                    "elapsed_ms": None,
                    "response_excerpt": None,
                    "response_json": None,
                    "error": message,
                },
                "isError": True,
            }

        result = self.bridge.perform_call(
            target=str(args.get("target")),
            cmd=str(args.get("cmd")),
            params=args.get("params") or {},
            method=args.get("method", "GET"),
            timeout=args.get("timeout"),
            headers=args.get("headers"),
            json_payload=args.get("json_payload"),
            text_payload=args.get("text_payload"),
            absolute_url=args.get("absolute_url"),
        )

        summary = f"{result.method} {result.url} -> "
        if result.status_code is not None:
            summary += f"{result.status_code}"
        if result.error:
            summary += f" (error: {result.error})"
        content_text = summary
        if result.response_json is not None:
            snippet = _json_dumps(result.response_json)
            content_text += f"\nJSON: {snippet[:1200]}"
        elif result.response_excerpt:
            content_text += f"\nTEXT: {result.response_excerpt[:1200]}"

        return {
            "content": [{"type": "text", "text": content_text}],
            "structuredContent": result.structured(),
            "isError": not result.ok,
        }

    def _execute_batch(self, args: Dict[str, Any]) -> Dict[str, Any]:
        commands = args.get("commands") or []
        if not isinstance(commands, list) or not commands:
            return {
                "content": [{"type": "text", "text": "commands must be a non-empty list"}],
                "structuredContent": {
                    "executed": 0,
                    "errors": 1,
                    "results": [],
                },
                "isError": True,
            }
        results: List[Dict[str, Any]] = []
        error_count = 0
        for idx, command in enumerate(commands, start=1):
            single_result = self._execute_single_command(command)
            structured = single_result.get("structuredContent") or {
                "ok": False,
                "error": "Tool execution returned no structured content",
            }
            structured["index"] = idx
            results.append(structured)
            if single_result.get("isError"):
                error_count += 1
        text = f"Executed {len(commands)} VRM command(s). Errors: {error_count}"
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": {
                "executed": len(commands),
                "errors": error_count,
                "results": results,
            },
            "isError": error_count > 0,
        }

    # VOICEVOX ----------------------------------------------------------
    def _execute_voicevox_speak(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize text with VOICEVOX and send to VRM Agent Host."""
        if not self.voicevox_client:
            return {
                "content": [{"type": "text", "text": "VOICEVOX is not configured"}],
                "structuredContent": {"ok": False, "error": "VOICEVOX not configured"},
                "isError": True,
            }

        text = args.get("text", "")
        if not text:
            return {
                "content": [{"type": "text", "text": "text parameter is required"}],
                "structuredContent": {"ok": False, "error": "text is required"},
                "isError": True,
            }

        speaker_id = args.get("speaker_id", self.voicevox_config.style_id)
        speed_scale = args.get("speed_scale", 1.0)
        volume_scale = args.get("volume_scale", 1.0)

        import traceback
        step = "init"
        audio_size = 0
        try:
            # Step 1: Synthesize audio with VOICEVOX
            step = "synthesize"
            audio_data = self.voicevox_client.synthesize(
                text, speaker_id, speed_scale, volume_scale
            )
            audio_size = len(audio_data)

            # Step 2: Send audio to VRM Agent Host waveplay endpoint
            step = "prepare_request"
            headers = {
                "Content-Type": "audio/wav",
                "X-Audio-ID": f"voicevox_{int(time.time() * 1000)}",
            }

            step = "send_to_vrmah"
            response = self.bridge._request_with_base_fallback(
                method="POST",
                path="/waveplay/",
                text_payload=audio_data,
                headers=headers,
                timeout=30,
            )

            step = "process_response"
            if response.ok:
                result_text = f"Synthesized and played ({audio_size} bytes)"
                return {
                    "content": [{"type": "text", "text": result_text}],
                    "structuredContent": {
                        "ok": True,
                        "audio_size": audio_size,
                        "vrmah_status": response.status_code,
                    },
                    "isError": False,
                }
            else:
                error_msg = f"VRM Agent Host returned {response.status_code}"
                return {
                    "content": [{"type": "text", "text": error_msg}],
                    "structuredContent": {
                        "ok": False,
                        "error": error_msg,
                        "audio_size": audio_size,
                        "vrmah_status": response.status_code,
                    },
                    "isError": True,
                }

        except Exception as e:
            # Get traceback info
            tb_lines = traceback.format_exc().split('\n')
            # Keep only last few lines to avoid encoding issues
            tb_short = '\n'.join(tb_lines[-5:]) if len(tb_lines) > 5 else '\n'.join(tb_lines)
            # Safely convert error to ASCII
            try:
                error_str = str(e).encode('ascii', 'replace').decode('ascii')
            except Exception:
                error_str = "encoding error"
            error_msg = f"Error at step '{step}': {error_str}"
            return {
                "content": [{"type": "text", "text": error_msg}],
                "structuredContent": {"ok": False, "error": error_str, "step": step, "audio_size": audio_size},
                "isError": True,
            }

    def _execute_voicevox_speakers(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get list of available VOICEVOX speakers."""
        if not self.voicevox_client:
            return {
                "content": [{"type": "text", "text": "VOICEVOX is not configured"}],
                "structuredContent": {"ok": False, "error": "VOICEVOX not configured"},
                "isError": True,
            }

        try:
            speakers = self.voicevox_client.get_speakers()

            # Format speaker list for display
            lines = ["Available VOICEVOX speakers:"]
            for sp in speakers:
                name = sp.get("name", "")
                for style in sp.get("styles", []):
                    style_id = style.get("id", "")
                    style_name = style.get("name", "")
                    lines.append(f"  {style_id}: {name} - {style_name}")

            text = "\n".join(lines)
            return {
                "content": [{"type": "text", "text": text}],
                "structuredContent": {
                    "ok": True,
                    "speakers": speakers,
                    "default_speaker_id": self.voicevox_config.style_id,
                    "default_speaker_name": self.voicevox_config.name,
                },
                "isError": False,
            }

        except Exception as e:
            error_msg = f"Failed to get speakers: {e}"
            logging.error(error_msg)
            return {
                "content": [{"type": "text", "text": error_msg}],
                "structuredContent": {"ok": False, "error": str(e)},
                "isError": True,
            }

    # Resources ---------------------------------------------------------
    def _read_file_safe(self, file_path: str, file_name: str) -> str:
        """Read a file and return its contents, with error handling."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logging.warning("%s not found at %s", file_name, file_path)
            return f"File not found: {file_path}\n\nPlease ensure {file_name} exists in the mcp_proxy directory."
        except Exception as exc:
            logging.error("Failed to read %s: %s", file_name, exc)
            return f"Error reading {file_name}: {exc}"

    def _resource_entries(self) -> List[Dict[str, Any]]:
        return [
            {
                "uri": "vrm-proxy://instructions",
                "name": "vrm_proxy_instructions",
                "title": "VRM MCP proxy usage",
                "description": "Step-by-step instructions for vrm_command tool",
            },
            {
                "uri": "vrm-proxy://api-spec",
                "name": "vrm_api_specification",
                "title": "VRM Agent Host API Quick Reference",
                "description": "Basic API commands for common operations (animation, menu, gaze, lip sync)",
            },
            {
                "uri": "vrm-proxy://api-spec-detailed",
                "name": "vrm_api_specification_detailed",
                "title": "VRM Agent Host API Detailed Reference",
                "description": "Complete API reference including Body Interaction, IK/FK, advanced parameters",
            }
        ]

    def _handle_resources_list(self, request_id: Any) -> None:
        result = {
            "resources": self._resource_entries(),
        }
        self._send_result(request_id, result)

    def _handle_resource_templates_list(self, request_id: Any) -> None:
        result = {
            "resourceTemplates": [],
        }
        self._send_result(request_id, result)

    def _handle_resource_read(self, request_id: Any, params: Dict[str, Any]) -> None:
        uri = params.get("uri")
        if uri == "vrm-proxy://instructions":
            text = (
                "Use `vrm_command` to proxy any VRM Agent Host HTTP endpoint. "
                "Required fields: target, cmd. Optional: params (dict), method, "
                "timeout, headers, json_payload, text_payload, absolute_url. "
                "For sequential operations, call the `batch_vrm_commands` tool."
            )
        elif uri == "vrm-proxy://api-spec":
            # Read from instructions.md file (quick reference)
            script_dir = os.path.dirname(os.path.abspath(__file__))
            instructions_path = os.path.join(script_dir, "instructions.md")
            text = self._read_file_safe(instructions_path, "instructions.md")
        elif uri == "vrm-proxy://api-spec-detailed":
            # Read from detailed_instructions.md file (complete reference)
            script_dir = os.path.dirname(os.path.abspath(__file__))
            detailed_path = os.path.join(script_dir, "detailed_instructions.md")
            text = self._read_file_safe(detailed_path, "detailed_instructions.md")
        else:
            text = f"Unknown resource: {uri}"
        result = {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/plain",
                    "text": text,
                }
            ]
        }
        self._send_result(request_id, result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VRM MCP proxy server")
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("VRM_AGENT_HOST_TIMEOUT", "10.0")),
        help="Default timeout (seconds) for HTTP requests",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("VRM_MCP_PROXY_LOG", "INFO"),
        help="Logging level (DEBUG, INFO, ...)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # Configure logging to use stderr (already reconfigured for UTF-8 with errors='replace')
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

    # Load config.json
    config = _load_config()

    base_url, vrmah_candidates = _resolve_vrmah_endpoints(config)
    logging.info("VRM Agent Host URL: %s", base_url)
    if vrmah_candidates:
        logging.info("VRM fallback candidates: %s", ", ".join(vrmah_candidates))

    server = MCPProxyServer(
        base_url,
        vrmah_candidates=vrmah_candidates,
        default_timeout=args.timeout,
        config=config,
    )
    try:
        server.run_stdio_loop()
    except KeyboardInterrupt:
        logging.info("Interrupted by user, shutting down")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
