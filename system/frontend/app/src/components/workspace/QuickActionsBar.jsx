import React from "react";

const QUICK_ACTIONS = [
  { id: "list_directory", label: "List files", icon: "📂" },
  { id: "execute_command", label: "Run command", icon: "⚡" },
  { id: "fetch_url", label: "Fetch URL", icon: "🌐" },
  { id: "analyze_project", label: "Analyze project", icon: "🔍" },
  { id: "send_telegram_message", label: "Telegram", icon: "📱" },
  { id: "get_system_status", label: "System status", icon: "📊" },
];

export default function QuickActionsBar({ freqCaps, onAction }) {
  // Use frequent capabilities if available, fallback to defaults
  const actions = (freqCaps && freqCaps.length > 0)
    ? freqCaps.slice(0, 6).map(c => ({
        id: c.id || c,
        label: c.name || c.id || c,
        icon: "⚡",
      }))
    : QUICK_ACTIONS;

  return (
    <div className="quick-actions">
      {actions.map(a => (
        <button
          key={a.id}
          className="quick-action-btn"
          onClick={() => onAction(a.id)}
          title={a.label}
        >
          <span>{a.icon}</span>
          <span>{a.label}</span>
        </button>
      ))}
    </div>
  );
}
