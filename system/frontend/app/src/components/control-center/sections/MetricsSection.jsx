import React, { useEffect, useState } from "react";
import sdk from "../../../sdk";

export default function MetricsSection({ toast }) {
  const [metrics, setMetrics] = useState(null);

  useEffect(() => {
    async function refreshMetrics() {
      try { const r = await sdk.memory.metrics(); setMetrics(r.metrics || null); } catch {}
    }
    refreshMetrics();
    const id = setInterval(refreshMetrics, 30000);
    return () => clearInterval(id);
  }, []);

  if (!metrics) return (
    <div style={{display:"flex",flexDirection:"column",gap:6}}>
      <div className="skeleton skeleton-block"/>
      <div className="skeleton skeleton-block"/>
    </div>
  );

  return (<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Metrics</h2>
    <div className="kpi-grid">
      <div className="kpi-card"><div className="kpi-label">Success</div><div className="kpi-value" style={{color:metrics.execution_success_rate>=80?"var(--success)":"var(--error)"}}>{metrics.execution_success_rate}%</div></div>
      <div className="kpi-card"><div className="kpi-label">Avg</div><div className="kpi-value">{metrics.avg_execution_time_ms}<span className="dim" style={{fontSize:10}}>ms</span></div></div>
      <div className="kpi-card"><div className="kpi-label">Fail</div><div className="kpi-value">{metrics.tool_failure_rate}%</div></div>
      <div className="kpi-card"><div className="kpi-label">Total</div><div className="kpi-value">{metrics.total_executions}</div></div>
    </div>
    {Object.keys(metrics.error_rate_by_capability||{}).length>0&&Object.entries(metrics.error_rate_by_capability).sort((a,b)=>b[1]-a[1]).slice(0,3).map(([c,n])=><div key={c} className="item-row"><span className="mono" style={{fontSize:10}}>{c}</span><span className="badge badge-error">{n}</span></div>)}
  </div>);
}
