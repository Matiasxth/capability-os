import React from "react";

function collectScreenshotPaths(value, acc = []) {
  if (typeof value === "string" && value.toLowerCase().endsWith(".png")) {
    acc.push(value);
    return acc;
  }
  if (Array.isArray(value)) {
    value.forEach((item) => collectScreenshotPaths(item, acc));
    return acc;
  }
  if (value && typeof value === "object") {
    Object.values(value).forEach((item) => collectScreenshotPaths(item, acc));
  }
  return acc;
}

export default function InspectorPanel({ execution, selectedStepId }) {
  if (!execution) {
    return (
      <section className="workspace-panel inspector-panel">
        <h2>Inspector</h2>
        <p className="empty-block">Run a plan to inspect outputs and errors.</p>
      </section>
    );
  }

  const stepRuns = Array.isArray(execution.step_runs) ? execution.step_runs : [];
  const selectedRun = stepRuns.find((run) => run.step_id === selectedStepId) || stepRuns[stepRuns.length - 1] || null;
  const selectedOutput = selectedRun?.final_output || {};
  const screenshots = [...new Set(collectScreenshotPaths(selectedOutput, []))];
  const domElements = Array.isArray(selectedOutput?.elements) ? selectedOutput.elements : [];

  return (
    <section className="workspace-panel inspector-panel">
      <h2>Inspector</h2>
      <p>
        selected_step: <strong>{selectedRun?.step_id || "-"}</strong>
      </p>
      <p>
        capability: <strong>{selectedRun?.capability || "-"}</strong>
      </p>
      <p>
        step_error: <strong>{selectedRun?.error_code || "-"}</strong>
      </p>
      {selectedRun?.error_message && <p className="error-text">{selectedRun.error_message}</p>}

      <h3>Output JSON</h3>
      <pre>{JSON.stringify(selectedOutput, null, 2)}</pre>

      <h3>Screenshots</h3>
      {screenshots.length === 0 && <p>None</p>}
      {screenshots.length > 0 && (
        <ul className="plain-list">
          {screenshots.map((path) => (
            <li key={path}>{path}</li>
          ))}
        </ul>
      )}

      <h3>DOM Elements</h3>
      {domElements.length === 0 && <p>None</p>}
      {domElements.length > 0 && <pre>{JSON.stringify(domElements, null, 2)}</pre>}
    </section>
  );
}
