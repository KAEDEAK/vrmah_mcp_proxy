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
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

import requests

# Force UTF-8 encoding for Windows (must be done early, before any I/O)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="surrogateescape")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="surrogateescape")
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="surrogateescape")

# Side-by-side lifecycle module. ``_lifecycle`` installs idle / parent
# watchdog daemon threads so this process exits cleanly when the MCP
# host (codex / claude / VSCode) goes away — without it, orphaned
# generations accumulate on Windows because ``stdin`` does not always
# see EOF when ``codex.exe app-server`` hands a fresh subprocess
# without closing the previous one's pipe. See ``_lifecycle.py`` next
# to this file for the full rationale.
try:
    import _lifecycle  # type: ignore
except Exception:  # pragma: no cover - lifecycle is optional, never fatal
    _lifecycle = None  # type: ignore[assignment]

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
    "Common VRM Agent Host commands (partial list, NOT exhaustive):\n"
    "- vrm/getLoc - Get avatar position\n"
    "- vrm/getRot - Get avatar rotation\n"
    "- vrm/gaze_control - Control gaze (enable=true/false)\n"
    "- animation/play - Play animation (id=Idle_generic&seamless=y)\n"
    "- background/fill - Set background color (color=FF0000)\n"
    "- fk/play, fk/stop, fk/upload_clip - FK animation playback\n"
    "- wing_menu/... - Wing radial menu operations\n\n"
    "Use `vrm_command` with target and cmd parameters. Use `batch_vrm_commands` for "
    "multi-step sequences. `fk_generate_and_play` is also exposed when soma_to_vrm "
    "is configured server-side (text-to-motion generation).\n\n"
    "VOICEVOX TTS:\n"
    "- voicevox_speak - Synthesize text and play through VRM Agent Host\n"
    "- voicevox_speakers - List available speakers\n\n"
    "## IMPORTANT: How to discover the exact target/cmd/params\n"
    "The list above is a minimal cheat sheet. Follow this TWO-STEP lookup:\n\n"
    "**Step 1 — Read the Quick Reference FIRST:**\n"
    "    uri: vrm-proxy://api-spec\n"
    "This concise document covers the most common commands (animation, wing_menu, gaze, "
    "camera, background, lip sync, etc.). Most tasks can be solved with this alone.\n\n"
    "**Step 2 — Only if Step 1 didn't cover your need**, read the detailed spec:\n"
    "    uri: vrm-proxy://api-spec-detailed\n"
    "This is a ~30KB full reference. Page through it to find advanced or uncommon commands "
    "(Body Interaction, IK/FK, advanced parameters).\n\n"
    "If a vrm_command call fails with 'Unknown command' or a 4xx, it means you guessed "
    "wrong — read the spec (start with api-spec) and retry. "
    "Do NOT give up after one failed guess.\n\n"
    "Resources exposed by this server:\n"
    "- vrm-proxy://instructions      (these instructions, full text)\n"
    "- vrm-proxy://api-spec          (concise API spec — READ THIS FIRST)\n"
    "- vrm-proxy://api-spec-detailed (full reference, ~30KB — use only when api-spec is insufficient)"
)


def _load_config(config_file: str = "config.json") -> Dict[str, Any]:
    """Load configuration from a JSON file in the same directory."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, config_file)
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


def _resolve_soma_endpoint(config: Dict[str, Any]) -> Tuple[Optional[str], List[str]]:
    """Resolve soma_to_vrm API server URL and fallback candidates from config.

    Accepts either a plain string or a dict with `host` / `server` and `candidates`.
    Returns (base_url, candidates). base_url is None if not configured.
    """
    soma = config.get("soma_to_vrm") if isinstance(config, dict) else None
    if isinstance(soma, str):
        base = _normalize_base_url(soma, "")
        return (base or None), []
    if isinstance(soma, dict):
        base = _normalize_base_url(soma.get("host") or soma.get("server"), "")
        if not base:
            return None, []
        candidates = _normalize_url_candidates(soma.get("candidates"), base)
        # Drop the primary itself from candidates list
        candidates = [c for c in candidates if c != base]
        return base, candidates
    return None, []


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

        # soma_to_vrm setup (optional)
        self.soma_base_url: Optional[str] = None
        self.soma_candidates: List[str] = []
        if config:
            self.soma_base_url, self.soma_candidates = _resolve_soma_endpoint(config)
            if self.soma_base_url:
                logging.info("soma_to_vrm URL: %s", self.soma_base_url)
                if self.soma_candidates:
                    logging.info("soma_to_vrm fallback candidates: %s",
                                 ", ".join(self.soma_candidates))

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
        # Bracket every host-driven message with the lifecycle in-flight
        # counter so the idle watchdog cannot recycle the process while
        # we are still serving a request. ``mark_request_end`` is in a
        # ``finally`` so an internal exception path cannot leak the
        # counter — a leaked counter would block the idle watchdog
        # indefinitely.
        if _lifecycle is not None:
            _lifecycle.mark_request_start()
        try:
            if "method" in message:
                if "id" in message:
                    self._handle_request(message)
                else:
                    self._handle_notification(message)
            else:
                logging.debug("Ignoring message without method: %s", message)
        finally:
            if _lifecycle is not None:
                _lifecycle.mark_request_end()

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

        # FK helper tools
        fk_sample_pose_tool = {
            "name": "fk_sample_pose",
            "title": "FK Pose Sampling",
            "description": (
                "Sample FK bone rotations multiple times during animation playback. "
                "Returns min/max/avg statistics for each bone axis. "
                "Euler angles are signed-normalized (-180..180) before statistics."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "samples": {
                        "type": "integer",
                        "description": "Number of samples to take (default: 5)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 100,
                    },
                    "interval_ms": {
                        "type": "integer",
                        "description": "Interval between samples in milliseconds (default: 500)",
                        "default": 500,
                        "minimum": 0,
                    },
                    "bones": {
                        "type": "string",
                        "description": "Bone filter: 'main' for 18 main bones, comma-separated names (e.g. 'Hips,Spine,Head'), or omit for all",
                    },
                },
            },
        }

        fk_snapshot_to_frame_tool = {
            "name": "fk_snapshot_to_frame",
            "title": "FK Snapshot to Animation Frame",
            "description": (
                "Capture current FK bone rotations and save as an IK animation frame. "
                "Only saves rotation (not position). Use fk_get for position if needed."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "anim_name": {
                        "type": "string",
                        "description": "Animation name to save to",
                    },
                    "frame": {
                        "type": "integer",
                        "description": "Frame number",
                    },
                    "playtime": {
                        "type": "number",
                        "description": "Playtime in seconds (default: 0.4)",
                        "default": 0.4,
                    },
                    "bones": {
                        "type": "string",
                        "description": "Bone filter: 'main' for 18 main bones, comma-separated names (e.g. 'Hips,Spine,Head'), or omit for all",
                    },
                },
                "required": ["anim_name", "frame"],
            },
        }

        fk_rotate_delta_tool = {
            "name": "fk_rotate_delta",
            "title": "FK Relative Rotation",
            "description": (
                "Apply a relative rotation delta to a bone. "
                "Reads current rotation, adds delta, and sets the result."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "bone": {
                        "type": "string",
                        "description": "HumanBodyBones name (e.g. RightUpperArm)",
                    },
                    "delta": {
                        "type": "string",
                        "description": "Rotation delta as x,y,z (e.g. '0,10,0')",
                    },
                    "coord": {
                        "type": "string",
                        "description": "Coordinate system: 'local' (default) or 'global'",
                        "default": "local",
                        "enum": ["local", "global"],
                    },
                },
                "required": ["bone", "delta"],
            },
        }

        tools.extend([fk_sample_pose_tool, fk_snapshot_to_frame_tool, fk_rotate_delta_tool])

        if self.soma_base_url:
            fk_generate_and_play_tool = {
                "name": "fk_generate_and_play",
                "title": "Text to FK Animation (generate & play)",
                "description": (
                    "Generate an FK animation clip from text via soma_to_vrm and play it on the VRM avatar. "
                    "Submits text to the soma_to_vrm API, polls until done, uploads the resulting clip "
                    "to VRM Agent Host, and starts FK playback. Hides the entire pipeline behind a single call."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Natural-language motion description (e.g. 'a person waves hello')",
                            "minLength": 1,
                            "maxLength": 2048,
                        },
                        "pose_type": {
                            "type": "string",
                            "description": "Rest pose: 'T' (default) or 'A'",
                            "default": "T",
                            "enum": ["T", "A"],
                        },
                        "loop": {
                            "type": "boolean",
                            "description": "Loop playback (default false)",
                            "default": False,
                        },
                        "speed": {
                            "type": "number",
                            "description": "Playback speed multiplier (default 1.0)",
                            "default": 1.0,
                            "minimum": 0.1,
                            "maximum": 5.0,
                        },
                        "blend": {
                            "type": "number",
                            "description": "Crossfade blend duration in seconds (default 0.25)",
                            "default": 0.25,
                            "minimum": 0.0,
                            "maximum": 5.0,
                        },
                        "auto_enable_fk": {
                            "type": "boolean",
                            "description": "Auto-issue 'fk enable=true' before play (default true)",
                            "default": True,
                        },
                        "seconds": {
                            "type": "number",
                            "description": "Motion duration in seconds (default 3.0, range 0.5-30.0)",
                            "default": 3.0,
                            "minimum": 0.5,
                            "maximum": 30.0,
                        },
                    },
                    "required": ["text"],
                },
            }
            tools.append(fk_generate_and_play_tool)

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
        elif name == "fk_sample_pose":
            result = self._execute_fk_sample_pose(arguments)
            self._send_result(request_id, result)
        elif name == "fk_snapshot_to_frame":
            result = self._execute_fk_snapshot_to_frame(arguments)
            self._send_result(request_id, result)
        elif name == "fk_rotate_delta":
            result = self._execute_fk_rotate_delta(arguments)
            self._send_result(request_id, result)
        elif name == "fk_generate_and_play":
            result = self._execute_fk_generate_and_play(arguments)
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

    # FK helpers --------------------------------------------------------
    @staticmethod
    def _signed_angle(val: float) -> float:
        """Normalize 0-360 Euler to -180..180 range."""
        if val > 180.0:
            return val - 360.0
        return val

    @staticmethod
    def _extract_error_message(result) -> str:
        """Extract meaningful error message from VRMCommandResult.

        Falls back through: result.error -> response_json.message -> response_excerpt -> generic.
        """
        if result.error:
            return result.error
        if result.response_json and isinstance(result.response_json, dict):
            msg = result.response_json.get("message")
            if msg:
                return str(msg)
        if result.response_excerpt:
            return result.response_excerpt[:200]
        return f"HTTP {result.status_code}" if result.status_code else "unknown error"

    @staticmethod
    def _unwrap_angles(angles: List[float]) -> List[float]:
        """Unwrap angle series so that consecutive jumps > 180 are corrected.

        Uses raw previous value (not accumulated) to compute diff,
        and while-loops for ±360 normalization to handle multi-rotation.
        """
        if not angles:
            return angles
        unwrapped = [angles[0]]
        for i in range(1, len(angles)):
            diff = angles[i] - angles[i - 1]
            while diff > 180.0:
                diff -= 360.0
            while diff < -180.0:
                diff += 360.0
            unwrapped.append(unwrapped[-1] + diff)
        return unwrapped

    def _fk_get_all(self, bones: str = None) -> Dict[str, Any]:
        """Call fk get_all and return parsed result."""
        params: Dict[str, Any] = {}
        if bones == "main":
            params["bones"] = bones
        result = self.bridge.perform_call(target="fk", cmd="get_all", params=params)
        return result

    @staticmethod
    def _filter_bone_list(bone_list: list, bones_filter: str) -> list:
        """Filter bone_list by comma-separated bone names (client-side).

        If bones_filter is None, empty, or 'main', returns bone_list as-is
        (server already handled 'main' filtering).
        """
        if not bones_filter or bones_filter == "main":
            return bone_list
        allowed = set(b.strip() for b in bones_filter.split(",") if b.strip())
        return [b for b in bone_list if b.get("bone", "") in allowed]

    def _execute_fk_sample_pose(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Sample FK rotations N times and return min/max/avg statistics."""
        samples = int(args.get("samples", 5))
        interval_ms = int(args.get("interval_ms", 500))
        bones_filter = args.get("bones")

        if samples < 1 or samples > 100:
            return {
                "content": [{"type": "text", "text": "samples must be 1-100"}],
                "structuredContent": {"ok": False, "error": "samples out of range"},
                "isError": True,
            }
        if interval_ms < 0:
            return {
                "content": [{"type": "text", "text": "interval_ms must be >= 0"}],
                "structuredContent": {"ok": False, "error": "interval_ms out of range"},
                "isError": True,
            }

        all_snapshots: List[Dict[str, List[float]]] = []
        for i in range(samples):
            result = self._fk_get_all(bones_filter)
            if not result.ok or not result.response_json:
                err_msg = self._extract_error_message(result)
                return {
                    "content": [{"type": "text", "text": f"fk get_all failed at sample {i+1}: {err_msg}"}],
                    "structuredContent": {"ok": False, "error": err_msg},
                    "isError": True,
                }
            data = result.response_json.get("data", {})
            bone_list = self._filter_bone_list(data.get("bones", []), bones_filter)
            snapshot: Dict[str, List[float]] = {}
            for b in bone_list:
                name = b.get("bone", "")
                rot = b.get("local_rotation", {})
                snapshot[name] = [
                    self._signed_angle(float(rot.get("x", 0))),
                    self._signed_angle(float(rot.get("y", 0))),
                    self._signed_angle(float(rot.get("z", 0))),
                ]
            all_snapshots.append(snapshot)
            if i < samples - 1:
                time.sleep(interval_ms / 1000.0)

        # Compute statistics with circular mean and unwrapped min/max
        stats: Dict[str, Any] = {}
        if all_snapshots:
            all_bones = list(all_snapshots[0].keys())
            for bone_name in all_bones:
                vals = [s[bone_name] for s in all_snapshots if bone_name in s]
                if not vals:
                    continue
                axis_stats = {"min": [], "max": [], "avg": [], "samples": len(vals)}
                for ax in range(3):
                    raw = [v[ax] for v in vals]
                    unwrapped = self._unwrap_angles(raw)
                    axis_stats["min"].append(round(min(unwrapped), 2))
                    axis_stats["max"].append(round(max(unwrapped), 2))
                    axis_stats["avg"].append(round(sum(unwrapped) / len(unwrapped), 2))
                stats[bone_name] = axis_stats

        text = f"Sampled {samples} poses, {len(stats)} bones"
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": {
                "ok": True,
                "samples": samples,
                "interval_ms": interval_ms,
                "bone_count": len(stats),
                "statistics": stats,
            },
            "isError": False,
        }

    def _execute_fk_snapshot_to_frame(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Capture current FK rotations and save as animation frame."""
        anim_name = args.get("anim_name", "")
        frame = args.get("frame")
        playtime = float(args.get("playtime", 0.4))
        bones_filter = args.get("bones")

        if not anim_name or frame is None:
            return {
                "content": [{"type": "text", "text": "anim_name and frame are required"}],
                "structuredContent": {"ok": False, "error": "missing required params"},
                "isError": True,
            }

        # Get current bone rotations
        result = self._fk_get_all(bones_filter)
        if not result.ok or not result.response_json:
            err_msg = self._extract_error_message(result)
            return {
                "content": [{"type": "text", "text": f"fk get_all failed: {err_msg}"}],
                "structuredContent": {"ok": False, "error": err_msg},
                "isError": True,
            }

        data = result.response_json.get("data", {})
        bone_list = self._filter_bone_list(data.get("bones", []), bones_filter)
        saved_count = 0
        errors: List[str] = []

        for b in bone_list:
            bone_name = b.get("bone", "")
            rot = b.get("local_rotation", {})
            rot_str = f"{rot.get('x', 0)},{rot.get('y', 0)},{rot.get('z', 0)}"

            edit_result = self.bridge.perform_call(
                target="ik",
                cmd="animation",
                params={
                    "op": "edit",
                    "anim_name": anim_name,
                    "frame": str(frame),
                    "type": "FK",
                    "bone": bone_name,
                    "rot": rot_str,
                    "coord": "local",
                    "playtime": str(playtime),
                },
            )
            if edit_result.ok:
                saved_count += 1
            else:
                errors.append(f"{bone_name}: {self._extract_error_message(edit_result)}")

        text = f"Saved {saved_count}/{len(bone_list)} bones to {anim_name} frame {frame}"
        if errors:
            text += f" ({len(errors)} errors)"

        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": {
                "ok": len(errors) == 0,
                "anim_name": anim_name,
                "frame": frame,
                "saved_count": saved_count,
                "total_bones": len(bone_list),
                "errors": errors,
            },
            "isError": len(errors) > 0,
        }

    def _execute_fk_rotate_delta(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Apply relative rotation delta to a bone."""
        bone = args.get("bone", "")
        delta_str = args.get("delta", "")
        coord = args.get("coord", "local")

        if not bone or not delta_str:
            return {
                "content": [{"type": "text", "text": "bone and delta are required"}],
                "structuredContent": {"ok": False, "error": "missing required params"},
                "isError": True,
            }

        # Parse delta
        try:
            parts = [float(x.strip()) for x in delta_str.split(",")]
            if len(parts) != 3:
                raise ValueError("need 3 values")
            dx, dy, dz = parts
        except (ValueError, TypeError) as e:
            return {
                "content": [{"type": "text", "text": f"Invalid delta format: {e}"}],
                "structuredContent": {"ok": False, "error": f"invalid delta: {e}"},
                "isError": True,
            }

        # Get current rotation
        get_params: Dict[str, Any] = {"bone": bone}
        if coord == "global":
            get_params["coord"] = "global"
        get_result = self.bridge.perform_call(target="fk", cmd="get", params=get_params)
        if not get_result.ok or not get_result.response_json:
            err_msg = self._extract_error_message(get_result)
            return {
                "content": [{"type": "text", "text": f"fk get failed: {err_msg}"}],
                "structuredContent": {"ok": False, "error": err_msg},
                "isError": True,
            }

        data = get_result.response_json.get("data", {})
        if coord == "global":
            rot = data.get("global_rotation", data.get("local_rotation", {}))
        else:
            rot = data.get("local_rotation", {})

        cur_x = float(rot.get("x", 0))
        cur_y = float(rot.get("y", 0))
        cur_z = float(rot.get("z", 0))

        new_x = cur_x + dx
        new_y = cur_y + dy
        new_z = cur_z + dz

        # Set new rotation
        set_params: Dict[str, Any] = {
            "bone": bone,
            "rot": f"{new_x},{new_y},{new_z}",
        }
        if coord == "global":
            set_params["coord"] = "global"
        set_result = self.bridge.perform_call(target="fk", cmd="set", params=set_params)

        text = f"fk set {bone} rot={new_x:.1f},{new_y:.1f},{new_z:.1f} (delta={dx},{dy},{dz})"
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": {
                "ok": set_result.ok,
                "bone": bone,
                "previous_rotation": {"x": cur_x, "y": cur_y, "z": cur_z},
                "delta": {"x": dx, "y": dy, "z": dz},
                "new_rotation": {"x": new_x, "y": new_y, "z": new_z},
                "coord": coord,
                "status_code": set_result.status_code,
                "error": self._extract_error_message(set_result) if not set_result.ok else None,
            },
            "isError": not set_result.ok,
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

    def _execute_fk_generate_and_play(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Text -> soma_to_vrm -> upload_clip -> fk play (single MCP call).

        Pipeline (per dev/docs/soma_to_vrm_automation_plan1.md):
          1. POST /generate (transport-failure-only retry x2 with same idempotency_key)
          2. Poll GET /jobs/<id> every 3s, max 5 attempts. 500 = discard.
          3. GET /jobs/<id>/file
          4. fk upload_clip (POST body=clip JSON)
          5. fk enable + fk stop&reset=y + fk play
        """

        def _err(msg: str, **extra: Any) -> Dict[str, Any]:
            sc: Dict[str, Any] = {"ok": False, "error": msg}
            sc.update(extra)
            return {
                "content": [{"type": "text", "text": msg}],
                "structuredContent": sc,
                "isError": True,
            }

        if not self.soma_base_url:
            return _err("soma_to_vrm not configured (config.json: soma_to_vrm.host)")

        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            return _err("text is required and must be a non-empty string")

        if len(text) > 2048:
            return _err(f"text exceeds maxLength=2048 (got {len(text)})")

        pose_type = str(args.get("pose_type") or "T").upper()
        if pose_type not in ("T", "A"):
            return _err(f"pose_type must be 'T' or 'A', got: {pose_type}")
        loop = bool(args.get("loop", False))
        auto_enable_fk = bool(args.get("auto_enable_fk", True))
        try:
            speed = float(args.get("speed", 1.0))
        except (TypeError, ValueError):
            return _err("speed must be a number")
        try:
            blend = float(args.get("blend", 0.25))
        except (TypeError, ValueError):
            return _err("blend must be a number")
        if not (0.1 <= speed <= 5.0):
            return _err(f"speed out of range [0.1, 5.0]: {speed}")
        if not (0.0 <= blend <= 5.0):
            return _err(f"blend out of range [0.0, 5.0]: {blend}")
        try:
            seconds = float(args.get("seconds", 3.0))
        except (TypeError, ValueError):
            return _err("seconds must be a number")
        if not (0.5 <= seconds <= 30.0):
            return _err(f"seconds out of range [0.5, 30.0]: {seconds}")

        idem = "ik-" + uuid.uuid4().hex[:16]
        clip_name = idem  # ik- prefix is required for janitor (TODO-1)
        clip_file = f"{clip_name}.vrm.json"

        # Build base URL list with candidates fallback (M1 partial)
        soma_base_urls = [self.soma_base_url] + [
            c for c in self.soma_candidates if c != self.soma_base_url
        ]

        def _soma_request(method: str, path: str, **kw: Any):
            """Try primary URL first, then candidates on transport failure only.
            Returns (response, base_url_used) or raises the last exception."""
            last_exc: Optional[Exception] = None
            for base in soma_base_urls:
                try:
                    return requests.request(method, f"{base}{path}", **kw), base
                except (requests.ConnectionError, requests.Timeout) as e:
                    last_exc = e
                    logging.warning("soma %s %s transport failure on %s: %s",
                                    method, path, base, e)
                    continue
            raise last_exc if last_exc else RuntimeError("no soma endpoint available")

        payload = {"idempotency_key": idem, "text": text, "pose_type": pose_type, "seconds": seconds}

        # 1) submit (transport failure only -> retry x2 with same key, across candidates)
        submit_resp = None
        submit_err = None
        for attempt in range(2):
            try:
                submit_resp, _ = _soma_request("POST", "/generate", json=payload, timeout=4.0)
                break
            except (requests.ConnectionError, requests.Timeout) as e:
                submit_err = e
                logging.warning("soma submit attempt=%d transport failure: %s", attempt + 1, e)
                continue
        if submit_resp is None:
            return _err(f"soma_to_vrm submit failed (transport): {submit_err}", idempotency_key=idem)
        if submit_resp.status_code == 429:
            # Surface retry_after_ms for the caller (m2)
            retry_after_ms = None
            try:
                retry_after_ms = submit_resp.json().get("retry_after_ms")
            except ValueError:
                pass
            return _err(
                f"soma_to_vrm queue full (HTTP 429)",
                idempotency_key=idem,
                http_status=429,
                retry_after_ms=retry_after_ms,
            )
        if submit_resp.status_code not in (200, 202):
            return _err(
                f"soma_to_vrm submit HTTP {submit_resp.status_code}: {submit_resp.text[:300]}",
                idempotency_key=idem,
                http_status=submit_resp.status_code,
            )

        try:
            submit_json = submit_resp.json()
        except ValueError:
            return _err(f"soma_to_vrm submit returned non-JSON: {submit_resp.text[:300]}")

        job_id = submit_json.get("job_id")
        if not job_id:
            return _err(f"soma_to_vrm submit missing job_id: {submit_json}")

        # 2) poll if not already done (HTTP 200 + status=done = inline completion)
        is_done = (submit_resp.status_code == 200 and submit_json.get("status") == "done")
        result_meta: Dict[str, Any] = {
            "frame_count": submit_json.get("frame_count"),
            "fps": submit_json.get("fps"),
        }
        if not is_done:
            for attempt in range(30):
                time.sleep(5.0)
                try:
                    pr, _ = _soma_request("GET", f"/jobs/{job_id}", timeout=5.0)
                except (requests.ConnectionError, requests.Timeout) as e:
                    logging.warning("soma poll attempt=%d transport: %s", attempt + 1, e)
                    continue
                # M2: 4xx は確定失敗として即返す。retry 対象は transport failure と queued/running のみ。
                if 400 <= pr.status_code < 500:
                    return _err(
                        f"soma job poll HTTP {pr.status_code}: {pr.text[:200]}",
                        job_id=job_id,
                        http_status=pr.status_code,
                    )
                if pr.status_code == 500:
                    return _err(f"soma job 500 (discarded): {pr.text[:200]}", job_id=job_id)
                if pr.status_code != 200:
                    logging.warning("soma poll attempt=%d HTTP %d", attempt + 1, pr.status_code)
                    continue
                try:
                    pj = pr.json()
                except ValueError:
                    continue
                st = pj.get("status")
                if st == "done":
                    is_done = True
                    if pj.get("frame_count") is not None:
                        result_meta["frame_count"] = pj.get("frame_count")
                    if pj.get("fps") is not None:
                        result_meta["fps"] = pj.get("fps")
                    break
                if st == "error":
                    return _err(
                        f"soma job error: {pj.get('error_code', 'unknown')}",
                        job_id=job_id,
                    )
                # queued / running -> next poll
            if not is_done:
                return _err(f"soma job poll timeout (150s)", job_id=job_id)

        # 3) fetch result file
        try:
            fr, _ = _soma_request("GET", f"/jobs/{job_id}/file", timeout=10.0)
        except (requests.ConnectionError, requests.Timeout) as e:
            return _err(f"soma fetch file transport failure: {e}", job_id=job_id)
        if fr.status_code != 200:
            return _err(
                f"soma fetch file HTTP {fr.status_code}: {fr.text[:200]}",
                job_id=job_id,
                http_status=fr.status_code,
            )
        clip_text = fr.text
        clip_bytes = len(fr.content)

        # 4) upload to VRM Agent Host
        up = self.bridge.perform_call(
            target="fk",
            cmd="upload_clip",
            params={"name": clip_name},
            method="POST",
            headers={"Content-Type": "application/json"},
            text_payload=clip_text,
        )
        if not up.ok:
            return _err(
                f"upload_clip failed: {self._extract_error_message(up)}",
                job_id=job_id,
                clip_name=clip_name,
            )

        # 5) (optional) enable + stop&reset + play
        # m1: best-effort 失敗もログに残す
        if auto_enable_fk:
            en = self.bridge.perform_call(target="fk", cmd="enable", params={"enable": "true"})
            if not en.ok:
                logging.warning("fk enable best-effort failed: %s",
                                self._extract_error_message(en))
        st = self.bridge.perform_call(target="fk", cmd="stop", params={"reset": "y"})
        if not st.ok:
            logging.warning("fk stop best-effort failed: %s",
                            self._extract_error_message(st))
        play = self.bridge.perform_call(
            target="fk",
            cmd="play",
            params={
                "file": clip_file,
                "loop": "y" if loop else "n",
                "speed": f"{speed:g}",
                "blend": f"{blend:g}",
            },
        )
        if not play.ok:
            return _err(
                f"fk play failed: {self._extract_error_message(play)}",
                job_id=job_id,
                clip_file=clip_file,
            )

        return {
            "content": [{"type": "text", "text": f"Generated and playing: {clip_file}"}],
            "structuredContent": {
                "ok": True,
                "job_id": job_id,
                "idempotency_key": idem,
                "clip_name": clip_name,
                "clip_file": clip_file,
                "clip_bytes": clip_bytes,
                "frame_count": result_meta.get("frame_count"),
                "fps": result_meta.get("fps"),
                "auto_enable_fk": auto_enable_fk,
                "play_response": play.response_json,
            },
            "isError": False,
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
            # initialize 応答の instructions と同じテキストを返す
            # (Codex 実装後レビュー Minor 1 対応: contract 自己矛盾の解消)
            text = self.instructions or INSTRUCTION_TEXT
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
    parser.add_argument(
        "--config",
        default=os.environ.get("VRM_MCP_CONFIG", "config.json"),
        help="Config filename in the mcp_proxy directory (default: config.json)",
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

    # Load config
    config = _load_config(args.config)
    logging.info("Config file: %s", args.config)

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

    # Install process-lifecycle watchdogs (idle timeout + parent-death
    # detection). Best-effort: if the module is missing or its startup
    # fails we still want to serve requests, so the failure is logged
    # and swallowed rather than aborting boot.
    if _lifecycle is not None:
        try:
            _lifecycle.startup(config_file=args.config, base_url=base_url)
        except Exception as exc:  # pragma: no cover - defensive
            logging.warning("lifecycle.startup() failed: %s", exc)

    try:
        server.run_stdio_loop()
    except KeyboardInterrupt:
        logging.info("Interrupted by user, shutting down")
        if _lifecycle is not None:
            _lifecycle.shutdown("signal_int")
    except SystemExit as exc:
        if _lifecycle is not None:
            _lifecycle.shutdown("system_exit", code=exc.code)
        raise
    except Exception as exc:  # pragma: no cover - top-level fatal
        if _lifecycle is not None:
            _lifecycle.shutdown(
                "exception", type=type(exc).__name__, message=str(exc)
            )
        raise
    else:
        if _lifecycle is not None:
            _lifecycle.shutdown("normal")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
