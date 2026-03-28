"""MCP (Model Context Protocol) client for connecting to external tool servers.

Supports two transports:
  - **stdio**: spawns a subprocess and communicates via stdin/stdout JSON-RPC 2.0
  - **http**: connects to an HTTP+SSE MCP server via POST requests

Key protocol methods:
  - ``initialize``   — handshake with server
  - ``tools/list``   — discover available tools
  - ``tools/call``   — execute a tool with arguments

Thread-safety: each MCPClient instance is independent; MCPClientManager
holds multiple clients keyed by server id.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4


class MCPClientError(RuntimeError):
    """Raised when MCP communication fails."""

    def __init__(self, error_code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 helpers
# ---------------------------------------------------------------------------

def _jsonrpc_request(method: str, params: dict[str, Any] | None = None, req_id: int | str | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    msg["id"] = req_id if req_id is not None else uuid4().hex[:8]
    return msg


def _parse_jsonrpc_response(raw: dict[str, Any], expected_id: int | str | None = None) -> Any:
    if not isinstance(raw, dict):
        raise MCPClientError("mcp_protocol_error", "Response is not a JSON object.")
    if raw.get("jsonrpc") != "2.0":
        raise MCPClientError("mcp_protocol_error", "Response missing jsonrpc 2.0.")
    if expected_id is not None and raw.get("id") != expected_id:
        raise MCPClientError("mcp_protocol_error", f"Response id mismatch: expected {expected_id}, got {raw.get('id')}.")
    if "error" in raw:
        err = raw["error"]
        raise MCPClientError(
            "mcp_server_error",
            err.get("message", "Unknown MCP error"),
            {"code": err.get("code"), "data": err.get("data")},
        )
    return raw.get("result")


# ---------------------------------------------------------------------------
# Transport: stdio
# ---------------------------------------------------------------------------

class _StdioTransport:
    """Spawns an MCP server as a subprocess and communicates via stdin/stdout."""

    def __init__(self, command: list[str], env: dict[str, str] | None = None, cwd: str | None = None):
        self._command = list(command)
        self._env = env
        self._cwd = cwd
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.RLock()

    def connect(self) -> None:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return
            env = dict(os.environ)
            if self._env:
                env.update(self._env)
            env["PYTHONUNBUFFERED"] = "1"
            self._process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
                cwd=self._cwd,
                env=env,
            )

    def send(self, message: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        with self._lock:
            proc = self._process
        if proc is None or proc.poll() is not None:
            raise MCPClientError("mcp_transport_error", "Stdio process is not running.")
        if proc.stdin is None or proc.stdout is None:
            raise MCPClientError("mcp_transport_error", "Stdio pipes not available.")

        raw = json.dumps(message, ensure_ascii=True) + "\n"
        try:
            proc.stdin.write(raw)
            proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise MCPClientError("mcp_transport_error", f"Write failed: {exc}") from exc

        try:
            line = proc.stdout.readline()
        except (OSError, ValueError) as exc:
            raise MCPClientError("mcp_transport_error", f"Read failed: {exc}") from exc

        if not line:
            raise MCPClientError("mcp_transport_error", "Server closed stdout.")
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise MCPClientError("mcp_protocol_error", f"Invalid JSON from server: {exc}") from exc

    def disconnect(self) -> None:
        with self._lock:
            proc = self._process
            self._process = None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
        except Exception:
            pass
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass

    @property
    def alive(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None


# ---------------------------------------------------------------------------
# Transport: HTTP
# ---------------------------------------------------------------------------

class _HttpTransport:
    """Connects to an MCP server via HTTP POST (JSON-RPC over HTTP)."""

    def __init__(self, url: str):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise MCPClientError("mcp_config_error", f"HTTP transport requires http/https URL, got '{url}'.")
        self._url = url

    def connect(self) -> None:
        pass  # stateless — each send is a new request

    def send(self, message: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        body = json.dumps(message, ensure_ascii=True).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = Request(self._url, data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=max(0.5, timeout_ms / 1000)) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise MCPClientError("mcp_transport_error", f"HTTP {exc.code}: {body_text[:500]}") from exc
        except URLError as exc:
            raise MCPClientError("mcp_transport_error", f"Connection failed: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise MCPClientError("mcp_protocol_error", f"Invalid JSON response: {exc}") from exc

    def disconnect(self) -> None:
        pass

    @property
    def alive(self) -> bool:
        return True  # stateless


# ---------------------------------------------------------------------------
# MCPClient — typed interface over a transport
# ---------------------------------------------------------------------------

class MCPClient:
    """Client for a single MCP server."""

    def __init__(
        self,
        server_id: str,
        transport: str = "stdio",
        command: list[str] | None = None,
        url: str | None = None,
        env: dict[str, str] | None = None,
        timeout_ms: int = 10000,
    ):
        self.server_id = server_id
        self.timeout_ms = max(1000, int(timeout_ms))
        self._server_info: dict[str, Any] | None = None
        self._tools: list[dict[str, Any]] = []

        if transport == "stdio":
            if not command:
                raise MCPClientError("mcp_config_error", "Stdio transport requires 'command'.")
            self._transport: _StdioTransport | _HttpTransport = _StdioTransport(command, env=env)
        elif transport == "http":
            if not url:
                raise MCPClientError("mcp_config_error", "HTTP transport requires 'url'.")
            self._transport = _HttpTransport(url)
        else:
            raise MCPClientError("mcp_config_error", f"Unknown transport '{transport}'. Use 'stdio' or 'http'.")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> dict[str, Any]:
        """Connect and perform the MCP initialize handshake."""
        self._transport.connect()
        req = _jsonrpc_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "capability-os", "version": "1.0.0"},
        })
        result = self._call(req)
        self._server_info = result
        return deepcopy(result) if isinstance(result, dict) else {"raw": result}

    def disconnect(self) -> None:
        """Send notifications/cancelled if supported, then close transport."""
        self._transport.disconnect()
        self._server_info = None
        self._tools = []

    # ------------------------------------------------------------------
    # Tool discovery
    # ------------------------------------------------------------------

    def discover_tools(self) -> list[dict[str, Any]]:
        """Call tools/list and return the list of tool descriptors."""
        req = _jsonrpc_request("tools/list", {})
        result = self._call(req)
        if isinstance(result, dict):
            tools = result.get("tools", [])
        elif isinstance(result, list):
            tools = result
        else:
            tools = []
        self._tools = [t for t in tools if isinstance(t, dict)]
        return deepcopy(self._tools)

    def get_cached_tools(self) -> list[dict[str, Any]]:
        """Return the last discovered tool list without a network call."""
        return deepcopy(self._tools)

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call tools/call and return the result content."""
        req = _jsonrpc_request("tools/call", {
            "name": tool_name,
            "arguments": arguments or {},
        })
        result = self._call(req)
        if isinstance(result, dict):
            return deepcopy(result)
        return {"content": [{"type": "text", "text": str(result)}]}

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "connected": self._transport.alive,
            "server_info": deepcopy(self._server_info),
            "tools_discovered": len(self._tools),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call(self, request: dict[str, Any]) -> Any:
        raw_response = self._transport.send(request, self.timeout_ms)
        return _parse_jsonrpc_response(raw_response, expected_id=request.get("id"))


# ---------------------------------------------------------------------------
# MCPClientManager — holds multiple servers
# ---------------------------------------------------------------------------

class MCPClientManager:
    """Manages connections to multiple MCP servers."""

    def __init__(self, default_timeout_ms: int = 10000):
        self._clients: dict[str, MCPClient] = {}
        self._lock = threading.RLock()
        self._default_timeout_ms = default_timeout_ms

    def add_server(self, config: dict[str, Any]) -> MCPClient:
        """Create and connect to an MCP server from config."""
        server_id = config.get("id")
        if not isinstance(server_id, str) or not server_id:
            raise MCPClientError("mcp_config_error", "Server config must include 'id'.")

        client = MCPClient(
            server_id=server_id,
            transport=config.get("transport", "stdio"),
            command=config.get("command"),
            url=config.get("url"),
            env=config.get("env"),
            timeout_ms=config.get("timeout_ms", self._default_timeout_ms),
        )
        with self._lock:
            existing = self._clients.get(server_id)
            if existing is not None:
                existing.disconnect()
            self._clients[server_id] = client
        return client

    def remove_server(self, server_id: str) -> bool:
        with self._lock:
            client = self._clients.pop(server_id, None)
        if client is not None:
            client.disconnect()
            return True
        return False

    def get_client(self, server_id: str) -> MCPClient | None:
        with self._lock:
            return self._clients.get(server_id)

    def list_servers(self) -> list[dict[str, Any]]:
        with self._lock:
            return [client.status() for client in self._clients.values()]

    def disconnect_all(self) -> None:
        with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()
        for client in clients:
            try:
                client.disconnect()
            except Exception:
                pass
