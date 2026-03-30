import React from "react";

function stDot(v) {
  if (["ready", "enabled", "ok", "available", "success"].includes(v)) return "dot-success";
  if (v === "running" || v === "preparing") return "dot-running";
  if (["error", "down", "not_configured", "disabled"].includes(v)) return "dot-error";
  return "dot-neutral";
}

export default function KPIBar({ health, integrations, workspaceCount }) {
  const llm = health?.llm || {};
  const bw = health?.browser_worker || {};
  const tr = bw.transport || {};
  const bwSt = bw.status || (tr.alive ? "ready" : tr.worker_failed ? "error" : "available");

  return (
    <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(4,1fr)", marginBottom: 10 }}>
      <div className="kpi-card">
        <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 1 }}>
          <span className="dot dot-success" /><span className="kpi-label">API</span>
        </div>
        <div className="kpi-value accent" style={{ fontSize: 14 }}>Online</div>
      </div>
      <div className="kpi-card">
        <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 1 }}>
          <span className={`dot ${stDot(bwSt)}`} /><span className="kpi-label">Browser</span>
        </div>
        <div className="kpi-value" style={{ fontSize: 14 }}>{bwSt}</div>
      </div>
      <div className="kpi-card">
        <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 1 }}>
          <span className={`dot ${stDot(llm.status || "unknown")}`} /><span className="kpi-label">LLM</span>
        </div>
        <div className="kpi-value" style={{ fontSize: 12 }}>{llm.provider || "—"}</div>
      </div>
      <div className="kpi-card">
        <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 1 }}>
          <span className="dot dot-success" /><span className="kpi-label">Workspaces</span>
        </div>
        <div className="kpi-value" style={{ fontSize: 14 }}>{workspaceCount || 0}</div>
      </div>
    </div>
  );
}

export { stDot };
