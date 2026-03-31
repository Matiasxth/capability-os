import { get, post, del } from "../client.js";

export const mcp = {
  servers: {
    list: () => get("/mcp/servers"),
    add: (serverConfig) => post("/mcp/servers", { server: serverConfig }),
    remove: (id) => del(`/mcp/servers/${id}`),
    discover: (id) => post(`/mcp/servers/${id}/discover`, {}),
  },
  tools: {
    list: () => get("/mcp/tools"),
    install: (id) => post(`/mcp/tools/${id}/install`, {}),
    uninstall: (id) => del(`/mcp/tools/${id}/uninstall`),
  },
};
