import React from "react";

function StepRunCard({ run, isActive, onSelectStep }) {
  return (
    <article className={`run-card ${isActive ? "is-active" : ""}`}>
      <header>
        <strong>{run.step_id}</strong>
        <span className={`run-status run-${run.status}`}>{run.status}</span>
      </header>
      <p>{run.capability}</p>
      <p>execution_id: {run.execution_id || "-"}</p>
      <button type="button" onClick={() => onSelectStep(run.step_id)}>
        Inspect
      </button>
    </article>
  );
}

export default function ExecutionPanel({ execution, logs, selectedStepId, onSelectStep }) {
  const runs = Array.isArray(execution?.step_runs) ? execution.step_runs : [];
  return (
    <section className="workspace-panel execution-panel">
      <h2>Execution</h2>
      {!execution && <p className="empty-block">No execution yet.</p>}
      {execution && (
        <div className="execution-summary">
          <p>
            status: <strong>{execution.status}</strong>
          </p>
          <p>
            current_step: <strong>{execution.current_step || "-"}</strong>
          </p>
          <p>
            started_at: <strong>{execution.started_at || "-"}</strong>
          </p>
          <p>
            ended_at: <strong>{execution.ended_at || "-"}</strong>
          </p>
          <p>
            duration_ms: <strong>{execution.duration_ms ?? 0}</strong>
          </p>
          <p>
            failed_step: <strong>{execution.failed_step || "-"}</strong>
          </p>
          <p>
            error_code: <strong>{execution.error_code || "-"}</strong>
          </p>
          <p className="error-text">{execution.error_message || ""}</p>
        </div>
      )}

      <div className="run-list">
        {runs.map((run) => (
          <StepRunCard
            key={run.step_id}
            run={run}
            isActive={selectedStepId === run.step_id}
            onSelectStep={onSelectStep}
          />
        ))}
      </div>

      <h3>Timeline</h3>
      <ul className="timeline">
        {logs.length === 0 && <li>No events yet.</li>}
        {logs.map((event, index) => (
          <li key={`${event.timestamp || "no-ts"}-${event.event || "event"}-${index}`}>
            <div>
              <strong>{event.event || "event"}</strong>
              <small>{event.timestamp || "-"}</small>
            </div>
            <pre>{JSON.stringify(event.payload || {}, null, 2)}</pre>
          </li>
        ))}
      </ul>
    </section>
  );
}
