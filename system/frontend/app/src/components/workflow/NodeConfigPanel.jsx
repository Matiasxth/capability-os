import React, { useEffect, useState } from "react";
import sdk from "../../sdk";

/* ── Shared hooks for loading tools/agents ── */
function useToolList() {
  const [tools, setTools] = useState([]);
  useEffect(() => { sdk.capabilities.list().then(r => setTools(r.capabilities || [])).catch(() => {}); }, []);
  return tools;
}
function useAgentList() {
  const [agents, setAgents] = useState([]);
  useEffect(() => { sdk.agents.list().then(r => setAgents(r.agents || [])).catch(() => {}); }, []);
  return agents;
}

/* ── Per-type config forms ── */

function TriggerConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Schedule</label>
      <select className="wf-cfg-input" value={data.schedule || "manual"} onChange={(e) => onChange({ ...data, schedule: e.target.value })}>
        <option value="manual">Manual</option>
        <option value="daily">Daily (HH:MM)</option>
        <option value="every_5min">Every 5 min</option>
        <option value="every_15min">Every 15 min</option>
        <option value="every_30min">Every 30 min</option>
        <option value="every_60min">Every 60 min</option>
      </select>
      {data.schedule === "daily" && (
        <>
          <label className="wf-cfg-label">Time (HH:MM)</label>
          <input className="wf-cfg-input" type="time" value={data.time || "09:00"} onChange={(e) => onChange({ ...data, time: e.target.value })} />
        </>
      )}
    </>
  );
}

function ToolConfig({ data, onChange }) {
  const tools = useToolList();
  return (
    <>
      <label className="wf-cfg-label">Tool</label>
      <select className="wf-cfg-input" value={data.tool_id || ""} onChange={(e) => onChange({ ...data, tool_id: e.target.value })}>
        <option value="">-- select tool --</option>
        {tools.map(t => <option key={t.id} value={t.id}>{t.name || t.id}</option>)}
      </select>
      {data.tool_id && <div style={{ fontSize: 9, color: "var(--text-muted)", margin: "2px 0 6px" }}>{tools.find(t => t.id === data.tool_id)?.description || ""}</div>}
      <label className="wf-cfg-label">Params (JSON)</label>
      <textarea className="wf-cfg-textarea" rows={5} placeholder='{"path": "/tmp/data.txt"}' value={data.params_json || ""} onChange={(e) => onChange({ ...data, params_json: e.target.value })} />
    </>
  );
}

function AgentConfig({ data, onChange }) {
  const agents = useAgentList();
  return (
    <>
      <label className="wf-cfg-label">Agent</label>
      <select className="wf-cfg-input" value={data.agent_id || ""} onChange={(e) => onChange({ ...data, agent_id: e.target.value })}>
        <option value="">-- default agent --</option>
        {agents.map(a => <option key={a.id} value={a.id}>{a.emoji} {a.name}</option>)}
      </select>
      <label className="wf-cfg-label">Message</label>
      <textarea className="wf-cfg-textarea" rows={4} placeholder="What should the agent do?" value={data.message || ""} onChange={(e) => onChange({ ...data, message: e.target.value })} />
    </>
  );
}

function ConditionConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Expression</label>
      <input className="wf-cfg-input" placeholder='e.g. result.status == "ok"' value={data.expression || ""} onChange={(e) => onChange({ ...data, expression: e.target.value })} />
      <label className="wf-cfg-label">True label</label>
      <input className="wf-cfg-input" value={data.true_label || "True"} onChange={(e) => onChange({ ...data, true_label: e.target.value })} />
      <label className="wf-cfg-label">False label</label>
      <input className="wf-cfg-input" value={data.false_label || "False"} onChange={(e) => onChange({ ...data, false_label: e.target.value })} />
    </>
  );
}

function LoopConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Iterations</label>
      <input className="wf-cfg-input" type="number" min={0} placeholder="Leave blank for collection iteration" value={data.iterations ?? ""} onChange={(e) => onChange({ ...data, iterations: e.target.value ? Number(e.target.value) : undefined })} />
      <label className="wf-cfg-label">Collection expression</label>
      <input className="wf-cfg-input" placeholder="e.g. result.items" value={data.collection || ""} onChange={(e) => onChange({ ...data, collection: e.target.value })} />
    </>
  );
}

function TransformConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Transform expression</label>
      <textarea className="wf-cfg-textarea" rows={4} placeholder="e.g. { summary: result.text.slice(0,100) }" value={data.expression || ""} onChange={(e) => onChange({ ...data, expression: e.target.value })} />
    </>
  );
}

function DelayConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Seconds</label>
      <input className="wf-cfg-input" type="number" min={0} value={data.seconds ?? 0} onChange={(e) => onChange({ ...data, seconds: Number(e.target.value) })} />
    </>
  );
}

function OutputConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Channel</label>
      <select className="wf-cfg-input" value={data.channel || "ui"} onChange={(e) => onChange({ ...data, channel: e.target.value })}>
        <option value="ui">UI</option>
        <option value="whatsapp">WhatsApp</option>
        <option value="telegram">Telegram</option>
        <option value="discord">Discord</option>
        <option value="slack">Slack</option>
      </select>
      <label className="wf-cfg-label">Template</label>
      <textarea className="wf-cfg-textarea" rows={4} placeholder="Output template with {{result}} placeholders" value={data.template || ""} onChange={(e) => onChange({ ...data, template: e.target.value })} />
    </>
  );
}

function HttpConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Method</label>
      <select className="wf-cfg-input" value={data.method || "GET"} onChange={(e) => onChange({ ...data, method: e.target.value })}>
        <option value="GET">GET</option>
        <option value="POST">POST</option>
        <option value="PUT">PUT</option>
        <option value="DELETE">DELETE</option>
        <option value="PATCH">PATCH</option>
      </select>
      <label className="wf-cfg-label">URL</label>
      <input className="wf-cfg-input" placeholder="https://api.example.com/data" value={data.url || ""} onChange={(e) => onChange({ ...data, url: e.target.value })} />
      <label className="wf-cfg-label">Headers (JSON)</label>
      <textarea className="wf-cfg-textarea" rows={3} placeholder='{"Authorization": "Bearer ..."}' value={data.headers_json || ""} onChange={(e) => onChange({ ...data, headers_json: e.target.value })} />
      <label className="wf-cfg-label">Body (JSON)</label>
      <textarea className="wf-cfg-textarea" rows={4} placeholder='{"key": "value"}' value={data.body_json || ""} onChange={(e) => onChange({ ...data, body_json: e.target.value })} />
    </>
  );
}

function NotificationConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Channel</label>
      <select className="wf-cfg-input" value={data.channel || "ui"} onChange={(e) => onChange({ ...data, channel: e.target.value })}>
        <option value="ui">UI Toast</option>
        <option value="whatsapp">WhatsApp</option>
        <option value="telegram">Telegram</option>
        <option value="slack">Slack</option>
        <option value="discord">Discord</option>
      </select>
      <label className="wf-cfg-label">Message</label>
      <textarea className="wf-cfg-textarea" rows={3} placeholder="Workflow completed! Result: {{result}}" value={data.message || ""} onChange={(e) => onChange({ ...data, message: e.target.value })} />
      <label className="wf-cfg-label">Recipient (optional)</label>
      <input className="wf-cfg-input" placeholder="chat_id, channel_id, or phone" value={data.recipient || ""} onChange={(e) => onChange({ ...data, recipient: e.target.value })} />
    </>
  );
}

function ScriptConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Language</label>
      <select className="wf-cfg-input" value={data.language || "python"} onChange={(e) => onChange({ ...data, language: e.target.value })}>
        <option value="python">Python</option>
        <option value="javascript">JavaScript</option>
      </select>
      <label className="wf-cfg-label">Code</label>
      <textarea className="wf-cfg-textarea" rows={8} placeholder={"# Access previous result via 'result' variable\noutput = result['data']"} value={data.code || ""} onChange={(e) => onChange({ ...data, code: e.target.value })} style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11 }} />
    </>
  );
}

function PromptConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Prompt</label>
      <textarea className="wf-cfg-textarea" rows={5} placeholder="Summarize the following data: {{result}}" value={data.prompt || ""} onChange={(e) => onChange({ ...data, prompt: e.target.value })} />
      <label className="wf-cfg-label">Model (optional)</label>
      <input className="wf-cfg-input" placeholder="Leave blank for system default" value={data.model || ""} onChange={(e) => onChange({ ...data, model: e.target.value })} />
      <label className="wf-cfg-label">Max tokens</label>
      <input className="wf-cfg-input" type="number" min={1} max={8192} placeholder="1024" value={data.max_tokens ?? ""} onChange={(e) => onChange({ ...data, max_tokens: e.target.value ? Number(e.target.value) : undefined })} />
    </>
  );
}

function FileConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Operation</label>
      <select className="wf-cfg-input" value={data.operation || "read"} onChange={(e) => onChange({ ...data, operation: e.target.value })}>
        <option value="read">Read file</option>
        <option value="write">Write file</option>
        <option value="append">Append to file</option>
        <option value="list">List directory</option>
      </select>
      <label className="wf-cfg-label">Path</label>
      <input className="wf-cfg-input" placeholder="/path/to/file.txt" value={data.path || ""} onChange={(e) => onChange({ ...data, path: e.target.value })} />
      {(data.operation === "write" || data.operation === "append") && (
        <>
          <label className="wf-cfg-label">Content</label>
          <textarea className="wf-cfg-textarea" rows={4} placeholder="Content to write (supports {{result}} placeholders)" value={data.content || ""} onChange={(e) => onChange({ ...data, content: e.target.value })} />
        </>
      )}
    </>
  );
}

const CONFIG_MAP = {
  trigger: TriggerConfig,
  tool: ToolConfig,
  agent: AgentConfig,
  condition: ConditionConfig,
  loop: LoopConfig,
  transform: TransformConfig,
  delay: DelayConfig,
  output: OutputConfig,
  http: HttpConfig,
  notification: NotificationConfig,
  script: ScriptConfig,
  prompt: PromptConfig,
  file: FileConfig,
};

export default function NodeConfigPanel({ node, onChange }) {
  if (!node) {
    return (
      <div className="wf-config-panel wf-config-empty">
        <div className="wf-config-empty-text">Select a node to configure</div>
      </div>
    );
  }

  const ConfigForm = CONFIG_MAP[node.type];

  function handleDataChange(newData) {
    onChange(node.id, { ...node.data, ...newData });
  }

  return (
    <div className="wf-config-panel">
      <div className="wf-config-title">Configure: {node.data.label || node.type}</div>

      <label className="wf-cfg-label">Label</label>
      <input className="wf-cfg-input" value={node.data.label || ""} onChange={(e) => handleDataChange({ label: e.target.value })} />

      {ConfigForm && <ConfigForm data={node.data} onChange={handleDataChange} />}

      {/* Run status indicator */}
      {node.data._runStatus && (
        <div style={{ marginTop: 8, padding: "6px 10px", borderRadius: 6, fontSize: 11, background: node.data._runStatus === "success" ? "rgba(0,255,136,0.1)" : "rgba(255,68,68,0.1)", color: node.data._runStatus === "success" ? "var(--success)" : "var(--error)", border: `1px solid ${node.data._runStatus === "success" ? "rgba(0,255,136,0.2)" : "rgba(255,68,68,0.2)"}` }}>
          {node.data._runStatus === "success" ? "Last run: Success" : "Last run: Error"}
          {node.data._runOutput && <pre style={{ margin: "4px 0 0", fontSize: 10, whiteSpace: "pre-wrap", maxHeight: 100, overflow: "auto" }}>{typeof node.data._runOutput === "string" ? node.data._runOutput : JSON.stringify(node.data._runOutput, null, 2)}</pre>}
        </div>
      )}
    </div>
  );
}
