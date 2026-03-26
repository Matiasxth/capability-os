import React from "react";

const SECTIONS = [
  { id: "llm", label: "LLM" },
  { id: "browser", label: "Browser" },
  { id: "integrations", label: "Integrations" },
  { id: "workspace", label: "Workspace" },
  { id: "system", label: "System" }
];

export default function SettingsSidebar({ activeSection, onSelectSection }) {
  return (
    <aside className="settings-sidebar">
      <h2>Control Center</h2>
      <nav>
        {SECTIONS.map((section) => (
          <button
            key={section.id}
            type="button"
            className={`sidebar-item ${activeSection === section.id ? "is-active" : ""}`}
            onClick={() => onSelectSection(section.id)}
          >
            {section.label}
          </button>
        ))}
      </nav>
    </aside>
  );
}

