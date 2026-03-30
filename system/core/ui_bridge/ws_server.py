"""Stdlib-only WebSocket server for real-time event broadcasting.

Runs on a separate port (default 8001) in a daemon thread.
Subscribes to the EventBus and pushes JSON text frames to all
connected clients.  No external dependencies — implements the
RFC 6455 handshake and framing with hashlib/struct/base64.

Usage::

    from system.core.ui_bridge.event_bus import event_bus
    from system.core.ui_bridge.ws_server import start_ws_server

    ws = start_ws_server("127.0.0.1", 8001, event_bus)
    # ... later ...
    ws.shutdown()
"""
from __future__ import annotations

import base64
import hashlib
import json
import socket
import struct
import threading
import time
from typing import Any

from system.core.ui_bridge.event_bus import EventBus

_WS_MAGIC = b"258EAFA5-E914-47DA-95CA-5AB5E11635C8"
_MAX_CLIENTS = 50


# ---------------------------------------------------------------------------
# Frame helpers (RFC 6455)
# ---------------------------------------------------------------------------

def _encode_text_frame(text: str) -> bytes:
    """Build an unmasked text frame (server → client)."""
    payload = text.encode("utf-8")
    length = len(payload)
    if length < 126:
        header = struct.pack("!BB", 0x81, length)
    elif length < 65536:
        header = struct.pack("!BBH", 0x81, 126, length)
    else:
        header = struct.pack("!BBQ", 0x81, 127, length)
    return header + payload


def _encode_close_frame(code: int = 1000) -> bytes:
    return struct.pack("!BBH", 0x88, 2, code)


def _encode_ping_frame() -> bytes:
    return struct.pack("!BB", 0x89, 0)


def _decode_frame(sock: socket.socket) -> tuple[int, bytes] | None:
    """Read one frame. Returns (opcode, payload) or None on failure."""
    try:
        head = _recv_exact(sock, 2)
        if head is None:
            return None
        opcode = head[0] & 0x0F
        masked = (head[1] & 0x80) != 0
        length = head[1] & 0x7F
        if length == 126:
            ext = _recv_exact(sock, 2)
            if ext is None:
                return None
            length = struct.unpack("!H", ext)[0]
        elif length == 127:
            ext = _recv_exact(sock, 8)
            if ext is None:
                return None
            length = struct.unpack("!Q", ext)[0]
        if length > 1_000_000:  # 1 MB max
            return None
        mask_key = b""
        if masked:
            mask_key = _recv_exact(sock, 4)
            if mask_key is None:
                return None
        data = _recv_exact(sock, length) if length > 0 else b""
        if data is None:
            return None
        if masked and mask_key:
            data = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
        return opcode, data
    except Exception:
        return None


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except Exception:
            return None
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


# ---------------------------------------------------------------------------
# Handshake
# ---------------------------------------------------------------------------

def _do_handshake(conn: socket.socket) -> bool:
    """Read HTTP upgrade request, send 101 response. Returns True on success."""
    try:
        request = b""
        while b"\r\n\r\n" not in request:
            chunk = conn.recv(4096)
            if not chunk:
                return False
            request += chunk
            if len(request) > 8192:
                return False

        headers: dict[str, str] = {}
        lines = request.decode("utf-8", errors="replace").split("\r\n")
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        if headers.get("upgrade", "").lower() != "websocket":
            conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return False

        key = headers.get("sec-websocket-key", "")
        if not key:
            conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return False

        accept = base64.b64encode(
            hashlib.sha1(key.encode("utf-8") + _WS_MAGIC).digest()
        ).decode("ascii")

        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "\r\n"
        )
        conn.sendall(response.encode("utf-8"))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# WebSocket Server
# ---------------------------------------------------------------------------

class WebSocketServer:
    """Manages client connections and broadcasts events."""

    def __init__(self, host: str, port: int, event_bus: EventBus):
        self._host = host
        self._port = port
        self._event_bus = event_bus
        self._clients: dict[socket.socket, threading.Lock] = {}
        self._clients_lock = threading.Lock()
        self._server_socket: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._ping_thread: threading.Thread | None = None
        self._running = False
        self._unsub: Any = None

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        if self._running:
            return
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.settimeout(1.0)
        self._server_socket.bind((self._host, self._port))
        self._server_socket.listen(8)
        self._running = True

        # Subscribe to event bus
        self._unsub = self._event_bus.subscribe(self._broadcast)

        # Accept thread
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True, name="ws-accept")
        self._accept_thread.start()

        # Ping thread
        self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True, name="ws-ping")
        self._ping_thread.start()

        print(f"[WS] WebSocket server listening on ws://{self._host}:{self._port}", flush=True)

    def shutdown(self) -> None:
        self._running = False
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None
        with self._clients_lock:
            for conn in list(self._clients.keys()):
                self._close_client(conn)
            self._clients.clear()

    @property
    def client_count(self) -> int:
        with self._clients_lock:
            return len(self._clients)

    # ------------------------------------------------------------------
    # Accept loop
    # ------------------------------------------------------------------

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, addr = self._server_socket.accept()
            except socket.timeout:
                continue
            except Exception:
                if self._running:
                    time.sleep(0.5)
                continue

            with self._clients_lock:
                if len(self._clients) >= _MAX_CLIENTS:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    continue

            # Handshake + client read loop in a new thread
            t = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
            t.start()

    def _handle_client(self, conn: socket.socket) -> None:
        if not _do_handshake(conn):
            try:
                conn.close()
            except Exception:
                pass
            return

        write_lock = threading.Lock()
        with self._clients_lock:
            self._clients[conn] = write_lock

        # Read loop — handle pong and close frames
        try:
            conn.settimeout(60.0)
            while self._running:
                frame = _decode_frame(conn)
                if frame is None:
                    break
                opcode, data = frame
                if opcode == 0x8:  # close
                    break
                if opcode == 0xA:  # pong — ignore
                    continue
                if opcode == 0x9:  # ping from client — send pong
                    try:
                        with write_lock:
                            conn.sendall(struct.pack("!BB", 0x8A, len(data)) + data)
                    except Exception:
                        break
                # Text frames from client are ignored (server is push-only)
        except Exception:
            pass
        finally:
            with self._clients_lock:
                self._clients.pop(conn, None)
            try:
                conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    def _broadcast(self, event: dict[str, Any]) -> None:
        """Called by the event bus for every emitted event."""
        try:
            frame = _encode_text_frame(json.dumps(event, ensure_ascii=True, default=str))
        except Exception:
            return

        with self._clients_lock:
            clients = list(self._clients.items())

        dead: list[socket.socket] = []
        for conn, write_lock in clients:
            try:
                with write_lock:
                    conn.sendall(frame)
            except Exception:
                dead.append(conn)

        if dead:
            with self._clients_lock:
                for conn in dead:
                    self._clients.pop(conn, None)
                    self._close_client(conn)

    # ------------------------------------------------------------------
    # Ping loop
    # ------------------------------------------------------------------

    def _ping_loop(self) -> None:
        ping = _encode_ping_frame()
        while self._running:
            time.sleep(30)
            with self._clients_lock:
                clients = list(self._clients.items())
            dead: list[socket.socket] = []
            for conn, write_lock in clients:
                try:
                    with write_lock:
                        conn.sendall(ping)
                except Exception:
                    dead.append(conn)
            if dead:
                with self._clients_lock:
                    for conn in dead:
                        self._clients.pop(conn, None)
                        self._close_client(conn)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _close_client(conn: socket.socket) -> None:
        try:
            conn.sendall(_encode_close_frame())
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_ws_server(host: str = "127.0.0.1", port: int = 8001, bus: EventBus | None = None) -> WebSocketServer:
    """Create and start a WebSocket server in a daemon thread."""
    from system.core.ui_bridge.event_bus import event_bus as default_bus
    server = WebSocketServer(host, port, bus or default_bus)
    server.start()
    return server
