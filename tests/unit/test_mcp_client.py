"""
Tests for Componente 1 — MCP Client.

Uses mock transports to test the protocol layer without real MCP servers.

Validates:
  1. JSON-RPC 2.0 request building.
  2. JSON-RPC response parsing (success + error).
  3. MCPClient: connect/initialize handshake.
  4. MCPClient: tools/list discovery.
  5. MCPClient: tools/call execution.
  6. MCPClient: error handling (transport error, protocol error, server error).
  7. MCPClient: status reporting.
  8. MCPClientManager: add, remove, list, disconnect_all.
  9. StdioTransport: connect, disconnect lifecycle.
  10. HttpTransport: URL validation.
  11. Config validation (missing command, missing url, unknown transport).
"""
from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from system.core.mcp.mcp_client import (
    MCPClient,
    MCPClientError,
    MCPClientManager,
    _HttpTransport,
    _StdioTransport,
    _jsonrpc_request,
    _parse_jsonrpc_response,
)


# ===========================================================================
# 1. JSON-RPC helpers
# ===========================================================================

class TestJsonRpcHelpers(unittest.TestCase):

    def test_request_format(self):
        req = _jsonrpc_request("tools/list", {"cursor": None}, req_id="test1")
        self.assertEqual(req["jsonrpc"], "2.0")
        self.assertEqual(req["method"], "tools/list")
        self.assertEqual(req["id"], "test1")
        self.assertEqual(req["params"], {"cursor": None})

    def test_request_auto_id(self):
        req = _jsonrpc_request("initialize")
        self.assertIn("id", req)
        self.assertIsInstance(req["id"], str)

    def test_parse_success(self):
        result = _parse_jsonrpc_response({"jsonrpc": "2.0", "id": "r1", "result": {"tools": []}}, "r1")
        self.assertEqual(result, {"tools": []})

    def test_parse_error_raises(self):
        with self.assertRaises(MCPClientError) as ctx:
            _parse_jsonrpc_response({
                "jsonrpc": "2.0", "id": "r1",
                "error": {"code": -32600, "message": "Invalid request"},
            }, "r1")
        self.assertEqual(ctx.exception.error_code, "mcp_server_error")

    def test_parse_id_mismatch_raises(self):
        with self.assertRaises(MCPClientError):
            _parse_jsonrpc_response({"jsonrpc": "2.0", "id": "wrong", "result": {}}, "expected")

    def test_parse_missing_jsonrpc_raises(self):
        with self.assertRaises(MCPClientError):
            _parse_jsonrpc_response({"id": "r1", "result": {}}, "r1")

    def test_parse_non_dict_raises(self):
        with self.assertRaises(MCPClientError):
            _parse_jsonrpc_response("not a dict", None)


# ===========================================================================
# 2. MCPClient with mock transport
# ===========================================================================

def _mock_transport(responses: list[dict[str, Any]]) -> MagicMock:
    """Create a mock transport that echoes request id into each response."""
    response_iter = iter(responses)
    transport = MagicMock()
    transport.alive = True
    transport.connect = MagicMock()
    transport.disconnect = MagicMock()

    def _send(message: dict, timeout_ms: int) -> dict:
        resp = next(response_iter)
        # Echo the request id so id-matching passes
        resp = dict(resp)
        resp["id"] = message.get("id")
        return resp

    transport.send = MagicMock(side_effect=_send)
    return transport


class TestMCPClientConnect(unittest.TestCase):

    def test_initialize_handshake(self):
        client = MCPClient(server_id="test", transport="http", url="http://localhost:1234")
        init_response = {"jsonrpc": "2.0", "id": None, "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "test-server", "version": "0.1.0"},
        }}
        # Patch the transport
        mock_t = _mock_transport([init_response])
        client._transport = mock_t
        result = client.connect()
        self.assertIn("protocolVersion", result)
        mock_t.connect.assert_called_once()

    def test_disconnect(self):
        client = MCPClient(server_id="test", transport="http", url="http://localhost:1234")
        mock_t = _mock_transport([])
        client._transport = mock_t
        client.disconnect()
        mock_t.disconnect.assert_called_once()


class TestMCPClientDiscovery(unittest.TestCase):

    def test_discover_returns_tools(self):
        client = MCPClient(server_id="test", transport="http", url="http://localhost:1234")
        list_response = {"jsonrpc": "2.0", "id": None, "result": {
            "tools": [
                {"name": "read_file", "description": "Read a file", "inputSchema": {
                    "type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"],
                }},
                {"name": "write_file", "description": "Write a file", "inputSchema": {}},
            ],
        }}
        mock_t = _mock_transport([list_response])
        client._transport = mock_t
        tools = client.discover_tools()
        self.assertEqual(len(tools), 2)
        self.assertEqual(tools[0]["name"], "read_file")

    def test_cached_tools(self):
        client = MCPClient(server_id="test", transport="http", url="http://localhost:1234")
        self.assertEqual(client.get_cached_tools(), [])
        # After discover
        list_response = {"jsonrpc": "2.0", "id": None, "result": {"tools": [{"name": "a"}]}}
        client._transport = _mock_transport([list_response])
        client.discover_tools()
        self.assertEqual(len(client.get_cached_tools()), 1)

    def test_discover_handles_list_result(self):
        """Some servers return tools as a bare list instead of {tools: [...]}."""
        client = MCPClient(server_id="test", transport="http", url="http://localhost:1234")
        list_response = {"jsonrpc": "2.0", "id": None, "result": [{"name": "tool_a"}]}
        client._transport = _mock_transport([list_response])
        tools = client.discover_tools()
        self.assertEqual(len(tools), 1)


class TestMCPClientCallTool(unittest.TestCase):

    def test_call_tool_success(self):
        client = MCPClient(server_id="test", transport="http", url="http://localhost:1234")
        call_response = {"jsonrpc": "2.0", "id": None, "result": {
            "content": [{"type": "text", "text": "hello world"}],
        }}
        client._transport = _mock_transport([call_response])
        result = client.call_tool("greet", {"name": "World"})
        self.assertEqual(result["content"][0]["text"], "hello world")

    def test_call_tool_wraps_scalar_result(self):
        client = MCPClient(server_id="test", transport="http", url="http://localhost:1234")
        call_response = {"jsonrpc": "2.0", "id": None, "result": "just a string"}
        client._transport = _mock_transport([call_response])
        result = client.call_tool("echo", {})
        self.assertIn("content", result)

    def test_call_tool_server_error(self):
        client = MCPClient(server_id="test", transport="http", url="http://localhost:1234")
        error_response = {"jsonrpc": "2.0", "id": None, "error": {
            "code": -32601, "message": "Method not found",
        }}
        client._transport = _mock_transport([error_response])
        with self.assertRaises(MCPClientError) as ctx:
            client.call_tool("nonexistent", {})
        self.assertEqual(ctx.exception.error_code, "mcp_server_error")


class TestMCPClientStatus(unittest.TestCase):

    def test_status_disconnected(self):
        client = MCPClient(server_id="s1", transport="http", url="http://localhost:1234")
        mock_t = MagicMock()
        mock_t.alive = False
        client._transport = mock_t
        status = client.status()
        self.assertEqual(status["server_id"], "s1")
        self.assertFalse(status["connected"])
        self.assertEqual(status["tools_discovered"], 0)


class TestMCPClientErrors(unittest.TestCase):

    def test_transport_error_on_send(self):
        client = MCPClient(server_id="test", transport="http", url="http://localhost:1234")
        mock_t = MagicMock()
        mock_t.alive = True
        mock_t.connect = MagicMock()
        mock_t.send.side_effect = MCPClientError("mcp_transport_error", "Connection refused")
        client._transport = mock_t
        with self.assertRaises(MCPClientError) as ctx:
            client.connect()
        self.assertEqual(ctx.exception.error_code, "mcp_transport_error")


# ===========================================================================
# 3. Config validation
# ===========================================================================

class TestMCPClientConfig(unittest.TestCase):

    def test_stdio_requires_command(self):
        with self.assertRaises(MCPClientError):
            MCPClient(server_id="s", transport="stdio")

    def test_http_requires_url(self):
        with self.assertRaises(MCPClientError):
            MCPClient(server_id="s", transport="http")

    def test_unknown_transport_raises(self):
        with self.assertRaises(MCPClientError):
            MCPClient(server_id="s", transport="grpc")

    def test_http_invalid_scheme_raises(self):
        with self.assertRaises(MCPClientError):
            _HttpTransport("ftp://example.com")


# ===========================================================================
# 4. MCPClientManager
# ===========================================================================

class TestMCPClientManager(unittest.TestCase):

    def test_add_and_list(self):
        mgr = MCPClientManager()
        client = mgr.add_server({"id": "srv1", "transport": "http", "url": "http://localhost:1"})
        self.assertEqual(client.server_id, "srv1")
        servers = mgr.list_servers()
        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0]["server_id"], "srv1")

    def test_remove_server(self):
        mgr = MCPClientManager()
        mgr.add_server({"id": "srv1", "transport": "http", "url": "http://localhost:1"})
        self.assertTrue(mgr.remove_server("srv1"))
        self.assertFalse(mgr.remove_server("srv1"))
        self.assertEqual(len(mgr.list_servers()), 0)

    def test_get_client(self):
        mgr = MCPClientManager()
        mgr.add_server({"id": "srv1", "transport": "http", "url": "http://localhost:1"})
        self.assertIsNotNone(mgr.get_client("srv1"))
        self.assertIsNone(mgr.get_client("nonexistent"))

    def test_add_replaces_existing(self):
        mgr = MCPClientManager()
        mgr.add_server({"id": "srv1", "transport": "http", "url": "http://localhost:1"})
        mgr.add_server({"id": "srv1", "transport": "http", "url": "http://localhost:2"})
        self.assertEqual(len(mgr.list_servers()), 1)

    def test_disconnect_all(self):
        mgr = MCPClientManager()
        mgr.add_server({"id": "s1", "transport": "http", "url": "http://localhost:1"})
        mgr.add_server({"id": "s2", "transport": "http", "url": "http://localhost:2"})
        mgr.disconnect_all()
        self.assertEqual(len(mgr.list_servers()), 0)

    def test_missing_id_raises(self):
        mgr = MCPClientManager()
        with self.assertRaises(MCPClientError):
            mgr.add_server({"transport": "http", "url": "http://localhost:1"})


# ===========================================================================
# 5. StdioTransport edge cases
# ===========================================================================

class TestStdioTransportEdgeCases(unittest.TestCase):

    def test_alive_false_before_connect(self):
        t = _StdioTransport(["echo", "hello"])
        self.assertFalse(t.alive)

    def test_disconnect_without_connect(self):
        t = _StdioTransport(["echo", "hello"])
        t.disconnect()  # should not raise

    def test_send_without_connect_raises(self):
        t = _StdioTransport(["echo", "hello"])
        with self.assertRaises(MCPClientError):
            t.send({"jsonrpc": "2.0"}, 5000)


if __name__ == "__main__":
    unittest.main()
