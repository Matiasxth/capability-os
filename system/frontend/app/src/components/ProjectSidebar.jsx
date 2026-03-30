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
    container: { display: "flex", flexDirection: "column", height: "100%", background: "#080b14" },
    section: { padding: "8px 6px" },
    sectionTitle: {
      fontSize: 9, textTransform: "uppercase", letterSpacing: 2, color: "#3a4a6a",
      fontWeight: 700, marginBottom: 6, padding: "0 6px", display: "flex", alignItems: "center", justifyContent: "space-between",
    },
    addBtn: {
      fontSize: 14, color: "#3a5a8a", cursor: "pointer", background: "none", border: "none",
      padding: 0, lineHeight: 1,
    },
    project: (active) => ({
      display: "flex", alignItems: "center", gap: 6, padding: "6px 8px", borderRadius: 6,
      cursor: "pointer", marginBottom: 2, fontSize: 12, transition: "background 0.15s",
      background: active ? "rgba(74,138,245,0.1)" : "transparent",
      border: active ? "1px solid rgba(74,138,245,0.2)" : "1px solid transparent",
      color: active ? "#c8d4e8" : "#6a7fa5",
    }),
    statusDot: (color) => ({
      width: 7, height: 7, borderRadius: "50%", background: color || "#444", flexShrink: 0,
    }),
    projectName: { flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 11 },
    projectIcon: { fontSize: 14, flexShrink: 0 },
    divider: { height: 1, background: "#121828", margin: "4px 6px" },
    histTitle: { flex: 1 },
    histItem: {
      display: "flex", alignItems: "center", gap: 5, padding: "5px 8px", borderRadius: 4,
      cursor: "pointer", fontSize: 11, color: "#5a6a8a", marginBottom: 1,
    },
    histIcon: { fontSize: 11, flexShrink: 0 },
    histText: { flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
    histMeta: { fontSize: 9, color: "#3a4a6a", flexShrink: 0 },
    histList: { flex: 1, overflowY: "auto", padding: "0 6px" },
    empty: { fontSize: 10, color: "#2a3a5a", textAlign: "center", padding: "20px 10px" },
    footer: { padding: "6px 8px", borderTop: "1px solid #121828", display: "flex", gap: 4 },
    footerBtn: {
      flex: 1, height: 24, border: "1px solid #1a2444", borderRadius: 4,
      background: "transparent", color: "#4a5a7a", fontSize: 9, cursor: "pointer",
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
