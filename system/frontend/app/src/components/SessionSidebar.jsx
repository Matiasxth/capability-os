import React from "react";

export default function SessionSidebar({
  history, wsConnected, userName, deletingId, confirmClear,
  onNewSession, onRestoreSession, onDeleteSession,
  setConfirmClear, onClearAll,
}) {
  return (
    <aside className="conv-sidebar">
      <div className="conv-sidebar-header">
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <div style={{width:18,height:18,borderRadius:4,background:"var(--accent)"}}/>
          <span style={{fontSize:13,fontWeight:600,color:"var(--text)"}}>CapOS</span>
          <span className={`dot ${wsConnected?"dot-success":"dot-warning"}`} title={wsConnected?"Real-time":"Polling"} style={{marginLeft:2}}/>
        </div>
        <button onClick={onNewSession} style={{width:"100%",height:30,fontSize:12,fontWeight:500,background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.06)",borderRadius:7,color:"var(--text-dim)",cursor:"pointer"}}>+ New session</button>
      </div>
      <div className="conv-sidebar-list">
        <div style={{fontSize:10,fontWeight:600,color:"var(--text-muted)",textTransform:"uppercase",letterSpacing:"0.06em",padding:"8px 10px 4px"}}>Recent</div>
        {history.map((h,i) => (
          <div key={h.id||i} className={`conv-sidebar-item${deletingId===h.id?" session-fade-out":""}`} onClick={() => onRestoreSession(h)}>
            <span style={{fontSize:11,width:16,textAlign:"center",flexShrink:0}}>
              {h.intent?.startsWith("[TG") ? "\uD83D\uDCF1" : (h.hasExecution||h.plan_steps||h.step_runs) ? "\u26A1" : "\uD83D\uDCAC"}
            </span>
            <span style={{flex:1,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",fontSize:12}}>
              {h.intent?.slice(0,30) || `Session ${new Date(h.time||Date.now()).toLocaleDateString("es-CL",{day:"numeric",month:"short"})}`}
            </span>
            {h.isChat && h.message_count > 0 && <span style={{fontSize:10,color:"var(--text-muted)",flexShrink:0}}>{h.message_count}</span>}
            {!h.isChat && h.duration_ms > 0 && <span style={{fontSize:10,color:"var(--text-muted)",flexShrink:0}}>{h.duration_ms}ms</span>}
            <span className={`dot dot-${h.status==="success"?"success":"error"}`}/>
            <button className="session-delete" onClick={e => { e.stopPropagation(); onDeleteSession(h.id); }}>✕</button>
          </div>
        ))}
        {history.length === 0 && <div style={{padding:"12px 10px",fontSize:12,color:"var(--text-muted)"}}>No sessions yet.</div>}
      </div>
      <div className="conv-sidebar-footer">
        {history.length > 0 && !confirmClear && <button className="conv-sidebar-clear" onClick={() => setConfirmClear(true)}>Clear all sessions</button>}
        {confirmClear && (
          <div style={{display:"flex",gap:6,padding:"2px 10px"}}>
            <button className="conv-sidebar-clear" style={{color:"#ff4444",flex:1}} onClick={onClearAll}>Confirm</button>
            <button className="conv-sidebar-clear" style={{flex:1}} onClick={() => setConfirmClear(false)}>Cancel</button>
          </div>
        )}
        <div className="conv-sidebar-item" onClick={() => { window.history.pushState({},"","/control-center"); window.dispatchEvent(new PopStateEvent("popstate")); }}>
          <span style={{fontSize:13}}>⚙</span><span>Control Center</span>
        </div>
        <div style={{display:"flex",alignItems:"center",gap:8,padding:"4px 10px"}}>
          <div style={{width:22,height:22,borderRadius:6,background:"var(--bg-elevated)",display:"flex",alignItems:"center",justifyContent:"center",fontSize:11,fontWeight:600,color:"var(--accent)"}}>
            {(userName||"U").charAt(0).toUpperCase()}
          </div>
          <span style={{fontSize:12,color:"var(--text-dim)"}}>{userName||"User"}</span>
        </div>
      </div>
    </aside>
  );
}
