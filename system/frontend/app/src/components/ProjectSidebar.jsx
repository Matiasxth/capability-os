import React, { useState } from "react";
import StatusPicker from "./StatusPicker";

export default function ProjectSidebar({
  workspaces, activeProjectId, projectStates,
  history, userName, wsConnected,
  onSelectProject, onNewProject, onUpdateStatus, onDeleteProject,
  onNewSession, onRestoreSession, onDeleteSession, onClearAll,
}) {
  const [statusPicker, setStatusPicker] = useState(null); // {wsId, rect}
  const [confirmClear, setConfirmClear] = useState(false);

  const cx = {
    container: { display: "flex", flexDirection: "column", height: "100%" },
    section: { padding: "14px 14px" },
    sectionTitle: {
      fontSize: 11, textTransform: "uppercase", letterSpacing: 3, color: "#00f0ff",
      fontWeight: 700, marginBottom: 10, padding: "0 4px", display: "flex", alignItems: "center", justifyContent: "space-between",
    },
    addBtn: {
      fontSize: 20, color: "#00f0ff", cursor: "pointer", background: "none", border: "none",
      padding: 0, lineHeight: 1, transition: "color 0.15s", textShadow: "0 0 8px rgba(0,240,255,0.3)",
    },
    project: (active) => ({
      display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", borderRadius: 8,
      cursor: "pointer", marginBottom: 4, fontSize: 14, transition: "all 0.15s",
      background: active ? "rgba(0,240,255,0.08)" : "transparent",
      border: active ? "1px solid rgba(0,240,255,0.25)" : "1px solid transparent",
      color: active ? "#e8ecf4" : "#9da3c0",
    }),
    statusDot: (color) => ({
      width: 10, height: 10, borderRadius: "50%", background: color || "#444", flexShrink: 0,
      boxShadow: `0 0 8px ${color || "#444"}66`,
    }),
    projectName: { flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 14, fontWeight: 500 },
    projectIcon: { fontSize: 18, flexShrink: 0 },
    divider: { height: 1, background: "linear-gradient(90deg, transparent, #1a1e48, transparent)", margin: "8px 12px" },
    histTitle: { flex: 1 },
    histItem: {
      display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderRadius: 6,
      cursor: "pointer", fontSize: 13, color: "#9da3c0", marginBottom: 3, transition: "all 0.12s",
    },
    histIcon: { fontSize: 14, flexShrink: 0 },
    histText: { flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
    histMeta: { fontSize: 11, color: "#6a70a0", flexShrink: 0 },
    histList: { flex: 1, overflowY: "auto", padding: "0 10px" },
    empty: { fontSize: 13, color: "#7a80a0", textAlign: "center", padding: "32px 16px" },
    footer: { padding: "10px 14px", borderTop: "1px solid #1a1e48", display: "flex", gap: 6 },
    footerBtn: {
      flex: 1, height: 32, border: "1px solid #1a1e48", borderRadius: 6,
      background: "transparent", color: "#8a90b0", fontSize: 11, cursor: "pointer", transition: "all 0.15s",
    },
  };

  const filteredHistory = activeProjectId
    ? history.filter(h => {
        // Match by session_id prefix or workspace reference
        if (h.id?.startsWith?.(`ws_${activeProjectId}`)) return true;
        // Also show if no project assignment (legacy)
        const ws = workspaces.find(w => w.id === activeProjectId);
        if (ws && h.intent) return true; // Show all for now
        return true;
      })
    : history;

  const activeProject = workspaces.find(w => w.id === activeProjectId);

  return (
    <div style={cx.container}>
      {/* Projects section */}
      <div style={cx.section}>
        <div style={cx.sectionTitle}>
          <span>Projects</span>
          <button style={cx.addBtn} onClick={onNewProject} title="New Project">+</button>
        </div>
        {workspaces.length === 0 && <div style={cx.empty}>No projects yet</div>}
        {workspaces.map(ws => (
          <div
            key={ws.id}
            style={cx.project(ws.id === activeProjectId)}
            onClick={() => onSelectProject(ws.id)}
            onContextMenu={e => {
              e.preventDefault();
              setStatusPicker({ wsId: ws.id, x: e.clientX, y: e.clientY });
            }}
          >
            <span style={cx.projectIcon}>{ws.status?.icon || ws.icon || "\U0001f4c1"}</span>
            <span style={cx.projectName}>{ws.name}</span>
            <span style={cx.statusDot(ws.status?.color || ws.color)} title={ws.status?.name || ""} />
          </div>
        ))}
      </div>

      <div style={cx.divider} />

      {/* History section */}
      <div style={{ ...cx.section, flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={cx.sectionTitle}>
          <span style={cx.histTitle}>
            {activeProject ? activeProject.name : "History"}
          </span>
          <button style={cx.addBtn} onClick={onNewSession} title="New Session">+</button>
        </div>

        <div style={cx.histList}>
          {filteredHistory.length === 0 && <div style={cx.empty}>No sessions</div>}
          {filteredHistory.map(h => {
            const icon = h.id?.startsWith("telegram_") ? "\U0001f4f1"
              : h.id?.startsWith("whatsapp_") ? "\U0001f4ac"
              : h.hasExecution ? "\u26a1" : "\U0001f4ac";
            return (
              <div key={h.id} style={cx.histItem} onClick={() => onRestoreSession(h)}>
                <span style={cx.histIcon}>{icon}</span>
                <span style={cx.histText}>{(h.intent || "Session").slice(0, 40)}</span>
                <span style={cx.histMeta}>
                  {h.message_count ? `${h.message_count}` : h.duration_ms ? `${h.duration_ms}ms` : ""}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer */}
      <div style={cx.footer}>
        {!confirmClear ? (
          <button style={cx.footerBtn} onClick={() => setConfirmClear(true)}>Clear History</button>
        ) : (
          <>
            <button style={{ ...cx.footerBtn, color: "#ff4444", borderColor: "#ff444433" }} onClick={() => { onClearAll(); setConfirmClear(false); }}>Confirm</button>
            <button style={cx.footerBtn} onClick={() => setConfirmClear(false)}>Cancel</button>
          </>
        )}
      </div>

      {/* Status picker popup */}
      {statusPicker && (
        <div style={{ position: "fixed", left: statusPicker.x, top: statusPicker.y, zIndex: 9999 }}>
          <StatusPicker
            currentStatus={workspaces.find(w => w.id === statusPicker.wsId)?.status}
            states={projectStates}
            onSelect={s => onUpdateStatus(statusPicker.wsId, s)}
            onClose={() => setStatusPicker(null)}
          />
        </div>
      )}
    </div>
  );
}
