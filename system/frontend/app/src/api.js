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

export async function* streamChat(message, userName, conversationHistory) {
  const body = { message, user_name: userName || "User" };
  if (conversationHistory && conversationHistory.length > 0) {
    body.conversation_history = conversationHistory;
  }
  const resp = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    while (buffer.includes("\n\n")) {
      const idx = buffer.indexOf("\n\n");
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (!line.startsWith("data:")) continue;
      try {
        const data = JSON.parse(line.slice(5).trim());
        if (data.done) return;
        if (data.error) throw new Error(data.error);
        if (data.chunk) yield data.chunk;
      } catch (e) { if (e.message) throw e; }
    }
  }
}

export async function* streamExecution(capabilityId, inputs) {
  const resp = await fetch(`${API_BASE_URL}/execute/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ capability_id: capabilityId, inputs: inputs || {} })
  });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    while (buffer.includes("\n\n")) {
      const idx = buffer.indexOf("\n\n");
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (!line.startsWith("data:")) continue;
      try {
        const data = JSON.parse(line.slice(5).trim());
        yield data;
        if (data.done) return;
      } catch { /* ignore parse errors */ }
    }
  }
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

export function exportConfig() {
  return request("/system/export-config");
}

export function importConfig(data) {
  return request("/system/import-config", {
    method: "POST",
    body: JSON.stringify(data)
  });
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

export function getCDPStatus() {
  return request("/browser/cdp-status");
}

export function launchChrome() {
  return request("/browser/launch-chrome", {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function openWhatsApp() {
  return request("/browser/open-whatsapp", {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function closeWhatsAppSession() {
  return request("/integrations/whatsapp/close-session", {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function getWhatsAppSessionStatus() {
  return request("/integrations/whatsapp/session-status");
}

export function getWhatsAppQR() {
  return request("/integrations/whatsapp/qr");
}

export function getTelegramStatus() {
  return request("/integrations/telegram/status");
}

export function configureTelegram(botToken, defaultChatId, allowedUserIds) {
  return request("/integrations/telegram/configure", {
    method: "POST",
    body: JSON.stringify({ bot_token: botToken, default_chat_id: defaultChatId || "", allowed_user_ids: allowedUserIds || [] })
  });
}

export function testTelegram() {
  return request("/integrations/telegram/test", {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function startTelegramPolling() {
  return request("/integrations/telegram/polling/start", { method: "POST", body: "{}" });
}

export function stopTelegramPolling() {
  return request("/integrations/telegram/polling/stop", { method: "POST", body: "{}" });
}

export function getTelegramPollingStatus() {
  return request("/integrations/telegram/polling/status");
}

// Slack
export function getSlackStatus() { return request("/integrations/slack/status"); }
export function configureSlack(config) { return request("/integrations/slack/configure", { method: "POST", body: JSON.stringify(config) }); }
export function testSlack() { return request("/integrations/slack/test", { method: "POST", body: "{}" }); }
export function startSlackPolling() { return request("/integrations/slack/polling/start", { method: "POST", body: "{}" }); }
export function stopSlackPolling() { return request("/integrations/slack/polling/stop", { method: "POST", body: "{}" }); }
export function getSlackPollingStatus() { return request("/integrations/slack/polling/status"); }

// Discord
export function getDiscordStatus() { return request("/integrations/discord/status"); }
export function configureDiscord(config) { return request("/integrations/discord/configure", { method: "POST", body: JSON.stringify(config) }); }
export function testDiscord() { return request("/integrations/discord/test", { method: "POST", body: "{}" }); }
export function startDiscordPolling() { return request("/integrations/discord/polling/start", { method: "POST", body: "{}" }); }
export function stopDiscordPolling() { return request("/integrations/discord/polling/stop", { method: "POST", body: "{}" }); }
export function getDiscordPollingStatus() { return request("/integrations/discord/polling/status"); }

export function startWhatsApp() {
  return request("/integrations/whatsapp/start", {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function whatsappBridgeCheck() {
  return request("/integrations/whatsapp/session-status");
}

export function whatsappBridgeClose() {
  return request("/integrations/whatsapp/stop", {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function whatsappSwitchBackend(backend) {
  return request("/integrations/whatsapp/switch-backend", {
    method: "POST",
    body: JSON.stringify({ backend })
  });
}

export function whatsappConfigure(config) {
  return request("/integrations/whatsapp/configure", {
    method: "POST",
    body: JSON.stringify(config)
  });
}

export function whatsappListBackends() {
  return request("/integrations/whatsapp/backends");
}

export function connectBrowserCDP() {
  return request("/browser/connect-cdp", {
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

export function uninstallMCPTool(toolId) {
  return request(`/mcp/tools/${toolId}/uninstall`, { method: "DELETE" });
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

export function compactSessions(maxAgeHours = 24) {
  return request("/memory/compact", { method: "POST", body: JSON.stringify({ max_age_hours: maxAgeHours }) });
}

// Skills
export function listSkills() { return request("/skills"); }
export function getSkill(skillId) { return request(`/skills/${skillId}`); }
export function installSkill(source) { return request("/skills/install", { method: "POST", body: JSON.stringify({ source }) }); }
export function uninstallSkill(skillId) { return request(`/skills/${skillId}`, { method: "DELETE" }); }

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

// ── Agent API ──

export function runAgent(message, sessionId, history, agentId) {
  const body = { message };
  if (sessionId) body.session_id = sessionId;
  if (history) body.history = history;
  if (agentId) body.agent_id = agentId;
  return request("/agent", { method: "POST", body: JSON.stringify(body) });
}

export function confirmAgentAction(sessionId, confirmationId, approved, password) {
  return request("/agent/confirm", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, confirmation_id: confirmationId, approved, password })
  });
}

export function getAgentSession(sessionId) {
  return request(`/agent/${sessionId}`);
}

// ── Agent Registry API ──

export function listAgents() { return request("/agents"); }
export function createAgent(config) { return request("/agents", { method: "POST", body: JSON.stringify(config) }); }
export function getAgentDef(agentId) { return request(`/agents/${agentId}`); }
export function updateAgentDef(agentId, fields) { return request(`/agents/${agentId}`, { method: "POST", body: JSON.stringify(fields) }); }
export function deleteAgentDef(agentId) { return request(`/agents/${agentId}`, { method: "DELETE" }); }

export function updateWorkspaceStatus(wsId, status) {
  return request(`/workspaces/${wsId}/status`, {
    method: "POST",
    body: JSON.stringify({ status })
  });
}
