import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  chatMessage, clearAllMemory, deleteHistoryEntry, executeCapability,
  getExecution, getExecutionEvents, getMemoryContext, getMemoryHistory,
  listCapabilities, planIntent, saveChatSession, streamChat,
  runAgent, confirmAgentAction, streamAgent,
  listWorkspaces, addWorkspace, updateWorkspace, updateWorkspaceStatus, removeWorkspace, getSettings,
  listAgents,
} from "../api";
import ChatInput from "../components/ChatInput";
import ChatThread from "../components/ChatThread";
import AgentStepView from "../components/AgentStepView";
import ConfirmationModal from "../components/ConfirmationModal";
import FileDropZone from "../components/workspace/FileDropZone";
import QuickActionsBar from "../components/workspace/QuickActionsBar";
import { useVoice } from "../hooks/useVoice";
import { useTTS } from "../hooks/useTTS";
import { useCollapsible } from "../hooks/useCollapsible";
import ProjectSidebar from "../components/ProjectSidebar";
import NewProjectModal from "../components/NewProjectModal";
import ToastContainer from "../components/ToastContainer";
import { useToast } from "../hooks/useToast";
import { useWebSocket } from "../hooks/useWebSocket";
import { useWorkspaceState } from "../state/useWorkspaceState";

/* Template resolution */
const TMPL = /^\{\{([a-zA-Z0-9_.]+)\}\}$/;
function resolvePath(p,ctx){const s=p.split("."),r=s[0];if(!["inputs","state","steps","runtime"].includes(r))throw new Error(`Bad '${r}'.`);let n=ctx[r];for(let i=1;i<s.length;i++){const k=s[i];if(n==null||typeof n!=="object"||!(k in n))throw new Error(`Unresolved '{{${p}}}'.`);n=n[k]}return n}
function resolve(v,c){if(typeof v==="string"){const m=v.match(TMPL);if(!m)return v;return resolvePath(m[1],c)}if(Array.isArray(v))return v.map(x=>resolve(x,c));if(v&&typeof v==="object"){const o={};for(const[k,x]of Object.entries(v))o[k]=resolve(x,c);return o}return v}

export default function Workspace({ activeWorkspace, userName }) {
  const {intent,setIntent,plan,setPlan,planValidationErrors,setPlanValidationErrors,execution,setExecution,logs,setLogs}=useWorkspaceState();
  const voice=useVoice();
  const tts=useTTS();
  const {isCollapsed:sidebarCollapsed,toggle:toggleSidebar}=useCollapsible("capos_sidebar_collapsed");
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
  const {toasts,addToast,removeToast}=useToast();
  const [activeSessionId,setActiveSessionId]=useState(null);
  const activeSessionRef=useRef(null);
  const [autoExecute,setAutoExecute]=useState(()=>localStorage.getItem("capos_autoexecute")==="true");
  const [agentMode,setAgentMode]=useState(()=>localStorage.getItem("capos_agentmode")!=="false");
  const [agentEvents,setAgentEvents]=useState([]);
  const [agentSessionId,setAgentSessionId]=useState(null);
  const [pendingConfirmation,setPendingConfirmation]=useState(null);
  const [workspaces,setWorkspaces]=useState([]);
  const [activeProjectId,setActiveProjectId]=useState(null);
  const [projectStates,setProjectStates]=useState([]);
  const [showNewProject,setShowNewProject]=useState(false);
  const [agents,setAgents]=useState([]);
  const [activeAgentId,setActiveAgentId]=useState(null);
  const autoExecTimerRef=useRef(null);
  const sessionDirtyRef=useRef(false);
  const messagesRef=useRef(messages);
  const threadRef=useRef(null);

  // ── Load workspaces & project states ──
  useEffect(()=>{
    listWorkspaces().then(r=>{setWorkspaces(r.workspaces||[]);if(!activeProjectId&&r.default_id)setActiveProjectId(r.default_id)}).catch(()=>{});
    getSettings().then(r=>{const s=r.settings||r;setProjectStates(s.project_states||[])}).catch(()=>{});
    listAgents().then(r=>{const a=r.agents||[];setAgents(a);if(!activeAgentId&&a.length)setActiveAgentId(a[0].id)}).catch(()=>{});
  },[]);

  // ── History loading ──
  const historyIdsRef=useRef("");
  function loadHistory(force){
    return getMemoryHistory().then(r=>{
      const valid=(r.history||[]).filter(h=>h.intent&&h.intent.trim().length>0&&h.intent!=="session"&&h.intent!=="New session");
      const mapped=valid.slice(0,20).map(h=>({id:h.execution_id,intent:h.intent,status:h.status==="ready"?"success":h.status,duration_ms:h.duration_ms,time:h.timestamp,plan_steps:h.plan_steps||null,step_runs:h.step_runs||null,error_message:h.error_message||null,failed_step:h.failed_step||null,final_output:h.key_outputs||{},chat_response:h.chat_response||null,chat_messages:h.chat_messages||null,message_count:h.message_count||0,isChat:h.capability_id==="chat",hasExecution:!!h.has_execution}));
      const newIds=mapped.map(h=>h.id+":"+(h.message_count||0)+":"+(h.time||"")).join(",");
      if(force||newIds!==historyIdsRef.current){
        historyIdsRef.current=newIds;setHistory(mapped);
        const sid=activeSessionRef.current;
        if(sid&&sid.startsWith("telegram_")){
          const entry=mapped.find(h=>h.id===sid);
          if(entry&&entry.chat_messages&&entry.chat_messages.length>0){
            const restored=[];const ts=new Date(entry.time||Date.now());
            entry.chat_messages.forEach((m,i)=>{restored.push({id:Date.now()+i,role:m.role==="user"?"user":"system",content:m.content,meta:{},ts})});
            if(restored.length>0)setMessages(restored);
          }
        }
      }
    }).catch(()=>{});
  }

  // ── Init ──
  useEffect(()=>{let o=false;
    listCapabilities().then(r=>{if(!o)setCapabilities(r.capabilities||[])}).catch(()=>{});
    loadHistory(true);
    getMemoryContext().then(r=>{if(!o)setFreqCaps((r.context?.frequent_capabilities||[]).slice(0,6))}).catch(()=>{});
    return()=>{o=true};
  },[]);

  // ── WebSocket ──
  const HISTORY_EVENTS=["telegram_message","whatsapp_message","slack_message","discord_message","session_updated","execution_complete","memory_cleared"];
  const TOAST_EVENTS={
    settings_updated:"Settings updated",
    config_imported:"Configuration imported",
    workspace_changed:"Workspace updated",
    growth_update:"Growth system updated",
    integration_changed:"Integration updated",
    mcp_changed:"MCP updated",
    a2a_changed:"A2A updated",
    browser_changed:"Browser updated",
    preferences_updated:"Preferences saved",
  };
  const handleWsEvent=useCallback((event)=>{
    if(!event||!event.type)return;
    if(HISTORY_EVENTS.includes(event.type)){loadHistory()}
    if(TOAST_EVENTS[event.type]){addToast(TOAST_EVENTS[event.type]+(event.data?.action?" — "+event.data.action:""),"success")}
    if(event.type==="error"&&event.data?.message){addToast("Error: "+event.data.message.slice(0,80),"error")}
  },[]);
  const{connected:wsConnected}=useWebSocket(handleWsEvent);
  useEffect(()=>{const ms=wsConnected?30000:5000;const id=setInterval(()=>loadHistory(),ms);return()=>clearInterval(id)},[wsConnected]);

  // ── Messages ──
  useEffect(()=>{messagesRef.current=messages;if(threadRef.current)threadRef.current.scrollTop=threadRef.current.scrollHeight},[messages]);
  function addMsg(role,content,meta){setMessages(p=>[...p,{id:Date.now()+Math.random(),role,content,meta,ts:new Date()}])}
  function showToast(msg,type="info"){addToast(msg,type)}

  // ── Session flush ──
  const flushSession=useCallback(()=>{
    if(!sessionDirtyRef.current)return;
    setMessages(cur=>{
      const visible=cur.filter(m=>!m.meta?.loading&&!m.meta?.executing);
      const firstUser=visible.find(m=>m.role==="user"&&typeof m.content==="string"&&m.content.trim().length>0);
      if(!firstUser||visible.length<2)return cur;
      sessionDirtyRef.current=false;
      let hasExec=false,lastStatus="success",lastDur=0;
      const compact=visible.map(m=>{
        if(m.meta?.execution){hasExec=true;lastStatus=m.meta.execution.status||"success";lastDur=m.meta.execution.duration_ms||0;return{role:"assistant",content:"Execution: "+m.meta.execution.status,type:"execution",execution:m.meta.execution}}
        if(m.meta?.plan)return{role:"assistant",content:"Plan: "+m.meta.plan.steps?.map(s=>s.capability).join(", "),type:"plan",plan:m.meta.plan};
        if(m.meta?.agentEvents){const ft=m.meta.finalText||"";const tools=(m.meta.agentEvents||[]).filter(e=>e.event==="tool_call").map(e=>e.tool_id).join(", ");return{role:"assistant",content:ft||("Agent: "+tools),type:"agent",agentEvents:m.meta.agentEvents}}
        if(m.meta?.error)return{role:"assistant",content:m.content,type:"error"};
        return{role:m.role==="user"?"user":"assistant",content:typeof m.content==="string"?m.content:JSON.stringify(m.content),type:"chat"};
      });
      const intentText=firstUser.content;const sid=currentSessionId;
      saveChatSession(sid,intentText,compact,lastDur).then(()=>{
        const entry={id:sid,intent:intentText,status:lastStatus,duration_ms:lastDur,time:new Date().toISOString(),isChat:!hasExec,hasExecution:hasExec,chat_messages:compact,message_count:compact.length};
        setHistory(p=>{const idx=p.findIndex(h=>h.id===sid);if(idx>=0){const u=[...p];u[idx]=entry;return u}return[entry,...p].slice(0,10)});
      }).catch(()=>{});
      return cur;
    });
  },[currentSessionId]);

  // ── Conversation history for LLM ──
  function getConversationHistory(msgs,max=6){
    return msgs.filter(m=>!m.meta?.loading&&!m.meta?.executing).slice(-max).map(m=>{
      const role=m.role==="user"?"user":"assistant";
      let content=m.content;
      if(m.meta?.agentEvents&&m.meta?.finalText){content=m.meta.finalText}
      else if(m.meta?.plan){content="Plan: "+m.meta.plan.steps.map(s=>`${s.capability}(${Object.entries(s.inputs||{}).map(([k,v])=>k+"="+JSON.stringify(v)).join(", ")})`).join(" → ")}
      else if(m.meta?.execution){const ex=m.meta.execution;if(ex.status==="success"){const runs=(ex.step_runs||[]).map(r=>{const out=r.final_output||{};if(out.items)return`${r.capability}: listed ${out.items.length} items in ${out.path||"?"}`;if(out.content)return`${r.capability}: read file ${out.path||"?"}`;if("stdout" in out)return`${r.capability}: exit ${out.exit_code}`;return r.capability+": done"});content="Executed: "+runs.join("; ")}else{content="Failed: "+(ex.error_message||"error")}}
      const entry={role,content};
      if(m.meta?.suggestedAction)entry.suggested_action=m.meta.suggestedAction;
      return entry;
    });
  }

  // ── Session restore ──
  function restoreSession(h){
    flushSession();const restored=[];const ts=new Date(h.time||Date.now());
    if(h.id){setCurrentSessionId(h.id);setActiveSessionId(h.id);activeSessionRef.current=h.id}
    setPlan(null);setExecution(null);setPlanExecuted(false);sessionDirtyRef.current=false;
    if(h.chat_messages&&h.chat_messages.length>0){
      let restoredHasExec=false;
      h.chat_messages.forEach((m,i)=>{
        if(m.type==="execution"&&m.execution){restoredHasExec=true;setExecution(m.execution);restored.push({id:Date.now()+i,role:"system",content:"result",meta:{execution:m.execution},ts})}
        else if(m.type==="plan"&&m.plan){setPlan(m.plan);restored.push({id:Date.now()+i,role:"system",content:"plan",meta:{plan:m.plan},ts})}
        else if(m.type==="agent"&&m.agentEvents){restored.push({id:Date.now()+i,role:"system",content:m.agentEvents?.length>1?"agent_steps":m.content,meta:{agentEvents:m.agentEvents,finalText:m.content},ts})}
        else if(m.type==="error"){restored.push({id:Date.now()+i,role:"system",content:m.content,meta:{error:true},ts})}
        else{restored.push({id:Date.now()+i,role:m.role==="user"?"user":"system",content:m.content,meta:{},ts})}
      });
      if(restoredHasExec)setPlanExecuted(true);
      if(restored.length>0){setMessages(restored);setIntent("");setErrorMessage("");return}
    }
    if(h.intent)restored.push({id:Date.now()+1,role:"user",content:h.intent,ts});
    if(h.chat_response&&!h.plan_steps)restored.push({id:Date.now()+2,role:"system",content:h.chat_response,meta:{},ts});
    if(h.plan_steps?.length>0){const rp={steps:h.plan_steps};setPlan(rp);restored.push({id:Date.now()+2,role:"system",content:"plan",meta:{plan:rp},ts})}
    if(h.step_runs){const ex={status:h.status,current_step:"",started_at:h.time,ended_at:null,duration_ms:h.duration_ms||0,failed_step:h.failed_step||null,error_code:null,error_message:h.error_message||null,final_output:h.final_output||{},step_runs:h.step_runs};setExecution(ex);setPlanExecuted(true);restored.push({id:Date.now()+3,role:"system",content:"result",meta:{execution:ex},ts})}
    if(restored.length===0){setIntent(h.intent||"");setMessages([]);return}
    setMessages(restored);setIntent("");setErrorMessage(h.error_message||"");
  }

  // ── Submit + Execute ──
  async function handleSubmit(text){
    if(!text?.trim())return;
    const q=text.trim();setIntent("");addMsg("user",q);setLoadingPlan(true);setErrorMessage("");

    // Agent Mode: streaming tool-use loop
    if(agentMode){
      addMsg("system","",{loading:true});
      try{
        const hist=getConversationHistory(messages);
        const events=[];
        let finalText="";
        let sid=null;
        for await(const ev of streamAgent(q,agentSessionId,hist,activeAgentId)){
          events.push(ev);
          if(ev.session_id)sid=ev.session_id;
          // Update UI in real-time
          if(ev.event==="agent_response"){
            finalText=ev.text||"";
          }
          if(ev.event==="awaiting_confirmation"){
            setPendingConfirmation({...ev,session_id:sid||agentSessionId});
            setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:"agent_steps",meta:{agentEvents:events,awaiting:true},ts:new Date()};return c});
            setAgentSessionId(sid);setLoadingPlan(false);return;
          }
          // Live update: show steps as they arrive
          const stepsOnly=events.filter(e=>e.event!=="agent_start");
          if(stepsOnly.length>0){
            setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:"agent_steps",meta:{agentEvents:stepsOnly,finalText:finalText||undefined},ts:new Date()};return c});
          }
        }
        setAgentSessionId(sid);
        // Final render
        const hasToolCalls=events.some(e=>e.event==="tool_call");
        if(hasToolCalls){
          const stepsOnly=events.filter(e=>e.event!=="agent_start");
          setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:"agent_steps",meta:{agentEvents:stepsOnly,finalText:finalText||"Done."},ts:new Date()};return c});
          if(tts.autoSpeak&&finalText)tts.speak(finalText);
        }else{
          setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:finalText||"Done.",meta:{},ts:new Date()};return c});
          if(tts.autoSpeak&&finalText)tts.speak(finalText);
        }
        sessionDirtyRef.current=true;
        setTimeout(()=>flushSession(),500);
      }catch(e){
        const msg=e.payload?.error_message||e.message||"Agent error.";
        setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:msg,meta:{error:true},ts:new Date()};return c});
        setErrorMessage(msg);
      }finally{setLoadingPlan(false)}
      return;
    }

    // Classic Mode: plan-then-execute
    addMsg("system","Thinking...",{loading:true});
    try{
      const hist=getConversationHistory(messages);
      const cls=await chatMessage(q,userName,hist).catch(()=>({type:"action"}));
      if(cls.type==="chat"){
        let streamed="";
        try{for await(const chunk of streamChat(q,userName,hist)){streamed+=chunk;setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:streamed,meta:{},ts:new Date()};return c})}}catch{if(!streamed)streamed=cls.response||"How can I help?"}
        if(!streamed)streamed=cls.response||"How can I help?";
        setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:streamed,meta:{},ts:new Date()};return c});
        setSuggestedAction(null);sessionDirtyRef.current=true;setLoadingPlan(false);return;
      }
      const actionIntent=(cls.suggested_action&&suggestedAction)?suggestedAction:q;setSuggestedAction(null);
      setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now()+.1,role:"system",content:"Analyzing...",meta:{loading:true},ts:new Date()};return c});
      const r=await planIntent(actionIntent,hist);setPlan(r);setPlanValidationErrors(Array.isArray(r.errors)?r.errors:[]);setPlanExecuted(false);
      setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:"plan",meta:{plan:r},ts:new Date()};return c});
      sessionDirtyRef.current=true;
      if(autoExecute&&r?.steps?.length>0&&(!Array.isArray(r.errors)||r.errors.length===0)){autoExecTimerRef.current=setTimeout(()=>{autoExecTimerRef.current=null;runPlan()},800)}
    }catch(e){
      const msg=e.payload?.error_message||e.message||"Plan failed.";
      setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:msg,meta:{error:true},ts:new Date()};return c});
      setErrorMessage(msg);
    }finally{setLoadingPlan(false)}
  }

  // ── Agent confirmation handler ──
  async function handleAgentConfirm(confirmationId,password){
    if(!pendingConfirmation)return;
    const sid=pendingConfirmation.session_id;
    setPendingConfirmation(null);
    addMsg("system","Continuing...",{loading:true});
    try{
      const r=await confirmAgentAction(sid,confirmationId,true,password);
      setAgentEvents(r.events||[]);
      if(r.status==="awaiting_confirmation"&&r.confirmation){
        setPendingConfirmation({...r.confirmation,session_id:sid});
        setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:"agent_steps",meta:{agentEvents:r.events,awaiting:true},ts:new Date()};return c});
      }else{
        const finalText=r.final_text||"Done.";
        setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:r.events?.length>1?"agent_steps":"",meta:{agentEvents:r.events,finalText},ts:new Date()};return c});
        if(r.events?.length<=1)setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:finalText,meta:{},ts:new Date()};return c});
      }
    }catch(e){
      setMessages(p=>{const c=[...p];c[c.length-1]={id:Date.now(),role:"system",content:e.message||"Confirmation error",meta:{error:true},ts:new Date()};return c});
    }
  }

  function handleAgentDeny(){
    if(!pendingConfirmation)return;
    const sid=pendingConfirmation.session_id;
    const cid=pendingConfirmation.confirmation_id;
    setPendingConfirmation(null);
    confirmAgentAction(sid,cid,false).then(r=>{
      const finalText=r.final_text||"Action denied.";
      setMessages(p=>[...p,{id:Date.now(),role:"system",content:finalText,meta:{},ts:new Date()}]);
    }).catch(()=>{});
  }

  async function runPlan(){
    if(!plan?.steps?.length)return;setRunningPlan(true);setErrorMessage("");setLogs([]);addMsg("system","Executing...",{executing:true});
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
    sessionDirtyRef.current=true;setPlanExecuted(true);if(em)setErrorMessage(em);setRunningPlan(false);
  }

  // ── Effects ──
  const prevRunning=useRef(false);
  useEffect(()=>{if(prevRunning.current&&!runningPlan&&sessionDirtyRef.current)flushSession();prevRunning.current=runningPlan},[runningPlan,flushSession]);
  useEffect(()=>{const h=()=>{if(!sessionDirtyRef.current)return;const hasUser=messagesRef.current.some(m=>m.role==="user"&&typeof m.content==="string"&&m.content.trim().length>0);if(hasUser)flushSession()};window.addEventListener("beforeunload",h);return()=>window.removeEventListener("beforeunload",h)},[flushSession]);

  // ── Helpers ──
  function renderAmbiguousContacts(errorMessage){
    const m=errorMessage.match(/matching '([^']+)': (.+)\. Please/);if(!m)return null;
    const names=m[2].split(", ").map(n=>n.trim()).filter(Boolean);
    return(<div><div style={{color:"var(--warning)",fontWeight:500,marginBottom:8}}>Multiple contacts found</div><div style={{fontSize:12,color:"var(--text-dim)",marginBottom:6}}>Which one?</div>{names.map(name=><button key={name} className="conv-chip" style={{margin:"2px 0",display:"block"}} onClick={()=>handleSubmit("send whatsapp to "+name)}>{name}</button>)}</div>);
  }

  function handleNewSession(){
    flushSession();setMessages([]);setPlan(null);setExecution(null);setErrorMessage("");setSuggestedAction(null);setPlanExecuted(false);
    sessionDirtyRef.current=false;setCurrentSessionId("chat_"+Date.now());setActiveSessionId(null);activeSessionRef.current=null;
  }

  function handleDeleteSession(id){
    if(!id)return;setDeletingId(id);
    setTimeout(()=>{deleteHistoryEntry(id).then(()=>{setHistory(p=>p.filter(x=>x.id!==id));showToast("Session deleted")}).catch(()=>{showToast("Failed to delete")}).finally(()=>setDeletingId(null))},220);
  }

  function handleClearAll(){
    clearAllMemory().catch(()=>{});setHistory([]);setMessages([]);setPlan(null);setExecution(null);setConfirmClear(false);showToast("All sessions cleared");
  }

  const stepRuns=execution?.step_runs||[];

  // ── Render ──
  return (
    <div className={`conv-layout${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      {!sidebarCollapsed && <ProjectSidebar
        workspaces={workspaces} activeProjectId={activeProjectId} projectStates={projectStates}
        agents={agents} onUpdateAgents={async(wsId,ids)=>{try{await updateWorkspace(wsId,{agent_ids:ids});setWorkspaces(w=>w.map(ws=>ws.id===wsId?{...ws,agent_ids:ids}:ws))}catch{}}}
        history={history} userName={userName} wsConnected={wsConnected}
        onSelectProject={id=>{setActiveProjectId(id)}}
        onNewProject={()=>setShowNewProject(true)}
        onUpdateStatus={async(wsId,status)=>{try{await updateWorkspaceStatus(wsId,status);setWorkspaces(w=>w.map(ws=>ws.id===wsId?{...ws,status}:ws))}catch{}}}
        onDeleteProject={async(wsId)=>{try{await removeWorkspace(wsId);setWorkspaces(w=>w.filter(ws=>ws.id!==wsId));if(activeProjectId===wsId)setActiveProjectId(null)}catch{}}}
        onNewSession={handleNewSession} onRestoreSession={restoreSession}
        onDeleteSession={handleDeleteSession} onClearAll={handleClearAll}
      />}
      <FileDropZone onFileDrop={(files)=>{const names=Array.from(files).map(f=>f.name).join(", ");setIntent(p=>(p?p+" ":"")+`[files: ${names}]`)}}>
      <div className="conv-main-col">
        {sidebarCollapsed && <button className="sidebar-toggle" onClick={toggleSidebar} title="Show sidebar" style={{position:"absolute",left:4,top:8,zIndex:5}}>{"\u25B6"}</button>}
        <ChatThread
          messages={messages} userName={userName} freqCaps={freqCaps}
          activeSessionId={activeSessionId} planValidationErrors={planValidationErrors}
          planExecuted={planExecuted} runningPlan={runningPlan} stepRuns={stepRuns}
          autoExecTimerRef={autoExecTimerRef}
          onRunPlan={()=>{if(autoExecTimerRef.current){clearTimeout(autoExecTimerRef.current);autoExecTimerRef.current=null}runPlan()}}
          onCancelAutoExec={()=>{if(autoExecTimerRef.current){clearTimeout(autoExecTimerRef.current);autoExecTimerRef.current=null;showToast("Auto-execute cancelled")}}}
          onSubmit={handleSubmit} onNavigateDir={p=>p&&handleSubmit("list files in "+p)}
          renderAmbiguousContacts={renderAmbiguousContacts} threadRef={threadRef}
          voice={voice}
        />
        {messages.length===0 && <QuickActionsBar freqCaps={freqCaps} onAction={(capId)=>handleSubmit(capId)}/>}
        <ChatInput
          intent={intent} setIntent={setIntent} onSubmit={handleSubmit}
          loadingPlan={loadingPlan} hasConv={messages.length>0}
          autoExecute={autoExecute} setAutoExecute={setAutoExecute}
          agentMode={agentMode} setAgentMode={setAgentMode}
          agents={agents} activeAgentId={activeAgentId} setActiveAgentId={setActiveAgentId}
          voice={voice} tts={tts}
        />
      </div>
      </FileDropZone>
      <ToastContainer toasts={toasts} onDismiss={removeToast}/>
      <ConfirmationModal
        confirmation={pendingConfirmation}
        onConfirm={handleAgentConfirm}
        onDeny={handleAgentDeny}
      />
      {showNewProject && <NewProjectModal
        states={projectStates}
        onCreate={async(p)=>{
          try{
            const r=await addWorkspace(p.name,p.path,"write","*","#00ff88");
            if(r.workspace){
              await updateWorkspaceStatus(r.workspace.id,p.status);
              const ws={...r.workspace,status:p.status};
              setWorkspaces(prev=>[...prev,ws]);
              setActiveProjectId(ws.id);
            }
            setShowNewProject(false);
          }catch(e){alert(e.message||"Failed to create project")}
        }}
        onClose={()=>setShowNewProject(false)}
      />}
    </div>
  );
}
