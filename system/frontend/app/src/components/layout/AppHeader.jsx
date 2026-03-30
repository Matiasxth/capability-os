import React from "react";

export default function AppHeader({
  route, navigate, activeWs, userName,
  wsConnected, onToggleTheme, theme,
  unreadCount, onToggleFeed, onTogglePalette,
}) {
  return (
    <header className="app-header">
      <div className="app-header-left">
        <div className="app-logo"><div className="logo-icon" />CapOS</div>
        <nav className="app-nav">
          <button type="button" className={route === "/" ? "is-active" : ""} onClick={() => navigate("/")}>Workspace</button>
          <button type="button" className={route === "/control-center" ? "is-active" : ""} onClick={() => navigate("/control-center")}>Control Center</button>
        </nav>
      </div>
      <div className="app-header-right">
        {activeWs && (
          <div className="ws-selector" title={activeWs.path}>
            <span className="ws-dot" style={{ background: activeWs.color || "#00ff88" }} />
            <span>{activeWs.name}</span>
          </div>
        )}
        <button className="notification-bell" onClick={onToggleFeed} title="Activity feed">
          {"\u{1F514}"}
          {unreadCount > 0 && <span className="notification-bell-badge" />}
        </button>
        <div className={`dot ${wsConnected ? "dot-success" : "dot-neutral"}`} title={wsConnected ? "Real-time connected" : "Polling mode"} />
        <button onClick={onToggleTheme} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 14, padding: "2px 6px", borderRadius: 4, color: "var(--text-dim)" }} title={theme === "dark" ? "Switch to light" : "Switch to dark"}>
          {theme === "dark" ? "\u2600" : "\u263E"}
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-dim)" }}>
          <div style={{ width: 22, height: 22, borderRadius: 6, background: "var(--bg-elevated)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 600, color: "var(--accent)" }}>
            {userName?.charAt(0).toUpperCase() || "?"}
          </div>
          <span>{userName}</span>
        </div>
      </div>
    </header>
  );
}
