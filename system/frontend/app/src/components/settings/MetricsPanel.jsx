import React, { useEffect, useState } from "react";
import { getMetrics } from "../../api";

export default function MetricsPanel() {
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const response = await getMetrics();
      setMetrics(response.metrics || null);
    } catch (err) {
      setError(err.payload?.error_message || err.message || "Failed to load metrics.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  if (!metrics && !loading) {
    return (
      <section className="settings-section">
        <h3>Operational Metrics</h3>
        {error && <p className="status-banner error">{error}</p>}
        <p className="empty-block">Metrics unavailable.</p>
      </section>
    );
  }

  return (
    <section className="settings-section">
      <h3>Operational Metrics</h3>
      {error && <p className="status-banner error">{error}</p>}
      {loading && <p>Loading...</p>}
      {metrics && (
        <>
          <div className="status-row">
            <span>Execution Success Rate</span>
            <strong>{metrics.execution_success_rate}%</strong>
          </div>
          <div className="status-row">
            <span>Avg Execution Time</span>
            <strong>{metrics.avg_execution_time_ms} ms</strong>
          </div>
          <div className="status-row">
            <span>Tool Failure Rate</span>
            <strong>{metrics.tool_failure_rate}%</strong>
          </div>
          <div className="status-row">
            <span>Total Executions</span>
            <strong>{metrics.total_executions}</strong>
          </div>
          <div className="status-row">
            <span>Successful</span>
            <strong>{metrics.successful_executions}</strong>
          </div>
          <div className="status-row">
            <span>Tool Calls (total / failed)</span>
            <strong>{metrics.tool_calls_total} / {metrics.tool_calls_failed}</strong>
          </div>

          <h4>Error Rate by Capability</h4>
          {Object.keys(metrics.error_rate_by_capability || {}).length === 0 && (
            <p className="empty-block">No errors recorded.</p>
          )}
          {Object.entries(metrics.error_rate_by_capability || {}).map(([cap, count]) => (
            <div key={cap} className="status-row">
              <span>{cap}</span>
              <strong>{count} errors</strong>
            </div>
          ))}
        </>
      )}
      <button type="button" onClick={refresh} disabled={loading} style={{ marginTop: "1rem" }}>
        Refresh Metrics
      </button>
    </section>
  );
}
