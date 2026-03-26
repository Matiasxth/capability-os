import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

function jsonResponse(payload, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload
  });
}

function createFetchMock(routes) {
  return vi.fn((url, options = {}) => {
    const method = (options.method || "GET").toUpperCase();
    const path = new URL(url).pathname;
    const key = `${method} ${path}`;
    const route = routes[key];
    if (!route) {
      throw new Error(`Unhandled route in test: ${key}`);
    }
    if (typeof route === "function") {
      const result = route(options);
      return jsonResponse(result.payload, result.status || 200);
    }
    return jsonResponse(route.payload, route.status || 200);
  });
}

const settingsPayload = {
  settings: {
    llm: {
      provider: "ollama",
      base_url: "http://127.0.0.1:11434",
      model: "llama3.1:8b",
      api_key: "",
      timeout_ms: 30000
    },
    browser: { auto_start: true },
    workspace: {
      artifacts_path: "/tmp/workspace/artifacts",
      sequences_path: "/tmp/workspace/sequences"
    }
  }
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
    transport: { alive: true, worker_failed: false, dead_reason: null }
  },
  integrations: { total: 1, enabled: 1, error: 0, items: [] },
  issues: []
};

const integrationsPayload = {
  integrations: [
    {
      id: "whatsapp_web_connector",
      name: "WhatsApp Web Connector",
      type: "web_app",
      status: "enabled",
      capabilities: ["open_whatsapp_web"]
    }
  ]
};

describe("Control Center UI", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.history.pushState({}, "", "/control-center");
  });

  afterEach(() => {
    cleanup();
    window.history.pushState({}, "", "/");
  });

  it("renders control center sections", async () => {
    global.fetch = createFetchMock({
      "GET /settings": { payload: settingsPayload },
      "GET /health": { payload: healthPayload },
      "GET /integrations": { payload: integrationsPayload }
    });

    render(<App />);

    expect(await screen.findByText(/System Control Center/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "LLM" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Browser" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Integrations" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Workspace" }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: "System" })).toBeInTheDocument();
  });

  it("saves LLM config changes", async () => {
    global.fetch = createFetchMock({
      "GET /settings": { payload: settingsPayload },
      "GET /health": { payload: healthPayload },
      "GET /integrations": { payload: integrationsPayload },
      "POST /settings": {
        payload: {
          status: "success",
          settings: {
            ...settingsPayload.settings,
            llm: {
              ...settingsPayload.settings.llm,
              model: "new-model"
            }
          }
        }
      }
    });

    render(<App />);
    const modelInput = await screen.findByDisplayValue("llama3.1:8b");
    fireEvent.change(modelInput, { target: { value: "new-model" } });
    fireEvent.click(screen.getByRole("button", { name: /^Save$/i }));

    await waitFor(() => {
      const settingsSaveCall = global.fetch.mock.calls.find(([url, options = {}]) => {
        return new URL(url).pathname === "/settings" && (options.method || "GET").toUpperCase() === "POST";
      });
      expect(settingsSaveCall).toBeTruthy();
      const body = JSON.parse(settingsSaveCall[1].body);
      expect(body.settings.llm.model).toBe("new-model");
    });
  });

  it("tests LLM connection from UI", async () => {
    global.fetch = createFetchMock({
      "GET /settings": { payload: settingsPayload },
      "GET /health": { payload: healthPayload },
      "GET /integrations": { payload: integrationsPayload },
      "POST /llm/test": {
        payload: {
          status: "success",
          provider: "ollama",
          model: "llama3.1:8b",
          error_code: null,
          error_message: null
        }
      }
    });

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Test Connection/i }));
    expect(await screen.findByText(/LLM test: success/i)).toBeInTheDocument();
  });
});
