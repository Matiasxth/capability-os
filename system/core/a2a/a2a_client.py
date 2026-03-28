"""A2A Client — discovers remote agents and delegates tasks to them.

Reuses the same HTTP pattern as the MCP client (urllib, no external deps).
Also registers itself as a tool in the ToolRegistry so capabilities
can delegate via ``a2a_delegate_task``.
"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime


class A2AClientError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class A2AClient:
    """Client for a single remote A2A agent."""

    def __init__(self, agent_url: str, timeout_ms: int = 10000):
        self._base = agent_url.rstrip("/")
        self._timeout = max(1000, int(timeout_ms))
        self._card: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> dict[str, Any]:
        """Fetch the remote Agent Card."""
        url = f"{self._base}/.well-known/agent.json"
        data = self._get(url)
        self._card = data
        return deepcopy(data)

    def get_card(self) -> dict[str, Any] | None:
        return deepcopy(self._card)

    # ------------------------------------------------------------------
    # Task delegation
    # ------------------------------------------------------------------

    def send_task(self, skill_id: str, message: str) -> dict[str, Any]:
        """Send a task to the remote agent and return the result."""
        url = f"{self._base}/a2a"
        payload = {
            "skill_id": skill_id,
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": message}],
            },
        }
        return self._post(url, payload)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, url: str) -> dict[str, Any]:
        req = Request(url, method="GET")
        return self._do_request(req)

    def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=True).encode("utf-8")
        req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        return self._do_request(req)

    def _do_request(self, req: Request) -> dict[str, Any]:
        try:
            with urlopen(req, timeout=self._timeout / 1000) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise A2AClientError("a2a_http_error", f"HTTP {exc.code}: {body[:500]}") from exc
        except URLError as exc:
            raise A2AClientError("a2a_unreachable", f"Agent unreachable: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise A2AClientError("a2a_protocol_error", f"Invalid JSON: {exc}") from exc


# ---------------------------------------------------------------------------
# Tool registration: a2a_delegate_task
# ---------------------------------------------------------------------------

_DELEGATE_TOOL_CONTRACT: dict[str, Any] = {
    "id": "a2a_delegate_task",
    "name": "Delegate task to A2A agent",
    "category": "a2a",
    "description": "Send a task to a remote A2A-compatible agent and return the result.",
    "inputs": {
        "agent_url": {"type": "string", "required": True, "description": "Base URL of the remote agent."},
        "skill_id": {"type": "string", "required": True, "description": "Skill id to invoke on the remote agent."},
        "message": {"type": "string", "required": True, "description": "Text message to send."},
    },
    "outputs": {
        "status": {"type": "string"},
        "artifacts": {"type": "array"},
    },
    "constraints": {"timeout_ms": 30000, "allowlist": [], "workspace_only": False},
    "safety": {"level": "medium", "requires_confirmation": False},
    "lifecycle": {"version": "1.0.0", "status": "ready"},
}


def register_a2a_delegate_tool(
    tool_registry: ToolRegistry,
    tool_runtime: ToolRuntime,
    timeout_ms: int = 10000,
) -> None:
    """Register the a2a_delegate_task tool so capabilities can delegate."""
    try:
        tool_registry.register(_DELEGATE_TOOL_CONTRACT, source="a2a_client")
    except Exception:
        pass  # already registered or schema mismatch

    def _handler(params: dict[str, Any]) -> dict[str, Any]:
        agent_url = params.get("agent_url", "")
        skill_id = params.get("skill_id", "")
        message = params.get("message", "")
        if not agent_url or not skill_id:
            raise RuntimeError("agent_url and skill_id are required.")
        client = A2AClient(agent_url, timeout_ms=timeout_ms)
        try:
            result = client.send_task(skill_id, message)
            return {
                "status": result.get("status", {}).get("state", "unknown"),
                "artifacts": result.get("artifacts", []),
                "task_id": result.get("id"),
            }
        except A2AClientError as exc:
            raise RuntimeError(f"A2A delegation failed: {exc}") from exc

    tool_runtime.register_handler("a2a_delegate_task", _handler)
