const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options
  });

  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.error_message || "API request failed.");
    error.payload = payload;
    throw error;
  }
  return payload;
}

export function listCapabilities() {
  return request("/capabilities");
}

export function getCapability(capabilityId) {
  return request(`/capabilities/${capabilityId}`);
}

export function executeCapability(capabilityId, inputs) {
  return request("/execute", {
    method: "POST",
    body: JSON.stringify({ capability_id: capabilityId, inputs })
  });
}

export function getExecution(executionId) {
  return request(`/executions/${executionId}`);
}

export function getExecutionEvents(executionId) {
  return request(`/executions/${executionId}/events`);
}

export function interpretText(text) {
  return request("/interpret", {
    method: "POST",
    body: JSON.stringify({ text })
  });
}

export function planIntent(intent) {
  return request("/plan", {
    method: "POST",
    body: JSON.stringify({ intent })
  });
}

export function getSystemStatus() {
  return request("/status");
}

export function getSystemHealth() {
  return request("/health");
}

export function getSettings() {
  return request("/settings");
}

export function saveSettings(settings) {
  return request("/settings", {
    method: "POST",
    body: JSON.stringify({ settings })
  });
}

export function testLLMConnection() {
  return request("/llm/test", {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function restartBrowserWorker() {
  return request("/browser/restart", {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function listIntegrations() {
  return request("/integrations");
}

export function getIntegration(integrationId) {
  return request(`/integrations/${integrationId}`);
}

export function validateIntegration(integrationId) {
  return request(`/integrations/${integrationId}/validate`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function enableIntegration(integrationId) {
  return request(`/integrations/${integrationId}/enable`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function disableIntegration(integrationId) {
  return request(`/integrations/${integrationId}/disable`, {
    method: "POST",
    body: JSON.stringify({})
  });
}
