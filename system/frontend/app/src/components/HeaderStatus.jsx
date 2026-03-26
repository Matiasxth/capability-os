import React from "react";

function statusClass(value) {
  if (value === "ready" || value === "enabled" || value === "ok") {
    return "is-success";
  }
  if (value === "running") {
    return "is-running";
  }
  if (value === "error" || value === "down" || value === "not_configured") {
    return "is-error";
  }
  return "is-neutral";
}

export default function HeaderStatus({ status }) {
  const llm = status?.llm || {};
  const browser = status?.browser_worker || {};
  const integrations = status?.integrations || {};
  const transport = browser.transport || {};

  const llmLabel = llm.status || "unknown";
  const browserLabel = transport.alive ? "ready" : transport.worker_failed ? "error" : "idle";
  const activeSessionId = browser.active_session_id || "-";
  const enabledIntegrations = Number.isFinite(integrations.enabled) ? integrations.enabled : 0;
  const totalIntegrations = Number.isFinite(integrations.total) ? integrations.total : 0;

  return (
    <header className="workspace-header">
      <div className="workspace-title">
        <h1>Capability OS Workspace</h1>
        <p>{"Intent -> plan -> confirm -> execute"}</p>
      </div>
      <div className="status-grid">
        <div className={`status-chip ${statusClass(llmLabel)}`}>
          <span className="status-key">LLM</span>
          <span className="status-value">{llmLabel}</span>
          <small>{llm.provider || "none"}</small>
        </div>
        <div className={`status-chip ${statusClass(browserLabel)}`}>
          <span className="status-key">Browser Worker</span>
          <span className="status-value">{browserLabel}</span>
          <small>{transport.dead_reason || "healthy"}</small>
        </div>
        <div className="status-chip is-neutral">
          <span className="status-key">Active Session</span>
          <span className="status-value">{activeSessionId}</span>
          <small>{Array.isArray(browser.known_sessions) ? `${browser.known_sessions.length} sessions` : "0 sessions"}</small>
        </div>
        <div className="status-chip is-neutral">
          <span className="status-key">Integrations</span>
          <span className="status-value">
            {enabledIntegrations}/{totalIntegrations}
          </span>
          <small>enabled / total</small>
        </div>
      </div>
    </header>
  );
}
