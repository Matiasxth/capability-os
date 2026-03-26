import React from "react";

function statusClass(status) {
  if (status === "enabled" || status === "validated") {
    return "is-success";
  }
  if (status === "error") {
    return "is-error";
  }
  return "is-neutral";
}

export default function IntegrationsSettings({
  integrations,
  onValidate,
  onEnable,
  onDisable
}) {
  return (
    <section className="settings-section">
      <h3>Integrations</h3>
      <div className="integration-list">
        {integrations.length === 0 && <p className="empty-block">No integrations discovered.</p>}
        {integrations.map((integration) => (
          <article key={integration.id} className="integration-card">
            <header>
              <div>
                <strong>{integration.name || integration.id}</strong>
                <small>{integration.id}</small>
              </div>
              <span className={`status-pill ${statusClass(integration.status)}`}>
                {integration.status}
              </span>
            </header>
            <p>type: {integration.type || "unknown"}</p>
            <p>capabilities: {(integration.capabilities || []).length}</p>
            <div className="settings-actions">
              <button type="button" onClick={() => onValidate(integration.id)}>
                Validate
              </button>
              <button type="button" onClick={() => onEnable(integration.id)}>
                Enable
              </button>
              <button type="button" onClick={() => onDisable(integration.id)}>
                Disable
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

