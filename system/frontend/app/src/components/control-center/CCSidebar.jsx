import React, { useMemo, useState } from "react";
import { SECTION_REGISTRY } from "./sectionRegistry";

export default function CCSidebar({ activeSection, onSelectSection, wsConnected, highlightSection }) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search.trim()) return SECTION_REGISTRY;
    const q = search.toLowerCase();
    return SECTION_REGISTRY.filter(s =>
      s.label.toLowerCase().includes(q) ||
      s.keywords.some(k => k.includes(q))
    );
  }, [search]);

  return (
    <aside className="cc-sidebar">
      <h2 style={{ display: "flex", alignItems: "center", gap: 6 }}>
        Control
        {wsConnected != null && (
          <span
            className={`dot ${wsConnected ? "dot-success" : "dot-neutral"}`}
            title={wsConnected ? "Real-time connected" : "Polling mode"}
            style={{ width: 6, height: 6 }}
          />
        )}
      </h2>
      <input
        className="cc-search"
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder="Search settings..."
      />
      <nav>
        {filtered.map((s) => (
          <button
            key={s.id}
            type="button"
            className={`cc-sidebar-item ${activeSection === s.id ? "is-active" : ""}${highlightSection === s.id ? " has-update" : ""}`}
            onClick={() => onSelectSection(s.id)}
          >
            {s.label}
          </button>
        ))}
        {filtered.length === 0 && (
          <div style={{ padding: "8px", fontSize: 11, color: "var(--text-muted)" }}>No matching sections</div>
        )}
      </nav>
    </aside>
  );
}
