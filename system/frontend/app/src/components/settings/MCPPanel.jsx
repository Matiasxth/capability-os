import React, { useEffect, useState } from "react";
import sdk from "../../sdk";

export default function MCPPanel() {
  const [servers, setServers] = useState([]);
  const [tools, setTools] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Add server form state
  const [newId, setNewId] = useState("");
  const [newTransport, setNewTransport] = useState("stdio");
  const [newCommand, setNewCommand] = useState("");
  const [newUrl, setNewUrl] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [srvRes, toolRes] = await Promise.all([sdk.mcp.servers.list(), sdk.mcp.tools.list()]);
      setServers(srvRes.servers || []);
      setTools(toolRes.tools || []);
    } catch (err) {
      setError(err.payload?.error_message || err.message || "Failed to load.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function handleAction(action, label) {
    setMessage("");
    setError("");
    try {
      await action();
      setMessage(label);
      await refresh();
    } catch (err) {
      setError(err.payload?.error_message || err.message || "Action failed.");
    }
  }

  async function handleAddServer(e) {
    e.preventDefault();
    const config = { id: newId, transport: newTransport };
    if (newTransport === "stdio") config.command = newCommand.split(/\s+/);
    else config.url = newUrl;
    await handleAction(() => sdk.mcp.servers.add(config), `Server '${newId}' added.`);
    setNewId("");
    setNewCommand("");
    setNewUrl("");
  }

  return (
    <section className="settings-section">
      <h3>MCP Servers</h3>
      {message && <p className="status-banner success">{message}</p>}
      {error && <p className="status-banner error">{error}</p>}
      {loading && <p>Loading...</p>}

      {/* Add server form */}
      <form onSubmit={handleAddServer} style={{ marginBottom: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input placeholder="Server ID" value={newId} onChange={e => setNewId(e.target.value)} required style={{ flex: 1 }} />
          <select value={newTransport} onChange={e => setNewTransport(e.target.value)}>
            <option value="stdio">stdio</option>
            <option value="http">http</option>
          </select>
        </div>
        {newTransport === "stdio" && (
          <input placeholder="Command (e.g. python -m my_server)" value={newCommand} onChange={e => setNewCommand(e.target.value)} required />
        )}
        {newTransport === "http" && (
          <input placeholder="URL (e.g. http://localhost:3000/mcp)" value={newUrl} onChange={e => setNewUrl(e.target.value)} required />
        )}
        <button type="submit" disabled={!newId}>Add Server</button>
      </form>

      {/* Server list */}
      {servers.length === 0 && <p className="empty-block">No MCP servers configured.</p>}
      {servers.map((srv) => (
        <div key={srv.server_id} className="status-row" style={{ flexDirection: "column", alignItems: "flex-start", gap: "0.5rem", padding: "0.75rem 0", borderBottom: "1px solid #eee" }}>
          <div>
            <strong>{srv.server_id}</strong>
            <span style={{ marginLeft: "0.5rem", color: srv.connected ? "#52c41a" : "#888" }}>
              {srv.connected ? "connected" : "disconnected"}
            </span>
            <span style={{ marginLeft: "0.5rem", color: "#888" }}>{srv.tools_discovered} tools</span>
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" onClick={() => handleAction(() => sdk.mcp.servers.discover(srv.server_id), `Discovered tools from ${srv.server_id}`)}>
              Discover Tools
            </button>
            <button type="button" onClick={() => handleAction(() => sdk.mcp.servers.remove(srv.server_id), `Removed ${srv.server_id}`)}>
              Remove
            </button>
          </div>
        </div>
      ))}

      {/* Bridged tools */}
      <h4>MCP Tools</h4>
      {tools.length === 0 && <p className="empty-block">No MCP tools discovered yet.</p>}
      {tools.map((tool) => (
        <div key={tool.tool_id} className="status-row" style={{ justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid #eee" }}>
          <div>
            <strong>{tool.tool_id}</strong>
            <span style={{ marginLeft: "0.5rem", color: "#888" }}>{tool.server_id}</span>
          </div>
          <button type="button" onClick={() => handleAction(() => sdk.mcp.tools.install(tool.tool_id), `Proposal created for ${tool.tool_id}`)}>
            Install as Capability
          </button>
        </div>
      ))}

      <button type="button" onClick={refresh} disabled={loading} style={{ marginTop: "1rem" }}>
        Refresh
      </button>
    </section>
  );
}
