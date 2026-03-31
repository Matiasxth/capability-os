import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock client
vi.mock("../../client.js", () => ({
  get: vi.fn(() => Promise.resolve({})),
  post: vi.fn(() => Promise.resolve({})),
  put: vi.fn(() => Promise.resolve({})),
  del: vi.fn(() => Promise.resolve({})),
  delWithBody: vi.fn(() => Promise.resolve({})),
  request: vi.fn(() => Promise.resolve({})),
  publicGet: vi.fn(() => Promise.resolve({})),
  publicPost: vi.fn(() => Promise.resolve({})),
  publicRequest: vi.fn(() => Promise.resolve({})),
  streamSSE: vi.fn(async function* () {}),
}));

import * as client from "../../client.js";
import { agents } from "../agents.js";
import { capabilities } from "../capabilities.js";
import { memory } from "../memory.js";
import { workspaces } from "../workspaces.js";
import { system } from "../system.js";
import { integrations } from "../integrations.js";
import { workflows } from "../workflows.js";
import { auth } from "../auth.js";
import { mcp } from "../mcp.js";
import { growth } from "../growth.js";

describe("SDK domains", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("agents", () => {
    it("list() calls GET /agents", async () => {
      await agents.list();
      expect(client.get).toHaveBeenCalledWith("/agents");
    });

    it("create() calls POST /agents with config", async () => {
      await agents.create({ name: "test" });
      expect(client.post).toHaveBeenCalledWith("/agents", { name: "test" });
    });

    it("delete() calls DELETE /agents/{id}", async () => {
      await agents.delete("agt_1");
      expect(client.del).toHaveBeenCalledWith("/agents/agt_1");
    });

    it("confirm() calls POST /agent/confirm with params", async () => {
      await agents.confirm("s1", "c1", true, "pass");
      expect(client.post).toHaveBeenCalledWith("/agent/confirm", {
        session_id: "s1", confirmation_id: "c1", approved: true, password: "pass",
      });
    });
  });

  describe("capabilities", () => {
    it("list() calls GET /capabilities", async () => {
      await capabilities.list();
      expect(client.get).toHaveBeenCalledWith("/capabilities");
    });

    it("execute() calls POST /execute", async () => {
      await capabilities.execute("cap_1", { x: 1 });
      expect(client.post).toHaveBeenCalledWith("/execute", { capability_id: "cap_1", inputs: { x: 1 } });
    });

    it("plan() calls POST /plan with history", async () => {
      const hist = [{ role: "user", content: "hi" }];
      await capabilities.plan("do stuff", hist);
      expect(client.post).toHaveBeenCalledWith("/plan", { intent: "do stuff", conversation_history: hist });
    });
  });

  describe("memory", () => {
    it("context() calls GET /memory/context", async () => {
      await memory.context();
      expect(client.get).toHaveBeenCalledWith("/memory/context");
    });

    it("history() adds query params", async () => {
      await memory.history("cap1", "ws1");
      expect(client.get).toHaveBeenCalledWith("/memory/history?capability_id=cap1&workspace_id=ws1");
    });

    it("semantic.search() encodes query", async () => {
      await memory.semantic.search("hello world", 3);
      expect(client.get).toHaveBeenCalledWith("/memory/semantic/search?q=hello%20world&top_k=3");
    });

    it("clearAll() calls DELETE /memory", async () => {
      await memory.clearAll();
      expect(client.del).toHaveBeenCalledWith("/memory");
    });
  });

  describe("workspaces", () => {
    it("list() calls GET /workspaces", async () => {
      await workspaces.list();
      expect(client.get).toHaveBeenCalledWith("/workspaces");
    });

    it("add() calls POST /workspaces with defaults", async () => {
      await workspaces.add("My Project", "/path");
      expect(client.post).toHaveBeenCalledWith("/workspaces", {
        name: "My Project", path: "/path", access: "write", capabilities: "*", color: "#00ff88",
      });
    });

    it("remove() calls DELETE /workspaces/{id}", async () => {
      await workspaces.remove("ws_1");
      expect(client.del).toHaveBeenCalledWith("/workspaces/ws_1");
    });
  });

  describe("system", () => {
    it("health() calls GET /health", async () => {
      await system.health();
      expect(client.get).toHaveBeenCalledWith("/health");
    });

    it("settings.save() calls POST /settings", async () => {
      await system.settings.save({ llm: {} });
      expect(client.post).toHaveBeenCalledWith("/settings", { settings: { llm: {} } });
    });

    it("scheduler.deleteTask() calls DELETE", async () => {
      await system.scheduler.deleteTask("t1");
      expect(client.del).toHaveBeenCalledWith("/scheduler/tasks/t1");
    });
  });

  describe("integrations", () => {
    it("telegram uses channelDomain pattern", async () => {
      await integrations.telegram.status();
      expect(client.get).toHaveBeenCalledWith("/integrations/telegram/status");
      await integrations.telegram.test();
      expect(client.post).toHaveBeenCalledWith("/integrations/telegram/test", {});
    });

    it("new channels follow same pattern", async () => {
      await integrations.signal.status();
      expect(client.get).toHaveBeenCalledWith("/integrations/signal/status");
      await integrations.matrix.startPolling();
      expect(client.post).toHaveBeenCalledWith("/integrations/matrix/polling/start", {});
    });
  });

  describe("workflows", () => {
    it("CRUD maps to correct endpoints", async () => {
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
    it("login() calls publicPost /auth/login", async () => {
      await auth.login("user", "pass");
      expect(client.publicPost).toHaveBeenCalledWith("/auth/login", { username: "user", password: "pass" });
    });

    it("me() calls GET /auth/me", async () => {
      await auth.me();
      expect(client.get).toHaveBeenCalledWith("/auth/me");
    });
  });

  describe("mcp", () => {
    it("servers.list() calls GET /mcp/servers", async () => {
      await mcp.servers.list();
      expect(client.get).toHaveBeenCalledWith("/mcp/servers");
    });

    it("tools.install() calls POST", async () => {
      await mcp.tools.install("tool1");
      expect(client.post).toHaveBeenCalledWith("/mcp/tools/tool1/install", {});
    });
  });

  describe("growth", () => {
    it("gaps.pending() calls GET /gaps/pending", async () => {
      await growth.gaps.pending();
      expect(client.get).toHaveBeenCalledWith("/gaps/pending");
    });

    it("proposals.approve() calls POST", async () => {
      await growth.proposals.approve("cap1");
      expect(client.post).toHaveBeenCalledWith("/proposals/cap1/approve", {});
    });
  });
});
