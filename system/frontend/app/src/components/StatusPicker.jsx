import React, { useState } from "react";

export default function StatusPicker({ currentStatus, states, onSelect, onClose }) {
  if (!states || states.length === 0) return null;

  const cx = {
    overlay: { position: "fixed", inset: 0, zIndex: 9998, background: "transparent" },
    menu: {
      position: "absolute", zIndex: 9999, background: "#0d1225", border: "1px solid #1a2444",
      borderRadius: 8, padding: 4, minWidth: 180, boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
    },
    item: (active) => ({
      display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", borderRadius: 4,
      cursor: "pointer", fontSize: 12, color: active ? "#fff" : "#8a9fc5",
      background: active ? "rgba(255,255,255,0.05)" : "transparent",
    }),
    dot: (color) => ({
      width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0,
    }),
  };

  return (
    <>
      <div style={cx.overlay} onClick={onClose} />
      <div style={cx.menu}>
        {states.map(s => (
          <div
            key={s.name}
            style={cx.item(currentStatus?.name === s.name)}
            onClick={() => { onSelect(s); onClose(); }}
          >
            <span>{s.icon}</span>
            <span style={{ flex: 1 }}>{s.name}</span>
            <span style={cx.dot(s.color)} />
          </div>
        ))}
      </div>
    </>
  );
}
