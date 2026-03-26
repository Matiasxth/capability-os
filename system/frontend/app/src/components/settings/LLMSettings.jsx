import React from "react";

function updateLLM(settings, key, value, onChange) {
  onChange({
    ...settings,
    llm: {
      ...settings.llm,
      [key]: value
    }
  });
}

export default function LLMSettings({
  settings,
  onChange,
  onSave,
  onTestConnection,
  saving,
  testingConnection,
  testResult
}) {
  const llm = settings?.llm || {};
  return (
    <section className="settings-section">
      <h3>LLM Settings</h3>
      <div className="settings-form-grid">
        <label>
          Provider
          <select
            value={llm.provider || "ollama"}
            onChange={(event) => updateLLM(settings, "provider", event.target.value, onChange)}
          >
            <option value="ollama">ollama</option>
            <option value="openai">openai</option>
          </select>
        </label>
        <label>
          Base URL
          <input
            type="text"
            value={llm.base_url || ""}
            onChange={(event) => updateLLM(settings, "base_url", event.target.value, onChange)}
          />
        </label>
        <label>
          Model
          <input
            type="text"
            value={llm.model || ""}
            onChange={(event) => updateLLM(settings, "model", event.target.value, onChange)}
          />
        </label>
        <label>
          API Key
          <input
            type="password"
            value={llm.api_key || ""}
            onChange={(event) => updateLLM(settings, "api_key", event.target.value, onChange)}
          />
        </label>
        <label>
          Timeout (ms)
          <input
            type="number"
            value={llm.timeout_ms ?? 30000}
            onChange={(event) => updateLLM(settings, "timeout_ms", Number(event.target.value || 0), onChange)}
          />
        </label>
      </div>

      <div className="settings-actions">
        <button type="button" onClick={onSave} disabled={saving}>
          {saving ? "Saving..." : "Save"}
        </button>
        <button type="button" onClick={onTestConnection} disabled={testingConnection}>
          {testingConnection ? "Testing..." : "Test Connection"}
        </button>
      </div>

      {testResult && (
        <p className={testResult.status === "success" ? "status-pill is-success" : "status-pill is-error"}>
          LLM test: {testResult.status}
          {testResult.error_message ? ` - ${testResult.error_message}` : ""}
        </p>
      )}
    </section>
  );
}

