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

export function planIntent(intent, conversationHistory) {
  const body = { intent };
  if (conversationHistory && conversationHistory.length > 0) {
    body.conversation_history = conversationHistory;
  }
  return request("/plan", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function chatMessage(message, userName, conversationHistory) {
  const body = { message, user_name: userName || "User" };
  if (conversationHistory && conversationHistory.length > 0) {
    body.conversation_history = conversationHistory;
  }
  return request("/chat", {
    method: "POST",
    body: JSON.stringify(body)
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

export function getMetrics() {
  return request("/metrics");
}

// Self-improvement endpoints
export function getPendingGaps() {
  return request("/gaps/pending");
}

export function generateCapabilityForGap(gapId, overrides = {}) {
  return request(`/gaps/${gapId}/generate`, {
    method: "POST",
    body: JSON.stringify(overrides)
  });
}

export function analyzeGap(gapId) {
  return request(`/gaps/${gapId}/analyze`, { method: "POST", body: "{}" });
}

export function autoGenerateForGap(gapId) {
  return request(`/gaps/${gapId}/generate`, { method: "POST", body: "{}" });
}

export function listAutoProposals() {
  return request("/proposals");
}

export function regenerateProposal(proposalId) {
  return request(`/proposals/${proposalId}/regenerate`, { method: "POST", body: "{}" });
}

export function approveGap(gapId) {
  return request(`/gaps/${gapId}/approve`, { method: "POST", body: "{}" });
}

export function rejectGap(gapId) {
  return request(`/gaps/${gapId}/reject`, { method: "POST", body: "{}" });
}

export function getCapabilityHealth() {
  return request("/capabilities/health");
}

export function getPendingOptimizations() {
  return request("/optimizations/pending");
}

export function approveOptimization(optId, proposedContract) {
  return request(`/optimizations/${optId}/approve`, {
    method: "POST",
    body: JSON.stringify({ proposed_contract: proposedContract })
  });
}

export function rejectOptimization(optId) {
  return request(`/optimizations/${optId}/reject`, { method: "POST", body: "{}" });
}

export function approveProposal(capabilityId) {
  return request(`/proposals/${capabilityId}/approve`, { method: "POST", body: "{}" });
}

export function rejectProposal(capabilityId) {
  return request(`/proposals/${capabilityId}/reject`, { method: "POST", body: "{}" });
}

// MCP endpoints
export function getMCPServers() {
  return request("/mcp/servers");
}

export function addMCPServer(serverConfig) {
  return request("/mcp/servers", {
    method: "POST",
    body: JSON.stringify({ server: serverConfig })
  });
}

export function removeMCPServer(serverId) {
  return request(`/mcp/servers/${serverId}`, { method: "DELETE" });
}

export function discoverMCPTools(serverId) {
  return request(`/mcp/servers/${serverId}/discover`, { method: "POST", body: "{}" });
}

export function getMCPTools() {
  return request("/mcp/tools");
}

export function installMCPTool(toolId) {
  return request(`/mcp/tools/${toolId}/install`, { method: "POST", body: "{}" });
}

// Memory endpoints
export function getMemoryContext() {
  return request("/memory/context");
}

export function getMemoryHistory(capabilityId) {
  const qs = capabilityId ? `?capability_id=${capabilityId}` : "";
  return request(`/memory/history${qs}`);
}

export function deleteHistoryEntry(executionId) {
  return request(`/memory/history/${executionId}`, { method: "DELETE" });
}

export function saveChatSession(sessionId, intent, messages, durationMs) {
  return request("/memory/history/chat", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, intent, messages, duration_ms: durationMs || 0 })
  });
}

export function getMemoryPreferences() {
  return request("/memory/preferences");
}

export function setMemoryPreferences(preferences) {
  return request("/memory/preferences", {
    method: "POST",
    body: JSON.stringify({ preferences })
  });
}

export function clearAllMemory() {
  return request("/memory", { method: "DELETE" });
}

export function saveSession(session) {
  return request("/memory/sessions", {
    method: "POST",
    body: JSON.stringify(session)
  });
}

export function getSession(executionId) {
  return request(`/memory/sessions/${executionId}`);
}

// Semantic memory
export function searchSemanticMemory(query, topK = 5) {
  return request(`/memory/semantic/search?q=${encodeURIComponent(query)}&top_k=${topK}`);
}

export function addSemanticMemory(text, memoryType, metadata) {
  return request("/memory/semantic", {
    method: "POST",
    body: JSON.stringify({ text, memory_type: memoryType || "capability_context", metadata: metadata || {} })
  });
}

export function deleteSemanticMemory(memId) {
  return request(`/memory/semantic/${memId}`, { method: "DELETE" });
}

// A2A endpoints
export function getAgentCard() {
  return request("/.well-known/agent.json");
}

export function getA2AAgents() {
  return request("/a2a/agents");
}

export function addA2AAgent(url, id) {
  return request("/a2a/agents", {
    method: "POST",
    body: JSON.stringify({ url, id: id || url })
  });
}

export function removeA2AAgent(agentId) {
  return request(`/a2a/agents/${agentId}`, { method: "DELETE" });
}

export function delegateA2ATask(agentId, skillId, message) {
  return request(`/a2a/agents/${agentId}/delegate`, {
    method: "POST",
    body: JSON.stringify({ skill_id: skillId, message })
  });
}

// Workspace management
export function listWorkspaces() {
  return request("/workspaces");
}

export function addWorkspace(name, path, access, capabilities, color) {
  return request("/workspaces", {
    method: "POST",
    body: JSON.stringify({ name, path, access: access || "write", capabilities: capabilities || "*", color: color || "#00ff88" })
  });
}

export function updateWorkspace(wsId, fields) {
  return request(`/workspaces/${wsId}`, {
    method: "POST",
    body: JSON.stringify(fields)
  });
}

export function removeWorkspace(wsId) {
  return request(`/workspaces/${wsId}`, { method: "DELETE" });
}

export function setDefaultWorkspace(wsId) {
  return request(`/workspaces/${wsId}/set-default`, { method: "POST", body: "{}" });
}

export function browseWorkspace(wsId, relativePath) {
  const p = relativePath ? `?path=${encodeURIComponent(relativePath)}` : "";
  return request(`/workspaces/${wsId}/browse${p}`);
}
