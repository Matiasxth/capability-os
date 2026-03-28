import React, { useState } from "react";
import { setMemoryPreferences, saveSettings } from "../api";

const PROVIDERS = {
  groq: { label: "Groq", desc: "Free & fast", rec: true, provider: "openai", base_url: "https://api.groq.com/openai/v1", models: ["llama-3.1-70b-versatile","llama-3.1-8b-instant","mixtral-8x7b-32768","gemma2-9b-it"], needsKey: true },
  ollama: { label: "Ollama", desc: "Local & private", provider: "ollama", base_url: "http://localhost:11434", models: [], needsKey: false },
  openai: { label: "OpenAI", desc: "", provider: "openai", base_url: "https://api.openai.com/v1", models: ["gpt-4o","gpt-4o-mini","gpt-3.5-turbo"], needsKey: true },
};

const S = { wrap: { minHeight:"100vh", display:"flex", alignItems:"center", justifyContent:"center", background:"radial-gradient(ellipse at 50% 30%,#111118 0%,#0a0a0a 60%)", fontFamily:"'Inter',-apple-system,sans-serif" }, form: { display:"flex", flexDirection:"column", alignItems:"center", gap:28, maxWidth:420, width:"100%", padding:"0 24px", animation:"onb-in .6s cubic-bezier(0.16,1,0.3,1)" }, logo: { display:"flex", alignItems:"center", gap:10 }, logoBox: { width:32, height:32, borderRadius:8, background:"linear-gradient(135deg,#00ff88,#00cc6a)", boxShadow:"0 0 24px rgba(0,255,136,0.2)" }, title: { fontSize:26, fontWeight:300, color:"#e8e8e8", letterSpacing:"-0.02em", margin:0, lineHeight:1.3, textAlign:"center" }, input: (f) => ({ width:"100%", height:48, fontSize:16, fontFamily:"inherit", background:"#111114", border:`1px solid ${f?"rgba(0,255,136,0.4)":"rgba(255,255,255,0.08)"}`, borderRadius:10, color:"#f0f0f0", padding:"0 18px", outline:"none", transition:"all .2s", boxShadow:f?"0 0 0 3px rgba(0,255,136,0.06)":"none" }), btn: (ok) => ({ width:"100%", height:44, fontSize:14, fontWeight:600, fontFamily:"inherit", background:ok?"#00ff88":"#1a1a1a", color:ok?"#0a0a0a":"#555", border:"none", borderRadius:10, cursor:ok?"pointer":"not-allowed", transition:"all .2s" }), card: (active) => ({ padding:"14px 16px", borderRadius:10, border:`1px solid ${active?"rgba(0,255,136,0.3)":"rgba(255,255,255,0.06)"}`, background:active?"rgba(0,255,136,0.06)":"#111114", cursor:"pointer", transition:"all .15s", textAlign:"left" }), sub: { fontSize:12, color:"#555", textAlign:"center", maxWidth:280, lineHeight:1.5 } };

export default function Onboarding({ onComplete }) {
  const [step, setStep] = useState(1); // 1=name, 2=llm
  const [name, setName] = useState("");
  const [focused, setFocused] = useState(false);
  const [saving, setSaving] = useState(false);
  const [provider, setProvider] = useState("groq");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("llama-3.1-70b-versatile");
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [ollamaModel, setOllamaModel] = useState("llama3.1:8b");

  async function submitName(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try { await setMemoryPreferences({ name: name.trim() }); } catch {}
    setSaving(false);
    setStep(2);
  }

  async function submitLLM(skip) {
    setSaving(true);
    if (!skip) {
      const p = PROVIDERS[provider] || PROVIDERS.groq;
      const llm = {
        provider: p.provider,
        base_url: provider === "ollama" ? ollamaUrl : p.base_url,
        model: provider === "ollama" ? ollamaModel : model,
        api_key: p.needsKey ? apiKey : "",
        timeout_ms: 30000,
      };
      try { await saveSettings({ llm }); } catch {}
    }
    setSaving(false);
    onComplete(name.trim());
  }

  const Logo = () => <div style={S.logo}><div style={S.logoBox}/><span style={{fontSize:18,fontWeight:700,color:"#f0f0f0",letterSpacing:"-0.03em"}}>Capability OS</span></div>;

  // Step 1: Name
  if (step === 1) return (
    <div style={S.wrap}>
      <form onSubmit={submitName} style={S.form}>
        <Logo/>
        <h1 style={S.title}>Welcome. What's your name?</h1>
        <input type="text" value={name} onChange={e=>setName(e.target.value)} onFocus={()=>setFocused(true)} onBlur={()=>setFocused(false)} placeholder="Your name" autoFocus style={S.input(focused)}/>
        <button type="submit" disabled={!name.trim()||saving} style={S.btn(!!name.trim())}>{saving?"...":"Continue →"}</button>
        <p style={S.sub}>Your local assistant that learns and grows with you.</p>
      </form>
      <style>{`@keyframes onb-in{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}`}</style>
    </div>
  );

  // Step 2: LLM
  const P = PROVIDERS[provider] || PROVIDERS.groq;
  return (
    <div style={S.wrap}>
      <div style={{...S.form, gap:20}}>
        <Logo/>
        <h1 style={{...S.title, fontSize:22}}>How do you want to connect your LLM?</h1>

        <div style={{display:"flex",flexDirection:"column",gap:8,width:"100%"}}>
          {Object.entries(PROVIDERS).map(([k,v])=>(
            <div key={k} style={S.card(provider===k)} onClick={()=>{setProvider(k);if(v.models.length)setModel(v.models[0])}}>
              <div style={{display:"flex",alignItems:"center",gap:8}}>
                <span style={{fontWeight:600,fontSize:14,color:provider===k?"#00ff88":"#e0e0e0"}}>{v.label}</span>
                {v.rec&&<span style={{fontSize:10,padding:"1px 6px",borderRadius:3,background:"rgba(0,255,136,0.1)",color:"#00ff88",fontWeight:600}}>recommended</span>}
              </div>
              {v.desc&&<div style={{fontSize:12,color:"#666",marginTop:2}}>{v.desc}</div>}
            </div>
          ))}
        </div>

        {/* Provider-specific fields */}
        {provider==="groq"&&(<div style={{display:"flex",flexDirection:"column",gap:8,width:"100%"}}>
          <label style={{fontSize:12,color:"#888"}}>Model</label>
          <select value={model} onChange={e=>setModel(e.target.value)} style={S.input(false)}>
            {P.models.map(m=><option key={m} value={m}>{m}{m==="llama-3.1-70b-versatile"?" (recommended)":m==="llama-3.1-8b-instant"?" (fastest)":""}</option>)}
          </select>
          <label style={{fontSize:12,color:"#888"}}>API Key <a href="https://console.groq.com/keys" target="_blank" rel="noreferrer" style={{color:"#00ff88",fontSize:11,marginLeft:4}}>Get free key →</a></label>
          <input type="password" value={apiKey} onChange={e=>setApiKey(e.target.value)} placeholder="gsk_..." style={S.input(false)}/>
        </div>)}

        {provider==="ollama"&&(<div style={{display:"flex",flexDirection:"column",gap:8,width:"100%"}}>
          <p style={{fontSize:12,color:"#666"}}>Make sure Ollama is running locally.</p>
          <label style={{fontSize:12,color:"#888"}}>URL</label>
          <input value={ollamaUrl} onChange={e=>setOllamaUrl(e.target.value)} style={S.input(false)}/>
          <label style={{fontSize:12,color:"#888"}}>Model</label>
          <input value={ollamaModel} onChange={e=>setOllamaModel(e.target.value)} placeholder="llama3.1:8b" style={S.input(false)}/>
        </div>)}

        {provider==="openai"&&(<div style={{display:"flex",flexDirection:"column",gap:8,width:"100%"}}>
          <label style={{fontSize:12,color:"#888"}}>Model</label>
          <select value={model} onChange={e=>setModel(e.target.value)} style={S.input(false)}>
            {P.models.map(m=><option key={m} value={m}>{m}</option>)}
          </select>
          <label style={{fontSize:12,color:"#888"}}>API Key</label>
          <input type="password" value={apiKey} onChange={e=>setApiKey(e.target.value)} placeholder="sk-..." style={S.input(false)}/>
        </div>)}

        <div style={{display:"flex",gap:8,width:"100%"}}>
          <button onClick={()=>submitLLM(false)} disabled={saving||(P.needsKey&&!apiKey)} style={{...S.btn(!saving&&(!P.needsKey||!!apiKey)),flex:1}}>{saving?"...":"Save & start →"}</button>
        </div>
        <button onClick={()=>submitLLM(true)} style={{background:"none",border:"none",color:"#555",fontSize:12,cursor:"pointer",padding:4}}>Configure later →</button>
      </div>
      <style>{`@keyframes onb-in{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}`}</style>
    </div>
  );
}
