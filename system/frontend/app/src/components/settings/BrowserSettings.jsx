import React from "react";

export default function BrowserSettings({ browserHealth, onRestart, restarting }) {
  const transport = browserHealth?.transport || {};
  const knownSessions = Array.isArray(browserHealth?.known_sessions) ? browserHealth.known_sessions : [];
  const activeSessionId = browserHealth?.active_session_id || "-";
  const isAlive = Boolean(transport.alive);

  return (
    <section className="settings-section">
      <h3>Browser Worker</h3>
      <div className="status-row">
        <span>Status</span>
        <strong>{browserHealth?.status || (isAlive ? "ready" : "not_configured")}</strong>
      </div>
      <div className="status-row">
        <span>Active Session</span>
        <strong>{activeSessionId}</strong>
      </div>
      <div className="status-row">
        <span>Known Sessions</span>
        <strong>{knownSessions.length}</strong>
      </div>
      <div className="status-row">
        <span>Auto Start</span>
        <strong>{String(browserHealth?.auto_start ?? true)}</strong>
      </div>
      {transport.dead_reason && (
        <p className="error-text">worker error: {transport.dead_reason}</p>
      )}

      <div className="settings-actions">
        <button type="button" onClick={onRestart} disabled={restarting}>
          {restarting ? "Restarting..." : "Restart Worker"}
        </button>
        {!isAlive && (
          <button type="button" onClick={onRestart} disabled={restarting}>
            {restarting ? "Starting..." : "Start Worker"}
          </button>
        )}
      </div>
    </section>
  );
}

