import React, { useEffect, useState } from "react";
import sdk from "../../../sdk";

export default function SupervisorSection({ toast }) {
  const [svStatus, setSvStatus] = useState(null);
  const [svLog, setSvLog] = useState([]);
  const [svPrompt, setSvPrompt] = useState("");
  const [svResponse, setSvResponse] = useState("");
  const [svChat, setSvChat] = useState([]);
  const [svAsking, setSvAsking] = useState(false);

  useEffect(() => {
    sdk.system.supervisor.status().then(setSvStatus).catch(() => {});
    sdk.system.supervisor.log().then(r => setSvLog(r.log || [])).catch(() => {});
  }, []);

  const sv = svStatus || {};
  const h = sv.health || {};
  const cl = sv.claude || {};
  const errs = sv.errors || {};

  return (
    <div style={{display:"flex",flexDirection:"column",gap:12}}>
      <h2>Supervisor</h2>

      <div className="kpi-grid" style={{gridTemplateColumns:"1fr 1fr 1fr 1fr"}}>
        <div className="kpi-card"><div className="kpi-label">Status</div><div style={{display:"flex",alignItems:"center",gap:4}}><span className={`dot ${sv.running?"dot-success":"dot-error"}`}/><span style={{fontSize:13,fontWeight:600}}>{sv.running?"Active":"Off"}</span></div></div>
        <div className="kpi-card"><div className="kpi-label">Health</div><div style={{display:"flex",alignItems:"center",gap:4}}><span className={`dot ${h.status==="healthy"?"dot-success":h.status==="degraded"?"dot-warning":"dot-error"}`}/><span style={{fontSize:13,fontWeight:600}}>{h.status||"unknown"}</span></div></div>
        <div className="kpi-card"><div className="kpi-label">Claude</div><div style={{fontSize:13,fontWeight:600}}>{cl.available?`Ready (${cl.invocations||0}/hr)`:"Not found"}</div></div>
        <div className="kpi-card"><div className="kpi-label">Errors</div><div style={{fontSize:13,fontWeight:600}}>{Object.values(errs.summary||{}).reduce((a,b)=>a+b,0)||0} total</div></div>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
        <div className="card" style={{padding:14}}>
          <h4 style={{margin:"0 0 10px",fontSize:13}}>Health Checks</h4>
          {(h.checks||[]).map((c,i) => <div key={i} style={{display:"flex",alignItems:"center",gap:8,fontSize:13,padding:"6px 0",borderBottom:"1px solid var(--border)"}}>
            <span className={`dot ${c.ok?"dot-success":"dot-error"}`}/>
            <span style={{flex:1,fontWeight:500}}>{c.check.replace(/_/g," ")}</span>
            <span style={{fontSize:11,color:c.ok?"var(--success)":"var(--error)"}}>{c.ok?"OK":"FAIL"}</span>
          </div>)}
          <button style={{marginTop:10,height:32,fontSize:12,width:"100%"}} onClick={() => sdk.system.supervisor.healthCheck().then(r => { setSvStatus(s => ({...s, health:{...s?.health, checks:r.checks, status:r.status}})); toast("Health: "+r.status) }).catch(() => {})}>Run Health Check Now</button>
        </div>

        <div className="card" style={{padding:14}}>
          <h4 style={{margin:"0 0 10px",fontSize:13}}>Recent Interventions</h4>
          <div style={{maxHeight:250,overflowY:"auto"}}>
            {svLog.length===0 && <div style={{color:"var(--text-muted)",padding:16,textAlign:"center",fontSize:13}}>No interventions yet</div>}
            {svLog.map((e,i) => <div key={i} style={{padding:"6px 0",borderBottom:"1px solid var(--border)",fontSize:12,display:"flex",gap:8}}>
              <span style={{color:"var(--text-muted)",flexShrink:0,fontSize:11}}>{(e.timestamp||"").slice(11,19)}</span>
              <span style={{color:e.severity==="high"?"var(--error)":e.severity==="medium"?"var(--warning)":"var(--text-dim)",fontWeight:600,flexShrink:0}}>{(e.severity||e.action||"info").toUpperCase()}</span>
              <span style={{flex:1,color:"var(--text)"}}>{(e.message||e.diagnosis||e.context||"").slice(0,120)}</span>
            </div>)}
          </div>
        </div>
      </div>

      <div className="card" style={{padding:16}}>
        <h4 style={{margin:"0 0 12px",fontSize:14}}>Chat with Claude Supervisor</h4>
        <div style={{background:"var(--bg-root)",borderRadius:10,border:"1px solid var(--border)",minHeight:300,maxHeight:450,overflowY:"auto",padding:14,marginBottom:12,display:"flex",flexDirection:"column",gap:8}}>
          {svChat.length===0 && <div style={{color:"var(--text-muted)",textAlign:"center",padding:40,fontSize:13}}>Ask Claude to analyze your system, diagnose issues, or suggest improvements.</div>}
          {svChat.map((m,i) => {
            // Action cards for previews
            if (m.role==="action" && m.data) {
              const d = m.data;
              const pid = d.preview_id;
              if (d.type==="skill_preview") return (
                <div key={i} style={{alignSelf:"flex-start",maxWidth:"90%",padding:14,borderRadius:12,background:"var(--bg-elevated)",border:"1px solid var(--accent)",fontSize:12}}>
                  <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:8}}><span style={{fontSize:18}}>{"\u{1f527}"}</span><span style={{fontWeight:700,fontSize:14}}>New Skill: {d.spec?.name||d.spec?.tool_id}</span></div>
                  <div style={{color:"var(--text-dim)",marginBottom:6}}>{d.spec?.description}</div>
                  {d.spec?.handler_code && <pre style={{background:"var(--bg-root)",padding:8,borderRadius:6,fontSize:10,maxHeight:150,overflow:"auto",whiteSpace:"pre-wrap",marginBottom:6}}>{d.spec.handler_code}</pre>}
                  <div style={{fontSize:10,marginBottom:8,color:d.validation?.valid?"var(--success)":"var(--error)"}}>{d.validation?.valid?"\u2705 Code valid":"\u274C "+((d.validation?.errors||[]).join(", "))}</div>
                  {!m.resolved && <div style={{display:"flex",gap:6}}>
                    <button className="btn-primary" style={{height:28,fontSize:11}} onClick={async () => { try { const r = await sdk.system.supervisor.approve(pid); setSvChat(c => c.map((x,j) => j===i?{...x,resolved:true,result:r}:x)); toast(r.status==="success"?"Skill installed!":"Error: "+(r.error||"")) } catch(e) { toast(e.message,"error") } }}>Install</button>
                    <button style={{height:28,fontSize:11}} onClick={() => { sdk.system.supervisor.discard(pid); setSvChat(c => c.map((x,j) => j===i?{...x,resolved:true,result:{status:"discarded"}}:x)) }}>Discard</button>
                  </div>}
                  {m.resolved && <div style={{fontSize:11,color:m.result?.status==="success"?"var(--success)":"var(--text-muted)"}}>{m.result?.status==="success"?"\u2705 Installed":"\u274C Discarded"}</div>}
                </div>
              );
              if (d.type==="agent_preview") return (
                <div key={i} style={{alignSelf:"flex-start",maxWidth:"90%",padding:14,borderRadius:12,background:"var(--bg-elevated)",border:"1px solid var(--info)",fontSize:12}}>
                  <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:8}}><span style={{fontSize:18}}>{d.spec?.emoji||"\u{1f916}"}</span><span style={{fontWeight:700,fontSize:14}}>New Agent: {d.spec?.name}</span></div>
                  <div style={{color:"var(--text-dim)",marginBottom:4}}>{d.spec?.description}</div>
                  <div style={{fontSize:10,color:"var(--text-muted)",marginBottom:8}}>Tools: {(d.spec?.tool_ids||[]).length} | Lang: {d.spec?.language||"auto"}</div>
                  {!m.resolved && <div style={{display:"flex",gap:6}}>
                    <button className="btn-primary" style={{height:28,fontSize:11}} onClick={async () => { try { const r = await sdk.system.supervisor.approve(pid); setSvChat(c => c.map((x,j) => j===i?{...x,resolved:true,result:r}:x)); toast(r.status==="success"?"Agent created!":"Error") } catch(e) { toast(e.message,"error") } }}>Create</button>
                    <button style={{height:28,fontSize:11}} onClick={() => { sdk.system.supervisor.discard(pid); setSvChat(c => c.map((x,j) => j===i?{...x,resolved:true,result:{status:"discarded"}}:x)) }}>Discard</button>
                  </div>}
                  {m.resolved && <div style={{fontSize:11,color:m.result?.status==="success"?"var(--success)":"var(--text-muted)"}}>{m.result?.status==="success"?"\u2705 Created":"\u274C Discarded"}</div>}
                </div>
              );
              if (d.type==="config_preview" || d.type==="command_preview" || d.type==="restart_preview") return (
                <div key={i} style={{alignSelf:"flex-start",maxWidth:"90%",padding:14,borderRadius:12,background:"var(--bg-elevated)",border:"1px solid var(--warning)",fontSize:12}}>
                  <div style={{fontWeight:700,marginBottom:4}}>{d.type==="config_preview"?"\u2699\uFE0F Config Change":d.type==="command_preview"?"\u26A1 Command":"\u{1f504} Restart"}</div>
                  <div style={{color:"var(--text-dim)",marginBottom:4}}>{d.command||d.setting||d.component}: {d.new_value||d.reason||""}</div>
                  {!m.resolved && <div style={{display:"flex",gap:6}}>
                    <button className="btn-primary" style={{height:28,fontSize:11}} onClick={async () => { try { const r = await sdk.system.supervisor.approve(pid); setSvChat(c => c.map((x,j) => j===i?{...x,resolved:true,result:r}:x)); toast("Done") } catch(e) { toast(e.message,"error") } }}>Approve</button>
                    <button style={{height:28,fontSize:11}} onClick={() => { sdk.system.supervisor.discard(pid); setSvChat(c => c.map((x,j) => j===i?{...x,resolved:true,result:{status:"discarded"}}:x)) }}>Cancel</button>
                  </div>}
                  {m.resolved && <div style={{fontSize:11,color:m.result?.status==="success"?"var(--success)":"var(--text-muted)"}}>{m.result?.status==="success"?"\u2705 Applied":"\u274C Cancelled"}</div>}
                </div>
              );
              if (d.type==="diagnosis") return (
                <div key={i} style={{alignSelf:"flex-start",maxWidth:"90%",padding:14,borderRadius:12,background:"var(--bg-elevated)",border:"1px solid "+(d.analysis?.severity==="high"?"var(--error)":"var(--warning)"),fontSize:12}}>
                  <div style={{fontWeight:700,marginBottom:6}}>{"\u{1f50d}"} Diagnosis</div>
                  {d.analysis?.problem && <div><strong>Problem:</strong> {d.analysis.problem}</div>}
                  {d.analysis?.root_cause && <div><strong>Cause:</strong> {d.analysis.root_cause}</div>}
                  {d.analysis?.fix && <div><strong>Fix:</strong> {d.analysis.fix}</div>}
                </div>
              );
            }
            // Normal text messages
            return <div key={i} style={{alignSelf:m.role==="user"?"flex-end":"flex-start",maxWidth:"85%",padding:"10px 14px",borderRadius:12,fontSize:13,lineHeight:1.6,whiteSpace:"pre-wrap",
              background:m.role==="user"?"var(--accent-dim)":"var(--bg-elevated)",
              border:m.role==="user"?"1px solid var(--accent)":"1px solid var(--border)",
              color:"var(--text)",
              borderBottomRightRadius:m.role==="user"?4:12,
              borderBottomLeftRadius:m.role==="user"?12:4,
            }}>{m.content}</div>
          })}
          {svAsking && <div style={{alignSelf:"flex-start",padding:"10px 14px",borderRadius:12,background:"var(--bg-elevated)",border:"1px solid var(--border)",fontSize:13,color:"var(--text-muted)",animation:"pulse 1.5s infinite"}}>Thinking...</div>}
        </div>
        <form onSubmit={async e => { e.preventDefault(); if (!svPrompt.trim() || svAsking) return; const q = svPrompt; setSvPrompt(""); setSvChat(c => [...c,{role:"user",content:q}]); setSvAsking(true); try { const r = await sdk.system.supervisor.invoke(q); if (r.type && r.type!=="text" && r.preview_id) { setSvChat(c => [...c,{role:"action",data:r}]) } else if (r.type==="diagnosis") { setSvChat(c => [...c,{role:"action",data:r}]) } else { const resp = r.content||r.message||r.response||r.error||JSON.stringify(r); setSvChat(c => [...c,{role:"assistant",content:resp}]) } } catch(err) { setSvChat(c => [...c,{role:"assistant",content:"Error: "+err.message}]) } finally { setSvAsking(false) } }} style={{display:"flex",gap:8}}>
          <input value={svPrompt} onChange={e => setSvPrompt(e.target.value)} style={{flex:1,height:40,fontSize:14,padding:"0 14px",borderRadius:10,background:"var(--bg-input)",border:"1px solid var(--border)",color:"var(--text)",outline:"none"}} placeholder="Ask Claude about the system..." autoComplete="off"/>
          <button type="submit" disabled={svAsking||!svPrompt.trim()} style={{height:40,padding:"0 20px",fontSize:13,fontWeight:600,borderRadius:10,background:svPrompt.trim()?"var(--accent)":"var(--bg-elevated)",color:svPrompt.trim()?"var(--bg-root)":"var(--text-muted)",border:"none",cursor:svPrompt.trim()?"pointer":"not-allowed"}}>Send</button>
        </form>
      </div>
    </div>
  );
}
