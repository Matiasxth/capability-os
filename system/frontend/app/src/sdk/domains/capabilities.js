import { get, post } from "../client.js";
import { streamSSE } from "../client.js";

export const capabilities = {
  list: () => get("/capabilities"),
  get: (id) => get(`/capabilities/${id}`),
  health: () => get("/capabilities/health"),
  execute: (capabilityId, inputs) => post("/execute", { capability_id: capabilityId, inputs }),
  getExecution: (id) => get(`/executions/${id}`),
  getExecutionEvents: (id) => get(`/executions/${id}/events`),
  interpret: (text) => post("/interpret", { text }),
  plan: (intent, conversationHistory) => {
    const body = { intent };
    if (conversationHistory?.length) body.conversation_history = conversationHistory;
    return post("/plan", body);
  },
  chat: (message, userName, conversationHistory) => {
    const body = { message, user_name: userName || "User" };
    if (conversationHistory?.length) body.conversation_history = conversationHistory;
    return post("/chat", body);
  },

  /** @yields {string} text chunks */
  streamChat: (message, userName, conversationHistory) => {
    const body = { message, user_name: userName || "User" };
    if (conversationHistory?.length) body.conversation_history = conversationHistory;
    return (async function* () {
      for await (const data of streamSSE("/chat/stream", body)) {
        if (data.chunk) yield data.chunk;
      }
    })();
  },

  /** @yields {object} execution events */
  streamExecution: (capabilityId, inputs) =>
    streamSSE("/execute/stream", { capability_id: capabilityId, inputs: inputs || {} }),
};
