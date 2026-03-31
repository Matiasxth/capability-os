import React, { useEffect, useState } from "react";

/**
 * Generic channel configuration card.
 * Handles: status loading, token/fields input, Save/Test/Poll buttons, setup guide.
 *
 * @param {object} props
 * @param {string} props.name - Display name (e.g. "Telegram")
 * @param {object} props.sdk - Channel SDK domain (e.g. sdk.integrations.telegram) with status/configure/test/startPolling/stopPolling/pollingStatus
 * @param {Array<{key: string, label: string, placeholder: string, type?: string}>} props.fields - Config fields
 * @param {function} props.buildConfig - (values) => config object for configure()
 * @param {string|React.ReactNode} [props.guide] - Setup guide content
 * @param {boolean} props.saving
 * @param {function} props.toast
 * @param {function} props.act
 */
export default function ChannelCard({ name, sdk: channel, fields, buildConfig, guide, saving, toast, act }) {
  const [status, setStatus] = useState(null);
  const [polling, setPolling] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const [values, setValues] = useState(() => {
    const init = {};
    fields.forEach(f => { init[f.key] = ""; });
    return init;
  });

  useEffect(() => {
    channel.status().then(r => {
      setStatus(r);
      if (r.allowed_user_ids && values.user_ids !== undefined) {
        setValues(v => ({ ...v, user_ids: r.allowed_user_ids.join(", ") }));
      }
    }).catch(() => setStatus({ configured: false }));
    channel.pollingStatus().then(r => setPolling(r.running)).catch(() => {});
  }, []);

  const st = status || {};
  const hasToken = fields.some(f => f.key === "token") ? !!values.token : true;

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <div className="item-row" style={{ padding: "8px 10px", cursor: "pointer" }} onClick={() => setExpanded(!expanded)}>
        <span style={{ fontSize: 10, color: "var(--text-muted)", marginRight: 2 }}>{expanded ? "\u25BC" : "\u25B6"}</span>
        <span className={`dot ${st.connected ? "dot-success" : st.configured ? "dot-warning" : "dot-neutral"}`} style={{ marginRight: 3 }} />
        <span style={{ fontSize: 11, fontWeight: 500, flex: 1 }}>{name}</span>
        {st.bot_name ? <span className="dim" style={{ fontSize: 10 }}>@{st.bot_name}</span> : !st.configured && <span className="badge badge-neutral" style={{ fontSize: 8 }}>not configured</span>}
        {polling && <span className="badge badge-success" style={{ fontSize: 8, marginLeft: 3 }}>polling</span>}
      </div>

      {expanded && <div style={{ padding: "6px 10px", borderTop: "1px solid rgba(255,255,255,0.04)", display: "flex", flexDirection: "column", gap: 5 }}>
        {fields.map(f => (
          <div key={f.key} style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <label style={{ fontSize: 10, color: "var(--text-dim)", width: 55 }}>{f.label}</label>
            {f.type === "token" ? (
              <div style={{ display: "flex", flex: 1, gap: 3 }}>
                <input type={showToken ? "text" : "password"} value={values[f.key]} onChange={e => setValues({ ...values, [f.key]: e.target.value })} placeholder={f.placeholder} style={{ flex: 1, height: 22, fontSize: 10 }} />
                <button style={{ width: 24, height: 22, fontSize: 10, padding: 0 }} onClick={() => setShowToken(p => !p)}>{showToken ? "*" : "A"}</button>
              </div>
            ) : (
              <input value={values[f.key]} onChange={e => setValues({ ...values, [f.key]: e.target.value })} placeholder={f.placeholder} style={{ flex: 1, height: 22, fontSize: 10 }} />
            )}
          </div>
        ))}

        <div style={{ display: "flex", gap: 4 }}>
          <button className="btn-primary" style={{ fontSize: 10, height: 22, flex: 1 }} disabled={!hasToken || saving}
            onClick={() => act(async () => {
              await channel.configure(buildConfig(values));
              setStatus(await channel.status());
            }, "Saved")}>Save</button>
          <button style={{ fontSize: 10, height: 22, flex: 1 }} disabled={!hasToken || saving}
            onClick={() => act(async () => {
              const r = await channel.test();
              toast(r.valid ? `@${r.bot_name}` : r.error || "Failed", r.valid ? "success" : "error");
              setStatus(await channel.status());
            }, "")}>Test</button>
          <button style={{ fontSize: 10, height: 22, flex: 1, background: polling ? "var(--error-dim)" : "var(--success-dim)", color: polling ? "var(--error)" : "var(--accent)", border: "none", borderRadius: 4, cursor: "pointer" }}
            disabled={!st.connected || saving}
            onClick={() => act(async () => {
              if (polling) { await channel.stopPolling(); setPolling(false); }
              else { await channel.startPolling(); setPolling(true); }
            }, polling ? "Stopped" : "Started")}>{polling ? "Stop" : "Poll"}</button>
        </div>

        {guide && <details style={{ fontSize: 10, color: "var(--text-muted)" }}>
          <summary style={{ cursor: "pointer" }}>Setup guide</summary>
          {typeof guide === "string" ? <p style={{ margin: "4px 0", lineHeight: 1.6 }}>{guide}</p> : guide}
        </details>}
      </div>}
    </div>
  );
}
