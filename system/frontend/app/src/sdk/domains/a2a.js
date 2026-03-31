import { get, post, del } from "../client.js";

export const a2a = {
  agentCard: () => get("/.well-known/agent.json"),
  agents: {
    list: () => get("/a2a/agents"),
    add: (url, id) => post("/a2a/agents", { url, id: id || url }),
    remove: (id) => del(`/a2a/agents/${id}`),
  },
  delegate: (agentId, skillId, message) =>
    post(`/a2a/agents/${agentId}/delegate`, { skill_id: skillId, message }),
};
