import { get, post, del } from "../client.js";

export const system = {
  status: () => get("/status"),
  health: () => get("/health"),
  logs: () => get("/logs"),
  exportConfig: () => get("/system/export-config"),
  importConfig: (data) => post("/system/import-config", data),

  settings: {
    get: () => get("/settings"),
    save: (settings) => post("/settings", { settings }),
  },

  llm: {
    test: () => post("/llm/test", {}),
  },

  browser: {
    cdpStatus: () => get("/browser/cdp-status"),
    launchChrome: () => post("/browser/launch-chrome", {}),
    connectCDP: () => post("/browser/connect-cdp", {}),
    restart: () => post("/browser/restart", {}),
    openWhatsApp: () => post("/browser/open-whatsapp", {}),
  },

  plugins: {
    list: () => get("/plugins"),
    get: (id) => get(`/plugins/${id}`),
    reload: (id) => post(`/plugins/${id}/reload`),
    install: (path) => post("/plugins/install", { path }),
  },

  supervisor: {
    status: () => get("/supervisor/status"),
    log: () => get("/supervisor/log"),
    invoke: (prompt) => post("/supervisor/claude", { prompt }),
    healthCheck: () => post("/supervisor/health-check", {}),
    approve: (previewId) => post("/supervisor/approve", { preview_id: previewId }),
    discard: (previewId) => post("/supervisor/discard", { preview_id: previewId }),
  },

  scheduler: {
    status: () => get("/scheduler/status"),
    log: () => get("/scheduler/log"),
    listTasks: () => get("/scheduler/tasks"),
    createTask: (task) => post("/scheduler/tasks", task),
    updateTask: (taskId, fields) => post(`/scheduler/tasks/${taskId}`, fields),
    deleteTask: (taskId) => del(`/scheduler/tasks/${taskId}`),
    runNow: (taskId) => post(`/scheduler/tasks/${taskId}/run`, {}),
  },

  files: {
    tree: (wsId) => get(wsId ? `/files/tree/${wsId}` : "/files/tree"),
    read: (path, wsId) => get(`/files/read?path=${encodeURIComponent(path)}&ws=${wsId || ""}`),
    write: (path, content, wsId) => post("/files/write", { path, content, ws: wsId }),
    create: (path, content, wsId) => post("/files/create", { path, content, ws: wsId }),
    delete: (path, wsId) => del(`/files/delete?path=${encodeURIComponent(path)}&ws=${wsId || ""}`),
    terminal: (command, wsId) => post("/files/terminal", { command, ws: wsId }),
  },
};
