import React from "react";

export default function ChatInput({
  intent, setIntent, onSubmit, loadingPlan, hasConv,
  autoExecute, setAutoExecute,
  agentMode, setAgentMode,
  voice,
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
      <form onSubmit={e => { e.preventDefault(); onSubmit(intent); }}>
        <div className="conv-input-wrap">
          <input
            className="conv-input"
            value={intent}
            onChange={e => setIntent(e.target.value)}
            placeholder={hasConv ? "Ask a follow-up..." : "What do you want to do?"}
            autoFocus
          />
          {voice && voice.supported && (
            <button
              type="button"
              className={`voice-mic-btn${voice.isRecording ? " is-recording" : ""}`}
              onClick={handleMic}
              title={voice.isRecording ? "Stop recording" : "Voice input"}
            >
              {voice.isRecording ? "\u23F9" : "\u{1F3A4}"}
            </button>
          )}
          <div style={{position:"absolute",right:90,top:"50%",transform:"translateY(-50%)",display:"flex",alignItems:"center",gap:10}}>
            <div
              style={{display:"flex",alignItems:"center",gap:4,fontSize:10,color:agentMode?"#4a8af5":"#444",cursor:"pointer",userSelect:"none"}}
              onClick={() => { const v = !agentMode; setAgentMode(v); localStorage.setItem("capos_agentmode", String(v)); }}
              title={agentMode ? "Agent Mode: LLM calls tools autonomously" : "Classic Mode: plan-then-execute"}
            >
              <span>{agentMode ? "Agent" : "Classic"}</span>
              <div style={{width:26,height:14,borderRadius:7,background:agentMode?"#4a8af5":"rgba(255,255,255,0.1)",position:"relative",transition:"background .2s"}}>
                <div style={{position:"absolute",top:2,left:agentMode?14:2,width:10,height:10,borderRadius:"50%",background:"#fff",transition:"left .2s"}}/>
              </div>
            </div>
            {!agentMode && <div
              style={{display:"flex",alignItems:"center",gap:4,fontSize:10,color:autoExecute?"var(--accent)":"#444",cursor:"pointer",userSelect:"none"}}
              onClick={() => { const v = !autoExecute; setAutoExecute(v); localStorage.setItem("capos_autoexecute", String(v)); }}
            >
              <span>Auto</span>
              <div style={{width:26,height:14,borderRadius:7,background:autoExecute?"var(--accent)":"rgba(255,255,255,0.1)",position:"relative",transition:"background .2s"}}>
                <div style={{position:"absolute",top:2,left:autoExecute?14:2,width:10,height:10,borderRadius:"50%",background:"#fff",transition:"left .2s"}}/>
              </div>
            </div>}
          </div>
          <button type="submit" className="conv-input-btn" disabled={loadingPlan || !intent.trim()}>
            {loadingPlan ? "..." : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}
