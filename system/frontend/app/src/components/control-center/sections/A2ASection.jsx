import React, { useEffect, useState } from "react";
import sdk from "../../../sdk";

export default function A2ASection({ toast, act }) {
  const [a2aAgents, setA2aAgents] = useState([]);
  const [newAgentUrl, setNewAgentUrl] = useState("");
  const [expandedAgent, setExpandedAgent] = useState(null);
  const [delegateResults, setDelegateResults] = useState({});
  const [delegatedSkills, setDelegatedSkills] = useState(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const r = await sdk.a2a.agents.list();
      setA2aAgents(r.agents || []);
    } catch {}
  }
  useEffect(() => { refresh(); }, []);

  return (<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>A2A</h2>
    <form onSubmit={async e=>{e.preventDefault();await act(async()=>{await sdk.a2a.agents.add(newAgentUrl);await refresh()},"Added");setNewAgentUrl("")}} style={{display:"flex",gap:5}}>
      <input placeholder="Agent URL (e.g. http://localhost:8001)" value={newAgentUrl} onChange={e=>setNewAgentUrl(e.target.value)} required style={{flex:1}}/>
      <button type="submit" className="btn-primary" disabled={!newAgentUrl}>Add</button>
    </form>
    {a2aAgents.map(a=><div key={a.id} className="card" style={{padding:0,overflow:"hidden"}}>
      <div className="item-row" style={{cursor:"pointer",padding:"8px 10px"}} onClick={()=>{setExpandedAgent(expandedAgent===a.id?null:a.id);setDelegateResults({})}}>
        <span className={`dot ${a.status==="reachable"?"dot-success":"dot-error"}`} style={{marginRight:3}}/>
        <span style={{fontSize:11,flex:1,fontWeight:500}}>{a.name||a.id}</span>
        <span style={{fontSize:10,color:"var(--text-muted)",marginRight:4}}>{Array.isArray(a.skills)?a.skills.length:0} skills</span>
        <button className="btn-danger" style={{fontSize:10,height:20}} onClick={e=>{e.stopPropagation();act(async()=>{await sdk.a2a.agents.remove(a.id);setExpandedAgent(null);await refresh()},"Removed")}}>✕</button>
      </div>
      {expandedAgent===a.id&&<div style={{borderTop:"1px solid rgba(255,255,255,0.06)",padding:"6px 10px"}}>
        {Array.isArray(a.skills)&&a.skills.length>0?a.skills.map(sk=><div key={sk.id} style={{padding:"5px 0",borderBottom:"1px solid rgba(255,255,255,0.03)"}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
            <div><div style={{fontSize:12,color:"#e0e0e0"}}>{sk.name||sk.id}</div>{sk.description&&<div style={{fontSize:10,color:"#666",marginTop:1}}>{sk.description}</div>}</div>
            <div style={{display:"flex",gap:3,flexShrink:0}}>
              {delegatedSkills.has(sk.id)?<><button disabled style={{fontSize:10,height:20,opacity:0.6,cursor:"default",background:"transparent",border:"1px solid var(--accent)",color:"var(--accent)",borderRadius:4,padding:"0 6px"}}>✓</button><button style={{fontSize:10,height:20,background:"transparent",border:"1px solid rgba(255,255,255,0.15)",color:"#888",borderRadius:4,padding:"0 6px",cursor:"pointer"}} onClick={async()=>{setSaving(true);try{const r=await sdk.a2a.delegate(a.id,sk.id,"Execute "+sk.name);setDelegateResults(p=>({...p,[sk.id]:r}));toast(`Delegated to ${a.name||a.id}: ${sk.name||sk.id}`)}catch(e){setError(e.message)}finally{setSaving(false)}}}>Again</button></>:<button style={{fontSize:10,height:20}} onClick={async()=>{setSaving(true);try{const r=await sdk.a2a.delegate(a.id,sk.id,"Execute "+sk.name);setDelegateResults(p=>({...p,[sk.id]:r}));setDelegatedSkills(p=>new Set([...p,sk.id]));toast(`Delegated to ${a.name||a.id}: ${sk.name||sk.id}`)}catch(e){setError(e.message)}finally{setSaving(false)}}}>Delegate</button>}
            </div>
          </div>
          {delegateResults[sk.id]&&<div style={{marginTop:4,padding:"6px 8px",background:"rgba(0,255,136,0.04)",borderRadius:4,fontSize:10,color:"var(--text-dim)"}}>{delegateResults[sk.id].status==="success"?<span style={{color:"var(--accent)"}}>✓ {delegateResults[sk.id].artifact?.text||delegateResults[sk.id].message||"Completed"}</span>:<span style={{color:"var(--error)"}}>✗ {delegateResults[sk.id].error_message||"Failed"}</span>}</div>}
        </div>):<div style={{color:"#555",fontSize:11,padding:"4px 0"}}>{a.status==="error"?"Agent unreachable":"No skills available"}</div>}
      </div>}
    </div>)}
  </div>);
}
