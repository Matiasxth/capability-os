import React from "react";
import sdk from "../../../sdk";

export default function SystemSection({ health, integrations, settings, bwSt, bw, toast, act, refreshAll }) {
  const llm = health?.llm || {};
  return (<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>System</h2>
    {Array.isArray(health?.issues)&&health.issues.length>0&&<div style={{background:"var(--warning-dim)",border:"1px solid rgba(255,170,0,0.12)",borderRadius:"var(--radius-md)",padding:6}}>{health.issues.map((s,i)=><p key={i} style={{fontSize:11,color:"var(--warning)",margin:"1px 0"}}>{s}</p>)}</div>}
    <div className="kpi-grid" style={{gridTemplateColumns:"1fr 1fr 1fr"}}>
      <div className="kpi-card"><div className="kpi-label">Integrations</div><div className="kpi-value">{integrations.filter(i=>i.status==="enabled").length}/{integrations.length}</div></div>
      <div className="kpi-card"><div className="kpi-label">Model</div><div style={{fontSize:11,marginTop:2}}>{llm.model||"-"}</div></div>
      <div className="kpi-card"><div className="kpi-label">Sessions</div><div className="kpi-value">{Array.isArray(bw.known_sessions)?bw.known_sessions.length:0}</div></div>
    </div>
    {bwSt==="error"&&<button onClick={()=>act(()=>sdk.system.browser.restart(),"Restarted")}>Restart Worker</button>}
    <div style={{display:"flex",gap:5,marginTop:4}}>
      <button style={{flex:1,fontSize:11,height:26}} onClick={async()=>{try{const d=await sdk.system.exportConfig();const blob=new Blob([JSON.stringify(d,null,2)],{type:"application/json"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="capos-config.json";a.click();URL.revokeObjectURL(url);toast("Config exported")}catch(e){toast(e.message,"error")}}}>Export Config</button>
      <button style={{flex:1,fontSize:11,height:26}} onClick={()=>{const inp=document.createElement("input");inp.type="file";inp.accept=".json";inp.onchange=async e=>{const f=e.target.files[0];if(!f)return;try{const txt=await f.text();const data=JSON.parse(txt);await sdk.system.importConfig(data);toast("Config imported");await refreshAll()}catch(err){toast(err.message,"error")}};inp.click()}}>Import Config</button>
    </div>
  </div>);
}
