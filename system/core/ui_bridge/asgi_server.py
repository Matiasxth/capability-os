"""ASGI application — async server that wraps the existing sync handlers.

Replaces ThreadingHTTPServer with uvicorn for:
- True async I/O (no GIL blocking on network waits)
- Native SSE streaming
- Native WebSocket support
- 50+ concurrent connections without thread explosion

All existing handler functions are called via run_in_executor to avoid
blocking the event loop.
"""
from __future__ import annotations

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


# Thread pool for running sync handlers
_executor = ThreadPoolExecutor(max_workers=16)


class CapOSASGI:
    """ASGI application that delegates to the existing CapabilityOSUIBridgeService."""

    def __init__(self, service: Any, static_dir: str | Path | None = None) -> None:
        self.service = service
        self.static_dir = Path(static_dir) if static_dir else None
        self._router = service._router

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            await self._handle_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
        elif scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def _handle_http(self, scope: dict, receive: Any, send: Any) -> None:
        method = scope["method"]
        path = scope["path"]
        query = scope.get("query_string", b"").decode()
        raw_path = f"{path}?{query}" if query else path

        # Read body
        body = b""
        while True:
            msg = await receive()
            body += msg.get("body", b"")
            if not msg.get("more_body", False):
                break

        # Check for SSE streaming endpoints
        if method == "POST" and path in ("/agent/stream", "/chat/stream", "/execute/stream"):
            await self._handle_sse(path, body, send)
            return

        # API route
        if self._is_api_path(path):
            await self._handle_api(method, path, raw_path, body, send)
            return

        # Static file serving
        await self._serve_static(path, send)

    async def _handle_api(self, method: str, path: str, raw_path: str, body: bytes, send: Any) -> None:
        """Dispatch to sync handlers via thread pool."""
        payload = None
        if body:
            try:
                payload = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = None

        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                _executor,
                lambda: self._dispatch_sync(method, path, raw_path, payload),
            )
            await self._send_json(send, response.status_code, response.payload)
        except Exception as exc:
            await self._send_json(send, 500, {"error": str(exc)})

    def _dispatch_sync(self, method: str, path: str, raw_path: str, payload: Any) -> Any:
        """Run the existing router dispatch synchronously."""
        from system.core.ui_bridge.api_server import APIResponse, APIRequestError

        match = self._router.match(method, path)
        if match is None:
            return APIResponse(404, {"error": "Not found", "path": path})

        handler, path_params = match
        try:
            return handler(self.service, payload, _raw_path=raw_path, **path_params)
        except APIRequestError as exc:
            return APIResponse(exc.status_code, {
                "error_code": exc.error_code,
                "error_message": exc.error_message,
                **(exc.details or {}),
            })
        except Exception as exc:
            return APIResponse(500, {"error": str(exc)})

    async def _handle_sse(self, path: str, body: bytes, send: Any) -> None:
        """Handle SSE streaming endpoints asynchronously."""
        payload = {}
        if body:
            try:
                payload = json.loads(body)
            except Exception:
                pass

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/event-stream"],
                [b"cache-control", b"no-cache"],
                [b"connection", b"keep-alive"],
                [b"access-control-allow-origin", b"*"],
            ],
        })

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        def _run_generator():
            try:
                gen = self._get_sse_generator(path, payload)
                if gen is None:
                    return
                for event in gen:
                    asyncio.run_coroutine_threadsafe(queue.put(event), loop)
            except StopIteration:
                pass
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(
                    queue.put({"event": "error", "error": str(exc)[:300]}), loop
                )
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        _executor.submit(_run_generator)

        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=120)
                if event is None:
                    break
                line = f"data: {json.dumps(event, default=str)}\n\n"
                await send({"type": "http.response.body", "body": line.encode(), "more_body": True})
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass

        # Send done event
        try:
            await send({"type": "http.response.body", "body": b"data: {\"done\":true}\n\n", "more_body": False})
        except Exception:
            pass

    def _get_sse_generator(self, path: str, payload: dict) -> Any:
        """Create the appropriate generator for the SSE endpoint."""
        if path == "/agent/stream":
            return self._agent_stream_gen(payload)
        elif path == "/chat/stream":
            return self._chat_stream_gen(payload)
        elif path == "/execute/stream":
            return self._execute_stream_gen(payload)
        return None

    def _agent_stream_gen(self, payload: dict):
        service = self.service
        message = payload.get("message", "")
        session_id = payload.get("session_id")
        history = payload.get("history", [])
        agent_id = payload.get("agent_id")
        workspace_id = payload.get("workspace_id")

        agent_config = None
        if agent_id and hasattr(service, "agent_registry") and service.agent_registry:
            agent_config = service.agent_registry.get(agent_id)

        ws_root = str(service.workspace_root)
        if workspace_id and hasattr(service, "workspace_registry") and service.workspace_registry:
            ws = service.workspace_registry.get(workspace_id)
            if ws and ws.get("path"):
                ws_root = ws["path"]

        if not hasattr(service, "agent_loop") or service.agent_loop is None:
            yield {"event": "agent_error", "error": "Agent not available"}
            return

        gen = service.agent_loop.run(
            message, session_id=session_id, conversation_history=history,
            agent_config=agent_config, workspace_id=workspace_id, workspace_path=ws_root,
        )
        for event in gen:
            yield event

    def _chat_stream_gen(self, payload: dict):
        service = self.service
        text = payload.get("text", payload.get("message", ""))
        user_name = payload.get("user_name", "User")
        history = payload.get("history", [])

        if not hasattr(service, "intent_interpreter") or service.intent_interpreter is None:
            yield {"event": "error", "error": "Interpreter not available"}
            return

        # Stream chat response
        try:
            response = service.intent_interpreter.chat_response(text, user_name=user_name)
            yield {"event": "chat_response", "text": response}
        except Exception as exc:
            yield {"event": "error", "error": str(exc)}

    def _execute_stream_gen(self, payload: dict):
        service = self.service
        try:
            result = service._execute_capability(payload)
            yield {"event": "execution_complete", "result": result}
        except Exception as exc:
            yield {"event": "error", "error": str(exc)}

    # ------------------------------------------------------------------
    # Static files
    # ------------------------------------------------------------------

    async def _serve_static(self, path: str, send: Any) -> None:
        """Serve frontend static files with SPA fallback."""
        if self.static_dir is None:
            await self._send_json(send, 404, {"error": "No static dir"})
            return

        # Map path to file
        if path == "/" or not path.strip("/"):
            file_path = self.static_dir / "index.html"
        else:
            file_path = self.static_dir / path.lstrip("/")

        if not file_path.exists() or not file_path.is_file():
            # SPA fallback
            file_path = self.static_dir / "index.html"

        if not file_path.exists():
            await self._send_json(send, 404, {"error": "Not found"})
            return

        content = file_path.read_bytes()
        ct = self._content_type(file_path.suffix)

        headers = [[b"content-type", ct.encode()]]
        # No-cache for HTML
        if file_path.suffix in (".html", ".htm"):
            headers.append([b"cache-control", b"no-store, no-cache, must-revalidate"])
        else:
            headers.append([b"cache-control", b"public, max-age=31536000, immutable"])

        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": content})

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    async def _handle_websocket(self, scope: dict, receive: Any, send: Any) -> None:
        """WebSocket handler — bridges to the existing event bus."""
        await send({"type": "websocket.accept"})

        from system.core.ui_bridge.event_bus import event_bus

        queue: asyncio.Queue[dict] = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def on_event(event_type: str, data: dict | None = None):
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": event_type, **(data or {})}),
                loop,
            )

        sub_id = event_bus.subscribe(on_event)

        try:
            # Two tasks: receive from client + send from event bus
            async def _recv():
                while True:
                    msg = await receive()
                    if msg["type"] == "websocket.disconnect":
                        break

            async def _send_events():
                while True:
                    event = await queue.get()
                    try:
                        await send({
                            "type": "websocket.send",
                            "text": json.dumps(event, default=str),
                        })
                    except Exception:
                        break

            done, pending = await asyncio.wait(
                [asyncio.create_task(_recv()), asyncio.create_task(_send_events())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
        finally:
            event_bus.unsubscribe(sub_id)

    # ------------------------------------------------------------------
    # Lifespan
    # ------------------------------------------------------------------

    async def _handle_lifespan(self, scope: dict, receive: Any, send: Any) -> None:
        while True:
            msg = await receive()
            if msg["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif msg["type"] == "lifespan.shutdown":
                # Clean shutdown
                if hasattr(self.service, "container"):
                    self.service.container.stop_all()
                await send({"type": "lifespan.shutdown.complete"})
                return

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_api_path(self, path: str) -> bool:
        API_PREFIXES = (
            "/capabilities", "/execute", "/interpret", "/plan", "/chat",
            "/settings", "/health", "/status", "/integrations/",
            "/sequences/", "/browser/", "/gaps/", "/proposals/",
            "/workspaces", "/files/", "/llm/", "/system/",
            "/mcp/", "/a2a/", "/memory", "/metrics",
            "/agents", "/agent/", "/supervisor/", "/scheduler/",
            "/skills", "/voice/",
        )
        return any(path == p.rstrip("/") or path.startswith(p) for p in API_PREFIXES)

    @staticmethod
    async def _send_json(send: Any, status: int, data: dict) -> None:
        body = json.dumps(data, default=str, ensure_ascii=False).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                [b"content-type", b"application/json"],
                [b"access-control-allow-origin", b"*"],
                [b"access-control-allow-methods", b"GET, POST, PUT, DELETE, OPTIONS"],
                [b"access-control-allow-headers", b"Content-Type, Authorization"],
            ],
        })
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _content_type(ext: str) -> str:
        return {
            ".html": "text/html",
            ".js": "application/javascript",
            ".css": "text/css",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".woff2": "font/woff2",
            ".woff": "font/woff",
        }.get(ext, "application/octet-stream")
