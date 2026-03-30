import React, { useMemo, useState } from "react";

const EVENT_LABELS = {
  telegram_message: "Telegram", whatsapp_message: "WhatsApp", slack_message: "Slack",
  discord_message: "Discord", execution_complete: "Execution", session_updated: "Session",
  settings_updated: "Settings", config_imported: "Config", workspace_changed: "Workspace",
  growth_update: "Growth", integration_changed: "Integration", mcp_changed: "MCP",
  a2a_changed: "A2A", browser_changed: "Browser", memory_cleared: "Memory",
  preferences_updated: "Preferences", error: "Error",
};

const CATEGORIES = {
  telegram_message: "integrations", whatsapp_message: "integrations", slack_message: "integrations",
  discord_message: "integrations", integration_changed: "integrations",
  execution_complete: "executions", session_updated: "executions",
  error: "system", settings_updated: "system", config_imported: "system",
  workspace_changed: "system", browser_changed: "system", mcp_changed: "system",
  a2a_changed: "system", growth_update: "system", memory_cleared: "system",
  preferences_updated: "system",
};

const TABS = [
  { id: "all", label: "All" },
  { id: "integrations", label: "Integrations" },
  { id: "executions", label: "Executions" },
  { id: "system", label: "System" },
];

export default function NotificationCenter({ events, isOpen, onClose }) {
  const [filter, setFilter] = useState("all");

  const filtered = useMemo(() => {
    if (filter === "all") return events;
    return events.filter(e => CATEGORIES[e.type] === filter);
  }, [events, filter]);

  if (!isOpen) return null;

  return (
    <>
      <div className="nc-backdrop" onClick={onClose} />
      <aside className="notification-center is-open">
        <div className="nc-header">
          <span style={{ fontWeight: 600 }}>Activity</span>
          <button className="btn-ghost" onClick={onClose} style={{ height: 20, fontSize: 10, padding: "0 6px" }}>Close</button>
        </div>
        <div className="nc-tabs">
          {TABS.map(t => (
            <button key={t.id} className={`nc-tab${filter === t.id ? " is-active" : ""}`} onClick={() => setFilter(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="nc-list">
          {filtered.length === 0 && (
            <div className="empty-state" style={{ padding: 24 }}>
              <span className="empty-state-text">No events</span>
            </div>
          )}
          {filtered.map((evt, i) => (
            <div key={i} className={`nc-item${evt.type === "error" ? " is-error" : ""}`}>
              <span className="nc-item-badge">{EVENT_LABELS[evt.type] || evt.type}</span>
              <span className="nc-item-detail">
                {evt.data?.action || evt.data?.message || evt.data?.text?.slice(0, 40) || ""}
              </span>
              <span className="nc-item-time">
                {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : ""}
              </span>
            </div>
          ))}
        </div>
      </aside>
    </>
  );
}
