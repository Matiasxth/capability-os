import React from "react";

function updateWorkspace(settings, key, value, onChange) {
  onChange({
    ...settings,
    workspace: {
      ...settings.workspace,
      [key]: value
    }
  });
}

export default function WorkspaceSettings({ settings, onChange, onSave, saving }) {
  const workspace = settings?.workspace || {};
  return (
    <section className="settings-section">
      <h3>Workspace Paths</h3>
      <div className="settings-form-grid">
        <label>
          Artifacts Path
          <input
            type="text"
            value={workspace.artifacts_path || ""}
            onChange={(event) => updateWorkspace(settings, "artifacts_path", event.target.value, onChange)}
          />
        </label>
        <label>
          Sequences Path
          <input
            type="text"
            value={workspace.sequences_path || ""}
            onChange={(event) => updateWorkspace(settings, "sequences_path", event.target.value, onChange)}
          />
        </label>
      </div>
      <div className="settings-actions">
        <button type="button" onClick={onSave} disabled={saving}>
          {saving ? "Saving..." : "Save"}
        </button>
      </div>
    </section>
  );
}

