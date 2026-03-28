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
    "/executions/", "/mcp/",
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
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    service = CapabilityOSUIBridgeService(workspace_root=WORKSPACE_ROOT)
    server = ThreadingHTTPServer((host, port), UnifiedHandler)
    server.service = service

    print(f"Capability OS listening on http://{host}:{port}")
    print(f"  Workspace: {WORKSPACE_ROOT}")
    print(f"  Frontend:  {'available' if (DIST_DIR / 'index.html').exists() else 'not built'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
