import React, { useState } from "react";

const NODE_CATALOG = [
  // Flow control
  { type: "trigger",      icon: "⏱",  label: "Trigger",      accent: "#00ff88", desc: "Start the workflow on a schedule or event", category: "flow" },
  { type: "condition",    icon: "⑂",  label: "Condition",    accent: "#eab308", desc: "Branch based on an expression", category: "flow" },
  { type: "loop",         icon: "🔁", label: "Loop",         accent: "#a855f7", desc: "Iterate over a collection", category: "flow" },
  { type: "delay",        icon: "⏳", label: "Delay",        accent: "#6b7280", desc: "Wait for a specified duration", category: "flow" },

  // Actions
  { type: "tool",         icon: "🔧", label: "Tool",         accent: "#3b82f6", desc: "Execute a registered capability/tool", category: "action" },
  { type: "agent",        icon: "🤖", label: "Agent",        accent: "#06b6d4", desc: "Delegate a task to an agent", category: "action" },
  { type: "http",         icon: "🌐", label: "HTTP Request", accent: "#10b981", desc: "Call an external API endpoint", category: "action" },
  { type: "script",       icon: "📜", label: "Script",       accent: "#8b5cf6", desc: "Run Python or JavaScript code", category: "action" },
  { type: "prompt",       icon: "🧠", label: "AI Prompt",    accent: "#0ea5e9", desc: "Send a prompt to the LLM", category: "action" },
  { type: "file",         icon: "📁", label: "File",         accent: "#d97706", desc: "Read or write a file", category: "action" },

  // Data & Output
  { type: "transform",    icon: "⚡", label: "Transform",    accent: "#f97316", desc: "Transform data between steps", category: "data" },
  { type: "notification", icon: "🔔", label: "Notification", accent: "#f43f5e", desc: "Send notification to a channel", category: "data" },
  { type: "output",       icon: "📤", label: "Output",       accent: "#ec4899", desc: "Send result to a channel", category: "data" },
];

const CATEGORIES = [
  { id: "all", label: "All" },
  { id: "flow", label: "Flow" },
  { id: "action", label: "Actions" },
  { id: "data", label: "Data" },
];

export default function NodePalette() {
  const [filter, setFilter] = useState("all");

  function onDragStart(e, nodeType) {
    e.dataTransfer.setData("application/reactflow", nodeType);
    e.dataTransfer.effectAllowed = "move";
  }

  const filtered = filter === "all" ? NODE_CATALOG : NODE_CATALOG.filter(n => n.category === filter);

  return (
    <div className="wf-palette">
      <div className="wf-palette-title">Nodes</div>
      <div style={{ display: "flex", gap: 2, marginBottom: 6, padding: "0 8px" }}>
        {CATEGORIES.map(c => (
          <button key={c.id} onClick={() => setFilter(c.id)} style={{
            flex: 1, fontSize: 9, padding: "3px 0", border: "none", borderRadius: 4, cursor: "pointer",
            background: filter === c.id ? "var(--accent-dim, rgba(0,255,136,0.1))" : "transparent",
            color: filter === c.id ? "var(--accent, #00ff88)" : "var(--text-muted, #888)",
            fontWeight: filter === c.id ? 700 : 500,
          }}>{c.label}</button>
        ))}
      </div>
      {filtered.map((n) => (
        <div
          key={n.type}
          className="wf-palette-card"
          draggable
          onDragStart={(e) => onDragStart(e, n.type)}
          style={{ "--card-accent": n.accent }}
        >
          <div className="wf-palette-card-header">
            <span className="wf-palette-card-icon">{n.icon}</span>
            <span className="wf-palette-card-label">{n.label}</span>
          </div>
          <div className="wf-palette-card-desc">{n.desc}</div>
        </div>
      ))}
    </div>
  );
}
