import React, { useEffect, useState } from "react";
import sdk from "../../../sdk";

export default function AutoGrowthSection({ toast, act }) {
  const [gaps, setGaps] = useState([]);
  const [autoProposals, setAutoProposals] = useState([]);

  async function refresh() {
    try {
      const [g, p] = await Promise.all([sdk.growth.gaps.pending(), sdk.growth.proposals.list()]);
      setGaps(g.gaps || []);
      setAutoProposals(p.proposals || []);
    } catch {}
  }
  useEffect(() => { refresh(); }, []);

  const sb=s=>({existing_tool:"badge-success",browser:"badge-info",cli:"badge-info",python:"badge-warning",nodejs:"badge-warning",not_implementable:"badge-error"}[s]||"badge-neutral");

  return (<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Auto-Growth</h2>
    {gaps.length>0&&gaps.map(g=><div key={g.capability_id} className="card" style={{padding:7}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><span className="mono" style={{fontSize:10}}>{g.capability_id} <span className="dim">({g.frequency}x)</span></span><div style={{display:"flex",gap:3}}><button style={{fontSize:10,height:20}} onClick={()=>act(async()=>{const r=await sdk.growth.gaps.analyze(g.gap_ids[0]);toast(`${r.analysis?.strategy}`)},"OK")}>?</button><button className="btn-primary" style={{fontSize:10,padding:"1px 6px",height:20}} onClick={()=>act(async()=>{await sdk.growth.gaps.generate(g.gap_ids[0]);await refresh()},"Gen")}>Gen</button></div></div></div>)}
    {autoProposals.length>0&&<h4>Proposals</h4>}
    {autoProposals.map(p=><div key={p.proposal_id} className="card" style={{padding:7}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><div><span className={`badge ${sb(p.strategy)}`}>{p.strategy}</span><span className="mono" style={{marginLeft:4,fontSize:10}}>{p.contract?.id||p.proposal_id}</span>{p.validated&&<span className="badge badge-success" style={{marginLeft:3}}>✓</span>}</div><div style={{display:"flex",gap:3}}>{p.validated&&<button className="btn-primary" style={{fontSize:10,padding:"1px 6px",height:20}} onClick={()=>act(async()=>{await sdk.growth.proposals.approve(p.proposal_id);await refresh()},"OK")}>Install</button>}<button style={{fontSize:10,height:20}} onClick={()=>act(async()=>{await sdk.growth.proposals.regenerate(p.proposal_id);await refresh()},"OK")}>↻</button><button className="btn-ghost" style={{fontSize:10,height:20}} onClick={()=>act(async()=>{await sdk.growth.proposals.reject(p.proposal_id);await refresh()},"OK")}>✕</button></div></div>
      {p.code&&<details style={{marginTop:3}}><summary style={{cursor:"pointer",fontSize:10,color:"var(--text-muted)"}}>{p.runtime} code</summary><pre style={{marginTop:3,maxHeight:140,overflow:"auto"}}>{p.code}</pre></details>}
    </div>)}
  </div>);
}
