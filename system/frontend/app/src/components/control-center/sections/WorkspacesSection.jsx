import React, { useEffect, useState } from "react";
import sdk from "../../../sdk";

const colors = ["#00ff88", "#5588ff", "#ffaa00", "#ff4444", "#aa66ff", "#ff88aa"];

export default function WorkspacesSection({ toast, act }) {
  const [wsData, setWsData] = useState([]);
  const [wsDefaultId, setWsDefaultId] = useState(null);
  const [wsName, setWsName] = useState("");
  const [wsPath, setWsPath] = useState("");
  const [wsAccess, setWsAccess] = useState("write");
  const [wsColor, setWsColor] = useState("#00ff88");
  const [wsAnalysis, setWsAnalysis] = useState({});
  const [wsCleanPreview, setWsCleanPreview] = useState(null);
  const [analyzingAll, setAnalyzingAll] = useState(false);

  async function refreshWorkspaces() {
    try {
      const r = await sdk.workspaces.list();
      setWsData(r.workspaces || []);
      setWsDefaultId(r.default_id || null);
    } catch {}
  }

  useEffect(() => { refreshWorkspaces(); }, []);

  // Aggregated health summary
  const allAnalyzed = wsData.length > 0 && wsData.every(w => wsAnalysis[w.id]);
  const totalIssues = Object.values(wsAnalysis).reduce((sum, a) => sum + (a.issues || []).length, 0);
  const issuesBySeverity = Object.values(wsAnalysis).flatMap(a => a.issues || []).reduce((acc, iss) => {
    acc[iss.severity] = (acc[iss.severity] || 0) + 1; return acc;
  }, {});
  const totalFiles = Object.values(wsAnalysis).reduce((sum, a) => sum + (a.stats?.total_files || 0), 0);
  const allLangs = Object.values(wsAnalysis).flatMap(a => Object.entries(a.stats?.languages || {})).reduce((acc, [l, c]) => {
    acc[l] = (acc[l] || 0) + c; return acc;
  }, {});

  async function analyzeAll() {
    setAnalyzingAll(true);
    try {
      const results = await Promise.all(wsData.map(async w => {
        try { return { id: w.id, data: await sdk.workspaces.analyze(w.id) }; }
        catch { return { id: w.id, data: null }; }
      }));
      const map = {};
      results.forEach(r => { if (r.data) map[r.id] = r.data; });
      setWsAnalysis(prev => ({ ...prev, ...map }));
      toast(`Analyzed ${results.filter(r => r.data).length} workspaces`);
    } catch (e) { toast(e.message, "error"); }
    finally { setAnalyzingAll(false); }
  }

  return (<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Workspaces</h2>

    {/* Health Dashboard */}
    <div className="card" style={{padding:12}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
        <h4 style={{margin:0,fontSize:12}}>Health Overview</h4>
        <button style={{fontSize:10,height:24}} disabled={analyzingAll || wsData.length === 0} onClick={analyzeAll}>{analyzingAll ? "Analyzing..." : "Analyze All"}</button>
      </div>
      {allAnalyzed ? (<>
        <div className="kpi-grid" style={{gridTemplateColumns:"1fr 1fr 1fr 1fr"}}>
          <div className="kpi-card"><div className="kpi-label">Workspaces</div><div className="kpi-value">{wsData.length}</div></div>
          <div className="kpi-card"><div className="kpi-label">Total Files</div><div className="kpi-value">{totalFiles}</div></div>
          <div className="kpi-card"><div className="kpi-label">Issues</div><div className="kpi-value" style={{color:totalIssues > 0 ? "var(--warning)" : "var(--success)"}}>{totalIssues}</div></div>
          <div className="kpi-card"><div className="kpi-label">Languages</div><div className="kpi-value">{Object.keys(allLangs).length}</div></div>
        </div>
        {totalIssues > 0 && <div style={{display:"flex",gap:6,marginTop:6,flexWrap:"wrap"}}>
          {Object.entries(issuesBySeverity).sort(([,a],[,b]) => b - a).map(([sev, cnt]) =>
            <span key={sev} className={`badge ${sev === "high" ? "badge-error" : sev === "medium" ? "badge-warning" : "badge-neutral"}`}>{sev}: {cnt}</span>
          )}
        </div>}
        {Object.keys(allLangs).length > 0 && <div style={{display:"flex",gap:4,marginTop:6,flexWrap:"wrap"}}>
          {Object.entries(allLangs).sort(([,a],[,b]) => b - a).slice(0, 8).map(([lang, cnt]) =>
            <span key={lang} className="badge badge-info">{lang}: {cnt}</span>
          )}
        </div>}
      </>) : <div style={{fontSize:11,color:"var(--text-muted)"}}>Click "Analyze All" to see aggregated health.</div>}
    </div>
    {wsData.map(w=><div key={w.id}>
      <div className="item-row"><div className="item-row-info"><div style={{display:"flex",alignItems:"center",gap:5}}><span className="dot" style={{background:w.color||"#00ff88"}}/><span style={{fontWeight:500,fontSize:12}}>{w.name}</span>{w.id===wsDefaultId&&<span className="badge badge-success">default</span>}<span className="badge badge-neutral">{w.access==="write"?"✏️":"👁️"}</span></div><div className="dim" style={{fontSize:10,marginTop:1}}>{w.path}</div></div><div className="item-row-actions">
        <button style={{fontSize:10,height:22}} onClick={async()=>{try{const r=await sdk.workspaces.analyze(w.id);setWsAnalysis(p=>({...p,[w.id]:r}))}catch(e){toast(e.message,"error")}}}>Analyze</button>
        <button style={{fontSize:10,height:22}} onClick={async()=>{try{const r=await sdk.workspaces.autoClean(w.id,true);setWsCleanPreview({wsId:w.id,...r})}catch(e){toast(e.message,"error")}}}>Clean</button>
        <button style={{fontSize:10,height:22}} onClick={async()=>{try{await sdk.workspaces.generateReadme(w.id);toast("README generated")}catch(e){toast(e.message,"error")}}}>README</button>
        {w.id!==wsDefaultId&&<button style={{fontSize:10,height:22}} onClick={()=>act(async()=>{await sdk.workspaces.setDefault(w.id);await refreshWorkspaces()},"Default set")}>Default</button>}<button className="btn-danger" style={{fontSize:10,height:22}} onClick={()=>act(async()=>{await sdk.workspaces.remove(w.id);await refreshWorkspaces()},"Removed")}>✕</button></div></div>
      {wsAnalysis[w.id]&&<div className="card" style={{padding:10,margin:"4px 0 8px",fontSize:11}}>
        <div style={{display:"flex",gap:6,marginBottom:6,flexWrap:"wrap"}}>{wsAnalysis[w.id].stats&&<><span className="badge badge-neutral">{wsAnalysis[w.id].stats.total_files||0} files</span><span className="badge badge-neutral">{wsAnalysis[w.id].stats.total_size_human||"?"}</span>{Object.entries(wsAnalysis[w.id].stats.languages||{}).slice(0,3).map(([l,c])=><span key={l} className="badge badge-info">{l}: {c}</span>)}</>}</div>
        {(wsAnalysis[w.id].issues||[]).map((iss,i)=><div key={i} style={{padding:"2px 0",display:"flex",gap:6,alignItems:"center"}}><span className={`badge ${iss.severity==="high"?"badge-error":iss.severity==="medium"?"badge-warning":"badge-neutral"}`}>{iss.severity}</span><span>{iss.detail||iss.message}</span></div>)}
        {(wsAnalysis[w.id].suggestions||[]).map((s,i)=><div key={i} style={{padding:"1px 0",color:"var(--text-muted)"}}>💡 {s}</div>)}
        {!(wsAnalysis[w.id].issues||[]).length&&<span style={{color:"var(--success)"}}>No issues found</span>}
      </div>}
    </div>)}
    {wsCleanPreview&&<div className="card" style={{padding:12,margin:"6px 0",border:"1px solid var(--warning)"}}>
      <h4 style={{margin:"0 0 6px",color:"var(--warning)"}}>Auto-Clean Preview</h4>
      <div style={{fontSize:11,marginBottom:6}}>{(wsCleanPreview.files_to_remove||[]).length} files to remove, {(wsCleanPreview.actions||[]).length} actions</div>
      {(wsCleanPreview.files_to_remove||wsCleanPreview.actions||[]).slice(0,10).map((f,i)=><div key={i} style={{fontSize:10,color:"var(--text-muted)",padding:"1px 0"}}>{typeof f==="string"?f:f.detail||f.action}</div>)}
      <div style={{display:"flex",gap:6,marginTop:8}}>
        <button className="btn-primary" style={{fontSize:11,height:26}} onClick={async()=>{try{await sdk.workspaces.autoClean(wsCleanPreview.wsId,false);toast("Cleaned");setWsCleanPreview(null)}catch(e){toast(e.message,"error")}}}>Confirm Clean</button>
        <button style={{fontSize:11,height:26}} onClick={()=>setWsCleanPreview(null)}>Cancel</button>
      </div>
    </div>}
    {wsData.length===0&&<p className="dim" style={{fontSize:11}}>No workspaces.</p>}
    <h4>Add</h4>
    <form onSubmit={async e=>{e.preventDefault();await act(async()=>{await sdk.workspaces.add(wsName,wsPath,wsAccess,"*",wsColor);await refreshWorkspaces()},"Added");setWsName("");setWsPath("")}} style={{display:"flex",flexDirection:"column",gap:5}}>
      <div className="form-grid">
        <div className="form-group"><label className="form-label">Name</label><input value={wsName} onChange={e=>setWsName(e.target.value)} placeholder="My Project" required/></div>
        <div className="form-group"><label className="form-label">Path</label><input value={wsPath} onChange={e=>setWsPath(e.target.value)} placeholder="C:\projects\app" required/></div>
        <div className="form-group"><label className="form-label">Access</label><select value={wsAccess} onChange={e=>setWsAccess(e.target.value)}><option value="write">Write</option><option value="read">Read</option><option value="none">None</option></select></div>
        <div className="form-group"><label className="form-label">Color</label><div style={{display:"flex",gap:3}}>{colors.map(c=><button key={c} type="button" style={{width:18,height:18,borderRadius:3,background:c,border:wsColor===c?"2px solid white":"2px solid transparent",padding:0,cursor:"pointer"}} onClick={()=>setWsColor(c)}/>)}</div></div>
      </div>
      <button type="submit" className="btn-primary" disabled={!wsName||!wsPath}>Add Workspace</button>
    </form>
  </div>);
}
