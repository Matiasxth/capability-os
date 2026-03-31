import React, { useState } from "react";
import sdk from "../../../sdk";

export default function ProjectStatesSection({ settings, setSettings, toast, act }) {
  const [editingState, setEditingState] = useState(null);
  const [newStateName, setNewStateName] = useState("");
  const [newStateColor, setNewStateColor] = useState("#3b82f6");
  const [newStateIcon, setNewStateIcon] = useState("\u2b50");

  const pStates = settings?.project_states || [];

  return (
    <div style={{display:"flex",flexDirection:"column",gap:10}}>
      <h2>Project States</h2>
      <p style={{fontSize:11,color:"var(--text-muted)",margin:0}}>Customize the status labels for your projects. Each state has a name, color, and emoji icon.</p>

      {pStates.map((s, i) => (
        <div key={i} className="card" style={{padding:"8px 12px",display:"flex",alignItems:"center",gap:8}}>
          <span style={{fontSize:18}}>{s.icon}</span>
          <span style={{flex:1,fontSize:12,fontWeight:500}}>{s.name}</span>
          <span style={{width:12,height:12,borderRadius:"50%",background:s.color}}/>
          <button style={{fontSize:10,height:22,padding:"0 8px"}} onClick={() => { setEditingState(i); setNewStateName(s.name); setNewStateColor(s.color); setNewStateIcon(s.icon) }}>Edit</button>
          <button style={{fontSize:10,height:22,padding:"0 8px",color:"#ff4444"}} onClick={() => { const updated = [...pStates]; updated.splice(i, 1); act(() => sdk.system.settings.save({...settings, project_states: updated}).then(r => setSettings(r.settings || settings)), "State removed") }}>Del</button>
        </div>
      ))}

      <div className="card" style={{padding:12}}>
        <h4 style={{margin:"0 0 8px",fontSize:12}}>{editingState !== null ? "Edit State" : "Add State"}</h4>
        <div style={{display:"flex",gap:6,alignItems:"center",marginBottom:8}}>
          <input value={newStateIcon} onChange={e => setNewStateIcon(e.target.value)} style={{width:36,height:28,fontSize:16,textAlign:"center"}} title="Emoji icon"/>
          <input value={newStateName} onChange={e => setNewStateName(e.target.value)} style={{flex:1,height:28,fontSize:12}} placeholder="State name"/>
          <input type="color" value={newStateColor} onChange={e => setNewStateColor(e.target.value)} style={{width:28,height:28,border:"none",padding:0,cursor:"pointer"}}/>
        </div>
        <div style={{display:"flex",gap:4}}>
          <button className="btn-primary" style={{flex:1,height:28,fontSize:11}} onClick={() => {
            if (!newStateName.trim()) return;
            const entry = {name: newStateName.trim(), color: newStateColor, icon: newStateIcon || "\u2b50"};
            let updated;
            if (editingState !== null) { updated = [...pStates]; updated[editingState] = entry } else { updated = [...pStates, entry] }
            act(() => sdk.system.settings.save({...settings, project_states: updated}).then(r => setSettings(r.settings || settings)), editingState !== null ? "State updated" : "State added");
            setEditingState(null); setNewStateName(""); setNewStateColor("#3b82f6"); setNewStateIcon("\u2b50");
          }}>{editingState !== null ? "Save" : "Add"}</button>
          {editingState !== null && <button style={{height:28,fontSize:11,padding:"0 12px"}} onClick={() => { setEditingState(null); setNewStateName(""); setNewStateColor("#3b82f6"); setNewStateIcon("\u2b50") }}>Cancel</button>}
        </div>
      </div>
    </div>
  );
}
