import React, { useState, useRef, useEffect } from "react";

export default function Terminal({ onExecute }) {
  const [history, setHistory] = useState([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || running) return;
    const cmd = input;
    setInput("");
    setHistory(h => [...h, { type: "input", text: "$ " + cmd }]);
    setRunning(true);
    try {
      const result = await onExecute(cmd);
      if (result.stdout) setHistory(h => [...h, { type: "output", text: result.stdout }]);
      if (result.stderr) setHistory(h => [...h, { type: "error", text: result.stderr }]);
      if (result.exit_code !== 0 && !result.stderr) setHistory(h => [...h, { type: "error", text: `Exit code: ${result.exit_code}` }]);
    } catch (err) {
      setHistory(h => [...h, { type: "error", text: err.message }]);
    }
    setRunning(false);
  };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: "var(--bg-root)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
      <div style={{ padding: "4px 8px", background: "var(--bg-elevated)", borderBottom: "1px solid var(--border)", fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 1 }}>Terminal</div>
      <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
        {history.map((h, i) => (
          <div key={i} style={{ whiteSpace: "pre-wrap", wordBreak: "break-all", color: h.type === "error" ? "var(--error)" : h.type === "input" ? "var(--accent)" : "var(--text-dim)", marginBottom: 2 }}>
            {h.text}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={handleSubmit} style={{ display: "flex", borderTop: "1px solid var(--border)" }}>
        <span style={{ padding: "6px 8px", color: "var(--accent)", flexShrink: 0 }}>$</span>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={running}
          style={{ flex: 1, background: "transparent", border: "none", color: "var(--text)", outline: "none", padding: "6px 0", fontFamily: "inherit", fontSize: "inherit" }}
          placeholder={running ? "running..." : "type a command..."}
          autoFocus
        />
      </form>
    </div>
  );
}
