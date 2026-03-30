import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  disableIntegration, enableIntegration, exportConfig, importConfig, getMetrics, getSettings, getSystemHealth,
  listIntegrations, restartBrowserWorker, saveSettings, testLLMConnection, validateIntegration, getCDPStatus, launchChrome, openWhatsApp, connectBrowserCDP, closeWhatsAppSession, getWhatsAppSessionStatus, getWhatsAppQR, startWhatsApp, getTelegramStatus, configureTelegram, testTelegram, startTelegramPolling, stopTelegramPolling, getTelegramPollingStatus,
  getPendingGaps, getPendingOptimizations, approveGap, rejectGap, approveOptimization, rejectOptimization, generateCapabilityForGap,
  getMCPServers, getMCPTools, addMCPServer, removeMCPServer, discoverMCPTools, installMCPTool, uninstallMCPTool,
  searchSemanticMemory, deleteSemanticMemory, getMemoryContext,
  analyzeGap, autoGenerateForGap, listAutoProposals, regenerateProposal, approveProposal, rejectProposal,
  getA2AAgents, addA2AAgent, removeA2AAgent, delegateA2ATask,
  listWorkspaces, addWorkspace, removeWorkspace, setDefaultWorkspace,
  listCapabilities, listSkills, installSkill, uninstallSkill,
  getSlackStatus, configureSlack, testSlack, startSlackPolling, stopSlackPolling, getSlackPollingStatus,
  getDiscordStatus, configureDiscord, testDiscord, startDiscordPolling, stopDiscordPolling, getDiscordPollingStatus,
  whatsappBridgeCheck, whatsappBridgeClose, whatsappSwitchBackend, whatsappConfigure, whatsappListBackends,
  listAgents, createAgent, updateAgentDef, deleteAgentDef, designAgent,
} from "../api";
import CCLayout from "../components/control-center/CCLayout";
import KPIBar from "../components/control-center/KPIBar";
import ToastContainer from "../components/ToastContainer";
import { useToast } from "../hooks/useToast";
import { useWebSocket } from "../hooks/useWebSocket";
import { useControlCenterState } from "../state/useControlCenterState";

function stDot(v){if(["ready","enabled","ok","available","success"].includes(v))return"dot-success";if(v==="running"||v==="preparing")return"dot-running";if(["error","down","not_configured","disabled"].includes(v))return"dot-error";return"dot-neutral"}

export default function ControlCenter() {
  const {activeSection,setActiveSection,settings,setSettings,health,setHealth,integrations,setIntegrations,loading,setLoading,saving,setSaving,testingConnection,setTestingConnection,llmTestResult,setLlmTestResult,message,setMessage,error,setError}=useControlCenterState();
  const [metrics,setMetrics]=useState(null);const [gaps,setGaps]=useState([]);const [optimizations,setOptimizations]=useState([]);
  const [mcpServers,setMcpServers]=useState([]);const [mcpTools,setMcpTools]=useState([]);const [installedTools,setInstalledTools]=useState(new Set());
  const [memQuery,setMemQuery]=useState("");const [memResults,setMemResults]=useState([]);const [memContext,setMemContext]=useState(null);
  const [autoProposals,setAutoProposals]=useState([]);
  const [newSrvId,setNewSrvId]=useState("");const [newSrvTransport,setNewSrvTransport]=useState("stdio");const [newSrvCmd,setNewSrvCmd]=useState("");const [newSrvUrl,setNewSrvUrl]=useState("");
  const [a2aAgents,setA2aAgents]=useState([]);const [newAgentUrl,setNewAgentUrl]=useState("");const [expandedAgent,setExpandedAgent]=useState(null);const [delegateResults,setDelegateResults]=useState({});const [delegatedSkills,setDelegatedSkills]=useState(new Set());
  const [wsData,setWsData]=useState([]);const [wsDefaultId,setWsDefaultId]=useState(null);
  const [wsName,setWsName]=useState("");const [wsPath,setWsPath]=useState("");const [wsAccess,setWsAccess]=useState("write");const [wsColor,setWsColor]=useState("#00ff88");
  const {toasts,addToast,removeToast}=useToast();const [cdpStatus,setCdpStatus]=useState(null);const [cdpPort,setCdpPort]=useState("");const [wspSession,setWspSession]=useState(null);const [wspQR,setWspQR]=useState(null);const [wspConnecting,setWspConnecting]=useState(false);
  const [tgStatus,setTgStatus]=useState(null);const [tgToken,setTgToken]=useState("");const [tgChatId,setTgChatId]=useState("");const [showTgToken,setShowTgToken]=useState(false);const [tgUserIds,setTgUserIds]=useState("");const [tgPolling,setTgPolling]=useState(false);const [expandedIntegration,setExpandedIntegration]=useState(null);
  const [skills,setSkills]=useState([]);const [newSkillPath,setNewSkillPath]=useState("");
  const [slackStatus,setSlackStatus]=useState(null);const [slackToken,setSlackToken]=useState("");const [slackChannel,setSlackChannel]=useState("");const [slackUserIds,setSlackUserIds]=useState("");const [slackPolling,setSlackPolling]=useState(false);const [showSlackToken,setShowSlackToken]=useState(false);
  const [discordStatus,setDiscordStatus]=useState(null);const [discordToken,setDiscordToken]=useState("");const [discordChannel,setDiscordChannel]=useState("");const [discordGuild,setDiscordGuild]=useState("");const [discordUserIds,setDiscordUserIds]=useState("");const [discordPolling,setDiscordPolling]=useState(false);const [showDiscordToken,setShowDiscordToken]=useState(false);

  function toast(t,ty="success"){addToast(t,ty)}
  async function refreshAll(){const[sR,hR,iR]=await Promise.all([getSettings(),getSystemHealth(),listIntegrations()]);setSettings(sR.settings||null);setHealth(hR);setIntegrations(iR.integrations||[])}
  async function refreshMetrics(){try{const r=await getMetrics();setMetrics(r.metrics||null)}catch{}}
  async function refreshSI(){try{const[g,o]=await Promise.all([getPendingGaps(),getPendingOptimizations()]);setGaps(g.gaps||[]);setOptimizations(o.proposals||[])}catch{}}
  async function refreshMCP(){try{const[s,t,c]=await Promise.all([getMCPServers(),getMCPTools(),listCapabilities()]);setMcpServers(s.servers||[]);setMcpTools(t.tools||[]);const capIds=new Set((c.capabilities||[]).map(x=>x.id||x));const inst=new Set();(t.tools||[]).forEach(tool=>{if(capIds.has(tool.tool_id)||capIds.has("mcp_"+tool.tool_id))inst.add(tool.tool_id)});setInstalledTools(inst)}catch{}}
  async function refreshA2A(){try{const r=await getA2AAgents();setA2aAgents(r.agents||[])}catch{}}
  async function refreshMemory(){try{const r=await getMemoryContext();setMemContext(r.context||null)}catch{}}
  async function refreshAutoGrowth(){try{const[g,p]=await Promise.all([getPendingGaps(),listAutoProposals()]);setGaps(g.gaps||[]);setAutoProposals(p.proposals||[])}catch{}}
  async function refreshWorkspaces(){try{const r=await listWorkspaces();setWsData(r.workspaces||[]);setWsDefaultId(r.default_id||null)}catch{}}
  async function refreshSkills(){try{const r=await listSkills();setSkills(r.skills||[])}catch{}}

  // ── WebSocket real-time updates ──
  const SECTION_FOR_EVENT={settings_updated:"llm",config_imported:"system",workspace_changed:"workspaces",growth_update:"self-improvement",integration_changed:"integrations",mcp_changed:"mcp",a2a_changed:"a2a",browser_changed:"browser",memory_cleared:"memory",preferences_updated:"memory"};
  const REFRESH_MAP={system:refreshAll,llm:refreshAll,workspaces:refreshWorkspaces,"self-improvement":refreshSI,"auto-growth":refreshAutoGrowth,mcp:refreshMCP,a2a:refreshA2A,memory:refreshMemory,integrations:refreshAll,browser:()=>getCDPStatus().then(setCdpStatus).catch(()=>{})};
  const WS_LABELS={settings_updated:"Settings updated",config_imported:"Config imported",workspace_changed:"Workspace updated",growth_update:"Growth updated",integration_changed:"Integration updated",mcp_changed:"MCP updated",a2a_changed:"A2A updated",browser_changed:"Browser updated",memory_cleared:"Memory cleared",preferences_updated:"Preferences saved"};
  const [highlightSection,setHighlightSection]=useState(null);
  const highlightTimer=useRef(null);
  const handleWsEvent=useCallback((event)=>{
    if(!event||!event.type)return;
    const section=SECTION_FOR_EVENT[event.type];
    if(section){
      toast(WS_LABELS[event.type]+(event.data?.action?" — "+event.data.action:""),"info");
      if(section===activeSection){const fn=REFRESH_MAP[section];if(fn)fn()}
      setHighlightSection(section);
      if(highlightTimer.current)clearTimeout(highlightTimer.current);
      highlightTimer.current=setTimeout(()=>setHighlightSection(null),3000);
    }
    if(event.type==="error"&&event.data?.message){toast("Error: "+event.data.message.slice(0,80),"error")}
  },[activeSection]);
  const{connected:wsConnected}=useWebSocket(handleWsEvent);

  useEffect(()=>{let o=false;(async()=>{setLoading(true);setError("");try{await refreshAll();await refreshWorkspaces()}catch(e){if(!o)setError(e.payload?.error_message||e.message||"Load failed.")}finally{if(!o)setLoading(false)}})();return()=>{o=true}},[]);
  useEffect(()=>{
    if(activeSection==="metrics"){refreshMetrics();const id=setInterval(refreshMetrics,30000);return()=>clearInterval(id)}
    if(activeSection==="self-improvement")refreshSI();
    if(activeSection==="auto-growth")refreshAutoGrowth();
    if(activeSection==="memory")refreshMemory();
    if(activeSection==="a2a")refreshA2A();
    if(activeSection==="mcp")refreshMCP();
    if(activeSection==="workspaces")refreshWorkspaces();
    if(activeSection==="skills")refreshSkills();
    if(activeSection==="browser"){getCDPStatus().then(r=>setCdpStatus(r)).catch(()=>setCdpStatus({connected:false,tabs:0,port:9222}))}
    if(activeSection==="integrations"){getWhatsAppSessionStatus().then(r=>{setWspSession(r);if(r.active)setWspQR(null)}).catch(()=>setWspSession({active:false}));getTelegramStatus().then(r=>{setTgStatus(r);if(r.allowed_user_ids)setTgUserIds(r.allowed_user_ids.join(", "))}).catch(()=>setTgStatus({configured:false}));getTelegramPollingStatus().then(r=>setTgPolling(r.running)).catch(()=>{});getSlackStatus().then(r=>{setSlackStatus(r);if(r.allowed_user_ids)setSlackUserIds(r.allowed_user_ids.join(", "))}).catch(()=>setSlackStatus({configured:false}));getSlackPollingStatus().then(r=>setSlackPolling(r.running)).catch(()=>{});getDiscordStatus().then(r=>{setDiscordStatus(r);if(r.allowed_user_ids)setDiscordUserIds(r.allowed_user_ids.join(", "))}).catch(()=>setDiscordStatus({configured:false}));getDiscordPollingStatus().then(r=>setDiscordPolling(r.running)).catch(()=>{})}
  },[activeSection]);

  // Poll for WhatsApp auth when QR is visible (supports both Baileys and browser bridge)
  useEffect(()=>{if(!wspQR)return;const id=setInterval(()=>{whatsappBridgeCheck().then(r=>{if(r.connected||r.status==="connected"){setWspQR(null);setWspSession({active:true});toast("WhatsApp connected")}else if(r.qr_image){setWspQR(r.qr_image)}}).catch(()=>{});getWhatsAppSessionStatus().then(r=>{setWspSession(r);if(r.active){setWspQR(null);toast("WhatsApp connected")}}).catch(()=>{})},3000);return()=>clearInterval(id)},[wspQR]);

  async function act(fn,msg){setSaving(true);setError("");setMessage("");try{await fn();toast(msg);await refreshAll();if(activeSection==="self-improvement")await refreshSI();if(activeSection==="auto-growth")await refreshAutoGrowth();if(activeSection==="mcp")await refreshMCP();if(activeSection==="a2a")await refreshA2A();if(activeSection==="memory")await refreshMemory();if(activeSection==="workspaces")await refreshWorkspaces()}catch(e){setError(e.payload?.error_message||e.message||"Failed.")}finally{setSaving(false)}}

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
    <div style={{display:"flex",gap:5,marginTop:4}}>
      <button style={{flex:1,fontSize:11,height:26}} onClick={async()=>{try{const d=await exportConfig();const blob=new Blob([JSON.stringify(d,null,2)],{type:"application/json"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="capos-config.json";a.click();URL.revokeObjectURL(url);toast("Config exported")}catch(e){toast(e.message,"error")}}}>Export Config</button>
      <button style={{flex:1,fontSize:11,height:26}} onClick={()=>{const inp=document.createElement("input");inp.type="file";inp.accept=".json";inp.onchange=async e=>{const f=e.target.files[0];if(!f)return;try{const txt=await f.text();const data=JSON.parse(txt);await importConfig(data);toast("Config imported");await refreshAll()}catch(err){toast(err.message,"error")}};inp.click()}}>Import Config</button>
    </div>
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
    {mcpTools.map(t=><div key={t.tool_id} className="item-row"><span className="mono" style={{fontSize:10,flex:1}}>{t.tool_id}</span>{installedTools.has(t.tool_id)?<div style={{display:"flex",gap:3}}><button disabled style={{fontSize:10,height:20,opacity:0.6,cursor:"default",background:"transparent",border:"1px solid var(--accent)",color:"var(--accent)",borderRadius:4,padding:"0 6px"}}>✓</button><button className="btn-danger" style={{fontSize:10,height:20,padding:"0 6px"}} onClick={()=>act(async()=>{await uninstallMCPTool(t.tool_id);setInstalledTools(p=>{const n=new Set(p);n.delete(t.tool_id);return n})},"Uninstalled")}>✕</button></div>:<button style={{fontSize:10,height:20}} onClick={()=>act(async()=>{await installMCPTool(t.tool_id);setInstalledTools(p=>new Set([...p,t.tool_id]))},"Installed")}>Install</button>}</div>)}
  </div>)}

  function renderA2A(){return(<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>A2A</h2>
    <form onSubmit={async e=>{e.preventDefault();await act(async()=>{await addA2AAgent(newAgentUrl);await refreshA2A()},"Added");setNewAgentUrl("")}} style={{display:"flex",gap:5}}>
      <input placeholder="Agent URL (e.g. http://localhost:8001)" value={newAgentUrl} onChange={e=>setNewAgentUrl(e.target.value)} required style={{flex:1}}/>
      <button type="submit" className="btn-primary" disabled={!newAgentUrl}>Add</button>
    </form>
    {a2aAgents.map(a=><div key={a.id} className="card" style={{padding:0,overflow:"hidden"}}>
      <div className="item-row" style={{cursor:"pointer",padding:"8px 10px"}} onClick={()=>{setExpandedAgent(expandedAgent===a.id?null:a.id);setDelegateResults({})}}>
        <span className={`dot ${a.status==="reachable"?"dot-success":"dot-error"}`} style={{marginRight:3}}/>
        <span style={{fontSize:11,flex:1,fontWeight:500}}>{a.name||a.id}</span>
        <span style={{fontSize:10,color:"var(--text-muted)",marginRight:4}}>{Array.isArray(a.skills)?a.skills.length:0} skills</span>
        <button className="btn-danger" style={{fontSize:10,height:20}} onClick={e=>{e.stopPropagation();act(async()=>{await removeA2AAgent(a.id);setExpandedAgent(null);await refreshA2A()},"Removed")}}>✕</button>
      </div>
      {expandedAgent===a.id&&<div style={{borderTop:"1px solid rgba(255,255,255,0.06)",padding:"6px 10px"}}>
        {Array.isArray(a.skills)&&a.skills.length>0?a.skills.map(sk=><div key={sk.id} style={{padding:"5px 0",borderBottom:"1px solid rgba(255,255,255,0.03)"}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
            <div><div style={{fontSize:12,color:"#e0e0e0"}}>{sk.name||sk.id}</div>{sk.description&&<div style={{fontSize:10,color:"#666",marginTop:1}}>{sk.description}</div>}</div>
            <div style={{display:"flex",gap:3,flexShrink:0}}>
              {delegatedSkills.has(sk.id)?<><button disabled style={{fontSize:10,height:20,opacity:0.6,cursor:"default",background:"transparent",border:"1px solid var(--accent)",color:"var(--accent)",borderRadius:4,padding:"0 6px"}}>✓</button><button style={{fontSize:10,height:20,background:"transparent",border:"1px solid rgba(255,255,255,0.15)",color:"#888",borderRadius:4,padding:"0 6px",cursor:"pointer"}} onClick={async()=>{setSaving(true);try{const r=await delegateA2ATask(a.id,sk.id,"Execute "+sk.name);setDelegateResults(p=>({...p,[sk.id]:r}));toast(`Delegated to ${a.name||a.id}: ${sk.name||sk.id}`)}catch(e){setError(e.message)}finally{setSaving(false)}}}>Again</button></>:<button style={{fontSize:10,height:20}} onClick={async()=>{setSaving(true);try{const r=await delegateA2ATask(a.id,sk.id,"Execute "+sk.name);setDelegateResults(p=>({...p,[sk.id]:r}));setDelegatedSkills(p=>new Set([...p,sk.id]));toast(`Delegated to ${a.name||a.id}: ${sk.name||sk.id}`)}catch(e){setError(e.message)}finally{setSaving(false)}}}>Delegate</button>}
            </div>
          </div>
          {delegateResults[sk.id]&&<div style={{marginTop:4,padding:"6px 8px",background:"rgba(0,255,136,0.04)",borderRadius:4,fontSize:10,color:"var(--text-dim)"}}>{delegateResults[sk.id].status==="success"?<span style={{color:"var(--accent)"}}>✓ {delegateResults[sk.id].artifact?.text||delegateResults[sk.id].message||"Completed"}</span>:<span style={{color:"var(--error)"}}>✗ {delegateResults[sk.id].error_message||"Failed"}</span>}</div>}
        </div>):<div style={{color:"#555",fontSize:11,padding:"4px 0"}}>{a.status==="error"?"Agent unreachable":"No skills available"}</div>}
      </div>}
    </div>)}
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

  function renderIntegrations(){const wsp=wspSession||{};const tg=tgStatus||{};return(<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Integrations</h2>

    {/* ── WhatsApp Hub (collapsible) ── */}
    {(()=>{const wb=settings?.whatsapp?.backend||"browser";const isOfficial=wb==="official";const wspExp=expandedIntegration==="whatsapp";return<div className="card" style={{padding:0,overflow:"hidden"}}>
      <div className="item-row" style={{padding:"10px 14px",cursor:"pointer"}} onClick={()=>setExpandedIntegration(wspExp?null:"whatsapp")}>
        <span style={{fontSize:10,color:"var(--text-muted)",marginRight:4}}>{wspExp?"\u25BC":"\u25B6"}</span>
        <span style={{fontSize:16,marginRight:4}}>&#128172;</span>
        <span style={{fontSize:13,fontWeight:700,flex:1}}>WhatsApp</span>
        <span className={`dot ${wsp.active?"dot-success":"dot-neutral"}`} style={{marginRight:4}}/>
        <span style={{fontSize:10,color:wsp.active?"var(--success)":"var(--text-muted)",fontWeight:600}}>{wsp.active?"Online":"Offline"}</span>
      </div>
      {wspExp&&<div style={{padding:"0 14px 14px"}}>
        {/* Backend selector */}
        <div style={{background:"var(--bg-input)",border:"1px solid var(--border)",borderRadius:8,padding:10,marginBottom:8}}>
          <div style={{fontSize:9,textTransform:"uppercase",letterSpacing:2,color:"var(--accent)",marginBottom:6,fontWeight:600}}>Backend</div>
          <div style={{display:"flex",gap:4}}>
            {[{id:"browser",label:"Browser",desc:"Puppeteer"},{id:"baileys",label:"Baileys",desc:"Node.js"},{id:"official",label:"Official",desc:"Cloud API"}].map(b=><button key={b.id} onClick={async()=>{try{await whatsappSwitchBackend(b.id);const s=await getSettings();setSettings(s.settings||s);setWspSession({active:false});setWspQR(null);toast("Backend: "+b.label)}catch(err){toast(err.message,"error")}}} style={{flex:1,height:36,border:wb===b.id?"1px solid var(--accent)":"1px solid var(--border)",borderRadius:6,background:wb===b.id?"var(--accent-dim)":"var(--bg-input)",color:wb===b.id?"var(--accent)":"var(--text-dim)",fontSize:10,fontWeight:wb===b.id?700:500,cursor:"pointer",transition:"all 0.2s",display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",gap:1,padding:2}}><span>{b.label}</span><span style={{fontSize:8,opacity:0.6}}>{b.desc}</span></button>)}
          </div>
        </div>

        {/* Official API config */}
        {isOfficial&&<div style={{background:"var(--bg-input)",border:"1px solid var(--border)",borderRadius:8,padding:10,marginBottom:8}}>
          <div style={{fontSize:9,textTransform:"uppercase",letterSpacing:2,color:"var(--accent)",marginBottom:6,fontWeight:600}}>API Configuration</div>
          <label style={{display:"block",fontSize:10,color:"var(--text-dim)",marginBottom:2}}>Access Token</label>
          <input type="password" defaultValue={settings?.whatsapp?.official?.access_token||""} style={{width:"100%",height:28,fontSize:11,background:"var(--bg-elevated)",border:"1px solid var(--border)",borderRadius:4,color:"var(--text)",padding:"0 8px",marginBottom:6}} onBlur={e=>whatsappConfigure({official:{...(settings?.whatsapp?.official||{}),access_token:e.target.value}}).then(()=>toast("Saved")).catch(()=>{})} placeholder="EAA..."/>
          <label style={{display:"block",fontSize:10,color:"var(--text-dim)",marginBottom:2}}>Phone Number ID</label>
          <input defaultValue={settings?.whatsapp?.official?.phone_number_id||""} style={{width:"100%",height:28,fontSize:11,background:"var(--bg-elevated)",border:"1px solid var(--border)",borderRadius:4,color:"var(--text)",padding:"0 8px",marginBottom:6}} onBlur={e=>whatsappConfigure({official:{...(settings?.whatsapp?.official||{}),phone_number_id:e.target.value}}).then(()=>toast("Saved")).catch(()=>{})} placeholder="1234567890"/>
          <label style={{display:"block",fontSize:10,color:"var(--text-dim)",marginBottom:2}}>Verify Token</label>
          <input defaultValue={settings?.whatsapp?.official?.verify_token||""} style={{width:"100%",height:28,fontSize:11,background:"var(--bg-elevated)",border:"1px solid var(--border)",borderRadius:4,color:"var(--text)",padding:"0 8px",marginBottom:6}} onBlur={e=>whatsappConfigure({official:{...(settings?.whatsapp?.official||{}),verify_token:e.target.value}}).then(()=>toast("Saved")).catch(()=>{})} placeholder="my_secret_token"/>
          <div style={{fontSize:9,color:"var(--text-muted)",marginTop:2,padding:"4px 6px",background:"var(--bg-elevated)",borderRadius:4,fontFamily:"var(--font-mono)"}}>webhook: http://localhost:5001/webhook</div>
        </div>}

        {/* QR display */}
        {wspQR&&<div style={{background:"var(--bg-input)",border:"1px solid var(--border)",borderRadius:8,padding:10,marginBottom:8}}>
          <div style={{fontSize:9,textTransform:"uppercase",letterSpacing:2,color:"var(--accent)",marginBottom:6,fontWeight:600}}>Scan QR Code</div>
          <div style={{padding:12,background:"#ffffff",borderRadius:8,textAlign:"center",marginBottom:8}}><img src={wspQR} alt="QR" style={{width:180,height:180,imageRendering:"pixelated"}}/><div style={{fontSize:10,color:"#333",marginTop:6}}>Open WhatsApp &gt; Linked Devices &gt; Scan</div></div>
          <div style={{display:"flex",gap:4}}>
            <button style={{flex:1,height:28,fontSize:10}} onClick={async()=>{try{const r=await whatsappBridgeCheck();const c=r.connected||r.active||r.status==="connected";if(c){setWspQR(null);setWspSession({active:true});toast("Connected")}else if(r.qr_image)setWspQR(r.qr_image)}catch{}}}>Check Status</button>
            <button style={{flex:1,height:28,fontSize:10}} onClick={async()=>{await whatsappBridgeClose();setWspQR(null)}}>Cancel</button>
          </div>
        </div>}

        {/* Connect / Disconnect */}
        {!wspQR&&<div style={{display:"flex",gap:6}}>
          {!wsp.active?<button className="btn-primary" disabled={wspConnecting} onClick={async()=>{setWspConnecting(true);try{const r=await startWhatsApp();const c=r.connected||r.status==="connected";setWspSession({...wsp,...r,active:c});if(r.status==="error")toast(r.error||"Connection failed","error");else if(r.qr_image)setWspQR(r.qr_image);if(c){toast("WhatsApp connected");setWspQR(null)}}catch(e){toast(e.message,"error")}finally{setWspConnecting(false)}}} style={{flex:1,height:32,fontSize:11}}>{wspConnecting?"Connecting...":"Connect"}</button>
          :<button className="btn-danger" onClick={()=>act(async()=>{await whatsappBridgeClose();setWspSession({active:false});setWspQR(null)},"Disconnected")} style={{flex:1,height:32,fontSize:11}}>Disconnect</button>}
        </div>}
      </div>}
    </div>})()}

    {/* Other integrations (non-WhatsApp) */}
    {integrations.filter(i=>!["telegram_bot_connector","slack_bot_connector","discord_bot_connector","whatsapp_web_connector"].includes(i.id)).map(i=>{const exp=expandedIntegration===i.id;return<div key={i.id} className="card" style={{padding:0,overflow:"hidden"}}>
      <div className="item-row" style={{padding:"8px 10px",cursor:"pointer"}} onClick={()=>setExpandedIntegration(exp?null:i.id)}>
        <span style={{fontSize:10,color:"var(--text-muted)",marginRight:2}}>{exp?"\u25BC":"\u25B6"}</span>
        <span className={`dot ${stDot(i.status)}`} style={{marginRight:3}}/>
        <span style={{fontSize:11,fontWeight:500,flex:1}}>{i.name||i.id}</span>
        <span className="dim" style={{fontSize:10,marginLeft:3}}>{i.status}</span>
      </div>
      {exp&&<div style={{padding:"6px 10px",borderTop:"1px solid rgba(255,255,255,0.04)",fontSize:10,color:"var(--text-muted)"}}>No additional settings for this integration.</div>}
    </div>})}

    {/* Telegram config (always visible as a card) */}
    <div className="card" style={{padding:0,overflow:"hidden"}}>
      <div className="item-row" style={{padding:"8px 10px",cursor:"pointer"}} onClick={()=>setExpandedIntegration(expandedIntegration==="telegram"?null:"telegram")}>
        <span style={{fontSize:10,color:"var(--text-muted)",marginRight:2}}>{expandedIntegration==="telegram"?"\u25BC":"\u25B6"}</span>
        <span className={`dot ${tg.connected?"dot-success":tg.configured?"dot-warning":"dot-neutral"}`} style={{marginRight:3}}/>
        <span style={{fontSize:11,fontWeight:500,flex:1}}>Telegram</span>
        {tg.bot_name?<span className="dim" style={{fontSize:10}}>@{tg.bot_name}</span>:!tg.configured&&<span className="badge badge-neutral" style={{fontSize:8}}>not configured</span>}
        {tgPolling&&<span className="badge badge-success" style={{fontSize:8,marginLeft:3}}>polling</span>}
      </div>
      {expandedIntegration==="telegram"&&<div style={{padding:"6px 10px",borderTop:"1px solid rgba(255,255,255,0.04)",display:"flex",flexDirection:"column",gap:5}}>
        <div style={{display:"flex",gap:4,alignItems:"center"}}><label style={{fontSize:10,color:"var(--text-dim)",width:55}}>Token</label><div style={{display:"flex",flex:1,gap:3}}><input type={showTgToken?"text":"password"} value={tgToken} onChange={e=>setTgToken(e.target.value)} placeholder="123456:ABC-DEF..." style={{flex:1,height:22,fontSize:10}}/><button style={{width:24,height:22,fontSize:10,padding:0}} onClick={()=>setShowTgToken(p=>!p)}>{showTgToken?"*":"A"}</button></div></div>
        <div style={{display:"flex",gap:4,alignItems:"center"}}><label style={{fontSize:10,color:"var(--text-dim)",width:55}}>Chat ID</label><input value={tgChatId} onChange={e=>setTgChatId(e.target.value)} placeholder="-1234567890" style={{flex:1,height:22,fontSize:10}}/></div>
        <div style={{display:"flex",gap:4,alignItems:"center"}}><label style={{fontSize:10,color:"var(--text-dim)",width:55}}>Users</label><input value={tgUserIds} onChange={e=>setTgUserIds(e.target.value)} placeholder="user_id_1, user_id_2" style={{flex:1,height:22,fontSize:10}}/></div>
        <div style={{display:"flex",gap:4}}>
          <button className="btn-primary" style={{fontSize:10,height:22,flex:1}} disabled={!tgToken||saving} onClick={()=>{const ids=tgUserIds.split(",").map(s=>s.trim()).filter(Boolean);act(async()=>{await configureTelegram(tgToken,tgChatId,ids);setTgStatus(await getTelegramStatus())},"Saved")}}>Save</button>
          <button style={{fontSize:10,height:22,flex:1}} disabled={!tgToken||saving} onClick={()=>act(async()=>{const r=await testTelegram();toast(r.valid?`@${r.bot_name}`:r.error||"Failed",r.valid?"success":"error");setTgStatus(await getTelegramStatus())},"")}>Test</button>
          <button style={{fontSize:10,height:22,flex:1,background:tgPolling?"var(--error-dim)":"var(--success-dim)",color:tgPolling?"var(--error)":"var(--accent)",border:"none",borderRadius:4,cursor:"pointer"}} disabled={!tg.connected||saving} onClick={()=>act(async()=>{if(tgPolling){await stopTelegramPolling();setTgPolling(false)}else{await startTelegramPolling();setTgPolling(true)}},tgPolling?"Stopped":"Started")}>{tgPolling?"Stop":"Poll"}</button>
        </div>
        <details style={{fontSize:10,color:"var(--text-muted)"}}><summary style={{cursor:"pointer"}}>Setup guide</summary><ol style={{margin:"4px 0",paddingLeft:16,lineHeight:1.6}}><li>@BotFather in Telegram → /newbot → copy token</li><li>Your User ID: /start to @userinfobot</li><li>Paste token + user ID above, Save, then Poll</li></ol></details>
      </div>}
    </div>

    {/* Slack config */}
    {(()=>{const sl=slackStatus||{};return(<div className="card" style={{padding:0,overflow:"hidden"}}>
      <div className="item-row" style={{padding:"8px 10px",cursor:"pointer"}} onClick={()=>setExpandedIntegration(expandedIntegration==="slack"?null:"slack")}>
        <span style={{fontSize:10,color:"var(--text-muted)",marginRight:2}}>{expandedIntegration==="slack"?"\u25BC":"\u25B6"}</span>
        <span className={`dot ${sl.connected?"dot-success":sl.configured?"dot-warning":"dot-neutral"}`} style={{marginRight:3}}/>
        <span style={{fontSize:11,fontWeight:500,flex:1}}>Slack</span>
        {sl.bot_name?<span className="dim" style={{fontSize:10}}>@{sl.bot_name}</span>:<span className="badge badge-neutral" style={{fontSize:8}}>not configured</span>}
        {slackPolling&&<span className="badge badge-success" style={{fontSize:8,marginLeft:3}}>polling</span>}
      </div>
      {expandedIntegration==="slack"&&<div style={{padding:"6px 10px",borderTop:"1px solid rgba(255,255,255,0.04)",display:"flex",flexDirection:"column",gap:5}}>
        <div style={{display:"flex",gap:4,alignItems:"center"}}><label style={{fontSize:10,color:"var(--text-dim)",width:55}}>Token</label><div style={{display:"flex",flex:1,gap:3}}><input type={showSlackToken?"text":"password"} value={slackToken} onChange={e=>setSlackToken(e.target.value)} placeholder="xoxb-..." style={{flex:1,height:22,fontSize:10}}/><button style={{width:24,height:22,fontSize:10,padding:0}} onClick={()=>setShowSlackToken(p=>!p)}>{showSlackToken?"*":"A"}</button></div></div>
        <div style={{display:"flex",gap:4,alignItems:"center"}}><label style={{fontSize:10,color:"var(--text-dim)",width:55}}>Channel</label><input value={slackChannel} onChange={e=>setSlackChannel(e.target.value)} placeholder="C0123456789" style={{flex:1,height:22,fontSize:10}}/></div>
        <div style={{display:"flex",gap:4,alignItems:"center"}}><label style={{fontSize:10,color:"var(--text-dim)",width:55}}>Users</label><input value={slackUserIds} onChange={e=>setSlackUserIds(e.target.value)} placeholder="U0123, U0456" style={{flex:1,height:22,fontSize:10}}/></div>
        <div style={{display:"flex",gap:4}}>
          <button className="btn-primary" style={{fontSize:10,height:22,flex:1}} disabled={!slackToken||saving} onClick={()=>{const ids=slackUserIds.split(",").map(s=>s.trim()).filter(Boolean);act(async()=>{await configureSlack({bot_token:slackToken,channel_id:slackChannel,allowed_user_ids:ids});setSlackStatus(await getSlackStatus())},"Saved")}}>Save</button>
          <button style={{fontSize:10,height:22,flex:1}} disabled={!slackToken||saving} onClick={()=>act(async()=>{const r=await testSlack();toast(r.valid?`@${r.bot_name}`:r.error||"Failed",r.valid?"success":"error");setSlackStatus(await getSlackStatus())},"")}>Test</button>
          <button style={{fontSize:10,height:22,flex:1,background:slackPolling?"var(--error-dim)":"var(--success-dim)",color:slackPolling?"var(--error)":"var(--accent)",border:"none",borderRadius:4,cursor:"pointer"}} disabled={!sl.connected||saving} onClick={()=>act(async()=>{if(slackPolling){await stopSlackPolling();setSlackPolling(false)}else{await startSlackPolling();setSlackPolling(true)}},slackPolling?"Stopped":"Started")}>{slackPolling?"Stop":"Poll"}</button>
        </div>
        <details style={{fontSize:10,color:"var(--text-muted)"}}><summary style={{cursor:"pointer"}}>Setup guide</summary><ol style={{margin:"4px 0",paddingLeft:16,lineHeight:1.6}}><li>Create a Slack App at api.slack.com/apps</li><li>Enable Bot Token Scopes: chat:write, channels:history, channels:read</li><li>Install to workspace, copy Bot User OAuth Token (xoxb-...)</li><li>Invite bot to channel, get Channel ID from channel details</li></ol></details>
      </div>}
    </div>)})()}

    {/* Discord config */}
    {(()=>{const dc=discordStatus||{};return(<div className="card" style={{padding:0,overflow:"hidden"}}>
      <div className="item-row" style={{padding:"8px 10px",cursor:"pointer"}} onClick={()=>setExpandedIntegration(expandedIntegration==="discord"?null:"discord")}>
        <span style={{fontSize:10,color:"var(--text-muted)",marginRight:2}}>{expandedIntegration==="discord"?"\u25BC":"\u25B6"}</span>
        <span className={`dot ${dc.connected?"dot-success":dc.configured?"dot-warning":"dot-neutral"}`} style={{marginRight:3}}/>
        <span style={{fontSize:11,fontWeight:500,flex:1}}>Discord</span>
        {dc.bot_name?<span className="dim" style={{fontSize:10}}>@{dc.bot_name}</span>:<span className="badge badge-neutral" style={{fontSize:8}}>not configured</span>}
        {discordPolling&&<span className="badge badge-success" style={{fontSize:8,marginLeft:3}}>polling</span>}
      </div>
      {expandedIntegration==="discord"&&<div style={{padding:"6px 10px",borderTop:"1px solid rgba(255,255,255,0.04)",display:"flex",flexDirection:"column",gap:5}}>
        <div style={{display:"flex",gap:4,alignItems:"center"}}><label style={{fontSize:10,color:"var(--text-dim)",width:55}}>Token</label><div style={{display:"flex",flex:1,gap:3}}><input type={showDiscordToken?"text":"password"} value={discordToken} onChange={e=>setDiscordToken(e.target.value)} placeholder="Bot token..." style={{flex:1,height:22,fontSize:10}}/><button style={{width:24,height:22,fontSize:10,padding:0}} onClick={()=>setShowDiscordToken(p=>!p)}>{showDiscordToken?"*":"A"}</button></div></div>
        <div style={{display:"flex",gap:4,alignItems:"center"}}><label style={{fontSize:10,color:"var(--text-dim)",width:55}}>Channel</label><input value={discordChannel} onChange={e=>setDiscordChannel(e.target.value)} placeholder="Channel ID" style={{flex:1,height:22,fontSize:10}}/></div>
        <div style={{display:"flex",gap:4,alignItems:"center"}}><label style={{fontSize:10,color:"var(--text-dim)",width:55}}>Guild</label><input value={discordGuild} onChange={e=>setDiscordGuild(e.target.value)} placeholder="Guild/Server ID" style={{flex:1,height:22,fontSize:10}}/></div>
        <div style={{display:"flex",gap:4,alignItems:"center"}}><label style={{fontSize:10,color:"var(--text-dim)",width:55}}>Users</label><input value={discordUserIds} onChange={e=>setDiscordUserIds(e.target.value)} placeholder="user_id_1, user_id_2" style={{flex:1,height:22,fontSize:10}}/></div>
        <div style={{display:"flex",gap:4}}>
          <button className="btn-primary" style={{fontSize:10,height:22,flex:1}} disabled={!discordToken||saving} onClick={()=>{const ids=discordUserIds.split(",").map(s=>s.trim()).filter(Boolean);act(async()=>{await configureDiscord({bot_token:discordToken,channel_id:discordChannel,guild_id:discordGuild,allowed_user_ids:ids});setDiscordStatus(await getDiscordStatus())},"Saved")}}>Save</button>
          <button style={{fontSize:10,height:22,flex:1}} disabled={!discordToken||saving} onClick={()=>act(async()=>{const r=await testDiscord();toast(r.valid?`@${r.bot_name}`:r.error||"Failed",r.valid?"success":"error");setDiscordStatus(await getDiscordStatus())},"")}>Test</button>
          <button style={{fontSize:10,height:22,flex:1,background:discordPolling?"var(--error-dim)":"var(--success-dim)",color:discordPolling?"var(--error)":"var(--accent)",border:"none",borderRadius:4,cursor:"pointer"}} disabled={!dc.connected||saving} onClick={()=>act(async()=>{if(discordPolling){await stopDiscordPolling();setDiscordPolling(false)}else{await startDiscordPolling();setDiscordPolling(true)}},discordPolling?"Stopped":"Started")}>{discordPolling?"Stop":"Poll"}</button>
        </div>
        <details style={{fontSize:10,color:"var(--text-muted)"}}><summary style={{cursor:"pointer"}}>Setup guide</summary><ol style={{margin:"4px 0",paddingLeft:16,lineHeight:1.6}}><li>Go to discord.com/developers/applications → New Application</li><li>Bot tab → Reset Token → copy bot token</li><li>Enable MESSAGE CONTENT INTENT</li><li>OAuth2 → URL Generator → scopes: bot → permissions: Send Messages, Read Message History</li><li>Use generated URL to invite bot to your server</li><li>Right-click channel → Copy Channel ID (enable Developer Mode in settings)</li></ol></details>
      </div>}
    </div>)})()}
  </div>)}

  function renderBrowser(){const cdp=cdpStatus||{};const cdpConnected=cdp.connected;const curBackend=settings?.browser?.backend||"playwright";const isCDP=curBackend==="cdp";return(<div style={{display:"flex",flexDirection:"column",gap:10}}>
    <h2>Browser</h2>
    <div className="kpi-grid" style={{gridTemplateColumns:"1fr 1fr 1fr"}}><div className="kpi-card"><div className="kpi-label">Backend</div><div style={{display:"flex",alignItems:"center",gap:3,marginTop:1}}><span style={{fontSize:11,fontWeight:600,color:isCDP?"var(--text-muted)":"var(--accent)"}}>{isCDP?"CDP":"Playwright"}</span></div></div><div className="kpi-card"><div className="kpi-label">Worker</div><div style={{display:"flex",alignItems:"center",gap:3,marginTop:1}}><span className={`dot ${stDot(bwSt)}`}/><span style={{fontSize:11}}>{bwSt}</span></div></div><div className="kpi-card"><div className="kpi-label">Sessions</div><div className="kpi-value" style={{fontSize:14}}>{Array.isArray(bw.known_sessions)?bw.known_sessions.length:0}</div></div></div>
    {tr.dead_reason&&<div className="result-banner is-error" style={{fontSize:10}}>{tr.dead_reason}</div>}

    <div className="card" style={{padding:10}}>
      <h4 style={{margin:"0 0 6px"}}>Browser Backend</h4>
      <div style={{display:"flex",gap:8,alignItems:"center",marginBottom:6}}>
        <select value={curBackend} style={{height:28,fontSize:12,flex:1}} onChange={e=>{const nb=e.target.value;act(()=>saveSettings({...settings,browser:{...(settings?.browser||{}),backend:nb}}).then(r=>setSettings(r.settings||settings)),"Backend: "+nb)}}>
          <option value="playwright">Playwright (standalone)</option>
          <option value="cdp">CDP (Chrome)</option>
        </select>
      </div>
      <p style={{fontSize:10,color:"var(--text-muted)",margin:0}}>{isCDP?"Connects to an external Chrome with remote debugging port.":"Uses built-in Chromium — works out of the box, no setup needed."}</p>
    </div>

    {isCDP&&<div className="card" style={{padding:10}}>
      <h4 style={{margin:"0 0 6px"}}>CDP Connection</h4>
      <div style={{display:"flex",gap:5,alignItems:"center",marginBottom:8}}>
        <label style={{fontSize:11,color:"var(--text-dim)"}}>Port:</label>
        <input value={cdpPort||(cdp.port||9222)} onChange={e=>setCdpPort(e.target.value)} style={{width:70,height:24,fontSize:11}} placeholder="9222"/>
        <button style={{fontSize:10,height:24}} disabled={saving} onClick={()=>{const p=parseInt(cdpPort||cdp.port||9222);if(p>0)act(()=>saveSettings({...settings,browser:{...(settings?.browser||{}),cdp_port:p}}).then(r=>setSettings(r.settings||settings)),"Port saved")}}>Save</button>
      </div>
      {cdpConnected?<div style={{fontSize:11,color:"var(--accent)",marginBottom:4}}>Chrome connected — {cdp.tabs} tab{cdp.tabs!==1?"s":""} {cdp.browser&&<span className="dim">({cdp.browser})</span>}</div>:<div style={{fontSize:11,color:"var(--text-muted)",marginBottom:4}}>Chrome is not running with debugging.</div>}
      <button className={cdpConnected?"":"btn-primary"} style={{width:"100%",height:28,fontSize:12,marginBottom:4}} disabled={saving} onClick={()=>act(async()=>{const r=await launchChrome();const s=await getCDPStatus();setCdpStatus(s);toast(r.worker_connected?"Chrome launched + worker connected":r.already_running?"Chrome already running":"Chrome launched")},"")}>{cdpConnected?"Refresh status":"Launch Chrome with debugging"}</button>
      {cdpConnected&&bwSt!=="ready"&&<button style={{width:"100%",height:28,fontSize:12}} disabled={saving} onClick={()=>act(async()=>{const r=await connectBrowserCDP();const s=await getCDPStatus();setCdpStatus(s);toast(r.connected?"Worker connected to Chrome":"Connection failed — try Restart Worker")},"")}>{bw.active_session_id?"Worker connected":"Connect Worker to Chrome"}</button>}
      {cdpConnected&&bw.active_session_id&&<div style={{display:"flex",alignItems:"center",gap:5,fontSize:11,color:"var(--accent)",marginTop:4}}><span className="dot dot-success"/>Worker connected to Chrome (CDP)</div>}
    </div>}

    {isCDP&&<div className="card" style={{padding:10}}>
      <h4 style={{margin:"0 0 6px"}}>WhatsApp Web</h4>
      {cdp.whatsapp_open?<div style={{display:"flex",alignItems:"center",gap:5,fontSize:11,color:"var(--accent)",marginBottom:6}}><span className="dot dot-success"/>WhatsApp tab open</div>:null}
      <p style={{fontSize:11,color:"var(--text-muted)",margin:"0 0 4px"}}>Opens WhatsApp in the debugging Chrome.</p>
      <button style={{width:"100%",height:28,fontSize:12}} disabled={saving||!cdpConnected} onClick={()=>act(async()=>{await openWhatsApp();const s=await getCDPStatus();setCdpStatus(s);toast("WhatsApp tab opened")},"Opened")}>{cdp.whatsapp_open?"WhatsApp already open":cdpConnected?"Open WhatsApp Web":"Launch Chrome first"}</button>
    </div>}

    <div style={{display:"flex",gap:5}}>
      <button style={{flex:1,height:28,fontSize:12}} onClick={()=>act(async()=>{await restartBrowserWorker();const s=await getCDPStatus();setCdpStatus(s)},"Restarted")} disabled={saving}>Restart Worker</button>
    </div>
  </div>)}

  const renderSkills=()=>(<div className="settings-section">
    <h3>Installed Skills</h3>
    {skills.length===0&&<div className="empty-state"><span className="empty-state-text">No skills installed</span></div>}
    <div className="integration-list">
      {skills.map(s=>(<div key={s.id} className="integration-card">
        <header><div><strong>{s.name}</strong> <span className="badge badge-info">v{s.version}</span><br/><small>{s.description}</small></div>
          <button className="btn-danger" style={{height:24,fontSize:11}} disabled={saving} onClick={()=>act(async()=>{await uninstallSkill(s.id);await refreshSkills()},`Skill "${s.name}" uninstalled`)}>Uninstall</button>
        </header>
      </div>))}
    </div>
    <h4>Install from path</h4>
    <div style={{display:"flex",gap:6}}>
      <input value={newSkillPath} onChange={e=>setNewSkillPath(e.target.value)} placeholder="/path/to/skill-directory" style={{flex:1}}/>
      <button disabled={saving||!newSkillPath.trim()} onClick={()=>act(async()=>{await installSkill(newSkillPath.trim());setNewSkillPath("");await refreshSkills()},`Skill installed`)}>Install</button>
    </div>
  </div>);

  const [editingState,setEditingState]=useState(null);
  const [newStateName,setNewStateName]=useState("");
  const [newStateColor,setNewStateColor]=useState("#3b82f6");
  const [newStateIcon,setNewStateIcon]=useState("\u2b50");
  const pStates=settings?.project_states||[];

  function renderProjectStates(){return(<div style={{display:"flex",flexDirection:"column",gap:10}}>
    <h2>Project States</h2>
    <p style={{fontSize:11,color:"var(--text-muted)",margin:0}}>Customize the status labels for your projects. Each state has a name, color, and emoji icon.</p>

    {pStates.map((s,i)=>(<div key={i} className="card" style={{padding:"8px 12px",display:"flex",alignItems:"center",gap:8}}>
      <span style={{fontSize:18}}>{s.icon}</span>
      <span style={{flex:1,fontSize:12,fontWeight:500}}>{s.name}</span>
      <span style={{width:12,height:12,borderRadius:"50%",background:s.color}}/>
      <button style={{fontSize:10,height:22,padding:"0 8px"}} onClick={()=>{setEditingState(i);setNewStateName(s.name);setNewStateColor(s.color);setNewStateIcon(s.icon)}}>Edit</button>
      <button style={{fontSize:10,height:22,padding:"0 8px",color:"#ff4444"}} onClick={()=>{const updated=[...pStates];updated.splice(i,1);act(()=>saveSettings({...settings,project_states:updated}).then(r=>setSettings(r.settings||settings)),"State removed")}}>Del</button>
    </div>))}

    <div className="card" style={{padding:12}}>
      <h4 style={{margin:"0 0 8px",fontSize:12}}>{editingState!==null?"Edit State":"Add State"}</h4>
      <div style={{display:"flex",gap:6,alignItems:"center",marginBottom:8}}>
        <input value={newStateIcon} onChange={e=>setNewStateIcon(e.target.value)} style={{width:36,height:28,fontSize:16,textAlign:"center"}} title="Emoji icon"/>
        <input value={newStateName} onChange={e=>setNewStateName(e.target.value)} style={{flex:1,height:28,fontSize:12}} placeholder="State name"/>
        <input type="color" value={newStateColor} onChange={e=>setNewStateColor(e.target.value)} style={{width:28,height:28,border:"none",padding:0,cursor:"pointer"}}/>
      </div>
      <div style={{display:"flex",gap:4}}>
        <button className="btn-primary" style={{flex:1,height:28,fontSize:11}} onClick={()=>{
          if(!newStateName.trim())return;
          const entry={name:newStateName.trim(),color:newStateColor,icon:newStateIcon||"\u2b50"};
          let updated;
          if(editingState!==null){updated=[...pStates];updated[editingState]=entry}else{updated=[...pStates,entry]}
          act(()=>saveSettings({...settings,project_states:updated}).then(r=>setSettings(r.settings||settings)),editingState!==null?"State updated":"State added");
          setEditingState(null);setNewStateName("");setNewStateColor("#3b82f6");setNewStateIcon("\u2b50");
        }}>{editingState!==null?"Save":"Add"}</button>
        {editingState!==null&&<button style={{height:28,fontSize:11,padding:"0 12px"}} onClick={()=>{setEditingState(null);setNewStateName("");setNewStateColor("#3b82f6");setNewStateIcon("\u2b50")}}>Cancel</button>}
      </div>
    </div>
  </div>)}

  // ── Agents section ──
  const [agents,setAgents]=useState([]);
  const [editAgent,setEditAgent]=useState(null);
  const [agentForm,setAgentForm]=useState({name:"",emoji:"\U0001f916",description:"",system_prompt:"",tool_ids:[],llm_model:"",language:"auto",max_iterations:10});
  const refreshAgents=()=>listAgents().then(r=>setAgents(r.agents||[])).catch(()=>{});
  useEffect(()=>{if(activeSection==="agents")refreshAgents()},[activeSection]);

  const TOOL_CATS={
    "Filesystem":["filesystem_read_file","filesystem_write_file","filesystem_list_directory","filesystem_create_directory","filesystem_delete_file","filesystem_copy_file","filesystem_move_file","filesystem_edit_file"],
    "Execution":["execution_run_command","execution_run_script"],
    "Network":["network_http_get","network_extract_text","network_extract_links"],
    "Browser":["browser_navigate","browser_read_text","browser_screenshot","browser_click_element","browser_type_text"],
    "System":["system_get_os_info","system_get_workspace_info","system_get_env_var"],
  };

  function renderAgents(){return(<div style={{display:"flex",flexDirection:"column",gap:10}}>
    <h2>Agents</h2>
    <p style={{fontSize:11,color:"var(--text-muted)",margin:0}}>Create custom AI agents with unique personalities, tools, and behaviors. Assign them to projects or select them in conversations.</p>

    {agents.map(a=>(<div key={a.id} className="card" style={{padding:"10px 14px",display:"flex",alignItems:"center",gap:10}}>
      <span style={{fontSize:22}}>{a.emoji}</span>
      <div style={{flex:1}}>
        <div style={{fontSize:13,fontWeight:600,color:"var(--text)"}}>{a.name} {a.id==="agt_default"&&<span className="badge badge-info" style={{fontSize:8,marginLeft:4}}>default</span>}</div>
        <div style={{fontSize:10,color:"var(--text-dim)"}}>{a.description||"No description"}</div>
        {a.tool_ids?.length>0&&<div style={{fontSize:9,color:"var(--text-muted)",marginTop:2}}>{a.tool_ids.length} tools</div>}
      </div>
      {a.id!=="agt_default"&&<>
        <button style={{fontSize:10,height:24}} onClick={()=>{setEditAgent(a.id);setAgentForm({name:a.name,emoji:a.emoji,description:a.description,system_prompt:a.system_prompt||"",tool_ids:a.tool_ids||[],llm_model:a.llm_model||"",language:a.language||"auto",max_iterations:a.max_iterations||10})}}>Edit</button>
        <button style={{fontSize:10,height:24,color:"var(--error)"}} onClick={()=>act(async()=>{await deleteAgentDef(a.id);refreshAgents()},"Agent deleted")}>Del</button>
      </>}
    </div>))}

    <div className="card" style={{padding:14,marginBottom:8}}>
      <h4 style={{margin:"0 0 8px"}}>AI Agent Designer</h4>
      <p style={{fontSize:10,color:"var(--text-muted)",margin:"0 0 8px"}}>Describe the agent you want and the AI will design it for you.</p>
      <div style={{display:"flex",gap:6}}>
        <input id="ai-design-input" style={{flex:1,height:32,fontSize:12}} placeholder="e.g. An expert in Python that helps debug code"/>
        <button style={{height:32,fontSize:11,padding:"0 14px",whiteSpace:"nowrap"}} onClick={async()=>{
          const inp=document.getElementById("ai-design-input");
          const desc=inp?.value?.trim();
          if(!desc)return;
          toast("Designing agent...");
          try{
            const r=await designAgent(desc);
            if(r.config){
              setAgentForm({...agentForm,...r.config,llm_model:r.config.llm_model||""});
              setEditAgent(null);
              toast("Agent designed! Review and save below.");
            }else{toast(r.error||"Design failed","error")}
          }catch(e){toast(e.message||"Design failed","error")}
        }}>Design</button>
      </div>
    </div>

    <div className="card" style={{padding:14}}>
      <h4 style={{margin:"0 0 10px"}}>{editAgent?"Edit Agent":"Create Agent"}</h4>
      <div style={{display:"flex",gap:8,marginBottom:8}}>
        <input value={agentForm.emoji} onChange={e=>setAgentForm({...agentForm,emoji:e.target.value})} style={{width:40,height:32,fontSize:18,textAlign:"center"}} title="Emoji"/>
        <input value={agentForm.name} onChange={e=>setAgentForm({...agentForm,name:e.target.value})} style={{flex:1,height:32,fontSize:13}} placeholder="Agent name"/>
      </div>
      <input value={agentForm.description} onChange={e=>setAgentForm({...agentForm,description:e.target.value})} style={{width:"100%",height:28,fontSize:11,marginBottom:8}} placeholder="Description (what this agent does)"/>
      <label style={{fontSize:10,color:"var(--text-dim)",display:"block",marginBottom:2}}>System Prompt</label>
      <textarea value={agentForm.system_prompt} onChange={e=>setAgentForm({...agentForm,system_prompt:e.target.value})} style={{width:"100%",height:100,fontSize:11,background:"var(--bg-input)",border:"1px solid var(--border)",borderRadius:6,color:"var(--text)",padding:8,resize:"vertical",fontFamily:"var(--font-mono)"}} placeholder="You are an expert in..."/>

      <label style={{fontSize:10,color:"var(--text-dim)",display:"block",margin:"8px 0 4px"}}>Tools</label>
      <div style={{display:"flex",flexDirection:"column",gap:4,marginBottom:8}}>
        {Object.entries(TOOL_CATS).map(([cat,tools])=>(<div key={cat}>
          <div style={{fontSize:9,color:"var(--accent)",fontWeight:600,marginBottom:2}}>{cat}</div>
          <div style={{display:"flex",flexWrap:"wrap",gap:3}}>
            {tools.map(t=>{const on=agentForm.tool_ids.includes(t);return<button key={t} onClick={()=>{const ids=on?agentForm.tool_ids.filter(x=>x!==t):[...agentForm.tool_ids,t];setAgentForm({...agentForm,tool_ids:ids})}} style={{fontSize:9,height:22,padding:"0 6px",background:on?"var(--accent-dim)":"var(--bg-input)",color:on?"var(--accent)":"var(--text-muted)",border:on?"1px solid var(--accent)":"1px solid var(--border)"}}>{t.replace("filesystem_","").replace("execution_","").replace("network_","").replace("browser_","").replace("system_","")}</button>})}
          </div>
        </div>))}
        <button style={{fontSize:9,height:22,marginTop:2}} onClick={()=>{const all=Object.values(TOOL_CATS).flat();setAgentForm({...agentForm,tool_ids:agentForm.tool_ids.length===all.length?[]:all})}}>
          {agentForm.tool_ids.length===Object.values(TOOL_CATS).flat().length?"Deselect all":"Select all"}
        </button>
      </div>

      <div style={{display:"flex",gap:8,marginBottom:8}}>
        <div style={{flex:1}}>
          <label style={{fontSize:10,color:"var(--text-dim)"}}>LLM Model (empty = system default)</label>
          <input value={agentForm.llm_model} onChange={e=>setAgentForm({...agentForm,llm_model:e.target.value})} style={{width:"100%",height:28,fontSize:11}} placeholder="e.g. gpt-4o"/>
        </div>
        <div>
          <label style={{fontSize:10,color:"var(--text-dim)"}}>Language</label>
          <input value={agentForm.language} onChange={e=>setAgentForm({...agentForm,language:e.target.value})} style={{width:80,height:28,fontSize:11}} placeholder="auto"/>
        </div>
        <div>
          <label style={{fontSize:10,color:"var(--text-dim)"}}>Max iter</label>
          <input type="number" value={agentForm.max_iterations} onChange={e=>setAgentForm({...agentForm,max_iterations:parseInt(e.target.value)||10})} style={{width:50,height:28,fontSize:11}} min={1} max={50}/>
        </div>
      </div>

      <div style={{display:"flex",gap:6}}>
        <button className="btn-primary" style={{flex:1,height:32,fontSize:12}} onClick={async()=>{
          if(!agentForm.name.trim())return;
          try{
            if(editAgent){await updateAgentDef(editAgent,agentForm);toast("Agent updated")}
            else{await createAgent(agentForm);toast("Agent created")}
            refreshAgents();setEditAgent(null);setAgentForm({name:"",emoji:"\U0001f916",description:"",system_prompt:"",tool_ids:[],llm_model:"",language:"auto",max_iterations:10});
          }catch(e){toast(e.message||"Failed","error")}
        }}>{editAgent?"Save":"Create"}</button>
        {editAgent&&<button style={{height:32,fontSize:12,padding:"0 16px"}} onClick={()=>{setEditAgent(null);setAgentForm({name:"",emoji:"\U0001f916",description:"",system_prompt:"",tool_ids:[],llm_model:"",language:"auto",max_iterations:10})}}>Cancel</button>}
      </div>
    </div>
  </div>)}

  const R={system:renderSystem,workspaces:renderWorkspaces,llm:renderLLM,metrics:renderMetrics,"self-improvement":renderSI,"auto-growth":renderAutoGrowth,mcp:renderMCP,a2a:renderA2A,memory:renderMemory,integrations:renderIntegrations,browser:renderBrowser,skills:renderSkills,agents:renderAgents,"project-states":renderProjectStates};

  return (<>
    <CCLayout activeSection={activeSection} onSelectSection={setActiveSection} wsConnected={wsConnected} highlightSection={highlightSection}>
      <KPIBar health={health} integrations={integrations} workspaceCount={wsData.length}/>
      {message&&<div className="status-banner success">{message}</div>}
      {error&&<div className="status-banner error">{error}</div>}
      {loading?<div style={{display:"flex",flexDirection:"column",gap:6}}><div className="skeleton skeleton-block"/><div className="skeleton skeleton-block"/></div>:(R[activeSection]||renderSystem)()}
    </CCLayout>
    <ToastContainer toasts={toasts} onDismiss={removeToast}/>
  </>);
}
