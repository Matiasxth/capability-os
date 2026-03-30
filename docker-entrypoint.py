"""Docker entrypoint: serves API + built frontend on a single port (8000).

API paths (/capabilities, /execute, /status, etc.) are routed to the
CapabilityOSUIBridgeService.  All other paths are served as static files
from the frontend dist/ directory, with fallback to index.html for SPA routing.
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from system.core.ui_bridge.api_server import CapabilityOSUIBridgeService, APIRequestError

DIST_DIR = PROJECT_ROOT / "system" / "frontend" / "app" / "dist"
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", "/data/workspace")).resolve()

# API path prefixes — requests matching these go to the service
API_PREFIXES = (
    "/capabilities", "/execute", "/status", "/health", "/settings",
    "/llm/", "/browser/", "/metrics", "/gaps/", "/optimizations/",
    "/proposals/", "/integrations", "/interpret", "/plan",
    "/executions/", "/mcp/", "/a2a/", "/memory", "/chat",
    "/workspaces", "/.well-known", "/skills", "/agents", "/agent", "/logs", "/voice", "/supervisor", "/scheduler", "/files",
    "/plugins", "/workflows", "/auth/",
)


class UnifiedHandler(BaseHTTPRequestHandler):
    server_version = "CapabilityOS/1.0"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if self._is_api_path():
            self._dispatch_api("GET")
        else:
            self._serve_static()

    def do_POST(self) -> None:
        self._dispatch_api("POST")

    def do_DELETE(self) -> None:
        self._dispatch_api("DELETE")

    def log_message(self, format, *args):
        pass

    def _is_api_path(self) -> bool:
        path = urlparse(self.path).path
        return any(path == p.rstrip("/") or path.startswith(p) for p in API_PREFIXES)

    def _dispatch_api(self, method: str) -> None:
        service: CapabilityOSUIBridgeService = self.server.service
        try:
            payload = self._read_json() if method in ("POST", "DELETE") else None
            response = service.handle(method, self.path, payload)
        except APIRequestError as exc:
            response = type("R", (), {
                "status_code": exc.status_code,
                "payload": {"status": "error", "error_code": exc.error_code,
                            "error_message": exc.error_message, "details": exc.details},
            })()

        self.send_response(response.status_code)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(response.payload, ensure_ascii=False).encode("utf-8"))

    def _serve_static(self) -> None:
        path = urlparse(self.path).path.lstrip("/")
        if not path:
            path = "index.html"

        file_path = DIST_DIR / path
        if not file_path.exists() or not file_path.is_file():
            # SPA fallback
            file_path = DIST_DIR / "index.html"

        if not file_path.exists():
            self.send_error(404, "Frontend not built. Run npm run build first.")
            return

        content_type, _ = mimetypes.guess_type(str(file_path))
        content = file_path.read_bytes()
        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        # Hashed assets can cache; everything else must revalidate
        if "/assets/" in str(file_path).replace("\\", "/"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(content)

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}


def main() -> None:
    # Initialize logging
    try:
        from system.core.logging_config import setup_logging
        logger = setup_logging(workspace_root=WORKSPACE_ROOT)
        logger.info("Capability OS starting...")
    except Exception:
        pass

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    use_async = os.environ.get("CAPOS_ASYNC", "1") != "0"

    ws_port_str = os.environ.get("WS_PORT", "")
    ws_port = int(ws_port_str) if ws_port_str.isdigit() else None

    service = CapabilityOSUIBridgeService(workspace_root=WORKSPACE_ROOT)

    # Start error notifier
    try:
        from system.core.ui_bridge.event_bus import event_bus
        from system.core.observation.error_notifier import ErrorNotifier
        _notifier = ErrorNotifier(project_root=PROJECT_ROOT)
        _notifier.subscribe(event_bus)
    except Exception as exc:
        print(f"  ErrorNotifier: failed ({exc})")

    print(f"  Workspace: {WORKSPACE_ROOT}")
    print(f"  Frontend:  {'available' if (DIST_DIR / 'index.html').exists() else 'not built'}")

    # Try async server (uvicorn), fallback to sync
    if use_async:
        try:
            import uvicorn
            from system.core.ui_bridge.asgi_server import CapOSASGI

            app = CapOSASGI(service, static_dir=DIST_DIR)
            print(f"Capability OS (async) listening on http://{host}:{port}")
            uvicorn.run(app, host=host, port=port, log_level="warning", ws="auto")
            return
        except ImportError:
            print("  uvicorn not available, falling back to sync server")
        except Exception as exc:
            print(f"  Async server failed ({exc}), falling back to sync server")

    # Fallback: sync ThreadingHTTPServer
    server = ThreadingHTTPServer((host, port), UnifiedHandler)
    server.service = service
    server.ws_server = None

    if ws_port is not None:
        try:
            from system.core.ui_bridge.ws_server import start_ws_server
            from system.core.ui_bridge.event_bus import event_bus
            server.ws_server = start_ws_server(host, ws_port, event_bus)
            print(f"  WebSocket: ws://{host}:{ws_port}")
        except Exception as exc:
            print(f"  WebSocket: failed ({exc})")

    print(f"Capability OS (sync) listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server.ws_server:
            server.ws_server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
