import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  chatMessage, clearAllMemory, deleteHistoryEntry, executeCapability,
  getExecution, getExecutionEvents, getMemoryContext, getMemoryHistory,
  getSession, listCapabilities, planIntent, saveChatSession
} from "../api";
import OutputRenderer from "../components/OutputRenderer";
import { useWorkspaceState } from "../state/useWorkspaceState";

/* Template resolution (unchanged logic) */
const TMPL = /^\{\{([a-zA-Z0-9_.]+)\}\}$/;
function resolvePath(p,ctx){const s=p.split("."),r=s[0];if(!["inputs","state","steps","runtime"].includes(r))throw new Error(`Bad '${r}'.`);let n=ctx[r];for(let i=1;i<s.length;i++){const k=s[i];if(n==null||typeof n!=="object"||!(k in n))throw new Error(`Unresolved '{{${p}}}'.`);n=n[k]}return n}
function resolve(v,c){if(typeof v==="string"){const m=v.match(TMPL);if(!m)return v;return resolvePath(m[1],c)}if(Array.isArray(v))return v.map(x=>resolve(x,c));if(v&&typeof v==="object"){const o={};for(const[k,x]of Object.entries(v))o[k]=resolve(x,c);return o}return v}

function greeting(name){const h=new Date().getHours();const g=h<6?"Working late":h<12?"Good morning":h<18?"Good afternoon":"Good evening";return `${g}, ${name}`}

export default function Workspace({ activeWorkspace, userName }) {
  const {intent,setIntent,plan,setPlan,planValidationErrors,setPlanValidationErrors,execution,setExecution,logs,setLogs}=useWorkspaceState();
  const [capabilities,setCapabilities]=useState([]);
  const [freqCaps,setFreqCaps]=useState([]);
  const [loadingPlan,setLoadingPlan]=useState(false);
  const [runningPlan,setRunningPlan]=useState(false);
  const [planExecuted,setPlanExecuted]=useState(false);
  const [errorMessage,setErrorMessage]=useState("");
  const [history,setHistory]=useState([]);
  const [messages,setMessages]=useState([]);
  const [suggestedAction,setSuggestedAction]=useState(null);
  const [currentSessionId,setCurrentSessionId]=useState(()=>"chat_"+Date.now());
  const [deletingId,setDeletingId]=useState(null);
  const [confirmClear,setConfirmClear]=useState(false);
  const [toast,setToast]=useState(null);
  const sessionDirtyRef=useRef(false);
  const messagesRef=useRef(messages);
  const threadRef=useRef(null);

  useEffect(()=>{let o=false;
    listCapabilities().then(r=>{if(!o)setCapabilities(r.capabilities||[])}).catch(()=>{});
    getMemoryHistory().then(r=>{if(!o){const valid=(r.history||[]).filter(h=>h.intent&&h.intent.trim().length>0&&h.intent!=="session"&&h.intent!=="New session");setHistory(valid.slice(0,10).map(h=>({id:h.execution_id,intent:h.intent,status:h.status==="ready"?"success":h.status,duration_ms:h.duration_ms,time:h.timestamp,plan_steps:h.plan_steps||null,step_runs:h.step_runs||null,error_message:h.error_message||null,failed_step:h.failed_step||null,final_output:h.key_outputs||{},chat_response:h.chat_response||null,chat_messages:h.chat_messages||null,message_count:h.message_count||0,isChat:h.capability_id==="chat",hasExecution:!!h.has_execution})))}}).catch(()=>{});
    getMemoryContext().then(r=>{if(!o)setFreqCaps((r.context?.frequent_capabilities||[]).slice(0,6))}).catch(()=>{});
    return()=>{o=true};
  },[]);

  useEffect(()=>{messagesRef.current=messages;if(threadRef.current)threadRef.current.scrollTop=threadRef.current.scrollHeight},[messages]);

  function addMsg(role,content,meta){setMessages(p=>[...p,{id:Date.now()+Math.random(),role,content,meta,ts:new Date()}])}

  function showToast(msg){setToast(msg);setTimeout(()=>setToast(null),2500)}

  const flushSession=useCallback(()=>{
    if(!sessionDirtyRef.current)return;
    setMessages(cur=>{
      const visible=cur.filter(m=>!m.meta?.loading&&!m.meta?.executing);
      const firstUser=visible.find(m=>m.role==="user"&&typeof m.content==="string"&&m.content.trim().length>0);
      if(!firstUser||visible.length<2)return cur;
      sessionDirtyRef.current=false;
      let hasExec=false,lastStatus="success",lastDur=0;
      const compact=visible.map(m=>{
        if(m.meta?.execution){
          hasExec=true;lastStatus=m.meta.execution.status||"success";lastDur=m.meta.execution.duration_ms||0;
          return{role:"assistant",content:"Execution: "+m.meta.execution.status,type:"execution",execution:m.meta.execution};
        }
        if(m.meta?.plan)return{role:"assistant",content:"Plan: "+m.meta.plan.steps?.map(s=>s.capability).join(", "),type:"plan",plan:m.meta.plan};
        if(m.meta?.error)return{role:"assistant",content:m.content,type:"error"};
        return{role:m.role==="user"?"user":"assistant",content:typeof m.content==="string"?m.content:JSON.stringify(m.content),type:"chat"};
      });
      const intentText=firstUser.content;
      const sid=currentSessionId;
      saveChatSession(sid,intentText,compact,lastDur).then(()=>{
        const entry={id:sid,intent:intentText,status:lastStatus,duration_ms:lastDur,time:new Date().toISOString(),isChat:!hasExec,hasExecution:hasExec,chat_messages:compact,message_count:compact.length};
        setHistory(p=>{
          const idx=p.findIndex(h=>h.id===sid);
          if(idx>=0){const u=[...p];u[idx]=entry;return u}
          return[entry,...p].slice(0,10);
        });
      }).catch(()=>{});
      return cur;
    });
  },[currentSessionId]);

  function getConversationHistory(msgs,max=6){
    return msgs.filter(m=>!m.meta?.loading&&!m.meta?.executing).slice(-max).map(m=>{
      const role=m.role==="user"?"user":"assistant";
      let content=m.content;
      if(m.meta?.plan)content="I suggest a plan: "+m.meta.plan.steps.map(s=>s.capability).join(", ");
      else if(m.meta?.execution)content=m.meta.execution.status==="success"?"Execution completed successfully.":"Execution failed: "+(m.meta.execution.error_message||"error");
      const entry={role,content};
      if(m.meta?.suggestedAction)entry.suggested_action=m.meta.suggestedAction;
      return entry;
    });
  }

  function restoreSession(h){
    flushSession();
    const restored=[];
    const ts=new Date(h.time||Date.now());
    if(h.id)setCurrentSessionId(h.id);
    setPlan(null);setExecution(null);setPlanExecuted(false);sessionDirtyRef.current=false;
    // Unified format: chat_messages with type field
    if(h.chat_messages&&h.chat_messages.length>0){
      let restoredHasExec=false;
      h.chat_messages.forEach((m,i)=>{
        if(m.type==="execution"&&m.execution){
          restoredHasExec=true;
          setExecution(m.execution);
          restored.push({id:Date.now()+i,role:"system",content:"result",meta:{execution:m.execution},ts});
        }else if(m.type==="plan"&&m.plan){
          setPlan(m.plan);
          restored.push({id:Date.now()+i,role:"system",content:"plan",meta:{plan:m.plan},ts});
        }else if(m.type==="error"){
          restored.push({id:Date.now()+i,role:"system",content:m.content,meta:{error:true},ts});
        }else{
          restored.push({id:Date.now()+i,role:m.role==="user"?"user":"system",content:m.content,meta:{},ts});
        }
      });
      if(restoredHasExec)setPlanExecuted(true);
      if(restored.length>0){setMessages(restored);setIntent("");setErrorMessage("");return}
    }
    // Legacy format: separate plan_steps/step_runs fields
    if(h.intent)restored.push({id:Date.now()+1,role:"user",content:h.intent,ts});
    if(h.chat_response&&!h.plan_steps){
      restored.push({id:Date.now()+2,role:"system",content:h.chat_response,meta:{},ts});
    }
    if(h.plan_steps&&h.plan_steps.length>0){
      const restoredPlan={steps:h.plan_steps};
      setPlan(restoredPlan);setPlanValidationErrors([]);
      restored.push({id:Date.now()+2,role:"system",content:"plan",meta:{plan:restoredPlan},ts});
    }
    if(h.step_runs){
      const ex={status:h.status,current_step:"",started_at:h.time,ended_at:null,duration_ms:h.duration_ms||0,failed_step:h.failed_step||null,error_code:null,error_message:h.error_message||null,final_output:h.final_output||{},step_runs:h.step_runs};
      setExecution(ex);setPlanExecuted(true);
      restored.push({id:Date.now()+3,role:"system",content:"result",meta:{execution:ex},ts});
    }
    if(restored.length===0){setIntent(h.intent||"");setMessages([]);return}
    setMessages(restored);setIntent("");setErrorMessage(h.error_message||"");
  }

  function navigateDir(dirPath){
    if(!dirPath)return;
    handleSubmit("list files in "+dirPath);
  }

  async function handleSubmit(text){
    if(!text?.trim())return;
    const q=text.trim();setIntent("");
    addMsg("user",q);
    setLoadingPlan(true);setErrorMessage("");
    addMsg("system","Thinking...",{loading:true});
    try{
      const hist=getConversationHistory(messages);
      const cls=await chatMessage(q,userName,hist).catch(()=>({type:"action"}));
      if(cls.type==="chat"){
        const chatResp=cls.response||"How can I help?";
        setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:chatResp,meta:{},ts:new Date()};return c});
        setSuggestedAction(null);
        sessionDirtyRef.current=true;
        setLoadingPlan(false);return;
      }
      // If there's a suggested_action from a prior chat and user confirmed, use it as the intent
      const actionIntent=(cls.suggested_action&&suggestedAction)?suggestedAction:q;
      setSuggestedAction(null);
      setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now()+.1,role:"system",content:"Analyzing your request...",meta:{loading:true},ts:new Date()};return c});
      const r=await planIntent(actionIntent,hist);setPlan(r);setPlanValidationErrors(Array.isArray(r.errors)?r.errors:[]);setPlanExecuted(false);
      setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:"plan",meta:{plan:r},ts:new Date()};return c});
      sessionDirtyRef.current=true;
    }catch(e){
      const msg=e.payload?.error_message||e.message||"Plan failed.";
      setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:msg,meta:{error:true},ts:new Date()};return c});
      setErrorMessage(msg);
    }finally{setLoadingPlan(false)}
  }

  async function runPlan(){
    if(!plan?.steps?.length)return;setRunningPlan(true);setErrorMessage("");setLogs([]);
    addMsg("system","Executing...",{executing:true});
    const t0=new Date().toISOString(),runs=[],agg=[],ctx={inputs:{},state:{},steps:{},runtime:{}};
    let st="running",fail=null,ec=null,em=null,fo={};
    setExecution({status:"running",current_step:plan.steps[0].step_id,started_at:t0,ended_at:null,duration_ms:0,failed_step:null,error_code:null,error_message:null,final_output:{},step_runs:[]});
    for(const step of plan.steps){
      const run={step_id:step.step_id,capability:step.capability,status:"running",execution_id:null,final_output:{},error_code:null,error_message:null};runs.push(run);
      setExecution(p=>({...p,status:"running",current_step:step.step_id,step_runs:[...runs]}));
      try{
        const res=await executeCapability(step.capability,resolve(step.inputs||{},ctx));
        run.execution_id=res.execution_id||null;run.status=res.status;run.final_output=res.final_output||{};run.error_code=res.error_code||null;run.error_message=res.error_message||null;
        let latest=res;
        if(res.execution_id){latest=await getExecution(res.execution_id);const ev=await getExecutionEvents(res.execution_id);agg.push(...(ev.events||[]).map(e=>({...e,step_id:step.step_id})));setLogs([...agg])}
        else{agg.push(...(res.runtime?.logs||[]).map(e=>({...e,step_id:step.step_id})));setLogs([...agg])}
        ctx.steps[step.step_id]={outputs:latest.final_output||{}};Object.assign(ctx.state,latest.final_output||{});fo=latest.final_output||{};
        if(res.status!=="success"){st="error";fail=step.step_id;ec=res.error_code||"execution_error";em=res.error_message||`Step '${step.step_id}' failed.`;run.status="error";break}
      }catch(e){const a=e.payload||{};st="error";fail=step.step_id;ec=a.error_code||"execution_error";em=a.error_message||e.message||`Step '${step.step_id}' failed.`;run.status="error";run.error_code=ec;run.error_message=em;break}
      setExecution(p=>({...p,current_step:step.step_id,step_runs:[...runs]}));
    }
    const t1=new Date().toISOString(),dur=new Date(t1)-new Date(t0);if(st!=="error")st="success";
    const fin={status:st,current_step:fail||"",started_at:t0,ended_at:t1,duration_ms:dur,failed_step:fail,error_code:ec,error_message:em,final_output:fo,step_runs:[...runs]};
    setExecution(fin);
    setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:"result",meta:{execution:fin},ts:new Date()};return c});
    sessionDirtyRef.current=true;setPlanExecuted(true);
    if(em)setErrorMessage(em);setRunningPlan(false);
  }

  // Flush session after execution completes
  const prevRunning=useRef(false);
  useEffect(()=>{if(prevRunning.current&&!runningPlan&&sessionDirtyRef.current)flushSession();prevRunning.current=runningPlan},[runningPlan,flushSession]);

  // Flush session on page unload — only if there's a real user message
  useEffect(()=>{const h=()=>{if(!sessionDirtyRef.current)return;const hasUser=messagesRef.current.some(m=>m.role==="user"&&typeof m.content==="string"&&m.content.trim().length>0);if(hasUser)flushSession()};window.addEventListener("beforeunload",h);return()=>window.removeEventListener("beforeunload",h)},[flushSession]);

  const steps=plan?.steps||[];const stepRuns=execution?.step_runs||[];
  const hasConv=messages.length>0;

  return (
    <div className="conv-layout">
      {/* SIDEBAR */}
      <aside className="conv-sidebar">
        <div className="conv-sidebar-header">
          <div style={{display:"flex",alignItems:"center",gap:8}}><div style={{width:18,height:18,borderRadius:4,background:"var(--accent)"}}/><span style={{fontSize:13,fontWeight:600,color:"#f0f0f0"}}>CapOS</span></div>
          <button onClick={()=>{flushSession();setMessages([]);setPlan(null);setExecution(null);setErrorMessage("");setSuggestedAction(null);setPlanExecuted(false);sessionDirtyRef.current=false;setCurrentSessionId("chat_"+Date.now())}} style={{width:"100%",height:30,fontSize:12,fontWeight:500,background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.06)",borderRadius:7,color:"var(--text-dim)",cursor:"pointer"}}>+ New session</button>
        </div>
        <div className="conv-sidebar-list">
          <div style={{fontSize:10,fontWeight:600,color:"var(--text-muted)",textTransform:"uppercase",letterSpacing:"0.06em",padding:"8px 10px 4px"}}>Recent</div>
          {history.map((h,i)=><div key={h.id||i} className={`conv-sidebar-item${deletingId===h.id?" session-fade-out":""}`} onClick={()=>restoreSession(h)}><span style={{fontSize:11,width:16,textAlign:"center",flexShrink:0}}>{(h.hasExecution||h.plan_steps||h.step_runs)?"\u26A1":"\uD83D\uDCAC"}</span><span style={{flex:1,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",fontSize:12}}>{h.intent?.slice(0,30)||`Session ${new Date(h.time||Date.now()).toLocaleDateString("es-CL",{day:"numeric",month:"short"})}`}</span>{h.isChat&&h.message_count>0&&<span style={{fontSize:10,color:"var(--text-muted)",flexShrink:0}}>{h.message_count}</span>}{!h.isChat&&h.duration_ms>0&&<span style={{fontSize:10,color:"var(--text-muted)",flexShrink:0}}>{h.duration_ms}ms</span>}<span className={`dot dot-${h.status==="success"?"success":"error"}`}/><button className="session-delete" onClick={e=>{e.stopPropagation();if(!h.id)return;setDeletingId(h.id);setTimeout(()=>{deleteHistoryEntry(h.id).then(()=>{setHistory(p=>p.filter(x=>x.id!==h.id));showToast("Session deleted")}).catch(()=>{showToast("Failed to delete")}).finally(()=>setDeletingId(null))},220)}}>✕</button></div>)}
          {history.length===0&&<div style={{padding:"12px 10px",fontSize:12,color:"var(--text-muted)"}}>No sessions yet.</div>}
        </div>
        <div className="conv-sidebar-footer">
          {history.length>0&&!confirmClear&&<button className="conv-sidebar-clear" onClick={()=>setConfirmClear(true)}>Clear all sessions</button>}
          {confirmClear&&<div style={{display:"flex",gap:6,padding:"2px 10px"}}><button className="conv-sidebar-clear" style={{color:"#ff4444",flex:1}} onClick={()=>{clearAllMemory().catch(()=>{});setHistory([]);setMessages([]);setPlan(null);setExecution(null);setConfirmClear(false);showToast("All sessions cleared")}}>Confirm</button><button className="conv-sidebar-clear" style={{flex:1}} onClick={()=>setConfirmClear(false)}>Cancel</button></div>}
          <div className="conv-sidebar-item" onClick={()=>{window.history.pushState({},"","/control-center");window.dispatchEvent(new PopStateEvent("popstate"))}}><span style={{fontSize:13}}>⚙</span><span>Control Center</span></div>
          <div style={{display:"flex",alignItems:"center",gap:8,padding:"4px 10px"}}><div style={{width:22,height:22,borderRadius:6,background:"#1e1e2e",display:"flex",alignItems:"center",justifyContent:"center",fontSize:11,fontWeight:600,color:"var(--accent)"}}>{(userName||"U").charAt(0).toUpperCase()}</div><span style={{fontSize:12,color:"var(--text-dim)"}}>{userName||"User"}</span></div>
        </div>
      </aside>

      {/* MAIN */}
      <div className="conv-main-col">
        <div ref={threadRef} className="conv-messages">
          <div className="conv-messages-inner">
            {/* STATE 1: Empty */}
            {!hasConv&&(<>
              <div className="conv-greeting">{greeting(userName||"there")} 👋</div>
              <div className="conv-sub">What would you like to do?</div>
              {freqCaps.length>0&&<div className="conv-chips">{freqCaps.map(c=><button key={c} className="conv-chip" onClick={()=>handleSubmit(c.replace(/_/g," "))}>{c.replace(/_/g," ")}</button>)}</div>}
            </>)}

            {/* Conversation */}
            {hasConv&&<div className="conv-thread" style={{paddingTop:24}}>
              {messages.map(msg=>{
                if(msg.role==="user")return<div key={msg.id} className="conv-msg conv-msg-user">{msg.content}</div>;
                const m=msg.meta||{};
                if(m.loading)return<div key={msg.id} className="conv-msg conv-msg-system"><span style={{animation:"pulse 1.5s infinite",color:"var(--text-dim)"}}>{msg.content}</span></div>;
                if(m.error)return<div key={msg.id} className="conv-msg conv-msg-system" style={{borderColor:"rgba(255,68,68,0.15)"}}><span style={{color:"var(--error)"}}>✗ {msg.content}</span></div>;
                if(msg.content==="plan"&&m.plan){const st=m.plan.steps||[];return<div key={msg.id} className="conv-msg conv-msg-system">
                  <div style={{marginBottom:8,fontWeight:500}}>Here's my plan:</div>
                  {st.map((s,i)=><div key={s.step_id} className="conv-step is-ok" style={{opacity:0.8}}><span className="conv-step-icon">{i+1}</span><span className="conv-step-name">{s.step_id} <span style={{color:"var(--text-muted)"}}>→ {s.capability}</span></span></div>)}
                  {planValidationErrors.length>0&&<div style={{color:"var(--error)",fontSize:12,marginTop:6}}>{planValidationErrors.map(e=>e.message).join("; ")}</div>}
                  {!planExecuted&&<button className="btn-primary" style={{marginTop:12,width:"100%",height:36,fontSize:13,borderRadius:10}} onClick={runPlan} disabled={runningPlan||!st.length}>{runningPlan?"Executing...":"Execute plan →"}</button>}
                </div>}
                if(m.executing){return<div key={msg.id} className="conv-msg conv-msg-system">
                  <div style={{marginBottom:6,fontWeight:500,animation:"pulse 1.5s infinite"}}>Executing...</div>
                  {stepRuns.map(run=>{const cls=run.status==="success"?"is-ok":run.status==="error"?"is-err":"is-run";const icon=run.status==="success"?"✓":run.status==="error"?"✗":"⟳";return<div key={run.step_id} className={`conv-step ${cls}`}><span className="conv-step-icon">{icon}</span><span className="conv-step-name">{run.step_id}</span><span className="conv-step-time">{run.capability}</span></div>})}
                </div>}
                if(msg.content==="result"&&m.execution){const ex=m.execution;const allRuns=ex.step_runs||[];const shownOutputs=new Set();return<div key={msg.id} className="conv-msg conv-msg-system">
                  {ex.status==="success"?<div><div style={{color:"var(--success)",fontWeight:500,marginBottom:8}}>✓ Done in {ex.duration_ms}ms</div>{allRuns.map(r=>{const outKey=r.final_output?JSON.stringify(r.final_output):"";const isDup=outKey&&shownOutputs.has(outKey);if(outKey)shownOutputs.add(outKey);return<div key={r.step_id}><div className="conv-step is-ok"><span className="conv-step-icon">✓</span><span className="conv-step-name">{r.step_id} <span style={{color:"var(--text-muted)"}}>→ {r.capability}</span></span></div>{!isDup&&r.final_output&&Object.keys(r.final_output).length>0&&<OutputRenderer output={r.final_output} onNavigate={navigateDir}/>}</div>})}</div>
                  :<div><div style={{color:"var(--error)",fontWeight:500,marginBottom:8}}>✗ Error in "{ex.failed_step}"</div>{(ex.step_runs||[]).map(r=><div key={r.step_id} className={`conv-step ${r.status==="success"?"is-ok":"is-err"}`}><span className="conv-step-icon">{r.status==="success"?"✓":"✗"}</span><span className="conv-step-name">{r.step_id}</span></div>)}{ex.error_message&&<div style={{color:"var(--error)",fontSize:12,marginTop:6}}>{ex.error_message}</div>}</div>}
                </div>}
                return<div key={msg.id} className="conv-msg conv-msg-system">{msg.content}</div>;
              })}
            </div>}
          </div>
        </div>

        {/* Input */}
        <div className="conv-input-area">
          <form onSubmit={e=>{e.preventDefault();handleSubmit(intent)}}>
            <div className="conv-input-wrap">
              <input className="conv-input" value={intent} onChange={e=>setIntent(e.target.value)} placeholder={hasConv?"Ask a follow-up...":"What do you want to do?"} autoFocus/>
              <button type="submit" className="conv-input-btn" disabled={loadingPlan||!intent.trim()}>{loadingPlan?"...":"Send"}</button>
            </div>
          </form>
        </div>
      </div>
      {toast&&<div style={{position:"fixed",bottom:20,left:"50%",transform:"translateX(-50%)",padding:"8px 18px",borderRadius:8,background:"#1a1a2e",border:"1px solid rgba(255,255,255,0.08)",color:"#d0d0d0",fontSize:12,zIndex:999,animation:"msg-in .2s var(--ease)"}}>{toast}</div>}
    </div>
  );
}
