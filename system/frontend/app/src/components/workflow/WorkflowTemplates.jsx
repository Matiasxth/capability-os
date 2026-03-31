import React from "react";

const TEMPLATES = [
  {
    id: "monitor_notify",
    name: "Monitor & Notify",
    desc: "Check a URL periodically and send notification on change",
    icon: "📡",
    nodes: [
      { id: "t1", type: "trigger", position: { x: 250, y: 0 }, data: { label: "Schedule", schedule: "every_30min" } },
      { id: "t2", type: "http", position: { x: 250, y: 120 }, data: { label: "Check URL", method: "GET", url: "https://example.com/api/status" } },
      { id: "t3", type: "condition", position: { x: 250, y: 240 }, data: { label: "Changed?", expression: 'result.status != "ok"', true_label: "Alert", false_label: "OK" } },
      { id: "t4", type: "notification", position: { x: 100, y: 380 }, data: { label: "Send Alert", channel: "telegram", message: "Status changed: {{result}}" } },
    ],
    edges: [
      { id: "e1", source: "t1", target: "t2", animated: true },
      { id: "e2", source: "t2", target: "t3", animated: true },
      { id: "e3", source: "t3", sourceHandle: "true", target: "t4", animated: true },
    ],
  },
  {
    id: "file_pipeline",
    name: "File Processing",
    desc: "Read a file, transform it with AI, write the result",
    icon: "📄",
    nodes: [
      { id: "f1", type: "trigger", position: { x: 250, y: 0 }, data: { label: "Start", schedule: "manual" } },
      { id: "f2", type: "file", position: { x: 250, y: 120 }, data: { label: "Read Input", operation: "read", path: "/data/input.txt" } },
      { id: "f3", type: "prompt", position: { x: 250, y: 240 }, data: { label: "Process with AI", prompt: "Summarize the following text:\n\n{{result}}" } },
      { id: "f4", type: "file", position: { x: 250, y: 360 }, data: { label: "Write Output", operation: "write", path: "/data/summary.txt", content: "{{result}}" } },
    ],
    edges: [
      { id: "e1", source: "f1", target: "f2", animated: true },
      { id: "e2", source: "f2", target: "f3", animated: true },
      { id: "e3", source: "f3", target: "f4", animated: true },
    ],
  },
  {
    id: "agent_chain",
    name: "Agent Chain",
    desc: "Sequential agents — research, analyze, report",
    icon: "🔗",
    nodes: [
      { id: "a1", type: "trigger", position: { x: 250, y: 0 }, data: { label: "Start", schedule: "manual" } },
      { id: "a2", type: "agent", position: { x: 250, y: 120 }, data: { label: "Research", message: "Research the latest trends in AI" } },
      { id: "a3", type: "agent", position: { x: 250, y: 260 }, data: { label: "Analyze", message: "Analyze the research and identify key insights: {{result}}" } },
      { id: "a4", type: "agent", position: { x: 250, y: 400 }, data: { label: "Report", message: "Write a concise report based on this analysis: {{result}}" } },
      { id: "a5", type: "output", position: { x: 250, y: 540 }, data: { label: "Deliver", channel: "ui" } },
    ],
    edges: [
      { id: "e1", source: "a1", target: "a2", animated: true },
      { id: "e2", source: "a2", target: "a3", animated: true },
      { id: "e3", source: "a3", target: "a4", animated: true },
      { id: "e4", source: "a4", target: "a5", animated: true },
    ],
  },
  {
    id: "scheduled_report",
    name: "Scheduled Report",
    desc: "Daily report sent to a messaging channel",
    icon: "📊",
    nodes: [
      { id: "r1", type: "trigger", position: { x: 250, y: 0 }, data: { label: "Daily 9AM", schedule: "daily", time: "09:00" } },
      { id: "r2", type: "tool", position: { x: 250, y: 120 }, data: { label: "Gather Data", tool_id: "" } },
      { id: "r3", type: "prompt", position: { x: 250, y: 240 }, data: { label: "Generate Report", prompt: "Create a daily summary report from this data:\n\n{{result}}" } },
      { id: "r4", type: "notification", position: { x: 250, y: 380 }, data: { label: "Send Report", channel: "slack", message: "Daily Report:\n\n{{result}}" } },
    ],
    edges: [
      { id: "e1", source: "r1", target: "r2", animated: true },
      { id: "e2", source: "r2", target: "r3", animated: true },
      { id: "e3", source: "r3", target: "r4", animated: true },
    ],
  },
  {
    id: "data_scraper",
    name: "Web Scraper",
    desc: "Fetch data from URL, extract info, save to file",
    icon: "🕷",
    nodes: [
      { id: "s1", type: "trigger", position: { x: 250, y: 0 }, data: { label: "Start", schedule: "manual" } },
      { id: "s2", type: "http", position: { x: 250, y: 120 }, data: { label: "Fetch Page", method: "GET", url: "https://example.com" } },
      { id: "s3", type: "transform", position: { x: 250, y: 240 }, data: { label: "Extract Data", expression: "result.body" } },
      { id: "s4", type: "prompt", position: { x: 250, y: 360 }, data: { label: "Parse with AI", prompt: "Extract all product names and prices from this HTML:\n\n{{result}}" } },
      { id: "s5", type: "file", position: { x: 250, y: 480 }, data: { label: "Save Results", operation: "write", path: "/data/scraped.json", content: "{{result}}" } },
    ],
    edges: [
      { id: "e1", source: "s1", target: "s2", animated: true },
      { id: "e2", source: "s2", target: "s3", animated: true },
      { id: "e3", source: "s3", target: "s4", animated: true },
      { id: "e4", source: "s4", target: "s5", animated: true },
    ],
  },
];

export default function WorkflowTemplates({ onUseTemplate }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>Start from a template:</div>
      {TEMPLATES.map(t => (
        <button key={t.id} onClick={() => onUseTemplate(t)} style={{
          display: "flex", alignItems: "center", gap: 8, padding: "8px 10px",
          background: "var(--bg-input, #111)", border: "1px solid var(--border, #333)",
          borderRadius: 6, cursor: "pointer", textAlign: "left", color: "var(--text, #eee)",
          transition: "border-color 0.15s",
        }} onMouseEnter={e => e.currentTarget.style.borderColor = "var(--accent, #00ff88)"} onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border, #333)"}>
          <span style={{ fontSize: 18 }}>{t.icon}</span>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600 }}>{t.name}</div>
            <div style={{ fontSize: 9, color: "var(--text-muted)", marginTop: 1 }}>{t.desc}</div>
          </div>
        </button>
      ))}
    </div>
  );
}

export { TEMPLATES };
