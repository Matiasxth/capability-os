import React, { memo } from "react";
import { Handle, Position } from "@xyflow/react";

/* ── Shared node shell ── */
function NodeShell({ accent, icon, label, children, selected }) {
  return (
    <div
      className="wf-node"
      style={{
        border: `1.5px solid ${selected ? accent : "var(--border)"}`,
        boxShadow: selected ? `0 0 12px ${accent}44` : "var(--shadow)",
        "--node-accent": accent,
      }}
    >
      <div className="wf-node-header" style={{ borderBottom: `1px solid ${accent}33` }}>
        <span className="wf-node-icon" style={{ color: accent }}>{icon}</span>
        <span className="wf-node-label">{label}</span>
      </div>
      <div className="wf-node-body">{children}</div>
    </div>
  );
}

/* ── Trigger Node ── */
export const TriggerNode = memo(function TriggerNode({ data, selected }) {
  const schedule = data.schedule || "manual";
  return (
    <NodeShell accent="#00ff88" icon="⏱" label={data.label || "Trigger"} selected={selected}>
      <Handle type="source" position={Position.Bottom} style={{ background: "#00ff88" }} />
      <div className="wf-node-detail">{schedule === "manual" ? "Manual trigger" : schedule}</div>
    </NodeShell>
  );
});

/* ── Tool Node ── */
export const ToolNode = memo(function ToolNode({ data, selected }) {
  return (
    <NodeShell accent="#3b82f6" icon="🔧" label={data.label || "Tool"} selected={selected}>
      <Handle type="target" position={Position.Top} style={{ background: "#3b82f6" }} />
      <Handle type="source" position={Position.Bottom} style={{ background: "#3b82f6" }} />
      <div className="wf-node-detail">{data.tool_id || "No tool selected"}</div>
    </NodeShell>
  );
});

/* ── Agent Node ── */
export const AgentNode = memo(function AgentNode({ data, selected }) {
  const msg = data.message || "";
  return (
    <NodeShell accent="#06b6d4" icon="🤖" label={data.label || "Agent"} selected={selected}>
      <Handle type="target" position={Position.Top} style={{ background: "#06b6d4" }} />
      <Handle type="source" position={Position.Bottom} style={{ background: "#06b6d4" }} />
      <div className="wf-node-detail">{msg ? (msg.length > 40 ? msg.slice(0, 40) + "..." : msg) : "No message"}</div>
    </NodeShell>
  );
});

/* ── Condition Node ── */
export const ConditionNode = memo(function ConditionNode({ data, selected }) {
  return (
    <NodeShell accent="#eab308" icon="⑂" label={data.label || "Condition"} selected={selected}>
      <Handle type="target" position={Position.Top} style={{ background: "#eab308" }} />
      <Handle
        type="source"
        position={Position.Bottom}
        id="true"
        style={{ background: "#00ff88", left: "30%" }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="false"
        style={{ background: "#ff2d6f", left: "70%" }}
      />
      <div className="wf-node-detail">{data.expression || "No expression"}</div>
      <div className="wf-node-handles-label">
        <span style={{ color: "#00ff88" }}>{data.true_label || "True"}</span>
        <span style={{ color: "#ff2d6f" }}>{data.false_label || "False"}</span>
      </div>
    </NodeShell>
  );
});

/* ── Loop Node ── */
export const LoopNode = memo(function LoopNode({ data, selected }) {
  return (
    <NodeShell accent="#a855f7" icon="🔁" label={data.label || "Loop"} selected={selected}>
      <Handle type="target" position={Position.Top} style={{ background: "#a855f7" }} />
      <Handle type="source" position={Position.Bottom} style={{ background: "#a855f7" }} />
      <div className="wf-node-detail">{data.iterations ? `${data.iterations} iterations` : "Iterate over input"}</div>
    </NodeShell>
  );
});

/* ── Transform Node ── */
export const TransformNode = memo(function TransformNode({ data, selected }) {
  return (
    <NodeShell accent="#f97316" icon="⚡" label={data.label || "Transform"} selected={selected}>
      <Handle type="target" position={Position.Top} style={{ background: "#f97316" }} />
      <Handle type="source" position={Position.Bottom} style={{ background: "#f97316" }} />
      <div className="wf-node-detail">{data.expression || "Transform expression"}</div>
    </NodeShell>
  );
});

/* ── Delay Node ── */
export const DelayNode = memo(function DelayNode({ data, selected }) {
  return (
    <NodeShell accent="#6b7280" icon="⏳" label={data.label || "Delay"} selected={selected}>
      <Handle type="target" position={Position.Top} style={{ background: "#6b7280" }} />
      <Handle type="source" position={Position.Bottom} style={{ background: "#6b7280" }} />
      <div className="wf-node-detail">{data.seconds ? `${data.seconds}s` : "0s"}</div>
    </NodeShell>
  );
});

/* ── Output Node ── */
export const OutputNode = memo(function OutputNode({ data, selected }) {
  return (
    <NodeShell accent="#ec4899" icon="📤" label={data.label || "Output"} selected={selected}>
      <Handle type="target" position={Position.Top} style={{ background: "#ec4899" }} />
      <div className="wf-node-detail">{data.channel || "ui"}</div>
    </NodeShell>
  );
});

/* ── HTTP Request Node ── */
export const HttpNode = memo(function HttpNode({ data, selected }) {
  return (
    <NodeShell accent="#10b981" icon="🌐" label={data.label || "HTTP Request"} selected={selected}>
      <Handle type="target" position={Position.Top} style={{ background: "#10b981" }} />
      <Handle type="source" position={Position.Bottom} style={{ background: "#10b981" }} />
      <div className="wf-node-detail">{data.method || "GET"} {data.url ? data.url.slice(0, 30) : "No URL"}</div>
    </NodeShell>
  );
});

/* ── Notification Node ── */
export const NotificationNode = memo(function NotificationNode({ data, selected }) {
  return (
    <NodeShell accent="#f43f5e" icon="🔔" label={data.label || "Notification"} selected={selected}>
      <Handle type="target" position={Position.Top} style={{ background: "#f43f5e" }} />
      <Handle type="source" position={Position.Bottom} style={{ background: "#f43f5e" }} />
      <div className="wf-node-detail">{data.channel || "ui"}: {data.message ? data.message.slice(0, 30) : "No message"}</div>
    </NodeShell>
  );
});

/* ── Script Node ── */
export const ScriptNode = memo(function ScriptNode({ data, selected }) {
  return (
    <NodeShell accent="#8b5cf6" icon="📜" label={data.label || "Script"} selected={selected}>
      <Handle type="target" position={Position.Top} style={{ background: "#8b5cf6" }} />
      <Handle type="source" position={Position.Bottom} style={{ background: "#8b5cf6" }} />
      <div className="wf-node-detail">{data.language || "python"}: {data.code ? data.code.split("\n")[0].slice(0, 30) : "No code"}</div>
    </NodeShell>
  );
});

/* ── AI Prompt Node ── */
export const PromptNode = memo(function PromptNode({ data, selected }) {
  return (
    <NodeShell accent="#0ea5e9" icon="🧠" label={data.label || "AI Prompt"} selected={selected}>
      <Handle type="target" position={Position.Top} style={{ background: "#0ea5e9" }} />
      <Handle type="source" position={Position.Bottom} style={{ background: "#0ea5e9" }} />
      <div className="wf-node-detail">{data.prompt ? data.prompt.slice(0, 40) : "No prompt"}</div>
    </NodeShell>
  );
});

/* ── File Node ── */
export const FileNode = memo(function FileNode({ data, selected }) {
  return (
    <NodeShell accent="#d97706" icon="📁" label={data.label || "File"} selected={selected}>
      <Handle type="target" position={Position.Top} style={{ background: "#d97706" }} />
      <Handle type="source" position={Position.Bottom} style={{ background: "#d97706" }} />
      <div className="wf-node-detail">{data.operation || "read"}: {data.path || "No path"}</div>
    </NodeShell>
  );
});

/* ── Export map for ReactFlow ── */
export const nodeTypes = {
  trigger: TriggerNode,
  tool: ToolNode,
  agent: AgentNode,
  condition: ConditionNode,
  loop: LoopNode,
  transform: TransformNode,
  delay: DelayNode,
  output: OutputNode,
  http: HttpNode,
  notification: NotificationNode,
  script: ScriptNode,
  prompt: PromptNode,
  file: FileNode,
};
