import React, { useEffect, useState } from "react";
import {
  getPendingGaps,
  generateCapabilityForGap,
  approveGap,
  rejectGap,
  getPendingOptimizations,
  approveOptimization,
  rejectOptimization,
  approveProposal,
  rejectProposal,
} from "../../api";

export default function SelfImprovementPanel() {
  const [gaps, setGaps] = useState([]);
  const [optimizations, setOptimizations] = useState([]);
  const [proposals, setProposals] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [gapRes, optRes] = await Promise.all([
        getPendingGaps(),
        getPendingOptimizations(),
      ]);
      setGaps(gapRes.gaps || []);
      setOptimizations(optRes.proposals || []);
    } catch (err) {
      setError(err.payload?.error_message || err.message || "Failed to load.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function handleAction(action, label) {
    setMessage("");
    setError("");
    try {
      await action();
      setMessage(label);
      await refresh();
    } catch (err) {
      setError(err.payload?.error_message || err.message || "Action failed.");
    }
  }

  return (
    <section className="settings-section">
      <h3>Self-Improvement</h3>
      {message && <p className="status-banner success">{message}</p>}
      {error && <p className="status-banner error">{error}</p>}
      {loading && <p>Loading...</p>}

      {/* Capability Gaps */}
      <h4>Capability Gaps (pending)</h4>
      {gaps.length === 0 && <p className="empty-block">No actionable gaps.</p>}
      {gaps.map((gap) => (
        <div key={gap.capability_id} className="status-row" style={{ flexDirection: "column", alignItems: "flex-start", gap: "0.5rem", padding: "0.75rem 0", borderBottom: "1px solid #eee" }}>
          <div>
            <strong>{gap.capability_id}</strong>
            <span style={{ marginLeft: "0.5rem", color: "#888" }}>({gap.frequency}x, {gap.suggested_integration_type})</span>
          </div>
          <small>{gap.sample_intent}</small>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" onClick={() => handleAction(() => generateCapabilityForGap(gap.gap_ids[0]), `Generated proposal for ${gap.capability_id}`)}>
              Generate
            </button>
            <button type="button" onClick={() => handleAction(() => rejectGap(gap.gap_ids[0]), `Dismissed gap ${gap.capability_id}`)}>
              Ignore
            </button>
          </div>
        </div>
      ))}

      {/* Optimization Proposals */}
      <h4>Strategy Optimizations (pending)</h4>
      {optimizations.length === 0 && <p className="empty-block">No optimization proposals.</p>}
      {optimizations.map((opt) => (
        <div key={opt.id} className="status-row" style={{ flexDirection: "column", alignItems: "flex-start", gap: "0.5rem", padding: "0.75rem 0", borderBottom: "1px solid #eee" }}>
          <div>
            <strong>{opt.capability_id}</strong>
            <span style={{ marginLeft: "0.5rem" }}>
              {opt.suggestion_type} ({opt.error_rate}% errors)
            </span>
          </div>
          <small>{opt.reason}</small>
          <details>
            <summary>Preview proposed contract</summary>
            <pre style={{ fontSize: "0.75rem", maxHeight: "200px", overflow: "auto" }}>
              {JSON.stringify(opt.proposed_contract, null, 2)}
            </pre>
          </details>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" onClick={() => handleAction(() => approveOptimization(opt.id, opt.proposed_contract), `Applied optimization for ${opt.capability_id}`)}>
              Approve
            </button>
            <button type="button" onClick={() => handleAction(() => rejectOptimization(opt.id), `Discarded optimization for ${opt.capability_id}`)}>
              Discard
            </button>
          </div>
        </div>
      ))}

      <button type="button" onClick={refresh} disabled={loading} style={{ marginTop: "1rem" }}>
        Refresh
      </button>
    </section>
  );
}
