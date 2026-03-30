import React, { useState } from "react";

function FileNode({ item, depth, onSelect }) {
  const [expanded, setExpanded] = useState(depth < 1);
  const isDir = item.type === "directory";
  const icon = isDir ? (expanded ? "\u{1F4C2}" : "\u{1F4C1}") : getFileIcon(item.ext);

  return (
    <div>
      <div
        onClick={() => isDir ? setExpanded(!expanded) : onSelect(item)}
        style={{
          display: "flex", alignItems: "center", gap: 5,
          padding: "3px 0 3px " + (depth * 16 + 4) + "px",
          cursor: "pointer", fontSize: 12, color: "var(--text-dim)",
          borderRadius: 4, transition: "background 0.1s",
        }}
        onMouseEnter={e => e.currentTarget.style.background = "var(--bg-hover)"}
        onMouseLeave={e => e.currentTarget.style.background = "transparent"}
      >
        <span style={{ fontSize: 13, flexShrink: 0 }}>{icon}</span>
        <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.name}</span>
        {!isDir && item.size > 0 && <span style={{ fontSize: 9, color: "var(--text-muted)" }}>{formatSize(item.size)}</span>}
      </div>
      {isDir && expanded && item.children && item.children.map(c => (
        <FileNode key={c.path} item={c} depth={depth + 1} onSelect={onSelect} />
      ))}
    </div>
  );
}

function getFileIcon(ext) {
  const icons = {
    py: "\u{1F40D}", js: "\u{1F7E8}", jsx: "\u269B\uFE0F", ts: "\u{1F535}", tsx: "\u269B\uFE0F",
    json: "\u{1F4CB}", md: "\u{1F4DD}", html: "\u{1F310}", css: "\u{1F3A8}",
    png: "\u{1F5BC}\uFE0F", jpg: "\u{1F5BC}\uFE0F", svg: "\u{1F5BC}\uFE0F",
    sh: "\u{1F4DF}", yml: "\u2699\uFE0F", yaml: "\u2699\uFE0F",
  };
  return icons[ext] || "\u{1F4C4}";
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + "B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + "KB";
  return (bytes / (1024 * 1024)).toFixed(1) + "MB";
}

export default function FileExplorer({ tree, onSelectFile, onRefresh }) {
  return (
    <div style={{ height: "100%", overflow: "auto", padding: "8px 4px", fontSize: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 4px 8px", borderBottom: "1px solid var(--border)", marginBottom: 4 }}>
        <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 2, color: "var(--accent)", fontWeight: 700 }}>Files</span>
        <button onClick={onRefresh} style={{ background: "none", border: "none", fontSize: 12, cursor: "pointer", color: "var(--text-muted)", padding: 2 }} title="Refresh">{"\u{1F504}"}</button>
      </div>
      {(!tree || tree.length === 0) && <div style={{ color: "var(--text-muted)", textAlign: "center", padding: 20 }}>No files</div>}
      {(tree || []).map(item => (
        <FileNode key={item.path} item={item} depth={0} onSelect={onSelectFile} />
      ))}
    </div>
  );
}
