import React from "react";

/* ── Per-type config forms ── */

function TriggerConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Schedule</label>
      <select
        className="wf-cfg-input"
        value={data.schedule || "manual"}
        onChange={(e) => onChange({ ...data, schedule: e.target.value })}
      >
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
          <input
            className="wf-cfg-input"
            type="time"
            value={data.time || "09:00"}
            onChange={(e) => onChange({ ...data, time: e.target.value })}
          />
        </>
      )}
    </>
  );
}

function ToolConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Tool ID</label>
      <input
        className="wf-cfg-input"
        placeholder="e.g. read_file"
        value={data.tool_id || ""}
        onChange={(e) => onChange({ ...data, tool_id: e.target.value })}
      />
      <label className="wf-cfg-label">Params (JSON)</label>
      <textarea
        className="wf-cfg-textarea"
        rows={5}
        placeholder='{"path": "/tmp/data.txt"}'
        value={data.params_json || ""}
        onChange={(e) => onChange({ ...data, params_json: e.target.value })}
      />
    </>
  );
}

function AgentConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Agent</label>
      <input
        className="wf-cfg-input"
        placeholder="agent id or name"
        value={data.agent_id || ""}
        onChange={(e) => onChange({ ...data, agent_id: e.target.value })}
      />
      <label className="wf-cfg-label">Message</label>
      <textarea
        className="wf-cfg-textarea"
        rows={4}
        placeholder="What should the agent do?"
        value={data.message || ""}
        onChange={(e) => onChange({ ...data, message: e.target.value })}
      />
    </>
  );
}

function ConditionConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Expression</label>
      <input
        className="wf-cfg-input"
        placeholder='e.g. result.status == "ok"'
        value={data.expression || ""}
        onChange={(e) => onChange({ ...data, expression: e.target.value })}
      />
      <label className="wf-cfg-label">True label</label>
      <input
        className="wf-cfg-input"
        value={data.true_label || "True"}
        onChange={(e) => onChange({ ...data, true_label: e.target.value })}
      />
      <label className="wf-cfg-label">False label</label>
      <input
        className="wf-cfg-input"
        value={data.false_label || "False"}
        onChange={(e) => onChange({ ...data, false_label: e.target.value })}
      />
    </>
  );
}

function LoopConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Iterations</label>
      <input
        className="wf-cfg-input"
        type="number"
        min={0}
        placeholder="Leave blank for collection iteration"
        value={data.iterations ?? ""}
        onChange={(e) => onChange({ ...data, iterations: e.target.value ? Number(e.target.value) : undefined })}
      />
      <label className="wf-cfg-label">Collection expression</label>
      <input
        className="wf-cfg-input"
        placeholder="e.g. result.items"
        value={data.collection || ""}
        onChange={(e) => onChange({ ...data, collection: e.target.value })}
      />
    </>
  );
}

function TransformConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Transform expression</label>
      <textarea
        className="wf-cfg-textarea"
        rows={4}
        placeholder="e.g. { summary: result.text.slice(0,100) }"
        value={data.expression || ""}
        onChange={(e) => onChange({ ...data, expression: e.target.value })}
      />
    </>
  );
}

function DelayConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Seconds</label>
      <input
        className="wf-cfg-input"
        type="number"
        min={0}
        value={data.seconds ?? 0}
        onChange={(e) => onChange({ ...data, seconds: Number(e.target.value) })}
      />
    </>
  );
}

function OutputConfig({ data, onChange }) {
  return (
    <>
      <label className="wf-cfg-label">Channel</label>
      <select
        className="wf-cfg-input"
        value={data.channel || "ui"}
        onChange={(e) => onChange({ ...data, channel: e.target.value })}
      >
        <option value="ui">UI</option>
        <option value="whatsapp">WhatsApp</option>
        <option value="telegram">Telegram</option>
        <option value="discord">Discord</option>
        <option value="slack">Slack</option>
      </select>
      <label className="wf-cfg-label">Template</label>
      <textarea
        className="wf-cfg-textarea"
        rows={4}
        placeholder="Output template with {{result}} placeholders"
        value={data.template || ""}
        onChange={(e) => onChange({ ...data, template: e.target.value })}
      />
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
      <input
        className="wf-cfg-input"
        value={node.data.label || ""}
        onChange={(e) => handleDataChange({ label: e.target.value })}
      />

      {ConfigForm && <ConfigForm data={node.data} onChange={handleDataChange} />}
    </div>
  );
}
