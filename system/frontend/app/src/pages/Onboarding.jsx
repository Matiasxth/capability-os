import React, { useState } from "react";
import sdk from "../sdk";

const PROVIDERS = {
  anthropic: { label: "Anthropic", desc: "Claude models", rec: true, provider: "anthropic", base_url: "https://api.anthropic.com", models: ["claude-sonnet-4-20250514","claude-haiku-4-5-20251001"], needsKey: true },
  openai: { label: "OpenAI", desc: "GPT models", provider: "openai", base_url: "https://api.openai.com/v1", models: ["gpt-4o","gpt-4o-mini","gpt-3.5-turbo"], needsKey: true },
  groq: { label: "Groq", desc: "Free & fast", provider: "openai", base_url: "https://api.groq.com/openai/v1", models: ["llama-3.1-70b-versatile","llama-3.1-8b-instant","mixtral-8x7b-32768","gemma2-9b-it"], needsKey: true },
  ollama: { label: "Ollama", desc: "Local & private", provider: "ollama", base_url: "http://localhost:11434", models: [], needsKey: false },
  gemini: { label: "Google Gemini", desc: "Free tier available", provider: "gemini", base_url: "https://generativelanguage.googleapis.com", models: ["gemini-2.0-flash","gemini-1.5-pro"], needsKey: true },
  deepseek: { label: "DeepSeek", desc: "Cost-effective", provider: "deepseek", base_url: "https://api.deepseek.com/v1", models: ["deepseek-chat","deepseek-reasoner"], needsKey: true },
};

export default function Onboarding({ onComplete }) {
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [focused, setFocused] = useState(false);
  const [saving, setSaving] = useState(false);
  const [provider, setProvider] = useState("anthropic");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("claude-sonnet-4-20250514");
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [ollamaModel, setOllamaModel] = useState("llama3.1:8b");

  async function submitName(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try { await sdk.memory.setPreferences({ name: name.trim() }); } catch {}
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
      try { await sdk.system.settings.save({ llm }); } catch {}
    }
    setSaving(false);
    setStep(3);
  }

  // ── Cyberpunk styles ──
  const cx = {
    wrap: {
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "#06060e",
      backgroundImage: "radial-gradient(ellipse at 30% 20%, rgba(0,240,255,0.06) 0%, transparent 50%), radial-gradient(ellipse at 70% 80%, rgba(255,45,111,0.04) 0%, transparent 50%)",
      fontFamily: "'Inter',-apple-system,sans-serif",
    },
    form: {
      display: "flex", flexDirection: "column", alignItems: "center", gap: 24,
      maxWidth: 440, width: "100%", padding: "0 24px", animation: "onb-in .6s cubic-bezier(0.16,1,0.3,1)",
    },
    logoBox: {
      width: 36, height: 36, borderRadius: 8,
      background: "linear-gradient(135deg, #00f0ff, #7b2dff)",
      boxShadow: "0 0 24px rgba(0,240,255,0.25)",
    },
    title: {
      fontSize: 28, fontWeight: 300, color: "#e0e4f0", letterSpacing: "-0.02em",
      margin: 0, lineHeight: 1.3, textAlign: "center",
    },
    input: (f) => ({
      width: "100%", height: 48, fontSize: 16, fontFamily: "inherit",
      background: "rgba(10,14,26,0.8)", border: `1px solid ${f ? "rgba(0,240,255,0.5)" : "rgba(255,255,255,0.10)"}`,
      borderRadius: 10, color: "#eef0f6", padding: "0 18px", outline: "none",
      transition: "all .2s", boxShadow: f ? "0 0 12px rgba(0,240,255,0.1)" : "none",
    }),
    btn: (ok) => ({
      width: "100%", height: 48, fontSize: 14, fontWeight: 700, fontFamily: "inherit",
      letterSpacing: 1, textTransform: "uppercase",
      background: ok ? "linear-gradient(135deg, #00f0ff, #00c8dd)" : "rgba(20,20,30,0.6)",
      color: ok ? "#06060e" : "#444", border: ok ? "1px solid #00f0ff" : "1px solid rgba(255,255,255,0.06)",
      borderRadius: 10, cursor: ok ? "pointer" : "not-allowed", transition: "all .2s",
      boxShadow: ok ? "0 0 20px rgba(0,240,255,0.2)" : "none",
    }),
    card: (active) => ({
      padding: "14px 16px", borderRadius: 10,
      border: `1px solid ${active ? "rgba(0,240,255,0.35)" : "rgba(255,255,255,0.08)"}`,
      background: active ? "rgba(0,240,255,0.06)" : "rgba(10,14,26,0.6)",
      cursor: "pointer", transition: "all .15s", textAlign: "left",
      boxShadow: active ? "0 0 12px rgba(0,240,255,0.08)" : "none",
    }),
    sub: { fontSize: 12, color: "#505468", textAlign: "center", maxWidth: 300, lineHeight: 1.6 },
    skip: {
      background: "none", border: "none", color: "#505468", fontSize: 12,
      cursor: "pointer", padding: 4, transition: "color 0.2s",
    },
    hbar: {
      height: 1, width: "60%",
      background: "linear-gradient(90deg, transparent, rgba(0,240,255,0.3), rgba(123,45,223,0.3), transparent)",
      margin: "4px auto",
    },
  };

  function StepDots() {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 0, width: "100%", maxWidth: 200, margin: "0 auto 4px" }}>
        {[1, 2, 3].map((s, i) => (
          <React.Fragment key={s}>
            {i > 0 && <div style={{ flex: 1, height: 2, background: step > s - 1 ? "#00f0ff" : "rgba(255,255,255,0.06)", transition: "background .3s" }} />}
            <div style={{
              width: 28, height: 28, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 11, fontWeight: 700, flexShrink: 0, transition: "all .3s",
              background: step >= s ? "linear-gradient(135deg, #00f0ff, #7b2dff)" : "rgba(255,255,255,0.04)",
              color: step >= s ? "#06060e" : "#505468",
              boxShadow: step >= s ? "0 0 10px rgba(0,240,255,0.2)" : "none",
            }}>{s}</div>
          </React.Fragment>
        ))}
      </div>
    );
  }

  const Logo = () => (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <div style={cx.logoBox} />
      <span style={{ fontSize: 20, fontWeight: 800, letterSpacing: 2, background: "linear-gradient(90deg, #00f0ff, #7b2dff)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
        CAPABILITY OS
      </span>
    </div>
  );

  // ── Step 1: Name ──
  if (step === 1) return (
    <div style={cx.wrap}>
      <form onSubmit={submitName} style={cx.form}>
        <Logo />
        <StepDots />
        <div style={cx.hbar} />
        <h1 style={cx.title}>Welcome. What's your name?</h1>
        <input type="text" value={name} onChange={e => setName(e.target.value)} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} placeholder="Your name" autoFocus style={cx.input(focused)} />
        <button type="submit" disabled={!name.trim() || saving} style={cx.btn(!!name.trim())}>{saving ? "..." : "Continue"}</button>
        <p style={cx.sub}>Your local AI assistant that learns and grows with you.</p>
      </form>
      <style>{`@keyframes onb-in{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}`}</style>
    </div>
  );

  // ── Step 2: LLM ──
  if (step === 2) {
    const P = PROVIDERS[provider] || PROVIDERS.groq;
    return (
      <div style={cx.wrap}>
        <div style={{ ...cx.form, gap: 18 }}>
          <Logo />
          <StepDots />
          <div style={cx.hbar} />
          <h1 style={{ ...cx.title, fontSize: 22 }}>Connect your LLM</h1>

          <div style={{ display: "flex", flexDirection: "column", gap: 6, width: "100%" }}>
            {Object.entries(PROVIDERS).map(([k, v]) => (
              <div key={k} style={cx.card(provider === k)} onClick={() => { setProvider(k); if (v.models.length) setModel(v.models[0]); }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: 14, color: provider === k ? "#00f0ff" : "#c0c4d0" }}>{v.label}</span>
                  {v.rec && <span style={{ fontSize: 9, padding: "2px 6px", borderRadius: 4, background: "rgba(0,240,255,0.1)", color: "#00f0ff", fontWeight: 700, textTransform: "uppercase", letterSpacing: 1 }}>rec</span>}
                </div>
                {v.desc && <div style={{ fontSize: 11, color: "#505468", marginTop: 2 }}>{v.desc}</div>}
              </div>
            ))}
          </div>

          {provider === "groq" && (<div style={{ display: "flex", flexDirection: "column", gap: 6, width: "100%" }}>
            <label style={{ fontSize: 11, color: "#6a7090" }}>Model</label>
            <select value={model} onChange={e => setModel(e.target.value)} style={cx.input(false)}>
              {P.models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            <label style={{ fontSize: 11, color: "#6a7090" }}>API Key <a href="https://console.groq.com/keys" target="_blank" rel="noreferrer" style={{ color: "#00f0ff", fontSize: 10, marginLeft: 4 }}>Get free key</a></label>
            <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="gsk_..." style={cx.input(false)} />
          </div>)}

          {provider === "ollama" && (<div style={{ display: "flex", flexDirection: "column", gap: 6, width: "100%" }}>
            <p style={{ fontSize: 11, color: "#505468", margin: 0 }}>Make sure Ollama is running locally.</p>
            <label style={{ fontSize: 11, color: "#6a7090" }}>URL</label>
            <input value={ollamaUrl} onChange={e => setOllamaUrl(e.target.value)} style={cx.input(false)} />
            <label style={{ fontSize: 11, color: "#6a7090" }}>Model</label>
            <input value={ollamaModel} onChange={e => setOllamaModel(e.target.value)} placeholder="llama3.1:8b" style={cx.input(false)} />
          </div>)}

          {["openai", "anthropic", "gemini", "deepseek"].includes(provider) && (<div style={{ display: "flex", flexDirection: "column", gap: 6, width: "100%" }}>
            <label style={{ fontSize: 11, color: "#6a7090" }}>Model</label>
            <select value={model} onChange={e => setModel(e.target.value)} style={cx.input(false)}>
              {P.models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            <label style={{ fontSize: 11, color: "#6a7090" }}>API Key</label>
            <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="sk-..." style={cx.input(false)} />
          </div>)}

          <button onClick={() => submitLLM(false)} disabled={saving || (P.needsKey && !apiKey)} style={{ ...cx.btn(!saving && (!P.needsKey || !!apiKey)), flex: 1 }}>
            {saving ? "..." : "Save & Start"}
          </button>
          <button onClick={() => submitLLM(true)} style={cx.skip}>Skip, configure later</button>
        </div>
        <style>{`@keyframes onb-in{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}`}</style>
      </div>
    );
  }

  // ── Step 3: Ready ──
  return (
    <div style={cx.wrap}>
      <div style={{ ...cx.form, gap: 20 }}>
        <Logo />
        <StepDots />
        <div style={cx.hbar} />
        <h1 style={{ ...cx.title, fontSize: 24 }}>You're all set, {name}!</h1>
        <p style={{ ...cx.sub, maxWidth: 320 }}>Your AI assistant is ready. Configure workspaces and integrations anytime from the Control Center.</p>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%", background: "rgba(0,240,255,0.03)", border: "1px solid rgba(0,240,255,0.1)", borderRadius: 12, padding: 18 }}>
          {[
            ["\u{1F4AC}", "Chat with CapOS", "Ask anything in natural language"],
            ["\u2328\uFE0F", "Ctrl+K for Command Palette", "Quick access to everything"],
            ["\u2699\uFE0F", "Control Center", "Integrations, LLM, browser, skills"],
          ].map(([icon, title, desc], i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 18 }}>{icon}</span>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#c0c4d0" }}>{title}</div>
                <div style={{ fontSize: 11, color: "#505468" }}>{desc}</div>
              </div>
            </div>
          ))}
        </div>
        <button onClick={() => onComplete(name.trim())} style={cx.btn(true)}>Launch CapOS</button>
      </div>
      <style>{`@keyframes onb-in{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}`}</style>
    </div>
  );
}
