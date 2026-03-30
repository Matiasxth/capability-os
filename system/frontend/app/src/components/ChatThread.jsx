import React from "react";
import OutputRenderer from "./OutputRenderer";
import MarkdownRenderer from "./workspace/MarkdownRenderer";
import AgentStepView from "./AgentStepView";

function greeting(name) {
  const h = new Date().getHours();
  const g = h < 6 ? "Working late" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  return `${g}, ${name}`;
}

export default function ChatThread({
  messages, userName, freqCaps, activeSessionId,
  planValidationErrors, planExecuted, runningPlan, stepRuns,
  autoExecTimerRef, onRunPlan, onCancelAutoExec, onSubmit, onNavigateDir,
  renderAmbiguousContacts, threadRef, voice,
}) {
  const hasConv = messages.length > 0;

  return (
    <div ref={threadRef} className="conv-messages">
      <div className="conv-messages-inner">
        {!hasConv && (<>
          <div className="conv-greeting">{greeting(userName || "there")} 👋</div>
          <div className="conv-sub">What would you like to do?</div>
          {freqCaps.length > 0 && (
            <div className="conv-chips">
              {freqCaps.map(c => <button key={c} className="conv-chip" onClick={() => onSubmit(c.replace(/_/g, " "))}>{c.replace(/_/g, " ")}</button>)}
            </div>
          )}
        </>)}

        {hasConv && (
          <div className="conv-thread" style={{paddingTop: 24}}>
            {activeSessionId && activeSessionId.startsWith("telegram_") && (
              <div style={{fontSize: 11, color: "#555", textAlign: "center", padding: "4px 0 8px"}}>Telegram conversation — updates automatically</div>
            )}
            {messages.map(msg => {
              if (msg.role === "user") return <div key={msg.id} className="conv-msg conv-msg-user">{msg.content}</div>;
              const m = msg.meta || {};

              if (m.loading) return <div key={msg.id} className="conv-msg conv-msg-system"><span style={{animation: "pulse 1.5s infinite", color: "var(--text-dim)"}}>{msg.content}</span></div>;

              if (m.error) return <div key={msg.id} className="conv-msg conv-msg-system" style={{borderColor: "rgba(255,68,68,0.15)"}}><span style={{color: "var(--error)"}}>✗ {msg.content}</span></div>;

              if (msg.content === "agent_steps" && m.agentEvents) {
                const stepsOnly = (m.agentEvents || []).filter(e => e.event !== "agent_response" && e.event !== "agent_start");
                return (
                  <div key={msg.id} className="conv-msg conv-msg-system">
                    {stepsOnly.length > 0 && <AgentStepView events={stepsOnly} />}
                    {m.finalText && <div style={{marginTop: 8, lineHeight: 1.6, whiteSpace: "pre-wrap"}}>{m.finalText}</div>}
                    {m.awaiting && <div style={{color: "#ffaa00", fontSize: 11, marginTop: 6}}>Waiting for your approval...</div>}
                  </div>
                );
              }

              if (msg.content === "plan" && m.plan) {
                const st = m.plan.steps || [];
                return (
                  <div key={msg.id} className="conv-msg conv-msg-system">
                    <div style={{marginBottom: 8, fontWeight: 500}}>Here's my plan:</div>
                    {st.map((s, i) => (
                      <div key={s.step_id} className="conv-step is-ok" style={{opacity: 0.8}}>
                        <span className="conv-step-icon">{i + 1}</span>
                        <span className="conv-step-name">{s.step_id} <span style={{color: "var(--text-muted)"}}>→ {s.capability}</span></span>
                      </div>
                    ))}
                    {planValidationErrors.length > 0 && <div style={{color: "var(--error)", fontSize: 12, marginTop: 6}}>{planValidationErrors.map(e => e.message).join("; ")}</div>}
                    {!planExecuted && (
                      <div style={{display: "flex", gap: 6, marginTop: 12}}>
                        <button className="btn-primary" style={{flex: 1, height: 36, fontSize: 13, borderRadius: 10}} onClick={onRunPlan} disabled={runningPlan || !st.length}>
                          {runningPlan ? "Executing..." : autoExecTimerRef?.current ? "Auto-executing..." : "Execute plan →"}
                        </button>
                        {autoExecTimerRef?.current && (
                          <button style={{height: 36, padding: "0 14px", fontSize: 12, borderRadius: 10, background: "rgba(255,68,68,0.1)", border: "1px solid rgba(255,68,68,0.2)", color: "var(--error)", cursor: "pointer"}} onClick={onCancelAutoExec}>Cancel</button>
                        )}
                      </div>
                    )}
                  </div>
                );
              }

              if (m.executing) {
                return (
                  <div key={msg.id} className="conv-msg conv-msg-system">
                    <div style={{marginBottom: 6, fontWeight: 500, animation: "pulse 1.5s infinite"}}>Executing...</div>
                    {stepRuns.map(run => {
                      const cls = run.status === "success" ? "is-ok" : run.status === "error" ? "is-err" : "is-run";
                      const icon = run.status === "success" ? "✓" : run.status === "error" ? "✗" : "⟳";
                      return <div key={run.step_id} className={`conv-step ${cls}`}><span className="conv-step-icon">{icon}</span><span className="conv-step-name">{run.step_id}</span><span className="conv-step-time">{run.capability}</span></div>;
                    })}
                  </div>
                );
              }

              if (msg.content === "result" && m.execution) {
                const ex = m.execution;
                const allRuns = ex.step_runs || [];
                const shownOutputs = new Set();
                return (
                  <div key={msg.id} className="conv-msg conv-msg-system">
                    {ex.status === "success" ? (
                      <div>
                        <div style={{color: "var(--success)", fontWeight: 500, marginBottom: 8}}>✓ Done in {ex.duration_ms}ms</div>
                        {allRuns.map(r => {
                          const outKey = r.final_output ? JSON.stringify(r.final_output) : "";
                          const isDup = outKey && shownOutputs.has(outKey);
                          if (outKey) shownOutputs.add(outKey);
                          return (
                            <div key={r.step_id}>
                              <div className="conv-step is-ok"><span className="conv-step-icon">✓</span><span className="conv-step-name">{r.step_id} <span style={{color: "var(--text-muted)"}}>→ {r.capability}</span></span></div>
                              {!isDup && r.final_output && Object.keys(r.final_output).length > 0 && <OutputRenderer output={r.final_output} onNavigate={onNavigateDir}/>}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      (ex.error_message && ex.error_message.includes("contacts matching"))
                        ? renderAmbiguousContacts(ex.error_message)
                        : (
                          <div>
                            <div style={{color: "var(--error)", fontWeight: 500, marginBottom: 8}}>✗ Error in "{ex.failed_step}"</div>
                            {(ex.step_runs || []).map(r => (
                              <div key={r.step_id} className={`conv-step ${r.status === "success" ? "is-ok" : "is-err"}`}>
                                <span className="conv-step-icon">{r.status === "success" ? "✓" : "✗"}</span>
                                <span className="conv-step-name">{r.step_id}</span>
                              </div>
                            ))}
                            {ex.error_message && <div style={{color: "var(--error)", fontSize: 12, marginTop: 6}}>{ex.error_message}</div>}
                          </div>
                        )
                    )}
                  </div>
                );
              }

              return (
                <div key={msg.id} className="conv-msg conv-msg-system">
                  {typeof msg.content === "string" && msg.content.includes("\n") ? (
                    <MarkdownRenderer text={msg.content} />
                  ) : (
                    msg.content
                  )}
                  {voice && voice.ttsSupported && typeof msg.content === "string" && msg.content.length > 10 && (
                    <button
                      type="button"
                      className="voice-tts-btn"
                      onClick={() => voice.isSpeaking ? voice.stopSpeaking() : voice.speak(msg.content)}
                      title={voice.isSpeaking ? "Stop" : "Listen"}
                    >
                      {voice.isSpeaking ? "\u23F9" : "\u{1F50A}"}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
