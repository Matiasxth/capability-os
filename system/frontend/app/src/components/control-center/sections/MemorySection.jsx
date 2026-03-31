import React, { useEffect, useState } from "react";
import sdk from "../../../sdk";

export default function MemorySection({ toast, act }) {
  const [memQuery, setMemQuery] = useState("");
  const [memResults, setMemResults] = useState([]);
  const [memContext, setMemContext] = useState(null);
  const [mdMemory, setMdMemory] = useState("");
  const [mdSections, setMdSections] = useState({});
  const [mdEditing, setMdEditing] = useState(false);
  const [mdEditContent, setMdEditContent] = useState("");
  const [dailyDates, setDailyDates] = useState([]);
  const [dailyContent, setDailyContent] = useState("");
  const [dailyDate, setDailyDate] = useState("");
  const [sessionSummaries, setSessionSummaries] = useState([]);
  const [agentContext, setAgentContext] = useState("");
  const [memTab, setMemTab] = useState("overview");
  const [newFactSection, setNewFactSection] = useState("Decisions");
  const [newFactText, setNewFactText] = useState("");

  async function refresh() {
    try {
      const [ctx, md, daily, summaries, agCtx] = await Promise.all([
        sdk.memory.context(),
        sdk.memory.markdown.get(),
        sdk.memory.daily(),
        sdk.memory.summaries(),
        sdk.memory.agentContext()
      ]);
      setMemContext(ctx.context || null);
      setMdMemory(md.content || "");
      setMdSections(md.sections || {});
      setDailyDates(daily.dates || []);
      setDailyContent(daily.content || "");
      if (daily.dates?.length) setDailyDate(daily.dates[0]);
      setSessionSummaries(summaries.sessions || []);
      setAgentContext(agCtx.context || "");
    } catch {}
  }

  useEffect(() => { refresh() }, []);

  const ctx = memContext || {};
  const tabs = ["overview", "memory.md", "daily", "sessions", "semantic"];

  return (<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Memory</h2>
    {/* Tab bar */}
    <div style={{display:"flex",gap:2,borderBottom:"1px solid var(--border)",paddingBottom:4}}>
      {tabs.map(t=><button key={t} onClick={()=>setMemTab(t)} style={{padding:"4px 10px",fontSize:10,fontWeight:memTab===t?700:500,border:"none",borderBottom:memTab===t?"2px solid var(--accent)":"2px solid transparent",background:"none",color:memTab===t?"var(--accent)":"var(--text-muted)",cursor:"pointer",textTransform:"capitalize"}}>{t==="memory.md"?"MEMORY.md":t}</button>)}
    </div>

    {/* -- Overview tab -- */}
    {memTab==="overview"&&<div style={{display:"flex",flexDirection:"column",gap:8}}>
      <div className="kpi-grid" style={{gridTemplateColumns:"1fr 1fr 1fr"}}><div className="kpi-card"><div className="kpi-label">Lang</div><div style={{fontSize:11,marginTop:1}}>{ctx.preferred_language||"-"}</div></div><div className="kpi-card"><div className="kpi-label">Top Capabilities</div><div style={{fontSize:9,marginTop:1}}>{(ctx.frequent_capabilities||[]).slice(0,3).join(", ")||"-"}</div></div><div className="kpi-card"><div className="kpi-label">Preferences</div><div style={{fontSize:11,marginTop:1}}>{Object.keys(ctx.custom_preferences||{}).length}</div></div></div>
      <div className="kpi-grid" style={{gridTemplateColumns:"1fr 1fr 1fr"}}><div className="kpi-card"><div className="kpi-label">MEMORY.md</div><div style={{fontSize:11,marginTop:1}}>{Object.keys(mdSections).length} sections</div></div><div className="kpi-card"><div className="kpi-label">Daily Notes</div><div style={{fontSize:11,marginTop:1}}>{dailyDates.length} days</div></div><div className="kpi-card"><div className="kpi-label">Sessions</div><div style={{fontSize:11,marginTop:1}}>{sessionSummaries.length} compacted</div></div></div>
      {/* Agent context preview */}
      {agentContext&&<div className="card" style={{padding:10}}><div style={{fontSize:9,textTransform:"uppercase",letterSpacing:2,color:"var(--accent)",marginBottom:4,fontWeight:600}}>Agent Context (injected into prompts)</div><pre style={{fontSize:10,whiteSpace:"pre-wrap",color:"var(--text-dim)",margin:0,maxHeight:120,overflow:"auto"}}>{agentContext}</pre></div>}
    </div>}

    {/* -- MEMORY.md tab -- */}
    {memTab==="memory.md"&&<div style={{display:"flex",flexDirection:"column",gap:8}}>
      {/* Section cards */}
      {!mdEditing&&<>
        {Object.entries(mdSections).map(([sec,lines])=><div key={sec} className="card" style={{padding:10}}>
          <div style={{fontSize:11,fontWeight:700,color:"var(--accent)",marginBottom:4}}>{sec}</div>
          {lines.filter(l=>l.trim()).map((l,i)=><div key={i} style={{display:"flex",alignItems:"center",gap:4,fontSize:11,color:"var(--text-dim)",padding:"2px 0"}}>
            <span style={{flex:1}}>{l}</span>
            {l.trim().startsWith("-")&&<button className="btn-danger" style={{fontSize:9,height:18,padding:"0 4px"}} onClick={()=>act(async()=>{await sdk.memory.markdown.removeFact(sec,l.replace(/^-\s*/,"").trim());await refresh()},"Removed")}>&#10005;</button>}
          </div>)}
        </div>)}
        {/* Add fact form */}
        <div className="card" style={{padding:10}}>
          <div style={{fontSize:9,textTransform:"uppercase",letterSpacing:2,color:"var(--accent)",marginBottom:6,fontWeight:600}}>Add Fact</div>
          <div style={{display:"flex",gap:4}}>
            <select value={newFactSection} onChange={e=>setNewFactSection(e.target.value)} style={{width:120,fontSize:11}}>
              {["User","Decisions","Projects","Learned Patterns"].map(s=><option key={s} value={s}>{s}</option>)}
            </select>
            <input placeholder="New fact..." value={newFactText} onChange={e=>setNewFactText(e.target.value)} style={{flex:1,fontSize:11}}/>
            <button className="btn-primary" disabled={!newFactText.trim()} onClick={()=>act(async()=>{await sdk.memory.markdown.addFact(newFactSection,newFactText);setNewFactText("");await refresh()},"Added")} style={{fontSize:10}}>Add</button>
          </div>
        </div>
        <button className="btn-primary" style={{fontSize:10,alignSelf:"flex-start"}} onClick={()=>{setMdEditContent(mdMemory);setMdEditing(true)}}>Edit Raw</button>
      </>}
      {/* Raw editor */}
      {mdEditing&&<div style={{display:"flex",flexDirection:"column",gap:4}}>
        <textarea value={mdEditContent} onChange={e=>setMdEditContent(e.target.value)} rows={16} style={{fontFamily:"monospace",fontSize:11,resize:"vertical"}}/>
        <div style={{display:"flex",gap:4}}>
          <button className="btn-primary" onClick={()=>act(async()=>{await sdk.memory.markdown.save(mdEditContent);setMdEditing(false);await refresh()},"Saved")} style={{fontSize:10}}>Save</button>
          <button onClick={()=>setMdEditing(false)} style={{fontSize:10}}>Cancel</button>
        </div>
      </div>}
    </div>}

    {/* -- Daily notes tab -- */}
    {memTab==="daily"&&<div style={{display:"flex",flexDirection:"column",gap:8}}>
      {dailyDates.length===0&&<div style={{fontSize:11,color:"var(--text-muted)"}}>No daily notes yet. Activity is recorded automatically.</div>}
      {dailyDates.length>0&&<>
        <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>{dailyDates.map(d=><button key={d} onClick={async()=>{setDailyDate(d);try{const r=await sdk.memory.daily(d);setDailyContent(r.content||"")}catch{}}} style={{padding:"3px 8px",fontSize:10,fontWeight:dailyDate===d?700:500,border:dailyDate===d?"1px solid var(--accent)":"1px solid var(--border)",borderRadius:4,background:dailyDate===d?"var(--accent-dim)":"transparent",color:dailyDate===d?"var(--accent)":"var(--text-dim)",cursor:"pointer"}}>{d}</button>)}</div>
        {dailyContent&&<pre style={{fontSize:11,whiteSpace:"pre-wrap",color:"var(--text-dim)",background:"var(--bg-input)",padding:10,borderRadius:6,maxHeight:300,overflow:"auto",margin:0}}>{dailyContent}</pre>}
      </>}
    </div>}

    {/* -- Sessions tab -- */}
    {memTab==="sessions"&&<div style={{display:"flex",flexDirection:"column",gap:6}}>
      {sessionSummaries.length===0&&<div style={{fontSize:11,color:"var(--text-muted)"}}>No compacted sessions yet. Sessions are auto-compacted when context exceeds threshold.</div>}
      {sessionSummaries.map(s=><div key={s.session_id} className="card" style={{padding:10}}><div style={{fontSize:10,fontWeight:700,color:"var(--accent)",marginBottom:2}}>{s.session_id}</div><div style={{fontSize:11,color:"var(--text-dim)"}}>{s.summary||"(empty)"}</div></div>)}
    </div>}

    {/* -- Semantic search tab -- */}
    {memTab==="semantic"&&<div style={{display:"flex",flexDirection:"column",gap:8}}>
      <form onSubmit={async e=>{e.preventDefault();if(!memQuery.trim())return;try{setMemResults((await sdk.memory.semantic.search(memQuery,5)).results||[])}catch{}}} style={{display:"flex",gap:5}}>
        <input placeholder="Search semantic memory..." value={memQuery} onChange={e=>setMemQuery(e.target.value)} style={{flex:1}}/>
        <button type="submit" className="btn-primary" disabled={!memQuery.trim()}>Search</button>
      </form>
      {memResults.map((r,i)=><div key={r.memory?.id||i} className="item-row"><span className="badge badge-info" style={{fontSize:9}}>{Math.round(r.score*100)}%</span><span style={{fontSize:11,flex:1,marginLeft:4}}>{r.text}</span><button className="btn-danger" style={{fontSize:10,height:20}} onClick={()=>act(async()=>{await sdk.memory.semantic.delete(r.memory?.id);setMemResults((await sdk.memory.semantic.search(memQuery,5)).results||[])},"OK")}>&#10005;</button></div>)}
    </div>}
  </div>);
}
