import React, { useState } from "react";

/**
 * Renders agent loop events as a live step-by-step view.
 * Shows: thinking spinner, tool calls, results, errors, final response.
 */
export default function AgentStepView({ events }) {
  if (!events || events.length === 0) return null;

  const cx = {
    container: { marginTop: 8 },
    step: {
      background: "var(--glass-bg)", border: "1px solid var(--glass-border-light)", borderRadius: 8,
      padding: "8px 10px", marginBottom: 6, fontSize: 11,
    },
    thinking: { color: "#4a6fa5", fontStyle: "italic", display: "flex", alignItems: "center", gap: 6 },
    spinner: {
      width: 10, height: 10, border: "2px solid #1a2848", borderTopColor: "#4a8af5",
      borderRadius: "50%", animation: "spin 0.6s linear infinite", flexShrink: 0,
    },
    toolCall: { display: "flex", alignItems: "center", gap: 6, marginBottom: 4 },
    toolIcon: { fontSize: 13 },
    toolName: { color: "#4a8af5", fontWeight: 600 },
    secBadge: (level) => ({
      fontSize: 8, padding: "1px 5px", borderRadius: 3, fontWeight: 600,
      background: level === 1 ? "#0d2a1a" : level === 2 ? "#2a1a0a" : "#2a0a0a",
      color: level === 1 ? "#25d366" : level === 2 ? "#ffaa00" : "#ff4444",
      border: `1px solid ${level === 1 ? "#25d36633" : level === 2 ? "#ffaa0033" : "#ff444433"}`,
    }),
    params: {
      color: "#5a6f8a", fontFamily: "monospace", fontSize: 10,
      background: "rgba(0,0,0,0.2)", borderRadius: 6, padding: "6px 8px",
      maxHeight: 60, overflow: "auto", marginTop: 4,
    },
    result: {
      color: "#6a9f6a", fontFamily: "monospace", fontSize: 10,
      background: "rgba(0,0,0,0.2)", borderRadius: 6, padding: "6px 8px",
      maxHeight: 100, overflow: "auto", marginTop: 4,
    },
    error: { color: "#ff6666" },
    response: {
      color: "#c8d4e8", lineHeight: 1.6, whiteSpace: "pre-wrap",
    },
  };

  return (
    <div style={cx.container}>
      {events.map((ev, i) => {
        if (ev.event === "agent_thinking") {
          return (
            <div key={i} style={{ ...cx.step, ...cx.thinking }}>
              <div style={cx.spinner} />
              <span>Thinking... (step {ev.iteration})</span>
            </div>
          );
        }

        if (ev.event === "tool_call") {
          return (
            <div key={i} style={cx.step}>
              <div style={cx.toolCall}>
                <span style={cx.toolIcon}>{ev.security_level === 1 ? "\u2705" : ev.security_level === 2 ? "\u26A0\uFE0F" : "\uD83D\uDD12"}</span>
                <span style={cx.toolName}>{ev.tool_id}</span>
                <span style={cx.secBadge(ev.security_level)}>L{ev.security_level}</span>
              </div>
              {ev.params && Object.keys(ev.params).length > 0 && (
                <div style={cx.params}>{JSON.stringify(ev.params, null, 2)}</div>
              )}
            </div>
          );
        }

        if (ev.event === "tool_result") {
          const result = ev.result || {};
          const display = { ...result };
          delete display._success;
          const text = JSON.stringify(display, null, 2);
          return (
            <div key={i} style={{ ...cx.step, borderColor: ev.success ? "#1a3a1a" : "#3a1a1a" }}>
              <div style={{ fontSize: 10, color: ev.success ? "#4a8a4a" : "#aa4444", marginBottom: 2 }}>
                {ev.success ? "\u2714 Result" : "\u2718 Error"} — {ev.tool_id}
              </div>
              <div style={cx.result}>
                {text.length > 500 ? text.slice(0, 500) + "\n..." : text}
              </div>
            </div>
          );
        }

        if (ev.event === "agent_error") {
          return (
            <div key={i} style={{ ...cx.step, borderColor: "#3a1a1a" }}>
              <span style={cx.error}>{ev.error}</span>
            </div>
          );
        }

        if (ev.event === "agent_response") {
          return (
            <div key={i} style={cx.response}>
              {ev.text}
            </div>
          );
        }

        if (ev.event === "awaiting_confirmation") {
          return (
            <div key={i} style={{ ...cx.step, borderColor: "#3a2a0a" }}>
              <span style={{ color: "#ffaa00" }}>{"\u26A0\uFE0F"} Waiting for approval: {ev.tool_id}</span>
            </div>
          );
        }

        return null;
      })}
    </div>
  );
}
