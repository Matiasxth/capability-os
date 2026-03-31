import React, { useEffect, useState } from "react";
import sdk from "../../../sdk";

export default function MCPSection({ toast, act }) {
  const [mcpServers, setMcpServers] = useState([]);
  const [mcpTools, setMcpTools] = useState([]);
  const [installedTools, setInstalledTools] = useState(new Set());
  const [newSrvId, setNewSrvId] = useState("");
  const [newSrvTransport, setNewSrvTransport] = useState("stdio");
  const [newSrvCmd, setNewSrvCmd] = useState("");
  const [newSrvUrl, setNewSrvUrl] = useState("");

  async function refresh() {
    try {
      const [s, t, c] = await Promise.all([sdk.mcp.servers.list(), sdk.mcp.tools.list(), sdk.capabilities.list()]);
      setMcpServers(s.servers || []);
      setMcpTools(t.tools || []);
      const capIds = new Set((c.capabilities || []).map(x => x.id || x));
      const inst = new Set();
      (t.tools || []).forEach(tool => { if (capIds.has(tool.tool_id) || capIds.has("mcp_" + tool.tool_id)) inst.add(tool.tool_id) });
      setInstalledTools(inst);
    } catch {}
  }
  useEffect(() => { refresh(); }, []);

  return (<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>MCP</h2>
    <form onSubmit={async e=>{e.preventDefault();const c={id:newSrvId,transport:newSrvTransport};if(newSrvTransport==="stdio")c.command=newSrvCmd.split(/\s+/);else c.url=newSrvUrl;await act(()=>sdk.mcp.servers.add(c),"Added");setNewSrvId("");setNewSrvCmd("");setNewSrvUrl("");await refresh()}} style={{display:"flex",flexDirection:"column",gap:5}}>
      <div style={{display:"flex",gap:5}}><input placeholder="ID" value={newSrvId} onChange={e=>setNewSrvId(e.target.value)} required style={{flex:1}}/><select value={newSrvTransport} onChange={e=>setNewSrvTransport(e.target.value)} style={{width:70}}><option value="stdio">stdio</option><option value="http">http</option></select></div>
      {newSrvTransport==="stdio"&&<input placeholder="Command" value={newSrvCmd} onChange={e=>setNewSrvCmd(e.target.value)} required/>}
      {newSrvTransport==="http"&&<input placeholder="URL" value={newSrvUrl} onChange={e=>setNewSrvUrl(e.target.value)} required/>}
      <button type="submit" className="btn-primary" disabled={!newSrvId}>Add</button>
    </form>
    {mcpServers.map(s=><div key={s.server_id} className="item-row"><div className="item-row-info"><span className={`dot ${s.connected?"dot-success":"dot-error"}`} style={{marginRight:3}}/><span className="mono" style={{fontSize:10}}>{s.server_id}</span></div><div className="item-row-actions"><button style={{fontSize:10,height:20}} onClick={()=>act(async()=>{await sdk.mcp.servers.discover(s.server_id);await refresh()},"OK")}>Disc</button><button className="btn-danger" style={{fontSize:10,height:20}} onClick={()=>act(async()=>{await sdk.mcp.servers.remove(s.server_id);await refresh()},"OK")}>✕</button></div></div>)}
    {mcpTools.map(t=><div key={t.tool_id} className="item-row"><span className="mono" style={{fontSize:10,flex:1}}>{t.tool_id}</span>{installedTools.has(t.tool_id)?<div style={{display:"flex",gap:3}}><button disabled style={{fontSize:10,height:20,opacity:0.6,cursor:"default",background:"transparent",border:"1px solid var(--accent)",color:"var(--accent)",borderRadius:4,padding:"0 6px"}}>✓</button><button className="btn-danger" style={{fontSize:10,height:20,padding:"0 6px"}} onClick={()=>act(async()=>{await sdk.mcp.tools.uninstall(t.tool_id);setInstalledTools(p=>{const n=new Set(p);n.delete(t.tool_id);return n})},"Uninstalled")}>✕</button></div>:<button style={{fontSize:10,height:20}} onClick={()=>act(async()=>{await sdk.mcp.tools.install(t.tool_id);setInstalledTools(p=>new Set([...p,t.tool_id]))},"Installed")}>Install</button>}</div>)}
  </div>);
}
