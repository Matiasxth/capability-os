import React, { useEffect, useState } from "react";
import {
  disableIntegration, enableIntegration, getMetrics, getSettings, getSystemHealth,
  listIntegrations, restartBrowserWorker, saveSettings, testLLMConnection, validateIntegration,
  getPendingGaps, getPendingOptimizations, approveGap, rejectGap, approveOptimization, rejectOptimization, generateCapabilityForGap,
  getMCPServers, getMCPTools, addMCPServer, removeMCPServer, discoverMCPTools, installMCPTool,
  searchSemanticMemory, deleteSemanticMemory, getMemoryContext,
  analyzeGap, autoGenerateForGap, listAutoProposals, regenerateProposal, approveProposal, rejectProposal,
  getA2AAgents, addA2AAgent, removeA2AAgent, delegateA2ATask,
  listWorkspaces, addWorkspace, removeWorkspace, setDefaultWorkspace,
} from "../api";
import SettingsSidebar from "../components/SettingsSidebar";
import { useControlCenterState } from "../state/useControlCenterState";

function stDot(v){if(["ready","enabled","ok","available","success"].includes(v))return"dot-success";if(v==="running"||v==="preparing")return"dot-running";if(["error","down","not_configured","disabled"].includes(v))return"dot-error";return"dot-neutral"}

export default function ControlCenter() {
  const {activeSection,setActiveSection,settings,setSettings,health,setHealth,integrations,setIntegrations,loading,setLoading,saving,setSaving,testingConnection,setTestingConnection,llmTestResult,setLlmTestResult,message,setMessage,error,setError}=useControlCenterState();
  const [metrics,setMetrics]=useState(null);const [gaps,setGaps]=useState([]);const [optimizations,setOptimizations]=useState([]);
  const [mcpServers,setMcpServers]=useState([]);const [mcpTools,setMcpTools]=useState([]);
  const [memQuery,setMemQuery]=useState("");const [memResults,setMemResults]=useState([]);const [memContext,setMemContext]=useState(null);
  const [autoProposals,setAutoProposals]=useState([]);
  const [newSrvId,setNewSrvId]=useState("");const [newSrvTransport,setNewSrvTransport]=useState("stdio");const [newSrvCmd,setNewSrvCmd]=useState("");const [newSrvUrl,setNewSrvUrl]=useState("");
  const [a2aAgents,setA2aAgents]=useState([]);const [newAgentUrl,setNewAgentUrl]=useState("");
  const [wsData,setWsData]=useState([]);const [wsDefaultId,setWsDefaultId]=useState(null);
  const [wsName,setWsName]=useState("");const [wsPath,setWsPath]=useState("");const [wsAccess,setWsAccess]=useState("write");const [wsColor,setWsColor]=useState("#00ff88");
  const [toasts,setToasts]=useState([]);

  function toast(t,ty="success"){const id=Date.now();setToasts(p=>[...p,{id,text:t,type:ty}]);setTimeout(()=>setToasts(p=>p.filter(x=>x.id!==id)),3000)}
  async function refreshAll(){const[sR,hR,iR]=await Promise.all([getSettings(),getSystemHealth(),listIntegrations()]);setSettings(sR.settings||null);setHealth(hR);setIntegrations(iR.integrations||[])}
  async function refreshMetrics(){try{const r=await getMetrics();setMetrics(r.metrics||null)}catch{}}
  async function refreshSI(){try{const[g,o]=await Promise.all([getPendingGaps(),getPendingOptimizations()]);setGaps(g.gaps||[]);setOptimizations(o.proposals||[])}catch{}}
  async function refreshMCP(){try{const[s,t]=await Promise.all([getMCPServers(),getMCPTools()]);setMcpServers(s.servers||[]);setMcpTools(t.tools||[])}catch{}}
  async function refreshA2A(){try{const r=await getA2AAgents();setA2aAgents(r.agents||[])}catch{}}
  async function refreshMemory(){try{const r=await getMemoryContext();setMemContext(r.context||null)}catch{}}
  async function refreshAutoGrowth(){try{const[g,p]=await Promise.all([getPendingGaps(),listAutoProposals()]);setGaps(g.gaps||[]);setAutoProposals(p.proposals||[])}catch{}}
  async function refreshWorkspaces(){try{const r=await listWorkspaces();setWsData(r.workspaces||[]);setWsDefaultId(r.default_id||null)}catch{}}

  useEffect(()=>{let o=false;(async()=>{setLoading(true);setError("");try{await refreshAll();await refreshWorkspaces()}catch(e){if(!o)setError(e.payload?.error_message||e.message||"Load failed.")}finally{if(!o)setLoading(false)}})();return()=>{o=true}},[]);
  useEffect(()=>{
    if(activeSection==="metrics"){refreshMetrics();const id=setInterval(refreshMetrics,30000);return()=>clearInterval(id)}
    if(activeSection==="self-improvement")refreshSI();
    if(activeSection==="auto-growth")refreshAutoGrowth();
    if(activeSection==="memory")refreshMemory();
    if(activeSection==="a2a")refreshA2A();
    if(activeSection==="mcp")refreshMCP();
    if(activeSection==="workspaces")refreshWorkspaces();
  },[activeSection]);

  async function act(fn,msg){setSaving(true);setError("");setMessage("");try{await fn();toast(msg);await refreshAll()}catch(e){setError(e.payload?.error_message||e.message||"Failed.")}finally{setSaving(false)}}

  const llm=health?.llm||{};const bw=health?.browser_worker||{};const tr=bw.transport||{};
  const bwSt=bw.status||(tr.alive?"ready":tr.worker_failed?"error":"available");

  function KPI(){return(<div className="kpi-grid" style={{gridTemplateColumns:"repeat(4,1fr)",marginBottom:10}}>
    <div className="kpi-card"><div style={{display:"flex",alignItems:"center",gap:5,marginBottom:1}}><span className="dot dot-success"/><span className="kpi-label">API</span></div><div className="kpi-value accent" style={{fontSize:14}}>Online</div></div>
    <div className="kpi-card"><div style={{display:"flex",alignItems:"center",gap:5,marginBottom:1}}><span className={`dot ${stDot(bwSt)}`}/><span className="kpi-label">Browser</span></div><div className="kpi-value" style={{fontSize:14}}>{bwSt}</div></div>
    <div className="kpi-card"><div style={{display:"flex",alignItems:"center",gap:5,marginBottom:1}}><span className={`dot ${stDot(llm.status||"unknown")}`}/><span className="kpi-label">LLM</span></div><div className="kpi-value" style={{fontSize:12}}>{llm.provider||"—"}</div></div>
    <div className="kpi-card"><div style={{display:"flex",alignItems:"center",gap:5,marginBottom:1}}><span className="dot dot-success"/><span className="kpi-label">Workspaces</span></div><div className="kpi-value" style={{fontSize:14}}>{wsData.length}</div></div>
  </div>)}

  function renderSystem(){return(<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>System</h2>
    {Array.isArray(health?.issues)&&health.issues.length>0&&<div style={{background:"var(--warning-dim)",border:"1px solid rgba(255,170,0,0.12)",borderRadius:"var(--radius-md)",padding:6}}>{health.issues.map((s,i)=><p key={i} style={{fontSize:11,color:"var(--warning)",margin:"1px 0"}}>{s}</p>)}</div>}
    <div className="kpi-grid" style={{gridTemplateColumns:"1fr 1fr 1fr"}}>
      <div className="kpi-card"><div className="kpi-label">Integrations</div><div className="kpi-value">{integrations.filter(i=>i.status==="enabled").length}/{integrations.length}</div></div>
      <div className="kpi-card"><div className="kpi-label">Model</div><div style={{fontSize:11,marginTop:2}}>{llm.model||"-"}</div></div>
      <div className="kpi-card"><div className="kpi-label">Sessions</div><div className="kpi-value">{Array.isArray(bw.known_sessions)?bw.known_sessions.length:0}</div></div>
    </div>
    {bwSt==="error"&&<button onClick={()=>act(()=>restartBrowserWorker(),"Restarted")}>Restart Worker</button>}
  </div>)}

  const colors=["#00ff88","#5588ff","#ffaa00","#ff4444","#aa66ff","#ff88aa"];
  function renderWorkspaces(){return(<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Workspaces</h2>
    {wsData.map(w=><div key={w.id} className="item-row"><div className="item-row-info"><div style={{display:"flex",alignItems:"center",gap:5}}><span className="dot" style={{background:w.color||"#00ff88"}}/><span style={{fontWeight:500,fontSize:12}}>{w.name}</span>{w.id===wsDefaultId&&<span className="badge badge-success">default</span>}<span className="badge badge-neutral">{w.access==="write"?"✏️":"👁️"}</span></div><div className="dim" style={{fontSize:10,marginTop:1}}>{w.path}</div></div><div className="item-row-actions">{w.id!==wsDefaultId&&<button style={{fontSize:10,height:22}} onClick={()=>act(async()=>{await setDefaultWorkspace(w.id);await refreshWorkspaces()},"Default set")}>Default</button>}<button className="btn-danger" style={{fontSize:10,height:22}} onClick={()=>act(async()=>{await removeWorkspace(w.id);await refreshWorkspaces()},"Removed")}>✕</button></div></div>)}
    {wsData.length===0&&<p className="dim" style={{fontSize:11}}>No workspaces.</p>}
    <h4>Add</h4>
    <form onSubmit={async e=>{e.preventDefault();await act(async()=>{await addWorkspace(wsName,wsPath,wsAccess,"*",wsColor);await refreshWorkspaces()},"Added");setWsName("");setWsPath("")}} style={{display:"flex",flexDirection:"column",gap:5}}>
      <div className="form-grid">
        <div className="form-group"><label className="form-label">Name</label><input value={wsName} onChange={e=>setWsName(e.target.value)} placeholder="My Project" required/></div>
        <div className="form-group"><label className="form-label">Path</label><input value={wsPath} onChange={e=>setWsPath(e.target.value)} placeholder="C:\projects\app" required/></div>
        <div className="form-group"><label className="form-label">Access</label><select value={wsAccess} onChange={e=>setWsAccess(e.target.value)}><option value="write">Write</option><option value="read">Read</option><option value="none">None</option></select></div>
        <div className="form-group"><label className="form-label">Color</label><div style={{display:"flex",gap:3}}>{colors.map(c=><button key={c} type="button" style={{width:18,height:18,borderRadius:3,background:c,border:wsColor===c?"2px solid white":"2px solid transparent",padding:0,cursor:"pointer"}} onClick={()=>setWsColor(c)}/>)}</div></div>
      </div>
      <button type="submit" className="btn-primary" disabled={!wsName||!wsPath}>Add Workspace</button>
    </form>
  </div>)}

  const _PRESETS={groq:{label:"Groq",provider:"openai",base_url:"https://api.groq.com/openai/v1",models:["llama-3.1-70b-versatile","llama-3.1-8b-instant","mixtral-8x7b-32768","gemma2-9b-it"],needsKey:true},ollama:{label:"Ollama",provider:"ollama",base_url:"http://localhost:11434",models:[],needsKey:false},openai:{label:"OpenAI",provider:"openai",base_url:"https://api.openai.com/v1",models:["gpt-4o","gpt-4o-mini","gpt-3.5-turbo"],needsKey:true},custom:{label:"Custom",provider:"openai",base_url:"",models:[],needsKey:false}};
  function _detectPreset(url){if(!url)return"ollama";if(url.includes("groq.com"))return"groq";if(url.includes("localhost:11434")||url.includes("127.0.0.1:11434"))return"ollama";if(url.includes("openai.com"))return"openai";return"custom"}
  const [llmPreset,setLlmPreset]=useState(()=>_detectPreset(settings?.llm?.base_url));
  const [showKey,setShowKey]=useState(false);
  const [llmModel,setLlmModel]=useState(settings?.llm?.model||"");
  const [llmKey,setLlmKey]=useState("");
  const [llmUrl,setLlmUrl]=useState(settings?.llm?.base_url||"");
  const llmKeyMasked=settings?.llm?.api_key&&settings.llm.api_key.includes("*");

  function renderLLM(){if(!settings)return null;const l=settings.llm||{};const P=_PRESETS[llmPreset]||_PRESETS.custom;
    function selectPreset(k){setLlmPreset(k);const p=_PRESETS[k];setLlmUrl(p.base_url);if(p.models.length)setLlmModel(p.models[0]);else setLlmModel(l.model||"");setLlmKey("")}
    function doSave(){const p=_PRESETS[llmPreset]||_PRESETS.custom;const llm={provider:p.provider,base_url:llmPreset==="custom"?llmUrl:p.base_url,model:llmModel||l.model||"",api_key:llmKey||(llmKeyMasked?l.api_key:""),timeout_ms:l.timeout_ms||30000};act(()=>saveSettings({...settings,llm}).then(r=>setSettings(r.settings||settings)),"Saved")}
    const tabStyle=(active)=>({padding:"5px 12px",fontSize:11,fontWeight:600,borderRadius:6,border:`1px solid ${active?"rgba(0,255,136,0.3)":"rgba(255,255,255,0.06)"}`,background:active?"rgba(0,255,136,0.08)":"transparent",color:active?"#00ff88":"#888",cursor:"pointer",transition:"all .12s"});
    return(<div style={{display:"flex",flexDirection:"column",gap:10}}>
      <h2>LLM Provider</h2>
      <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>{Object.entries(_PRESETS).map(([k,v])=><button key={k} style={tabStyle(llmPreset===k)} onClick={()=>selectPreset(k)}>{v.label}</button>)}</div>
      <div style={{display:"flex",flexDirection:"column",gap:6}}>
        {P.models.length>0&&<div className="form-group"><label className="form-label">Model</label><select value={llmModel} onChange={e=>setLlmModel(e.target.value)} style={{height:30}}>{P.models.map(m=><option key={m} value={m}>{m}{m==="llama-3.1-70b-versatile"?" ★":""}</option>)}</select></div>}
        {P.models.length===0&&<div className="form-group"><label className="form-label">Model</label><input value={llmModel} onChange={e=>setLlmModel(e.target.value)} placeholder={llmPreset==="ollama"?"llama3.1:8b":"model-name"}/></div>}
        {llmPreset==="custom"&&<div className="form-group"><label className="form-label">Base URL</label><input value={llmUrl} onChange={e=>setLlmUrl(e.target.value)} placeholder="https://..."/></div>}
        {(P.needsKey||llmPreset==="custom")&&<div className="form-group"><label className="form-label">API Key {llmPreset==="groq"&&<a href="https://console.groq.com/keys" target="_blank" rel="noreferrer" style={{color:"#00ff88",fontSize:10,marginLeft:4}}>Get free →</a>}</label><div style={{display:"flex",gap:4}}><input type={showKey?"text":"password"} value={llmKey} onChange={e=>setLlmKey(e.target.value)} placeholder={llmKeyMasked?"(saved — type to replace)":llmPreset==="groq"?"gsk_...":"sk-..."} style={{flex:1}}/><button style={{width:30,padding:0,fontSize:12}} onClick={()=>setShowKey(p=>!p)}>{showKey?"🙈":"👁"}</button></div></div>}
        {llmPreset==="ollama"&&<div className="form-group"><label className="form-label">URL</label><input value={llmUrl||"http://localhost:11434"} onChange={e=>setLlmUrl(e.target.value)}/></div>}
      </div>
      <div style={{display:"flex",gap:5}}>
        <button className="btn-primary" disabled={saving} onClick={doSave}>Save</button>
        <button className={testingConnection?"btn-loading":""} disabled={testingConnection} onClick={async()=>{setTestingConnection(true);try{const r=await testLLMConnection();setLlmTestResult(r);toast(r.status==="success"?`✓ ${r.model||llmModel} — ${r.latency_ms||"?"}ms`:"Failed",r.status==="success"?"success":"error")}catch(e){setError(e.message)}finally{setTestingConnection(false)}}}>Test Connection</button>
      </div>
      {llmTestResult&&<div className={`result-banner ${llmTestResult.status==="success"?"is-success":"is-error"}`} style={{fontSize:11}}>
        {llmTestResult.status==="success"?`✓ Connected — ${llmTestResult.model||llmModel} — ${llmTestResult.latency_ms||"?"}ms`:`✗ ${llmTestResult.error_message||"Connection failed"}`}
      </div>}
    </div>)}

  function renderMetrics(){if(!metrics)return<div style={{display:"flex",flexDirection:"column",gap:6}}><div className="skeleton skeleton-block"/><div className="skeleton skeleton-block"/></div>;return(<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Metrics</h2>
    <div className="kpi-grid"><div className="kpi-card"><div className="kpi-label">Success</div><div className="kpi-value" style={{color:metrics.execution_success_rate>=80?"var(--success)":"var(--error)"}}>{metrics.execution_success_rate}%</div></div><div className="kpi-card"><div className="kpi-label">Avg</div><div className="kpi-value">{metrics.avg_execution_time_ms}<span className="dim" style={{fontSize:10}}>ms</span></div></div><div className="kpi-card"><div className="kpi-label">Fail</div><div className="kpi-value">{metrics.tool_failure_rate}%</div></div><div className="kpi-card"><div className="kpi-label">Total</div><div className="kpi-value">{metrics.total_executions}</div></div></div>
    {Object.keys(metrics.error_rate_by_capability||{}).length>0&&Object.entries(metrics.error_rate_by_capability).sort((a,b)=>b[1]-a[1]).slice(0,3).map(([c,n])=><div key={c} className="item-row"><span className="mono" style={{fontSize:10}}>{c}</span><span className="badge badge-error">{n}</span></div>)}
  </div>)}

  function renderSI(){return(<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Optimize</h2>
    <h4>Gaps {gaps.length>0&&<span className="badge badge-warning" style={{marginLeft:3}}>{gaps.length}</span>}</h4>
    {gaps.length===0&&<p className="dim" style={{fontSize:11}}>None.</p>}
    {gaps.map(g=><div key={g.capability_id} className="item-row"><div className="item-row-info"><span className="mono" style={{fontSize:10}}>{g.capability_id}</span></div><div className="item-row-actions"><button className="btn-primary" style={{fontSize:10,padding:"1px 6px",height:20}} onClick={()=>act(()=>generateCapabilityForGap(g.gap_ids[0]),"Gen")}>Gen</button><button className="btn-ghost" style={{fontSize:10,height:20}} onClick={()=>act(()=>rejectGap(g.gap_ids[0]),"OK")}>✕</button></div></div>)}
    <h4>Optimizations {optimizations.length>0&&<span className="badge badge-info" style={{marginLeft:3}}>{optimizations.length}</span>}</h4>
    {optimizations.map(o=><div key={o.id} className="card" style={{padding:7}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><span className="mono" style={{fontSize:10}}>{o.capability_id} <span className="badge badge-neutral">{o.suggestion_type}</span></span><div style={{display:"flex",gap:3}}><button className="btn-primary" style={{fontSize:10,padding:"1px 6px",height:20}} onClick={()=>act(()=>approveOptimization(o.id,o.proposed_contract),"OK")}>✓</button><button className="btn-ghost" style={{fontSize:10,height:20}} onClick={()=>act(()=>rejectOptimization(o.id),"OK")}>✕</button></div></div></div>)}
  </div>)}

  function renderAutoGrowth(){const sb=s=>({existing_tool:"badge-success",browser:"badge-info",cli:"badge-info",python:"badge-warning",nodejs:"badge-warning",not_implementable:"badge-error"}[s]||"badge-neutral");return(<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Auto-Growth</h2>
    {gaps.length>0&&gaps.map(g=><div key={g.capability_id} className="card" style={{padding:7}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><span className="mono" style={{fontSize:10}}>{g.capability_id} <span className="dim">({g.frequency}x)</span></span><div style={{display:"flex",gap:3}}><button style={{fontSize:10,height:20}} onClick={()=>act(async()=>{const r=await analyzeGap(g.gap_ids[0]);toast(`${r.analysis?.strategy}`)},"OK")}>?</button><button className="btn-primary" style={{fontSize:10,padding:"1px 6px",height:20}} onClick={()=>act(async()=>{await autoGenerateForGap(g.gap_ids[0]);await refreshAutoGrowth()},"Gen")}>Gen</button></div></div></div>)}
    {autoProposals.length>0&&<h4>Proposals</h4>}
    {autoProposals.map(p=><div key={p.proposal_id} className="card" style={{padding:7}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><div><span className={`badge ${sb(p.strategy)}`}>{p.strategy}</span><span className="mono" style={{marginLeft:4,fontSize:10}}>{p.contract?.id||p.proposal_id}</span>{p.validated&&<span className="badge badge-success" style={{marginLeft:3}}>✓</span>}</div><div style={{display:"flex",gap:3}}>{p.validated&&<button className="btn-primary" style={{fontSize:10,padding:"1px 6px",height:20}} onClick={()=>act(async()=>{await approveProposal(p.proposal_id);await refreshAutoGrowth()},"OK")}>Install</button>}<button style={{fontSize:10,height:20}} onClick={()=>act(async()=>{await regenerateProposal(p.proposal_id);await refreshAutoGrowth()},"OK")}>↻</button><button className="btn-ghost" style={{fontSize:10,height:20}} onClick={()=>act(async()=>{await rejectProposal(p.proposal_id);await refreshAutoGrowth()},"OK")}>✕</button></div></div>
      {p.code&&<details style={{marginTop:3}}><summary style={{cursor:"pointer",fontSize:10,color:"var(--text-muted)"}}>{p.runtime} code</summary><pre style={{marginTop:3,maxHeight:140,overflow:"auto"}}>{p.code}</pre></details>}
    </div>)}
  </div>)}

  function renderMCP(){return(<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>MCP</h2>
    <form onSubmit={async e=>{e.preventDefault();const c={id:newSrvId,transport:newSrvTransport};if(newSrvTransport==="stdio")c.command=newSrvCmd.split(/\s+/);else c.url=newSrvUrl;await act(()=>addMCPServer(c),"Added");setNewSrvId("");setNewSrvCmd("");setNewSrvUrl("");await refreshMCP()}} style={{display:"flex",flexDirection:"column",gap:5}}>
      <div style={{display:"flex",gap:5}}><input placeholder="ID" value={newSrvId} onChange={e=>setNewSrvId(e.target.value)} required style={{flex:1}}/><select value={newSrvTransport} onChange={e=>setNewSrvTransport(e.target.value)} style={{width:70}}><option value="stdio">stdio</option><option value="http">http</option></select></div>
      {newSrvTransport==="stdio"&&<input placeholder="Command" value={newSrvCmd} onChange={e=>setNewSrvCmd(e.target.value)} required/>}
      {newSrvTransport==="http"&&<input placeholder="URL" value={newSrvUrl} onChange={e=>setNewSrvUrl(e.target.value)} required/>}
      <button type="submit" className="btn-primary" disabled={!newSrvId}>Add</button>
    </form>
    {mcpServers.map(s=><div key={s.server_id} className="item-row"><div className="item-row-info"><span className={`dot ${s.connected?"dot-success":"dot-error"}`} style={{marginRight:3}}/><span className="mono" style={{fontSize:10}}>{s.server_id}</span></div><div className="item-row-actions"><button style={{fontSize:10,height:20}} onClick={()=>act(async()=>{await discoverMCPTools(s.server_id);await refreshMCP()},"OK")}>Disc</button><button className="btn-danger" style={{fontSize:10,height:20}} onClick={()=>act(async()=>{await removeMCPServer(s.server_id);await refreshMCP()},"OK")}>✕</button></div></div>)}
    {mcpTools.map(t=><div key={t.tool_id} className="item-row"><span className="mono" style={{fontSize:10,flex:1}}>{t.tool_id}</span><button style={{fontSize:10,height:20}} onClick={()=>act(()=>installMCPTool(t.tool_id),"OK")}>Install</button></div>)}
  </div>)}

  function renderA2A(){return(<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>A2A</h2>
    <form onSubmit={async e=>{e.preventDefault();await act(async()=>{await addA2AAgent(newAgentUrl);await refreshA2A()},"Added");setNewAgentUrl("")}} style={{display:"flex",gap:5}}>
      <input placeholder="URL" value={newAgentUrl} onChange={e=>setNewAgentUrl(e.target.value)} required style={{flex:1}}/>
      <button type="submit" className="btn-primary" disabled={!newAgentUrl}>Add</button>
    </form>
    {a2aAgents.map(a=><div key={a.id} className="item-row"><span className={`dot ${a.status==="reachable"?"dot-success":"dot-error"}`} style={{marginRight:3}}/><span style={{fontSize:11,flex:1}}>{a.name||a.id}</span><button className="btn-danger" style={{fontSize:10,height:20}} onClick={()=>act(async()=>{await removeA2AAgent(a.id);await refreshA2A()},"OK")}>✕</button></div>)}
  </div>)}

  function renderMemory(){const ctx=memContext||{};return(<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Memory</h2>
    <form onSubmit={async e=>{e.preventDefault();if(!memQuery.trim())return;try{setMemResults((await searchSemanticMemory(memQuery,5)).results||[])}catch{}}} style={{display:"flex",gap:5}}>
      <input placeholder="Search..." value={memQuery} onChange={e=>setMemQuery(e.target.value)} style={{flex:1}}/>
      <button type="submit" className="btn-primary" disabled={!memQuery.trim()}>Go</button>
    </form>
    {memResults.map((r,i)=><div key={r.memory?.id||i} className="item-row"><span className="badge badge-info" style={{fontSize:9}}>{Math.round(r.score*100)}%</span><span style={{fontSize:11,flex:1,marginLeft:4}}>{r.text}</span><button className="btn-danger" style={{fontSize:10,height:20}} onClick={()=>act(async()=>{await deleteSemanticMemory(r.memory?.id);setMemResults((await searchSemanticMemory(memQuery,5)).results||[])},"OK")}>✕</button></div>)}
    <div className="kpi-grid" style={{gridTemplateColumns:"1fr 1fr 1fr"}}><div className="kpi-card"><div className="kpi-label">Lang</div><div style={{fontSize:11,marginTop:1}}>{ctx.preferred_language||"-"}</div></div><div className="kpi-card"><div className="kpi-label">Top</div><div style={{fontSize:9,marginTop:1}}>{(ctx.frequent_capabilities||[]).slice(0,3).join(", ")||"-"}</div></div><div className="kpi-card"><div className="kpi-label">Prefs</div><div style={{fontSize:11,marginTop:1}}>{Object.keys(ctx.custom_preferences||{}).length}</div></div></div>
  </div>)}

  function renderIntegrations(){return(<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Integrations</h2>
    {integrations.map(i=><div key={i.id} className="item-row"><div className="item-row-info"><span className={`dot ${stDot(i.status)}`} style={{marginRight:3}}/><span style={{fontSize:11,fontWeight:500}}>{i.name||i.id}</span><span className="dim" style={{fontSize:10,marginLeft:3}}>{i.status}</span></div><div className="item-row-actions"><button style={{fontSize:10,height:20}} onClick={()=>act(()=>validateIntegration(i.id),"OK")}>Val</button>{i.status!=="enabled"?<button className="btn-primary" style={{fontSize:10,padding:"1px 6px",height:20}} onClick={()=>act(()=>enableIntegration(i.id),"OK")}>On</button>:<button style={{fontSize:10,height:20}} onClick={()=>act(()=>disableIntegration(i.id),"OK")}>Off</button>}</div></div>)}
  </div>)}

  function renderBrowser(){return(<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Browser</h2>
    <div className="kpi-grid" style={{gridTemplateColumns:"1fr 1fr 1fr"}}><div className="kpi-card"><div className="kpi-label">Status</div><div style={{display:"flex",alignItems:"center",gap:3,marginTop:1}}><span className={`dot ${stDot(bwSt)}`}/><span style={{fontSize:11}}>{bwSt}</span></div></div><div className="kpi-card"><div className="kpi-label">Sessions</div><div className="kpi-value" style={{fontSize:14}}>{Array.isArray(bw.known_sessions)?bw.known_sessions.length:0}</div></div><div className="kpi-card"><div className="kpi-label">Active</div><div className="mono" style={{fontSize:9,marginTop:1}}>{bw.active_session_id||"-"}</div></div></div>
    {tr.dead_reason&&<div className="result-banner is-error" style={{fontSize:10}}>{tr.dead_reason}</div>}
    <button onClick={()=>act(()=>restartBrowserWorker(),"Restarted")} disabled={saving}>Restart</button>
  </div>)}

  const R={system:renderSystem,workspaces:renderWorkspaces,llm:renderLLM,metrics:renderMetrics,"self-improvement":renderSI,"auto-growth":renderAutoGrowth,mcp:renderMCP,a2a:renderA2A,memory:renderMemory,integrations:renderIntegrations,browser:renderBrowser};

  return (<div className="cc-layout">
    <SettingsSidebar activeSection={activeSection} onSelectSection={setActiveSection}/>
    <div className="cc-content">
      <KPI/>
      {message&&<div className="status-banner success">{message}</div>}
      {error&&<div className="status-banner error">{error}</div>}
      {loading?<div style={{display:"flex",flexDirection:"column",gap:6}}><div className="skeleton skeleton-block"/><div className="skeleton skeleton-block"/></div>:(R[activeSection]||renderSystem)()}
    </div>
    <div className="toast-container">{toasts.map(t=><div key={t.id} className={`toast toast-${t.type}`}>{t.text}</div>)}</div>
  </div>);
}
