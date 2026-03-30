import React from "react";

export default function ChatInput({
  intent, setIntent, onSubmit, loadingPlan, hasConv,
  autoExecute, setAutoExecute,
  agentMode, setAgentMode,
  agents, activeAgentId, setActiveAgentId,
  voice, tts,
}) {
  const handleMic = () => {
    if (!voice || !voice.supported) return;
    if (voice.isRecording) {
      voice.stopRecording();
    } else {
      voice.startRecording((transcript) => setIntent(transcript));
    }
  };

  return (
    <div className="conv-input-area">
      {/* Controls bar above input */}
      <div style={{display:"flex",alignItems:"center",justifyContent:"flex-end",gap:8,padding:"0 4px 6px",flexWrap:"wrap"}}>
        {agentMode && agents && agents.length > 1 && (
          <select
            value={activeAgentId || ""}
            onChange={e => setActiveAgentId(e.target.value || null)}
            style={{height:24,fontSize:10,background:"var(--bg-input)",border:"1px solid var(--border)",borderRadius:4,color:"var(--text-dim)",padding:"0 6px",maxWidth:120}}
          >
            {agents.map(a => <option key={a.id} value={a.id}>{a.emoji} {a.name}</option>)}
          </select>
        )}
        <div
          style={{display:"flex",alignItems:"center",gap:4,fontSize:10,color:agentMode?"var(--accent)":"var(--text-muted)",cursor:"pointer",userSelect:"none"}}
          onClick={() => { const v = !agentMode; setAgentMode(v); localStorage.setItem("capos_agentmode", String(v)); }}
          title={agentMode ? "Agent Mode: LLM calls tools autonomously" : "Classic Mode: plan-then-execute"}
        >
          <span>{agentMode ? "Agent" : "Classic"}</span>
          <div style={{width:26,height:14,borderRadius:7,background:agentMode?"var(--accent)":"rgba(255,255,255,0.1)",position:"relative",transition:"background .2s"}}>
            <div style={{position:"absolute",top:2,left:agentMode?14:2,width:10,height:10,borderRadius:"50%",background:"#fff",transition:"left .2s"}}/>
          </div>
        </div>
        {!agentMode && (
          <div
            style={{display:"flex",alignItems:"center",gap:4,fontSize:10,color:autoExecute?"var(--accent)":"var(--text-muted)",cursor:"pointer",userSelect:"none"}}
            onClick={() => { const v = !autoExecute; setAutoExecute(v); localStorage.setItem("capos_autoexecute", String(v)); }}
          >
            <span>Auto</span>
            <div style={{width:26,height:14,borderRadius:7,background:autoExecute?"var(--accent)":"rgba(255,255,255,0.1)",position:"relative",transition:"background .2s"}}>
              <div style={{position:"absolute",top:2,left:autoExecute?14:2,width:10,height:10,borderRadius:"50%",background:"#fff",transition:"left .2s"}}/>
            </div>
          </div>
        )}
      </div>

      {/* Input row */}
      <form onSubmit={e => { e.preventDefault(); onSubmit(intent); }}>
        <div style={{display:"flex",alignItems:"center",gap:6}}>
          <input
            className="conv-input"
            value={intent}
            onChange={e => setIntent(e.target.value)}
            placeholder={hasConv ? "Ask a follow-up..." : "What do you want to do?"}
            autoFocus
            style={{flex:1,paddingRight:12}}
          />
          {voice && voice.supported && (
            <button
              type="button"
              onClick={handleMic}
              title={voice.isRecording ? "Stop recording" : "Voice input"}
              style={{
                width:40,height:40,borderRadius:"50%",flexShrink:0,display:"flex",alignItems:"center",justifyContent:"center",
                fontSize:16,cursor:"pointer",transition:"all 0.2s",
                background:voice.isRecording?"var(--error)":"var(--bg-elevated)",
                border:voice.isRecording?"1px solid var(--error)":"1px solid var(--border)",
                color:voice.isRecording?"#fff":"var(--text-dim)",
                animation:voice.isRecording?"pulse 1.5s infinite":"none",
              }}
            >
              {voice.isRecording ? "\u23F9" : "\u{1F3A4}"}
            </button>
          )}
          {tts && tts.supported && (
            <button
              type="button"
              onClick={tts.speaking ? tts.stop : tts.toggleAutoSpeak}
              title={tts.speaking ? "Stop speaking" : tts.autoSpeak ? "Auto-speak ON" : "Auto-speak OFF"}
              style={{
                width:40,height:40,borderRadius:"50%",flexShrink:0,display:"flex",alignItems:"center",justifyContent:"center",
                fontSize:16,cursor:"pointer",transition:"all 0.2s",
                background:tts.speaking?"var(--accent-dim)":"var(--bg-elevated)",
                border:tts.autoSpeak?"1px solid var(--accent)":"1px solid var(--border)",
                color:tts.autoSpeak?"var(--accent)":"var(--text-muted)",
                animation:tts.speaking?"pulse 1s infinite":"none",
              }}
            >
              {tts.speaking ? "\u{1F50A}" : tts.autoSpeak ? "\u{1F509}" : "\u{1F507}"}
            </button>
          )}
          <button
            type="submit"
            disabled={loadingPlan || !intent.trim()}
            style={{
              width:40,height:40,borderRadius:"50%",flexShrink:0,display:"flex",alignItems:"center",justifyContent:"center",
              fontSize:14,fontWeight:700,cursor:loadingPlan||!intent.trim()?"not-allowed":"pointer",
              background:!intent.trim()?"var(--bg-elevated)":"var(--accent)",
              border:!intent.trim()?"1px solid var(--border)":"1px solid var(--accent)",
              color:!intent.trim()?"var(--text-muted)":"var(--bg-root)",
              transition:"all 0.2s",
            }}
          >
            {loadingPlan ? "..." : "\u2191"}
          </button>
        </div>
      </form>
    </div>
  );
}
