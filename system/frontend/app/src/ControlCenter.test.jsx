import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/* ── Payloads ── */
const settingsPayload = {
  settings: {
    llm: {
      provider: "ollama",
      base_url: "http://127.0.0.1:11434",
      model: "llama3.1:8b",
      api_key: "",
      timeout_ms: 30000,
    },
    browser: { auto_start: true },
    workspace: {
      artifacts_path: "/tmp/workspace/artifacts",
      sequences_path: "/tmp/workspace/sequences",
    },
  },
};

const healthPayload = {
  status: "ready",
  uptime_ms: 1000,
  llm: { status: "ready", provider: "ollama", model: "llama3.1:8b" },
  browser_worker: {
    status: "ready",
    auto_start: true,
    active_session_id: null,
    known_sessions: [],
    transport: { alive: true, worker_failed: false, dead_reason: null },
  },
  integrations: { total: 1, enabled: 1, error: 0, items: [] },
  issues: [],
};

const integrationsPayload = {
  integrations: [
    {
      id: "whatsapp_web_connector",
      name: "WhatsApp Web Connector",
      type: "web_app",
      status: "enabled",
      capabilities: ["open_whatsapp_web"],
    },
  ],
};

/* ── Hoisted mock helpers ── */
const { createMock, mockSdk } = vi.hoisted(() => {
  const createMock = (val = {}) => vi.fn(() => Promise.resolve(val));

  const mockSdk = {
    auth: {
      me: createMock({ user: { id: "u1", display_name: "Tester", role: "owner" } }),
      login: createMock({ access_token: "t", user: { id: "u1", display_name: "Tester", role: "owner" } }),
      status: createMock({ auth_enabled: true }),
    },
    system: {
      health: createMock({}),
      status: createMock({}),
      settings: {
        get: createMock({}),
        save: createMock({}),
      },
      llm: { test: createMock({}) },
      browser: { cdpStatus: createMock({}), launchChrome: createMock({}), connectCDP: createMock({}), restart: createMock({}), openWhatsApp: createMock({}) },
      plugins: { list: createMock({ plugins: [] }) },
      supervisor: { status: createMock({}) },
      scheduler: { status: createMock({}), listTasks: createMock({ tasks: [] }) },
      files: { tree: createMock({ tree: [] }) },
      logs: createMock([]),
      exportConfig: createMock({}),
      importConfig: createMock({}),
    },
    capabilities: {
      list: createMock({ capabilities: [] }),
      plan: createMock({}),
      execute: createMock({}),
      chat: createMock({ reply: "ok" }),
      interpret: createMock({}),
      get: createMock({}),
      health: createMock({}),
      getExecution: createMock({}),
      getExecutionEvents: createMock({ events: [] }),
      streamChat: vi.fn(async function* () {}),
      streamExecution: vi.fn(async function* () {}),
    },
    memory: {
      preferences: createMock({ preferences: { name: "Tester" } }),
      history: createMock({ history: [] }),
      context: createMock({}),
      deleteHistory: createMock({}),
      saveChatSession: createMock({}),
      clearAll: createMock({}),
      compact: createMock({}),
      metrics: createMock({}),
      setPreferences: createMock({}),
      semantic: { search: createMock({ results: [] }), add: createMock({}), delete: createMock({}) },
      markdown: { get: createMock({}), save: createMock({}), addFact: createMock({}), removeFact: createMock({}) },
    },
    workspaces: {
      list: createMock({ workspaces: [{ id: "ws1", name: "Main", path: "/tmp/ws", color: "#00ff88" }], default_id: "ws1" }),
    },
    agents: {
      list: createMock({ agents: [] }),
      stream: vi.fn(async function* () {}),
    },
    integrations: {
      list: createMock({}),
      get: createMock({}),
      validate: createMock({}),
      enable: createMock({}),
      disable: createMock({}),
      whatsapp: { status: createMock({}), start: createMock({}), stop: createMock({}), qr: createMock({}), configure: createMock({}), switchBackend: createMock({}), listBackends: createMock({}) },
      telegram: { status: createMock({}), configure: createMock({}), test: createMock({}), startPolling: createMock({}), stopPolling: createMock({}), pollingStatus: createMock({}) },
      slack: { status: createMock({}), configure: createMock({}), test: createMock({}), startPolling: createMock({}), stopPolling: createMock({}), pollingStatus: createMock({}) },
      discord: { status: createMock({}), configure: createMock({}), test: createMock({}), startPolling: createMock({}), stopPolling: createMock({}), pollingStatus: createMock({}) },
    },
    events: {
      on: vi.fn(),
      off: vi.fn(),
      isConnected: () => true,
      onConnectionChange: vi.fn(() => () => {}),
      destroy: vi.fn(),
    },
    session: {
      getToken: () => "test-token",
      setToken: vi.fn(),
      clearToken: vi.fn(),
      getUsername: () => "Tester",
      setUsername: vi.fn(),
      restoreChatMessages: () => [],
      saveChatMessages: vi.fn(),
      clearChatMessages: vi.fn(),
    },
    skills: {
      list: createMock({ skills: [] }),
      autoGenerated: createMock({ skills: [] }),
    },
    growth: {
      gaps: { pending: createMock({ gaps: [] }) },
      optimizations: { pending: createMock({ optimizations: [] }) },
      proposals: { list: createMock({ proposals: [] }) },
    },
    mcp: {},
    a2a: {},
    workflows: {},
  };

  return { createMock, mockSdk };
});

vi.mock("./sdk", () => ({ default: mockSdk }));
vi.mock("./sdk/notifications", () => ({
  showLocalNotification: vi.fn(),
  requestPermission: vi.fn(() => Promise.resolve("granted")),
  isInstalled: vi.fn(() => false),
}));
vi.mock("./sdk/events.js", () => ({
  createEventBus: () => mockSdk.events,
}));

import App from "./App";

describe("Control Center UI", () => {
  beforeEach(() => {
    // Set up return values for Control Center data fetches
    mockSdk.system.settings.get.mockResolvedValue(settingsPayload);
    mockSdk.system.health.mockResolvedValue(healthPayload);
    mockSdk.integrations.list.mockResolvedValue(integrationsPayload);
    mockSdk.system.llm.test.mockResolvedValue({
      status: "success",
      provider: "ollama",
      model: "llama3.1:8b",
      latency_ms: 42,
      error_code: null,
      error_message: null,
    });
    mockSdk.system.settings.save.mockImplementation((data) =>
      Promise.resolve({
        status: "success",
        settings: data.settings || data,
      })
    );

    window.history.pushState({}, "", "/control-center");
  });

  afterEach(() => {
    cleanup();
    window.history.pushState({}, "", "/");
  });

  it("renders control center sections", async () => {
    render(<App />);

    // Sidebar heading is "Control", content heading is "System" (default section)
    expect(await screen.findByText("Control")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "LLM" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Browser" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Integrations" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Workspaces" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "System" })).toBeInTheDocument();
  });

  it("saves LLM config changes", async () => {
    render(<App />);

    // Click on LLM sidebar button to navigate to LLM section
    fireEvent.click(await screen.findByRole("button", { name: "LLM" }));

    // Wait for the model input to appear (LLM section renders model input for ollama preset)
    const modelInput = await screen.findByDisplayValue("llama3.1:8b");
    fireEvent.change(modelInput, { target: { value: "new-model" } });
    fireEvent.click(screen.getByRole("button", { name: /^Save$/i }));

    await waitFor(() => {
      expect(mockSdk.system.settings.save).toHaveBeenCalled();
    });
  });

  it("tests LLM connection from UI", async () => {
    render(<App />);

    // Click on LLM sidebar button to navigate to LLM section
    fireEvent.click(await screen.findByRole("button", { name: "LLM" }));

    // Click "Test Connection"
    fireEvent.click(await screen.findByRole("button", { name: /Test Connection/i }));

    // The success banner shows "Connected" text
    expect(await screen.findByText(/Connected/i)).toBeInTheDocument();
  });
});
