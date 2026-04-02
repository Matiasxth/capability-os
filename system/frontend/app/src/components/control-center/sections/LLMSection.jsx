import React, { useState } from "react";
import sdk from "../../../sdk";

const _PRESETS = {
  anthropic: { label: "Anthropic", provider: "anthropic", base_url: "https://api.anthropic.com", models: ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001", "claude-opus-4-6-20250610"], needsKey: true },
  openai: { label: "OpenAI", provider: "openai", base_url: "https://api.openai.com/v1", models: ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"], needsKey: true },
  gemini: { label: "Gemini", provider: "gemini", base_url: "https://generativelanguage.googleapis.com", models: ["gemini-2.0-flash", "gemini-2.5-pro", "gemini-2.5-flash"], needsKey: true },
  deepseek: { label: "DeepSeek", provider: "deepseek", base_url: "https://api.deepseek.com/v1", models: ["deepseek-chat", "deepseek-reasoner"], needsKey: true },
  groq: { label: "Groq", provider: "openai", base_url: "https://api.groq.com/openai/v1", models: ["llama-3.1-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"], needsKey: true },
  ollama: { label: "Ollama", provider: "ollama", base_url: "http://localhost:11434", models: [], needsKey: false },
  custom: { label: "Custom", provider: "openai", base_url: "", models: [], needsKey: false }
};

function _detectPreset(url) {
  if (!url) return "ollama";
  if (url.includes("anthropic.com")) return "anthropic";
  if (url.includes("groq.com")) return "groq";
  if (url.includes("generativelanguage.googleapis.com")) return "gemini";
  if (url.includes("deepseek.com")) return "deepseek";
  if (url.includes("localhost:11434") || url.includes("127.0.0.1:11434")) return "ollama";
  if (url.includes("openai.com")) return "openai";
  return "custom";
}

export default function LLMSection({ settings, setSettings, saving, setSaving, testingConnection, setTestingConnection, llmTestResult, setLlmTestResult, error, setError, toast, act }) {
  const [llmPreset, setLlmPreset] = useState(() => _detectPreset(settings?.llm?.base_url));
  const [showKey, setShowKey] = useState(false);
  const [llmModel, setLlmModel] = useState(settings?.llm?.model || "");
  const [llmKey, setLlmKey] = useState("");
  const [llmUrl, setLlmUrl] = useState(settings?.llm?.base_url || "");

  if (!settings) return null;

  const l = settings.llm || {};
  const P = _PRESETS[llmPreset] || _PRESETS.custom;
  const llmKeyMasked = settings?.llm?.api_key && settings.llm.api_key.includes("*");

  function selectPreset(k) {
    setLlmPreset(k);
    const p = _PRESETS[k];
    setLlmUrl(p.base_url);
    if (p.models.length) setLlmModel(p.models[0]);
    else setLlmModel(l.model || "");
    setLlmKey("");
  }

  function doSave() {
    const p = _PRESETS[llmPreset] || _PRESETS.custom;
    const llm = {
      provider: p.provider,
      base_url: llmPreset === "custom" ? llmUrl : p.base_url,
      model: llmModel || l.model || "",
      api_key: llmKey || (llmKeyMasked ? l.api_key : ""),
      timeout_ms: l.timeout_ms || 30000
    };
    act(() => sdk.system.settings.save({ ...settings, llm }).then(r => setSettings(r.settings || settings)), "Saved");
  }

  const tabStyle = (active) => ({
    padding: "5px 12px", fontSize: 11, fontWeight: 600, borderRadius: 6,
    border: `1px solid ${active ? "rgba(0,255,136,0.3)" : "rgba(255,255,255,0.06)"}`,
    background: active ? "rgba(0,255,136,0.08)" : "transparent",
    color: active ? "#00ff88" : "#888", cursor: "pointer", transition: "all .12s"
  });

  return (<div style={{display:"flex",flexDirection:"column",gap:10}}>
    <h2>LLM Provider</h2>
    <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>{Object.entries(_PRESETS).map(([k,v])=><button key={k} style={tabStyle(llmPreset===k)} onClick={()=>selectPreset(k)}>{v.label}</button>)}</div>
    <div style={{display:"flex",flexDirection:"column",gap:6}}>
      {P.models.length>0&&<div className="form-group"><label className="form-label">Model</label><select value={llmModel} onChange={e=>setLlmModel(e.target.value)} style={{height:30}}>{P.models.map(m=><option key={m} value={m}>{m}{m==="llama-3.1-70b-versatile"?" ★":""}</option>)}</select></div>}
      {P.models.length===0&&<div className="form-group"><label className="form-label">Model</label><input value={llmModel} onChange={e=>setLlmModel(e.target.value)} placeholder={llmPreset==="ollama"?"llama3.1:8b":"model-name"}/></div>}
      {llmPreset==="custom"&&<div className="form-group"><label className="form-label">Base URL</label><input value={llmUrl} onChange={e=>setLlmUrl(e.target.value)} placeholder="https://..."/></div>}
      {(P.needsKey||llmPreset==="custom")&&<div className="form-group"><label className="form-label">API Key {llmPreset==="groq"&&<a href="https://console.groq.com/keys" target="_blank" rel="noreferrer" style={{color:"#00ff88",fontSize:10,marginLeft:4}}>Get free →</a>}</label><div style={{display:"flex",gap:4}}><input type={showKey?"text":"password"} value={llmKey} onChange={e=>setLlmKey(e.target.value)} placeholder={llmKeyMasked?"(saved — type to replace)":llmPreset==="groq"?"gsk_...":"sk-..."} style={{flex:1}}/><button style={{width:30,padding:0,fontSize:12}} onClick={()=>setShowKey(p=>!p)}>{showKey?"🙈":"👁"}</button></div></div>}
      {llmPreset==="ollama"&&<div className="form-group"><label className="form-label">URL</label><input value={llmUrl||"http://localhost:11434"} onChange={e=>setLlmUrl(e.target.value)}/></div>}
    </div>
    <div style={{display:"flex",gap:5}}>
      <button className="btn-primary" disabled={saving} onClick={doSave}>Save</button>
      <button className={testingConnection?"btn-loading":""} disabled={testingConnection} onClick={async()=>{setTestingConnection(true);try{const r=await sdk.system.llm.test();setLlmTestResult(r);toast(r.status==="success"?`✓ ${r.model||llmModel} — ${r.latency_ms||"?"}ms`:"Failed",r.status==="success"?"success":"error")}catch(e){setError(e.message)}finally{setTestingConnection(false)}}}>Test Connection</button>
    </div>
    {llmTestResult&&<div className={`result-banner ${llmTestResult.status==="success"?"is-success":"is-error"}`} style={{fontSize:11}}>
      {llmTestResult.status==="success"?`✓ Connected — ${llmTestResult.model||llmModel} — ${llmTestResult.latency_ms||"?"}ms`:`✗ ${llmTestResult.error_message||"Connection failed"}`}
    </div>}
  </div>);
}
