import React, { useEffect, useState } from "react";
import sdk from "../../../sdk";

const TOOL_CATS = {
  "Filesystem": ["filesystem_read_file","filesystem_write_file","filesystem_list_directory","filesystem_create_directory","filesystem_delete_file","filesystem_copy_file","filesystem_move_file","filesystem_edit_file"],
  "Execution": ["execution_run_command","execution_run_script"],
  "Network": ["network_http_get","network_extract_text","network_extract_links"],
  "Browser": ["browser_navigate","browser_read_text","browser_screenshot","browser_click_element","browser_type_text"],
  "System": ["system_get_os_info","system_get_workspace_info","system_get_env_var"],
};

export default function AgentsSection({ toast, act }) {
  const [agents, setAgents] = useState([]);
  const [editAgent, setEditAgent] = useState(null);
  const [agentForm, setAgentForm] = useState({name:"",emoji:"\u{1f916}",description:"",system_prompt:"",tool_ids:[],llm_model:"",language:"auto",max_iterations:10});

  const refreshAgents = () => sdk.agents.list().then(r => setAgents(r.agents || [])).catch(() => {});

  useEffect(() => { refreshAgents() }, []);

  return (
    <div style={{display:"flex",flexDirection:"column",gap:10}}>
      <h2>Agents</h2>
      <p style={{fontSize:11,color:"var(--text-muted)",margin:0}}>Create custom AI agents with unique personalities, tools, and behaviors. Assign them to projects or select them in conversations.</p>

      {agents.map(a => (
        <div key={a.id} className="card" style={{padding:"10px 14px",display:"flex",alignItems:"center",gap:10}}>
          <span style={{fontSize:22}}>{a.emoji}</span>
          <div style={{flex:1}}>
            <div style={{fontSize:13,fontWeight:600,color:"var(--text)"}}>{a.name} {a.id === "agt_default" && <span className="badge badge-info" style={{fontSize:8,marginLeft:4}}>default</span>}</div>
            <div style={{fontSize:10,color:"var(--text-dim)"}}>{a.description || "No description"}</div>
            {a.tool_ids?.length > 0 && <div style={{fontSize:9,color:"var(--text-muted)",marginTop:2}}>{a.tool_ids.length} tools</div>}
          </div>
          {a.id !== "agt_default" && <>
            <button style={{fontSize:10,height:24}} onClick={() => { setEditAgent(a.id); setAgentForm({name:a.name,emoji:a.emoji,description:a.description,system_prompt:a.system_prompt||"",tool_ids:a.tool_ids||[],llm_model:a.llm_model||"",language:a.language||"auto",max_iterations:a.max_iterations||10}) }}>Edit</button>
            <button style={{fontSize:10,height:24,color:"var(--error)"}} onClick={() => act(async () => { await sdk.agents.delete(a.id); refreshAgents() }, "Agent deleted")}>Del</button>
          </>}
        </div>
      ))}

      <div className="card" style={{padding:14,marginBottom:8}}>
        <h4 style={{margin:"0 0 8px"}}>AI Agent Designer</h4>
        <p style={{fontSize:10,color:"var(--text-muted)",margin:"0 0 8px"}}>Describe the agent you want and the AI will design it for you.</p>
        <div style={{display:"flex",gap:6}}>
          <input id="ai-design-input" style={{flex:1,height:32,fontSize:12}} placeholder="e.g. An expert in Python that helps debug code"/>
          <button style={{height:32,fontSize:11,padding:"0 14px",whiteSpace:"nowrap"}} onClick={async () => {
            const inp = document.getElementById("ai-design-input");
            const desc = inp?.value?.trim();
            if (!desc) return;
            toast("Designing agent...");
            try {
              const r = await sdk.agents.design(desc);
              if (r.config) {
                setAgentForm({...agentForm,...r.config,llm_model:r.config.llm_model||""});
                setEditAgent(null);
                toast("Agent designed! Review and save below.");
              } else { toast(r.error || "Design failed", "error") }
            } catch (e) { toast(e.message || "Design failed", "error") }
          }}>Design</button>
        </div>
      </div>

      <div className="card" style={{padding:14}}>
        <h4 style={{margin:"0 0 10px"}}>{editAgent ? "Edit Agent" : "Create Agent"}</h4>
        <div style={{display:"flex",gap:8,marginBottom:8}}>
          <input value={agentForm.emoji} onChange={e => setAgentForm({...agentForm,emoji:e.target.value})} style={{width:40,height:32,fontSize:18,textAlign:"center"}} title="Emoji"/>
          <input value={agentForm.name} onChange={e => setAgentForm({...agentForm,name:e.target.value})} style={{flex:1,height:32,fontSize:13}} placeholder="Agent name"/>
        </div>
        <input value={agentForm.description} onChange={e => setAgentForm({...agentForm,description:e.target.value})} style={{width:"100%",height:28,fontSize:11,marginBottom:8}} placeholder="Description (what this agent does)"/>
        <label style={{fontSize:10,color:"var(--text-dim)",display:"block",marginBottom:2}}>System Prompt</label>
        <textarea value={agentForm.system_prompt} onChange={e => setAgentForm({...agentForm,system_prompt:e.target.value})} style={{width:"100%",height:100,fontSize:11,background:"var(--bg-input)",border:"1px solid var(--border)",borderRadius:6,color:"var(--text)",padding:8,resize:"vertical",fontFamily:"var(--font-mono)"}} placeholder="You are an expert in..."/>

        <label style={{fontSize:10,color:"var(--text-dim)",display:"block",margin:"8px 0 4px"}}>Tools</label>
        <div style={{display:"flex",flexDirection:"column",gap:4,marginBottom:8}}>
          {Object.entries(TOOL_CATS).map(([cat, tools]) => (
            <div key={cat}>
              <div style={{fontSize:9,color:"var(--accent)",fontWeight:600,marginBottom:2}}>{cat}</div>
              <div style={{display:"flex",flexWrap:"wrap",gap:3}}>
                {tools.map(t => { const on = agentForm.tool_ids.includes(t); return <button key={t} onClick={() => { const ids = on ? agentForm.tool_ids.filter(x => x !== t) : [...agentForm.tool_ids, t]; setAgentForm({...agentForm, tool_ids: ids}) }} style={{fontSize:9,height:22,padding:"0 6px",background:on?"var(--accent-dim)":"var(--bg-input)",color:on?"var(--accent)":"var(--text-muted)",border:on?"1px solid var(--accent)":"1px solid var(--border)"}}>{t.replace("filesystem_","").replace("execution_","").replace("network_","").replace("browser_","").replace("system_","")}</button> })}
              </div>
            </div>
          ))}
          <button style={{fontSize:9,height:22,marginTop:2}} onClick={() => { const all = Object.values(TOOL_CATS).flat(); setAgentForm({...agentForm, tool_ids: agentForm.tool_ids.length === all.length ? [] : all}) }}>
            {agentForm.tool_ids.length === Object.values(TOOL_CATS).flat().length ? "Deselect all" : "Select all"}
          </button>
        </div>

        <div style={{display:"flex",gap:8,marginBottom:8}}>
          <div style={{flex:1}}>
            <label style={{fontSize:10,color:"var(--text-dim)"}}>LLM Model (empty = system default)</label>
            <input value={agentForm.llm_model} onChange={e => setAgentForm({...agentForm,llm_model:e.target.value})} style={{width:"100%",height:28,fontSize:11}} placeholder="e.g. gpt-4o"/>
          </div>
          <div>
            <label style={{fontSize:10,color:"var(--text-dim)"}}>Language</label>
            <input value={agentForm.language} onChange={e => setAgentForm({...agentForm,language:e.target.value})} style={{width:80,height:28,fontSize:11}} placeholder="auto"/>
          </div>
          <div>
            <label style={{fontSize:10,color:"var(--text-dim)"}}>Max iter</label>
            <input type="number" value={agentForm.max_iterations} onChange={e => setAgentForm({...agentForm,max_iterations:parseInt(e.target.value)||10})} style={{width:50,height:28,fontSize:11}} min={1} max={50}/>
          </div>
        </div>

        <div style={{display:"flex",gap:6}}>
          <button className="btn-primary" style={{flex:1,height:32,fontSize:12}} onClick={async () => {
            if (!agentForm.name.trim()) return;
            try {
              if (editAgent) { await sdk.agents.update(editAgent, agentForm); toast("Agent updated") }
              else { await sdk.agents.create(agentForm); toast("Agent created") }
              refreshAgents(); setEditAgent(null); setAgentForm({name:"",emoji:"\u{1f916}",description:"",system_prompt:"",tool_ids:[],llm_model:"",language:"auto",max_iterations:10});
            } catch (e) { toast(e.message || "Failed", "error") }
          }}>{editAgent ? "Save" : "Create"}</button>
          {editAgent && <button style={{height:32,fontSize:12,padding:"0 16px"}} onClick={() => { setEditAgent(null); setAgentForm({name:"",emoji:"\u{1f916}",description:"",system_prompt:"",tool_ids:[],llm_model:"",language:"auto",max_iterations:10}) }}>Cancel</button>}
        </div>
      </div>
    </div>
  );
}
