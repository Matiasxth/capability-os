import React from "react";

export default function SystemHealth({ health }) {
  if (!health) {
    return (
      <section className="settings-section">
        <h3>System Health</h3>
        <p className="empty-block">Health data unavailable.</p>
      </section>
    );
  }

  const issues = Array.isArray(health.issues) ? health.issues : [];
  return (
    <section className="settings-section">
      <h3>System Health</h3>
      <div className="status-row">
        <span>Overall Status</span>
        <strong>{health.status}</strong>
      </div>
      <div className="status-row">
        <span>Uptime (ms)</span>
        <strong>{health.uptime_ms ?? 0}</strong>
      </div>
      <div className="status-row">
        <span>LLM</span>
        <strong>{health.llm?.status || "-"}</strong>
      </div>
      <div className="status-row">
        <span>Browser</span>
        <strong>{health.browser_worker?.status || "-"}</strong>
      </div>
      <div className="status-row">
        <span>Integrations</span>
        <strong>{health.integrations?.enabled || 0}/{health.integrations?.total || 0}</strong>
      </div>

      <h4>Issues</h4>
      {issues.length === 0 && <p className="empty-block">No active issues.</p>}
      {issues.length > 0 && (
        <ul className="plain-list">
          {issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

