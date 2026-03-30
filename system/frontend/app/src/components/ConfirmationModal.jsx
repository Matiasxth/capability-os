import React, { useState } from "react";

/**
 * Security confirmation modal.
 * Level 2: simple Allow/Deny
 * Level 3: password required
 */
export default function ConfirmationModal({ confirmation, onConfirm, onDeny }) {
  const [password, setPassword] = useState("");
  if (!confirmation) return null;

  const { tool_id, params, security_level, description, confirmation_id } = confirmation;
  const isLevel3 = security_level >= 3;

  const cx = {
    overlay: {
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 9999,
      display: "flex", alignItems: "center", justifyContent: "center",
    },
    modal: {
      background: "linear-gradient(135deg, #0a0e1a, #0d1225)", border: "1px solid #1a2444",
      borderRadius: 12, padding: 20, width: 420, maxWidth: "90vw", position: "relative",
      overflow: "hidden",
    },
    glow: {
      position: "absolute", top: 0, left: 0, right: 0, height: 2,
      background: isLevel3
        ? "linear-gradient(90deg, transparent, #ff4444, #ff6644, transparent)"
        : "linear-gradient(90deg, transparent, #ffaa00, #ff8800, transparent)",
    },
    title: { fontSize: 14, fontWeight: 700, marginBottom: 12, color: isLevel3 ? "#ff4444" : "#ffaa00" },
    desc: { fontSize: 11, color: "#8a9fc5", marginBottom: 12 },
    tool: {
      background: "#080c18", border: "1px solid #141e38", borderRadius: 6,
      padding: 10, marginBottom: 12, fontSize: 11,
    },
    toolName: { color: "#4a8af5", fontWeight: 600, marginBottom: 4 },
    params: { color: "#6a7fa5", fontFamily: "monospace", fontSize: 10, whiteSpace: "pre-wrap", maxHeight: 120, overflow: "auto" },
    input: {
      width: "100%", height: 32, background: "#0a0f1e", border: "1px solid #1a2848",
      borderRadius: 4, color: "#c8d4e8", padding: "0 8px", fontSize: 12, marginBottom: 12,
    },
    btns: { display: "flex", gap: 8 },
    btnAllow: {
      flex: 1, height: 36, border: "1px solid #25d36644", borderRadius: 6,
      background: "linear-gradient(135deg, #0d3320, #0a2a1c)", color: "#25d366",
      fontWeight: 600, fontSize: 12, cursor: "pointer",
    },
    btnDeny: {
      flex: 1, height: 36, border: "1px solid #ff444444", borderRadius: 6,
      background: "linear-gradient(135deg, #2a0a0a, #200c0c)", color: "#ff4444",
      fontWeight: 600, fontSize: 12, cursor: "pointer",
    },
    level: {
      display: "inline-block", padding: "2px 8px", borderRadius: 4, fontSize: 9,
      fontWeight: 600, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8,
      background: isLevel3 ? "#2a0a0a" : "#2a1a0a",
      color: isLevel3 ? "#ff4444" : "#ffaa00",
      border: `1px solid ${isLevel3 ? "#ff444433" : "#ffaa0033"}`,
    },
  };

  const paramsStr = params ? JSON.stringify(params, null, 2) : "{}";

  return (
    <div style={cx.overlay} onClick={onDeny}>
      <div style={cx.modal} onClick={e => e.stopPropagation()}>
        <div style={cx.glow} />
        <div style={cx.level}>{isLevel3 ? "Password Required" : "Confirmation Required"}</div>
        <div style={cx.title}>{isLevel3 ? "Protected Operation" : "Action Requires Approval"}</div>
        <div style={cx.desc}>{description}</div>
        <div style={cx.tool}>
          <div style={cx.toolName}>{tool_id}</div>
          <div style={cx.params}>{paramsStr}</div>
        </div>
        {isLevel3 && (
          <input
            type="password"
            style={cx.input}
            placeholder="Enter security password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            autoFocus
          />
        )}
        <div style={cx.btns}>
          <button style={cx.btnAllow} onClick={() => onConfirm(confirmation_id, password)}>
            {isLevel3 ? "Authenticate & Allow" : "Allow"}
          </button>
          <button style={cx.btnDeny} onClick={onDeny}>Deny</button>
        </div>
      </div>
    </div>
  );
}
