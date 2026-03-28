import React from "react";

const SECTIONS = [
  { id: "system",           label: "System" },
  { id: "workspaces",       label: "Workspaces" },
  { id: "llm",              label: "LLM" },
  { id: "metrics",          label: "Metrics" },
  { id: "self-improvement", label: "Optimize" },
  { id: "auto-growth",      label: "Auto-Growth" },
  { id: "mcp",              label: "MCP" },
  { id: "a2a",              label: "A2A" },
  { id: "memory",           label: "Memory" },
  { id: "integrations",     label: "Integrations" },
  { id: "browser",          label: "Browser" },
];

export default function SettingsSidebar({ activeSection, onSelectSection }) {
  return (
    <aside className="cc-sidebar">
      <h2>Control</h2>
      <nav>
        {SECTIONS.map((s) => (
          <button key={s.id} type="button" className={`cc-sidebar-item ${activeSection === s.id ? "is-active" : ""}`} onClick={() => onSelectSection(s.id)}>
            {s.label}
          </button>
        ))}
      </nav>
    </aside>
  );
}
