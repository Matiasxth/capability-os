import React, { useState } from "react";

export default function NewProjectModal({ states, onCreate, onClose }) {
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [selectedState, setSelectedState] = useState(states?.[1] || states?.[0] || { name: "En construccion", color: "#ffaa00", icon: "\u{1f3d7}\ufe0f" });
  const [error, setError] = useState("");

  const cx = {
    overlay: {
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 9999,
      display: "flex", alignItems: "center", justifyContent: "center",
    },
    modal: {
      background: "linear-gradient(135deg, #0a0e1a, #0d1225)", border: "1px solid #1a2444",
      borderRadius: 12, padding: 20, width: 400, maxWidth: "90vw", position: "relative",
    },
    glow: {
      position: "absolute", top: 0, left: 0, right: 0, height: 2,
      background: "linear-gradient(90deg, transparent, #00f0ff, #7b2dff, transparent)",
    },
    title: { fontSize: 15, fontWeight: 700, marginBottom: 16, color: "#c8d4e8" },
    label: { fontSize: 10, color: "#6a7fa5", display: "block", marginBottom: 3, textTransform: "uppercase", letterSpacing: 1 },
    input: {
      width: "100%", height: 32, background: "#080c18", border: "1px solid #1a2848",
      borderRadius: 6, color: "#c8d4e8", padding: "0 10px", fontSize: 12, marginBottom: 12,
    },
    stateGrid: { display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 12 },
    stateBtn: (active) => ({
      display: "flex", alignItems: "center", gap: 4, padding: "4px 10px", borderRadius: 6,
      border: active ? "1px solid #4a8af5" : "1px solid #1a2848",
      background: active ? "rgba(74,138,245,0.1)" : "#080c18",
      color: active ? "#fff" : "#6a7fa5", fontSize: 11, cursor: "pointer",
    }),
    btns: { display: "flex", gap: 8, marginTop: 4 },
    btnCreate: {
      flex: 1, height: 36, border: "1px solid #00f0ff44", borderRadius: 6,
      background: "linear-gradient(135deg, #0a1a2a, #0d1a30)", color: "#00f0ff",
      fontWeight: 600, fontSize: 12, cursor: "pointer",
    },
    btnCancel: {
      flex: 1, height: 36, border: "1px solid #333", borderRadius: 6,
      background: "transparent", color: "#666", fontSize: 12, cursor: "pointer",
    },
    error: { color: "#ff4444", fontSize: 11, marginBottom: 8 },
  };

  const handleCreate = () => {
    if (!name.trim()) { setError("Project name is required"); return; }
    if (!path.trim()) { setError("Path is required"); return; }
    setError("");
    onCreate({ name: name.trim(), path: path.trim(), status: selectedState });
  };

  return (
    <div style={cx.overlay} onClick={onClose}>
      <div style={cx.modal} onClick={e => e.stopPropagation()}>
        <div style={cx.glow} />
        <div style={cx.title}>New Project</div>

        <label style={cx.label}>Project Name</label>
        <input style={cx.input} value={name} onChange={e => setName(e.target.value)} placeholder="My Project" autoFocus />

        <label style={cx.label}>Directory Path</label>
        <input style={cx.input} value={path} onChange={e => setPath(e.target.value)} placeholder="C:\Users\...\my-project" />

        <label style={cx.label}>Initial Status</label>
        <div style={cx.stateGrid}>
          {(states || []).map(s => (
            <div key={s.name} style={cx.stateBtn(selectedState?.name === s.name)} onClick={() => setSelectedState(s)}>
              <span>{s.icon}</span>
              <span>{s.name}</span>
            </div>
          ))}
        </div>

        {error && <div style={cx.error}>{error}</div>}

        <div style={cx.btns}>
          <button style={cx.btnCreate} onClick={handleCreate}>Create Project</button>
          <button style={cx.btnCancel} onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
