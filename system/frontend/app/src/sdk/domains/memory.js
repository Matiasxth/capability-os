import { get, post, del, delWithBody } from "../client.js";

export const memory = {
  context: () => get("/memory/context"),
  history: (capabilityId, workspaceId) => {
    const params = [];
    if (capabilityId) params.push(`capability_id=${capabilityId}`);
    if (workspaceId) params.push(`workspace_id=${workspaceId}`);
    const qs = params.length ? `?${params.join("&")}` : "";
    return get(`/memory/history${qs}`);
  },
  deleteHistory: (executionId) => del(`/memory/history/${executionId}`),
  saveChatSession: (sessionId, intent, messages, durationMs, workspaceId) =>
    post("/memory/history/chat", {
      session_id: sessionId, intent, messages,
      duration_ms: durationMs || 0, workspace_id: workspaceId || null,
    }),
  saveSession: (session) => post("/memory/sessions", session),
  getSession: (executionId) => get(`/memory/sessions/${executionId}`),
  preferences: () => get("/memory/preferences"),
  setPreferences: (prefs) => post("/memory/preferences", { preferences: prefs }),
  clearAll: () => del("/memory"),
  compact: (maxAgeHours = 24) => post("/memory/compact", { max_age_hours: maxAgeHours }),
  metrics: () => get("/metrics"),

  semantic: {
    search: (query, topK = 5) => get(`/memory/semantic/search?q=${encodeURIComponent(query)}&top_k=${topK}`),
    add: (text, memoryType, metadata) =>
      post("/memory/semantic", { text, memory_type: memoryType || "capability_context", metadata: metadata || {} }),
    delete: (memId) => del(`/memory/semantic/${memId}`),
  },

  markdown: {
    get: () => get("/memory/markdown"),
    save: (content) => post("/memory/markdown", { content }),
    addFact: (section, fact) => post("/memory/markdown/fact", { section, fact }),
    removeFact: (section, factSubstring) =>
      delWithBody("/memory/markdown/fact", { section, fact_substring: factSubstring }),
  },

  daily: (date) => get(`/memory/daily${date ? `?date=${date}` : ""}`),
  summaries: () => get("/memory/summaries"),
  agentContext: () => get("/memory/agent-context"),
};
