import React from "react";

function formatInputValue(value) {
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}

function parseInputValue(raw) {
  const trimmed = raw.trim();
  if (!trimmed) {
    return "";
  }
  if (trimmed === "true") {
    return true;
  }
  if (trimmed === "false") {
    return false;
  }
  if (/^-?\d+$/.test(trimmed)) {
    return Number.parseInt(trimmed, 10);
  }
  if (/^-?\d+\.\d+$/.test(trimmed)) {
    return Number(trimmed);
  }
  if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
    try {
      return JSON.parse(trimmed);
    } catch (error) {
      return raw;
    }
  }
  return raw;
}

export default function PlanPanel({
  plan,
  capabilitiesById,
  selectedStepId,
  onSelectStep,
  onUpdateStep,
  onDeleteStep,
  onMoveStep,
  onRunPlan,
  running,
  validationErrors
}) {
  const steps = Array.isArray(plan?.steps) ? plan.steps : [];
  return (
    <section className="workspace-panel plan-panel">
      <div className="panel-header">
        <h2>Plan</h2>
        <button type="button" onClick={onRunPlan} disabled={running || steps.length === 0}>
          {running ? "Running..." : "Run Plan"}
        </button>
      </div>
      <p className="panel-hint">
        Type: <strong>{plan?.type || "unknown"}</strong> | Steps: <strong>{steps.length}</strong> | suggest_only:{" "}
        <strong>{String(plan?.suggest_only === true)}</strong>
      </p>
      {validationErrors.length > 0 && (
        <div className="plan-errors">
          {validationErrors.map((error, index) => (
            <p key={`${error.code}-${index}`}>
              {error.step_id ? `[${error.step_id}] ` : ""}
              {error.message}
            </p>
          ))}
        </div>
      )}

      <div className="step-list">
        {steps.length === 0 && <p className="empty-block">No steps yet. Generate a plan from intent.</p>}
        {steps.map((step, index) => {
          const isSelected = selectedStepId === step.step_id;
          const capabilityContract = capabilitiesById[step.capability];
          const inputs = step.inputs && typeof step.inputs === "object" ? step.inputs : {};
          return (
            <article
              key={step.step_id}
              className={`step-card ${isSelected ? "is-selected" : ""}`}
              onClick={() => onSelectStep(step.step_id)}
            >
              <div className="step-header">
                <strong>{step.step_id}</strong>
                <div className="step-actions">
                  <button type="button" onClick={(event) => { event.stopPropagation(); onSelectStep(step.step_id); }}>
                    Edit
                  </button>
                  <button type="button" onClick={(event) => { event.stopPropagation(); onMoveStep(step.step_id, -1); }} disabled={index === 0}>
                    Up
                  </button>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onMoveStep(step.step_id, 1);
                    }}
                    disabled={index === steps.length - 1}
                  >
                    Down
                  </button>
                  <button type="button" onClick={(event) => { event.stopPropagation(); onDeleteStep(step.step_id); }}>
                    Delete
                  </button>
                </div>
              </div>
              <label>
                Capability
                <input
                  type="text"
                  value={step.capability}
                  onChange={(event) => onUpdateStep(step.step_id, { capability: event.target.value })}
                />
              </label>
              {capabilityContract && <small>{capabilityContract.name}</small>}
              <div className="step-inputs">
                {Object.keys(inputs).length === 0 && <small>No inputs defined.</small>}
                {Object.entries(inputs).map(([key, value]) => (
                  <label key={`${step.step_id}-${key}`}>
                    {key}
                    <input
                      type="text"
                      value={formatInputValue(value)}
                      onChange={(event) => {
                        const nextInputs = { ...inputs, [key]: parseInputValue(event.target.value) };
                        onUpdateStep(step.step_id, { inputs: nextInputs });
                      }}
                    />
                  </label>
                ))}
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    const nextKey = `input_${Object.keys(inputs).length + 1}`;
                    onUpdateStep(step.step_id, { inputs: { ...inputs, [nextKey]: "" } });
                  }}
                >
                  + Add input
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
