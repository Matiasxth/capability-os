import React, { useState } from "react";
import sdk from "../../sdk";

const SYSTEM_PROMPT = `You are a workflow designer for Capability OS. The user describes what they want and you generate a workflow definition.

Available node types:
- trigger: Start node (schedule: manual, daily, every_5min, every_15min, every_30min, every_60min)
- tool: Execute a registered tool (tool_id, params_json)
- agent: Delegate to an AI agent (agent_id, message)
- condition: Branch on expression (expression, true_label, false_label)
- loop: Iterate (iterations or collection)
- transform: Data transformation (expression)
- delay: Wait N seconds (seconds)
- output: Send result (channel: ui/whatsapp/telegram/slack/discord, template)
- http: HTTP request (method, url, headers_json, body_json)
- notification: Send notification (channel, message, recipient)
- script: Run code (language: python/javascript, code)
- prompt: AI prompt (prompt, model, max_tokens)
- file: File operation (operation: read/write/append/list, path, content)

Respond with ONLY a JSON object (no markdown, no explanation):
{
  "name": "Workflow Name",
  "description": "Brief description",
  "nodes": [
    {"id": "n1", "type": "trigger", "position": {"x": 250, "y": 0}, "data": {"label": "Start", "schedule": "manual"}},
    ...
  ],
  "edges": [
    {"id": "e1", "source": "n1", "target": "n2", "animated": true},
    ...
  ]
}

Position nodes vertically with ~130px spacing. Use descriptive labels.`;

export default function WorkflowAIChat({ onGenerate }) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!input.trim() || loading) return;
    const query = input.trim();
    setInput("");
    setHistory(h => [...h, { role: "user", text: query }]);
    setLoading(true);
    setError("");

    try {
      const resp = await sdk.capabilities.chat(
        `[WORKFLOW DESIGNER]\n\nSystem: ${SYSTEM_PROMPT}\n\nUser request: ${query}`,
        "WorkflowDesigner",
        []
      );
      const text = resp.response || resp.content || "";
      setHistory(h => [...h, { role: "assistant", text }]);

      // Try to parse JSON from response
      const jsonMatch = text.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        try {
          const wf = JSON.parse(jsonMatch[0]);
          if (wf.nodes && wf.edges) {
            onGenerate(wf);
            setHistory(h => [...h, { role: "system", text: `Generated "${wf.name}" with ${wf.nodes.length} nodes` }]);
          }
        } catch {
          setError("Could not parse workflow from response. Try being more specific.");
        }
      }
    } catch (err) {
      setError(err.message || "Failed to generate");
      setHistory(h => [...h, { role: "system", text: "Error: " + (err.message || "Failed") }]);
    } finally {
      setLoading(false);
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} title="AI Workflow Designer" style={{
        position: "absolute", bottom: 16, right: 16, zIndex: 50,
        width: 44, height: 44, borderRadius: "50%",
        background: "linear-gradient(135deg, #00f0ff, #7b2dff)",
        border: "none", cursor: "pointer", fontSize: 20, color: "#fff",
        boxShadow: "0 4px 16px rgba(0,240,255,0.3)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        {"🧠"}
      </button>
    );
  }

  return (
    <div style={{
      position: "absolute", bottom: 16, right: 16, zIndex: 50,
      width: 360, maxHeight: 480,
      background: "var(--bg-elevated, #1a1a2e)", border: "1px solid var(--accent, #00ff88)",
      borderRadius: 12, boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
      display: "flex", flexDirection: "column", overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border, #333)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)" }}>AI Workflow Designer</span>
        <button onClick={() => setOpen(false)} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 16 }}>&times;</button>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 8, minHeight: 200, maxHeight: 320 }}>
        {history.length === 0 && (
          <div style={{ color: "var(--text-muted)", fontSize: 11, textAlign: "center", padding: 20 }}>
            Describe the workflow you need.<br />
            <span style={{ fontSize: 10, opacity: 0.7 }}>e.g. "Monitor a URL every hour and notify me on Telegram if it's down"</span>
          </div>
        )}
        {history.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.role === "user" ? "flex-end" : "flex-start",
            maxWidth: "85%", padding: "8px 12px", borderRadius: 10, fontSize: 11, lineHeight: 1.5,
            background: m.role === "user" ? "var(--accent-dim, rgba(0,255,136,0.1))" : m.role === "system" ? "rgba(100,100,255,0.1)" : "var(--bg-input, #111)",
            color: m.role === "system" ? "var(--accent)" : "var(--text)",
            border: m.role === "user" ? "1px solid var(--accent)" : "1px solid var(--border)",
            whiteSpace: "pre-wrap", wordBreak: "break-word",
          }}>
            {m.text.length > 300 ? m.text.slice(0, 300) + "..." : m.text}
          </div>
        ))}
        {loading && <div style={{ fontSize: 11, color: "var(--text-muted)", padding: 8 }}>Designing workflow...</div>}
      </div>

      {/* Error */}
      {error && <div style={{ padding: "4px 12px", fontSize: 10, color: "var(--error)" }}>{error}</div>}

      {/* Input */}
      <form onSubmit={handleSubmit} style={{ padding: 8, borderTop: "1px solid var(--border, #333)", display: "flex", gap: 6 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Describe your workflow..."
          disabled={loading}
          style={{ flex: 1, height: 32, fontSize: 11, padding: "0 10px", borderRadius: 6, background: "var(--bg-input)", border: "1px solid var(--border)", color: "var(--text)", outline: "none" }}
        />
        <button type="submit" disabled={loading || !input.trim()} style={{
          height: 32, padding: "0 14px", fontSize: 11, fontWeight: 600, borderRadius: 6,
          background: input.trim() ? "var(--accent)" : "var(--bg-input)",
          color: input.trim() ? "var(--bg-root, #000)" : "var(--text-muted)",
          border: "none", cursor: input.trim() ? "pointer" : "not-allowed",
        }}>Generate</button>
      </form>
    </div>
  );
}
