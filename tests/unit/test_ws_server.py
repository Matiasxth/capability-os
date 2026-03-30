"""Tests for the stdlib WebSocket server."""
import base64
import hashlib
import json
import socket
import struct
import threading
import time
import unittest

from system.core.ui_bridge.event_bus import EventBus
from system.core.ui_bridge.ws_server import WebSocketServer, _encode_text_frame, _WS_MAGIC


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ws_handshake(sock: socket.socket) -> bool:
    """Perform a WebSocket client handshake. Returns True on 101."""
    key = base64.b64encode(b"test-key-1234567").decode()
    request = (
        f"GET / HTTP/1.1\r\n"
        f"Host: 127.0.0.1\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    sock.sendall(request.encode())
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk:
            return False
        response += chunk
    return b"101" in response


def _read_ws_frame(sock: socket.socket, timeout: float = 3.0) -> dict | None:
    """Read one text frame and parse as JSON."""
    sock.settimeout(timeout)
    try:
        head = sock.recv(2)
        if len(head) < 2:
            return None
        length = head[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", sock.recv(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", sock.recv(8))[0]
        data = b""
        while len(data) < length:
            data += sock.recv(length - len(data))
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


class TestWebSocketServer(unittest.TestCase):

    def setUp(self):
        self.bus = EventBus()
        self.port = _find_free_port()
        self.server = WebSocketServer("127.0.0.1", self.port, self.bus)
        self.server.start()
        time.sleep(0.1)

    def tearDown(self):
        self.server.shutdown()

    def _connect(self) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect(("127.0.0.1", self.port))
        self.assertTrue(_ws_handshake(s))
        time.sleep(0.1)  # let server register client
        return s

    def test_handshake(self):
        s = self._connect()
        self.assertGreaterEqual(self.server.client_count, 1)
        s.close()

    def test_receive_event(self):
        s = self._connect()
        self.bus.emit("test_event", {"hello": "world"})
        time.sleep(0.2)
        msg = _read_ws_frame(s)
        self.assertIsNotNone(msg)
        self.assertEqual(msg["type"], "test_event")
        self.assertEqual(msg["data"]["hello"], "world")
        s.close()

    def test_multiple_clients(self):
        s1 = self._connect()
        s2 = self._connect()
        self.bus.emit("broadcast", {"n": 1})
        time.sleep(0.2)
        m1 = _read_ws_frame(s1)
        m2 = _read_ws_frame(s2)
        self.assertIsNotNone(m1)
        self.assertIsNotNone(m2)
        self.assertEqual(m1["type"], "broadcast")
        self.assertEqual(m2["type"], "broadcast")
        s1.close()
        s2.close()

    def test_client_disconnect_cleanup(self):
        s = self._connect()
        self.assertEqual(self.server.client_count, 1)
        s.close()
        time.sleep(0.3)
        # Emit to trigger dead client pruning
        self.bus.emit("prune", {})
        time.sleep(0.2)
        self.assertEqual(self.server.client_count, 0)

    def test_encode_text_frame(self):
        frame = _encode_text_frame("hello")
        self.assertEqual(frame[0], 0x81)  # FIN + text opcode
        self.assertEqual(frame[1], 5)  # length
        self.assertEqual(frame[2:], b"hello")

    def test_server_port(self):
        self.assertEqual(self.server.port, self.port)


if __name__ == "__main__":
    unittest.main()
