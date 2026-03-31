import React, { useEffect, useState } from "react";
import sdk from "../../../sdk";

export default function OptimizeSection({ toast, act }) {
  const [gaps, setGaps] = useState([]);
  const [optimizations, setOptimizations] = useState([]);

  async function refresh() {
    try {
      const [g, o] = await Promise.all([sdk.growth.gaps.pending(), sdk.growth.optimizations.pending()]);
      setGaps(g.gaps || []);
      setOptimizations(o.proposals || []);
    } catch {}
  }
  useEffect(() => { refresh(); }, []);

  return (<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Optimize</h2>
    <h4>Gaps {gaps.length>0&&<span className="badge badge-warning" style={{marginLeft:3}}>{gaps.length}</span>}</h4>
    {gaps.length===0&&<p className="dim" style={{fontSize:11}}>None.</p>}
    {gaps.map(g=><div key={g.capability_id} className="item-row"><div className="item-row-info"><span className="mono" style={{fontSize:10}}>{g.capability_id}</span></div><div className="item-row-actions"><button className="btn-primary" style={{fontSize:10,padding:"1px 6px",height:20}} onClick={()=>act(()=>sdk.growth.gaps.generate(g.gap_ids[0]),"Gen")}>Gen</button><button className="btn-ghost" style={{fontSize:10,height:20}} onClick={()=>act(()=>sdk.growth.gaps.reject(g.gap_ids[0]),"OK")}>✕</button></div></div>)}
    <h4>Optimizations {optimizations.length>0&&<span className="badge badge-info" style={{marginLeft:3}}>{optimizations.length}</span>}</h4>
    {optimizations.map(o=><div key={o.id} className="card" style={{padding:7}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><span className="mono" style={{fontSize:10}}>{o.capability_id} <span className="badge badge-neutral">{o.suggestion_type}</span></span><div style={{display:"flex",gap:3}}><button className="btn-primary" style={{fontSize:10,padding:"1px 6px",height:20}} onClick={()=>act(()=>sdk.growth.optimizations.approve(o.id,o.proposed_contract),"OK")}>✓</button><button className="btn-ghost" style={{fontSize:10,height:20}} onClick={()=>act(()=>sdk.growth.optimizations.reject(o.id),"OK")}>✕</button></div></div></div>)}
  </div>);
}
