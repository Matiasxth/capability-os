import { get, post, del } from "../client.js";

export const workspaces = {
  list: () => get("/workspaces"),
  add: (name, path, access, capabilities, color) =>
    post("/workspaces", {
      name, path,
      access: access || "write",
      capabilities: capabilities || "*",
      color: color || "#00ff88",
    }),
  get: (id) => get(`/workspaces/${id}`),
  update: (id, fields) => post(`/workspaces/${id}`, fields),
  remove: (id) => del(`/workspaces/${id}`),
  setDefault: (id) => post(`/workspaces/${id}/set-default`, {}),
  updateStatus: (id, status) => post(`/workspaces/${id}/status`, { status }),
  browse: (id, relativePath) => {
    const p = relativePath ? `?path=${encodeURIComponent(relativePath)}` : "";
    return get(`/workspaces/${id}/browse${p}`);
  },
  analyze: (wsId) => get(`/files/analyze/${wsId}`),
  autoClean: (wsId, dryRun = true) => post(`/files/auto-clean/${wsId}`, { dry_run: dryRun }),
  generateReadme: (wsId) => post(`/files/generate-readme/${wsId}`, {}),
};
