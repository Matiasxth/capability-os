import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock client
vi.mock("../../client.js", () => ({
  get: vi.fn(() => Promise.resolve({})),
  post: vi.fn(() => Promise.resolve({})),
  put: vi.fn(() => Promise.resolve({})),
  del: vi.fn(() => Promise.resolve({})),
  delWithBody: vi.fn(() => Promise.resolve({})),
  request: vi.fn(() => Promise.resolve({})),
  streamSSE: vi.fn(async function* () {}),
}));

const client = await import("../../client.js");

describe("SDK domains", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("agents", () => {
    it("list() calls GET /agents", async () => {
      const { agents } = await import("../agents.js");
      await agents.list();
      expect(client.get).toHaveBeenCalledWith("/agents");
    });

    it("create() calls POST /agents with config", async () => {
      const { agents } = await import("../agents.js");
      await agents.create({ name: "test" });
      expect(client.post).toHaveBeenCalledWith("/agents", { name: "test" });
    });

    it("delete() calls DELETE /agents/{id}", async () => {
      const { agents } = await import("../agents.js");
      await agents.delete("agt_1");
      expect(client.del).toHaveBeenCalledWith("/agents/agt_1");
    });

    it("confirm() calls POST /agent/confirm with params", async () => {
      const { agents } = await import("../agents.js");
      await agents.confirm("s1", "c1", true, "pass");
      expect(client.post).toHaveBeenCalledWith("/agent/confirm", {
        session_id: "s1", confirmation_id: "c1", approved: true, password: "pass",
      });
    });
  });

  describe("capabilities", () => {
    it("list() calls GET /capabilities", async () => {
      const { capabilities } = await import("../capabilities.js");
      await capabilities.list();
      expect(client.get).toHaveBeenCalledWith("/capabilities");
    });

    it("execute() calls POST /execute", async () => {
      const { capabilities } = await import("../capabilities.js");
      await capabilities.execute("cap_1", { x: 1 });
      expect(client.post).toHaveBeenCalledWith("/execute", { capability_id: "cap_1", inputs: { x: 1 } });
    });

    it("plan() calls POST /plan with history", async () => {
      const { capabilities } = await import("../capabilities.js");
      const hist = [{ role: "user", content: "hi" }];
      await capabilities.plan("do stuff", hist);
      expect(client.post).toHaveBeenCalledWith("/plan", { intent: "do stuff", conversation_history: hist });
    });
  });

  describe("memory", () => {
    it("context() calls GET /memory/context", async () => {
      const { memory } = await import("../memory.js");
      await memory.context();
      expect(client.get).toHaveBeenCalledWith("/memory/context");
    });

    it("history() adds query params", async () => {
      const { memory } = await import("../memory.js");
      await memory.history("cap1", "ws1");
      expect(client.get).toHaveBeenCalledWith("/memory/history?capability_id=cap1&workspace_id=ws1");
    });

    it("semantic.search() encodes query", async () => {
      const { memory } = await import("../memory.js");
      await memory.semantic.search("hello world", 3);
      expect(client.get).toHaveBeenCalledWith("/memory/semantic/search?q=hello%20world&top_k=3");
    });

    it("clearAll() calls DELETE /memory", async () => {
      const { memory } = await import("../memory.js");
      await memory.clearAll();
      expect(client.del).toHaveBeenCalledWith("/memory");
    });
  });

  describe("workspaces", () => {
    it("list() calls GET /workspaces", async () => {
      const { workspaces } = await import("../workspaces.js");
      await workspaces.list();
      expect(client.get).toHaveBeenCalledWith("/workspaces");
    });

    it("add() calls POST /workspaces with defaults", async () => {
      const { workspaces } = await import("../workspaces.js");
      await workspaces.add("My Project", "/path");
      expect(client.post).toHaveBeenCalledWith("/workspaces", {
        name: "My Project", path: "/path", access: "write", capabilities: "*", color: "#00ff88",
      });
    });

    it("remove() calls DELETE /workspaces/{id}", async () => {
      const { workspaces } = await import("../workspaces.js");
      await workspaces.remove("ws_1");
      expect(client.del).toHaveBeenCalledWith("/workspaces/ws_1");
    });
  });

  describe("system", () => {
    it("health() calls GET /health", async () => {
      const { system } = await import("../system.js");
      await system.health();
      expect(client.get).toHaveBeenCalledWith("/health");
    });

    it("settings.save() calls POST /settings", async () => {
      const { system } = await import("../system.js");
      await system.settings.save({ llm: {} });
      expect(client.post).toHaveBeenCalledWith("/settings", { settings: { llm: {} } });
    });

    it("scheduler.deleteTask() calls DELETE", async () => {
      const { system } = await import("../system.js");
      await system.scheduler.deleteTask("t1");
      expect(client.del).toHaveBeenCalledWith("/scheduler/tasks/t1");
    });
  });

  describe("integrations", () => {
    it("telegram uses channelDomain pattern", async () => {
      const { integrations } = await import("../integrations.js");
      await integrations.telegram.status();
      expect(client.get).toHaveBeenCalledWith("/integrations/telegram/status");
      await integrations.telegram.test();
      expect(client.post).toHaveBeenCalledWith("/integrations/telegram/test", {});
    });

    it("new channels follow same pattern", async () => {
      const { integrations } = await import("../integrations.js");
      await integrations.signal.status();
      expect(client.get).toHaveBeenCalledWith("/integrations/signal/status");
      await integrations.matrix.startPolling();
      expect(client.post).toHaveBeenCalledWith("/integrations/matrix/polling/start", {});
    });
  });

  describe("workflows", () => {
    it("CRUD maps to correct endpoints", async () => {
      const { workflows } = await import("../workflows.js");
      await workflows.list();
      expect(client.get).toHaveBeenCalledWith("/workflows");
      await workflows.create("wf", "desc");
      expect(client.post).toHaveBeenCalledWith("/workflows", { name: "wf", description: "desc" });
      await workflows.delete("wf1");
      expect(client.del).toHaveBeenCalledWith("/workflows/wf1");
      await workflows.run("wf1");
      expect(client.post).toHaveBeenCalledWith("/workflows/wf1/run");
    });
  });

  describe("auth", () => {
    it("login() calls POST /auth/login", async () => {
      const { auth } = await import("../auth.js");
      await auth.login("user", "pass");
      expect(client.post).toHaveBeenCalledWith("/auth/login", { username: "user", password: "pass" });
    });

    it("me() calls GET /auth/me", async () => {
      const { auth } = await import("../auth.js");
      await auth.me();
      expect(client.get).toHaveBeenCalledWith("/auth/me");
    });
  });

  describe("mcp", () => {
    it("servers.list() calls GET /mcp/servers", async () => {
      const { mcp } = await import("../mcp.js");
      await mcp.servers.list();
      expect(client.get).toHaveBeenCalledWith("/mcp/servers");
    });

    it("tools.install() calls POST", async () => {
      const { mcp } = await import("../mcp.js");
      await mcp.tools.install("tool1");
      expect(client.post).toHaveBeenCalledWith("/mcp/tools/tool1/install", {});
    });
  });

  describe("growth", () => {
    it("gaps.pending() calls GET /gaps/pending", async () => {
      const { growth } = await import("../growth.js");
      await growth.gaps.pending();
      expect(client.get).toHaveBeenCalledWith("/gaps/pending");
    });

    it("proposals.approve() calls POST", async () => {
      const { growth } = await import("../growth.js");
      await growth.proposals.approve("cap1");
      expect(client.post).toHaveBeenCalledWith("/proposals/cap1/approve", {});
    });
  });
});
