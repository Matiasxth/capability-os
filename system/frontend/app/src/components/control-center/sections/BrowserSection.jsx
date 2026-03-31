import React, { useEffect, useState } from "react";
import sdk from "../../../sdk";

function stDot(v){if(["ready","enabled","ok","available","success"].includes(v))return"dot-success";if(v==="running"||v==="preparing")return"dot-running";if(["error","down","not_configured","disabled"].includes(v))return"dot-error";return"dot-neutral"}

export default function BrowserSection({ settings, setSettings, health, saving, toast, act }) {
  const [cdpStatus, setCdpStatus] = useState(null);
  const [cdpPort, setCdpPort] = useState("");

  const bw = health?.browser_worker || {};
  const tr = bw.transport || {};
  const bwSt = bw.status || (tr.alive ? "ready" : tr.worker_failed ? "error" : "available");

  useEffect(() => {
    sdk.system.browser.cdpStatus().then(r => setCdpStatus(r)).catch(() => setCdpStatus({ connected: false, tabs: 0, port: 9222 }));
  }, []);

  const cdp = cdpStatus || {};
  const cdpConnected = cdp.connected;
  const curBackend = settings?.browser?.backend || "playwright";
  const isCDP = curBackend === "cdp";

  return (<div style={{display:"flex",flexDirection:"column",gap:10}}>
    <h2>Browser</h2>
    <div className="kpi-grid" style={{gridTemplateColumns:"1fr 1fr 1fr"}}><div className="kpi-card"><div className="kpi-label">Backend</div><div style={{display:"flex",alignItems:"center",gap:3,marginTop:1}}><span style={{fontSize:11,fontWeight:600,color:isCDP?"var(--text-muted)":"var(--accent)"}}>{isCDP?"CDP":"Playwright"}</span></div></div><div className="kpi-card"><div className="kpi-label">Worker</div><div style={{display:"flex",alignItems:"center",gap:3,marginTop:1}}><span className={`dot ${stDot(bwSt)}`}/><span style={{fontSize:11}}>{bwSt}</span></div></div><div className="kpi-card"><div className="kpi-label">Sessions</div><div className="kpi-value" style={{fontSize:14}}>{Array.isArray(bw.known_sessions)?bw.known_sessions.length:0}</div></div></div>
    {tr.dead_reason&&<div className="result-banner is-error" style={{fontSize:10}}>{tr.dead_reason}</div>}

    <div className="card" style={{padding:10}}>
      <h4 style={{margin:"0 0 6px"}}>Browser Backend</h4>
      <div style={{display:"flex",gap:8,alignItems:"center",marginBottom:6}}>
        <select value={curBackend} style={{height:28,fontSize:12,flex:1}} onChange={e=>{const nb=e.target.value;act(()=>sdk.system.settings.save({...settings,browser:{...(settings?.browser||{}),backend:nb}}).then(r=>setSettings(r.settings||settings)),"Backend: "+nb)}}>
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
        <button style={{fontSize:10,height:24}} disabled={saving} onClick={()=>{const p=parseInt(cdpPort||cdp.port||9222);if(p>0)act(()=>sdk.system.settings.save({...settings,browser:{...(settings?.browser||{}),cdp_port:p}}).then(r=>setSettings(r.settings||settings)),"Port saved")}}>Save</button>
      </div>
      {cdpConnected?<div style={{fontSize:11,color:"var(--accent)",marginBottom:4}}>Chrome connected — {cdp.tabs} tab{cdp.tabs!==1?"s":""} {cdp.browser&&<span className="dim">({cdp.browser})</span>}</div>:<div style={{fontSize:11,color:"var(--text-muted)",marginBottom:4}}>Chrome is not running with debugging.</div>}
      <button className={cdpConnected?"":"btn-primary"} style={{width:"100%",height:28,fontSize:12,marginBottom:4}} disabled={saving} onClick={()=>act(async()=>{const r=await sdk.system.browser.launchChrome();const s=await sdk.system.browser.cdpStatus();setCdpStatus(s);toast(r.worker_connected?"Chrome launched + worker connected":r.already_running?"Chrome already running":"Chrome launched")},"")}>{cdpConnected?"Refresh status":"Launch Chrome with debugging"}</button>
      {cdpConnected&&bwSt!=="ready"&&<button style={{width:"100%",height:28,fontSize:12}} disabled={saving} onClick={()=>act(async()=>{const r=await sdk.system.browser.connectCDP();const s=await sdk.system.browser.cdpStatus();setCdpStatus(s);toast(r.connected?"Worker connected to Chrome":"Connection failed — try Restart Worker")},"")}>{bw.active_session_id?"Worker connected":"Connect Worker to Chrome"}</button>}
      {cdpConnected&&bw.active_session_id&&<div style={{display:"flex",alignItems:"center",gap:5,fontSize:11,color:"var(--accent)",marginTop:4}}><span className="dot dot-success"/>Worker connected to Chrome (CDP)</div>}
    </div>}

    {isCDP&&<div className="card" style={{padding:10}}>
      <h4 style={{margin:"0 0 6px"}}>WhatsApp Web</h4>
      {cdp.whatsapp_open?<div style={{display:"flex",alignItems:"center",gap:5,fontSize:11,color:"var(--accent)",marginBottom:6}}><span className="dot dot-success"/>WhatsApp tab open</div>:null}
      <p style={{fontSize:11,color:"var(--text-muted)",margin:"0 0 4px"}}>Opens WhatsApp in the debugging Chrome.</p>
      <button style={{width:"100%",height:28,fontSize:12}} disabled={saving||!cdpConnected} onClick={()=>act(async()=>{await sdk.system.browser.openWhatsApp();const s=await sdk.system.browser.cdpStatus();setCdpStatus(s);toast("WhatsApp tab opened")},"Opened")}>{cdp.whatsapp_open?"WhatsApp already open":cdpConnected?"Open WhatsApp Web":"Launch Chrome first"}</button>
    </div>}

    <div style={{display:"flex",gap:5}}>
      <button style={{flex:1,height:28,fontSize:12}} onClick={()=>act(async()=>{await sdk.system.browser.restart();const s=await sdk.system.browser.cdpStatus();setCdpStatus(s)},"Restarted")} disabled={saving}>Restart Worker</button>
    </div>
  </div>);
}
