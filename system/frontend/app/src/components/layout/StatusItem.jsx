import React from "react";

export default function StatusItem({ label, status = "neutral", onClick }) {
  const dotClass = status === "success" ? "dot-success" : status === "error" ? "dot-error" : status === "warning" ? "dot-warning" : "dot-neutral";
  return (
    <div className={`status-item${onClick ? " status-item-clickable" : ""}`} onClick={onClick} title={label}>
      <span className={`dot ${dotClass}`} style={{ width: 5, height: 5 }} />
      <span className="status-item-label">{label}</span>
    </div>
  );
}
