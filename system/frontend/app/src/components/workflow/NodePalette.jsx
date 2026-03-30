import React from "react";

const NODE_CATALOG = [
  { type: "trigger",   icon: "⏱",  label: "Trigger",   accent: "#00ff88", desc: "Start the workflow on a schedule or event" },
  { type: "tool",      icon: "🔧", label: "Tool",      accent: "#3b82f6", desc: "Execute a registered capability/tool" },
  { type: "agent",     icon: "🤖", label: "Agent",     accent: "#06b6d4", desc: "Delegate a task to an agent" },
  { type: "condition", icon: "⑂",  label: "Condition", accent: "#eab308", desc: "Branch based on an expression" },
  { type: "loop",      icon: "🔁", label: "Loop",      accent: "#a855f7", desc: "Iterate over a collection" },
  { type: "transform", icon: "⚡", label: "Transform", accent: "#f97316", desc: "Transform data between steps" },
  { type: "delay",     icon: "⏳", label: "Delay",     accent: "#6b7280", desc: "Wait for a specified duration" },
  { type: "output",    icon: "📤", label: "Output",    accent: "#ec4899", desc: "Send result to a channel" },
];

export default function NodePalette() {
  function onDragStart(e, nodeType) {
    e.dataTransfer.setData("application/reactflow", nodeType);
    e.dataTransfer.effectAllowed = "move";
  }

  return (
    <div className="wf-palette">
      <div className="wf-palette-title">Node Palette</div>
      {NODE_CATALOG.map((n) => (
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
