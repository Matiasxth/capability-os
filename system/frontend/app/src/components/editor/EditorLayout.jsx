import React, { useState, useEffect, useCallback } from "react";
import FileExplorer from "./FileExplorer";
import CodeEditor from "./CodeEditor";
import Terminal from "./Terminal";

import sdk from "../../sdk";

export default function EditorLayout({ wsId, workspaces = [] }) {
  const [activeWsId, setActiveWsId] = useState(wsId);
  const [tree, setTree] = useState([]);
  const [openFile, setOpenFile] = useState(null);
  const [showTerminal, setShowTerminal] = useState(false);

  // Sync if parent changes default
  useEffect(() => { if (wsId && wsId !== activeWsId) setActiveWsId(wsId); }, [wsId]);

  const loadTree = useCallback(async () => {
    try {
      const r = activeWsId ? await sdk.system.files.tree(activeWsId) : await sdk.system.files.tree();
      setTree(r.items || []);
    } catch {}
  }, [activeWsId]);

  useEffect(() => { loadTree(); }, [loadTree]);

  const handleSelectFile = async (item) => {
    try {
      const r = await sdk.system.files.read(item.path, activeWsId);
      setOpenFile({ path: item.path, content: r.content || "", language: r.language || "plaintext" });
    } catch {}
  };

  const handleSave = async (content) => {
    if (!openFile) return;
    try {
      await sdk.system.files.write(openFile.path, content, activeWsId);
      setOpenFile(f => ({ ...f, content }));
    } catch {}
  };

  const handleTerminal = async (command) => {
    return sdk.system.files.terminal(command, activeWsId);
  };

  const handleWsChange = (id) => {
    setActiveWsId(id);
    setOpenFile(null); // Close open file when switching workspace
  };

  const activeWs = workspaces.find(w => w.id === activeWsId);

  return (
    <div style={{ display: "flex", height: "100%", background: "var(--bg-root)" }}>
      {/* File Explorer */}
      <div style={{ width: 240, minWidth: 180, borderRight: "1px solid var(--border)", background: "var(--bg-surface)", flexShrink: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {/* Workspace selector */}
        {workspaces.length > 0 && (
          <div style={{ padding: "8px 10px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: activeWs?.color || "#00ff88", flexShrink: 0 }} />
            <select
              value={activeWsId || ""}
              onChange={e => handleWsChange(e.target.value)}
              style={{ flex: 1, fontSize: 11, background: "var(--bg-input)", border: "1px solid var(--border)", borderRadius: 4, padding: "3px 6px", color: "var(--text-dim)", cursor: "pointer" }}
            >
              {workspaces.map(ws => (
                <option key={ws.id} value={ws.id}>{ws.name || ws.path}</option>
              ))}
            </select>
          </div>
        )}
        <div style={{ flex: 1, overflow: "hidden" }}>
          <FileExplorer tree={tree} onSelectFile={handleSelectFile} onRefresh={loadTree} />
        </div>
      </div>

      {/* Main area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Editor */}
        <div style={{ flex: 1, minHeight: 0 }}>
          <CodeEditor file={openFile} onSave={handleSave} />
        </div>

        {/* Terminal toggle */}
        <div
          onClick={() => setShowTerminal(!showTerminal)}
          style={{ height: 28, display: "flex", alignItems: "center", padding: "0 12px", background: "var(--bg-elevated)", borderTop: "1px solid var(--border)", cursor: "pointer", fontSize: 10, color: "var(--text-muted)", userSelect: "none" }}
        >
          {showTerminal ? "\u25BC" : "\u25B2"} Terminal
        </div>

        {/* Terminal */}
        {showTerminal && (
          <div style={{ height: 200, borderTop: "1px solid var(--border)" }}>
            <Terminal onExecute={handleTerminal} />
          </div>
        )}
      </div>
    </div>
  );
}
