import React from "react";
import StatusItem from "./StatusItem";

export default function StatusBar({ wsConnected, apiOnline, health, activeWorkspace, onOpenPalette }) {
  const llm = health?.llm || {};
  const bw = health?.browser_worker || {};
  const bwStatus = bw.status || (bw.transport?.alive ? "ready" : "off");
  const llmLabel = llm.provider ? `${llm.provider}/${llm.model || "?"}` : "No LLM";

  return (
    <footer className="status-bar">
      <div className="status-bar-left">
        <StatusItem label={wsConnected ? "Real-time" : "Polling"} status={wsConnected ? "success" : "neutral"} />
        <StatusItem label={apiOnline ? "API" : "API offline"} status={apiOnline ? "success" : "error"} />
        <StatusItem label={llmLabel} status={llm.status === "ready" ? "success" : llm.provider ? "warning" : "neutral"} />
        <StatusItem label={`Browser: ${bwStatus}`} status={bwStatus === "ready" ? "success" : bwStatus === "error" ? "error" : "neutral"} />
      </div>
      <div className="status-bar-right">
        {activeWorkspace && <StatusItem label={activeWorkspace.name} status="success" />}
        <span className="status-bar-hint" onClick={onOpenPalette} title="Command Palette">Ctrl+K</span>
      </div>
    </footer>
  );
}
