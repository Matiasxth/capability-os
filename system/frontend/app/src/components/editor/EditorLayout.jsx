import React, { useState, useEffect, useCallback } from "react";
import FileExplorer from "./FileExplorer";
import CodeEditor from "./CodeEditor";
import Terminal from "./Terminal";

const API = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function api(path, opts = {}) {
  const r = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json" }, ...opts });
  return r.json();
}

export default function EditorLayout({ wsId }) {
  const [tree, setTree] = useState([]);
  const [openFile, setOpenFile] = useState(null);
  const [showTerminal, setShowTerminal] = useState(false);

  const loadTree = useCallback(async () => {
    try {
      const r = wsId ? await api(`/files/tree/${wsId}`) : await api("/files/tree");
      setTree(r.items || []);
    } catch {}
  }, [wsId]);

  useEffect(() => { loadTree(); }, [loadTree]);

  const handleSelectFile = async (item) => {
    try {
      const r = await api(`/files/read?path=${encodeURIComponent(item.path)}&ws=${wsId || ""}`);
      setOpenFile({ path: item.path, content: r.content || "", language: r.language || "plaintext" });
    } catch {}
  };

  const handleSave = async (content) => {
    if (!openFile) return;
    try {
      await api("/files/write", { method: "POST", body: JSON.stringify({ path: openFile.path, content, ws_id: wsId || "" }) });
      setOpenFile(f => ({ ...f, content }));
    } catch {}
  };

  const handleTerminal = async (command) => {
    return api("/files/terminal", { method: "POST", body: JSON.stringify({ command, ws_id: wsId || "" }) });
  };

  return (
    <div style={{ display: "flex", height: "100%", background: "var(--bg-root)" }}>
      {/* File Explorer */}
      <div style={{ width: 240, minWidth: 180, borderRight: "1px solid var(--border)", background: "var(--bg-surface)", flexShrink: 0, overflow: "hidden" }}>
        <FileExplorer tree={tree} onSelectFile={handleSelectFile} onRefresh={loadTree} />
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
