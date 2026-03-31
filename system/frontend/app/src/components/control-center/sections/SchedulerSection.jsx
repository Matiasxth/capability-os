import React, { useEffect, useState } from "react";
import sdk from "../../../sdk";

export default function SchedulerSection({ toast, act }) {
  const [schTasks, setSchTasks] = useState([]);
  const [schStatus, setSchStatus] = useState({});
  const [schLog, setSchLog] = useState([]);
  const [schForm, setSchForm] = useState({description:"",schedule:"daily_09:00",action_message:"",agent_id:"",channel:"",custom_cron:""});
  const [agents, setAgents] = useState([]);
  const [logFilter, setLogFilter] = useState("");
  const [useCustomCron, setUseCustomCron] = useState(false);

  useEffect(() => {
    sdk.system.scheduler.listTasks().then(r => setSchTasks(r.tasks || [])).catch(() => {});
    sdk.system.scheduler.status().then(setSchStatus).catch(() => {});
    sdk.system.scheduler.log().then(r => setSchLog(r.log || [])).catch(() => {});
    sdk.agents.list().then(r => setAgents(r.agents || [])).catch(() => {});
  }, []);

  return (
    <div style={{display:"flex",flexDirection:"column",gap:12}}>
      <h2>Scheduler</h2>
      <div className="kpi-grid" style={{gridTemplateColumns:"1fr 1fr 1fr"}}>
        <div className="kpi-card"><div className="kpi-label">Status</div><div style={{fontSize:13,fontWeight:600}}>{schStatus.running?"Active":"Off"}</div></div>
        <div className="kpi-card"><div className="kpi-label">Tasks</div><div style={{fontSize:13,fontWeight:600}}>{schStatus.queue_size||0}</div></div>
        <div className="kpi-card"><div className="kpi-label">Executions</div><div style={{fontSize:13,fontWeight:600}}>{schStatus.total_executions||0}</div></div>
      </div>

      {schTasks.map(t => (
        <div key={t.id} className="card" style={{padding:"10px 14px",display:"flex",alignItems:"center",gap:8}}>
          <button style={{padding:0,border:"none",background:"none",cursor:"pointer",fontSize:16}} title={t.enabled?"Disable":"Enable"} onClick={async () => { try { await sdk.system.scheduler.updateTask(t.id,{enabled:!t.enabled}); toast(t.enabled?"Disabled":"Enabled"); sdk.system.scheduler.listTasks().then(r => setSchTasks(r.tasks || [])) } catch(e) { toast(e.message,"error") } }}>{t.enabled?"\u{1f7e2}":"\u26AB"}</button>
          <div style={{flex:1,opacity:t.enabled?1:0.5}}>
            <div style={{fontSize:12,fontWeight:600}}>{t.description}</div>
            <div style={{fontSize:10,color:"var(--text-muted)"}}>
              {t.schedule} {t.agent_id?`[${t.agent_id}] `:""}{t.channel?`\u2192 ${t.channel}`:""} {t.last_run?`| Last: ${t.last_run.slice(11,19)}`:""}
              {t.next_run && <span style={{color:"var(--accent)",marginLeft:4}}>Next: {t.next_run.slice(11,16)}</span>}
            </div>
            {t.last_result && <div style={{fontSize:10,color:t.last_result.status==="success"?"var(--success)":"var(--error)",marginTop:1}}>{t.last_result.status}: {(t.last_result.response||t.last_result.error||"").slice(0,80)}</div>}
          </div>
          <button style={{fontSize:10,height:24}} onClick={() => act(async () => { const r = await sdk.system.scheduler.runNow(t.id); toast(r.status==="success"?"Executed":"Error") }, "Executed")}>Run</button>
          <button style={{fontSize:10,height:24,color:"var(--error)"}} onClick={() => act(async () => { await sdk.system.scheduler.deleteTask(t.id); setSchTasks(s => s.filter(x => x.id !== t.id)) }, "Deleted")}>Del</button>
        </div>
      ))}

      <div className="card" style={{padding:14}}>
        <h4 style={{margin:"0 0 8px"}}>Create Task</h4>
        <input value={schForm.description} onChange={e => setSchForm({...schForm,description:e.target.value})} style={{width:"100%",height:28,fontSize:12,marginBottom:6}} placeholder="Task description"/>
        <div style={{display:"flex",gap:6,marginBottom:6}}>
          {!useCustomCron ? <select value={schForm.schedule} onChange={e => setSchForm({...schForm,schedule:e.target.value})} style={{flex:1,height:28,fontSize:11}}>
            <option value="every_30min">Every 30 min</option>
            <option value="every_hour">Every hour</option>
            <option value="every_4hours">Every 4 hours</option>
            <option value="daily_09:00">Daily 09:00</option>
            <option value="daily_18:00">Daily 18:00</option>
            <option value="daily_21:00">Daily 21:00</option>
          </select> : <input value={schForm.custom_cron} onChange={e => setSchForm({...schForm,custom_cron:e.target.value,schedule:e.target.value})} placeholder="*/30 * * * * (cron)" style={{flex:1,height:28,fontSize:11,fontFamily:"var(--font-mono)"}}/>}
          <button type="button" style={{fontSize:9,height:28,padding:"0 8px",whiteSpace:"nowrap"}} onClick={()=>setUseCustomCron(!useCustomCron)}>{useCustomCron?"Presets":"Cron"}</button>
          <select value={schForm.channel} onChange={e => setSchForm({...schForm,channel:e.target.value})} style={{flex:1,height:28,fontSize:11}}>
            <option value="">No channel</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="telegram">Telegram</option>
            <option value="slack">Slack</option>
            <option value="discord">Discord</option>
          </select>
          <select value={schForm.agent_id||""} onChange={e => setSchForm({...schForm,agent_id:e.target.value})} style={{flex:1,height:28,fontSize:11}}>
            <option value="">Default agent</option>
            {(agents||[]).map(a => <option key={a.id} value={a.id}>{a.emoji} {a.name}</option>)}
          </select>
        </div>
        <textarea value={schForm.action_message} onChange={e => setSchForm({...schForm,action_message:e.target.value})} style={{width:"100%",height:50,fontSize:11,resize:"vertical",marginBottom:6}} placeholder="Message for the agent (what to do)"/>
        <button className="btn-primary" style={{width:"100%",height:30,fontSize:12}} onClick={async () => { if (!schForm.description.trim()) return; try { await sdk.system.scheduler.createTask(schForm); toast("Task created"); setSchForm({description:"",schedule:"daily_09:00",action_message:"",agent_id:"",channel:""}); sdk.system.scheduler.listTasks().then(r => setSchTasks(r.tasks || [])) } catch(e) { toast(e.message,"error") } }}>Create Task</button>
      </div>

      {schLog.length > 0 && <div className="card" style={{padding:14}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
          <h4 style={{margin:0}}>Recent Executions</h4>
          <select value={logFilter} onChange={e => setLogFilter(e.target.value)} style={{height:22,fontSize:10}}>
            <option value="">All tasks</option>
            {schTasks.map(t => <option key={t.id} value={t.id}>{t.description?.slice(0,30)}</option>)}
          </select>
        </div>
        {schLog.filter(l => !logFilter || l.task_id === logFilter).slice(-15).reverse().map((l,i) => <div key={i} style={{fontSize:11,padding:"3px 0",borderBottom:"1px solid var(--border)",display:"flex",gap:6}}>
          <span style={{color:"var(--text-muted)"}}>{(l.timestamp||"").slice(11,19)}</span>
          <span style={{color:l.status==="success"?"var(--success)":"var(--error)"}}>{l.status}</span>
          <span style={{flex:1,color:"var(--text-dim)"}}>{l.detail?.slice(0,80)}</span>
        </div>)}
      </div>}
    </div>
  );
}
