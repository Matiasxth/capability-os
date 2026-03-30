import React from "react";

export default function AgentAssignModal({ agents, assignedIds, onSave, onClose }) {
  const [selected, setSelected] = React.useState(new Set(assignedIds || []));

  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={onClose}>
      <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 12, padding: 20, width: 340, maxWidth: "90vw" }} onClick={e => e.stopPropagation()}>
        <h4 style={{ margin: "0 0 12px", color: "var(--text)" }}>Manage Project Agents</h4>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 14 }}>
          {(agents || []).map(a => {
            const on = selected.has(a.id);
            return (
              <div key={a.id} onClick={() => toggle(a.id)} style={{
                display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 6, cursor: "pointer",
                background: on ? "var(--accent-dim)" : "transparent",
                border: on ? "1px solid var(--accent)" : "1px solid var(--border)",
                transition: "all 0.15s",
              }}>
                <span style={{ fontSize: 18 }}>{a.emoji}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: on ? "var(--accent)" : "var(--text)" }}>{a.name}</div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{a.description || "No description"}</div>
                </div>
                <span style={{ fontSize: 14, color: on ? "var(--accent)" : "var(--text-muted)" }}>{on ? "\u2714" : ""}</span>
              </div>
            );
          })}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="btn-primary" style={{ flex: 1, height: 32, fontSize: 12 }} onClick={() => onSave([...selected])}>Save</button>
          <button style={{ flex: 1, height: 32, fontSize: 12 }} onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
