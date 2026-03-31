import { get, post, del } from "../client.js";
import { streamSSE } from "../client.js";

export const agents = {
  list: () => get("/agents"),
  create: (config) => post("/agents", config),
  get: (id) => get(`/agents/${id}`),
  update: (id, fields) => post(`/agents/${id}`, fields),
  delete: (id) => del(`/agents/${id}`),
  design: (description) => post("/agents/design", { description }),

  run: (message, sessionId, history, agentId) => {
    const body = { message };
    if (sessionId) body.session_id = sessionId;
    if (history) body.history = history;
    if (agentId) body.agent_id = agentId;
    return post("/agent", body);
  },

  confirm: (sessionId, confirmationId, approved, password) =>
    post("/agent/confirm", { session_id: sessionId, confirmation_id: confirmationId, approved, password }),

  getSession: (sessionId) => get(`/agent/${sessionId}`),

  /** @yields {object} agent events */
  stream: (message, sessionId, history, agentId, workspaceId) => {
    const body = { message };
    if (sessionId) body.session_id = sessionId;
    if (history) body.history = history;
    if (agentId) body.agent_id = agentId;
    if (workspaceId) body.workspace_id = workspaceId;
    return streamSSE("/agent/stream", body);
  },
};
