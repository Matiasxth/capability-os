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

const statusPayload = {
  llm: { status: "ready", provider: "openai", suggest_only: true },
  browser_worker: {
    active_session_id: "session_1",
    known_sessions: ["session_1"],
    transport: { alive: true, worker_failed: false, dead_reason: null }
  },
  integrations: {
    total: 1,
    enabled: 1,
    error: 0,
    items: [{ id: "whatsapp_web_connector", status: "enabled", name: "WhatsApp Web Connector", type: "web_app" }]
  }
};

const capabilitiesPayload = {
  capabilities: [
    { id: "read_file", name: "Read file", description: "Read file", domain: "archivos", type: "base", status: "ready" },
    { id: "write_file", name: "Write file", description: "Write file", domain: "archivos", type: "base", status: "ready" }
  ]
};

describe("Workspace UI", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders workspace layout", async () => {
    global.fetch = createFetchMock({
      "GET /capabilities": { payload: capabilitiesPayload },
      "GET /status": { payload: statusPayload }
    });

    const { container } = render(<App />);

    expect(await screen.findByText(/Capability OS Workspace/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/What do you want Capability OS to do/i)).toBeInTheDocument();
    expect(screen.getByText(/^Plan$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Execution$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Inspector$/i)).toBeInTheDocument();
  });

  it("generates plan and allows input editing", async () => {
    global.fetch = createFetchMock({
      "GET /capabilities": { payload: capabilitiesPayload },
      "GET /status": { payload: statusPayload },
      "POST /plan": {
        payload: {
          type: "capability",
          suggest_only: true,
          valid: true,
          errors: [],
          steps: [{ step_id: "step_1", capability: "read_file", inputs: { path: "demo.txt" } }]
        }
      }
    });

    const { container } = render(<App />);
    fireEvent.change(await screen.findByLabelText(/What do you want Capability OS to do/i), {
      target: { value: "read demo.txt" }
    });
    fireEvent.click(screen.getByRole("button", { name: /generate plan/i }));

    expect(await screen.findByText("step_1")).toBeInTheDocument();
    const pathInput = await screen.findByLabelText(/path/i);
    expect(pathInput).toBeInTheDocument();
    fireEvent.change(pathInput, { target: { value: "edited.txt" } });
    expect(pathInput.value).toBe("edited.txt");
  });

  it("executes plan and shows timeline", async () => {
    global.fetch = createFetchMock({
      "GET /capabilities": { payload: capabilitiesPayload },
      "GET /status": { payload: statusPayload },
      "POST /plan": {
        payload: {
          type: "capability",
          suggest_only: true,
          valid: true,
          errors: [],
          steps: [{ step_id: "step_1", capability: "read_file", inputs: { path: "demo.txt" } }]
        }
      },
      "POST /execute": {
        payload: {
          status: "success",
          execution_id: "exec_1",
          capability_id: "read_file",
          runtime: {
            status: "ready",
            logs: [{ event: "execution_started", timestamp: "2026-01-01T00:00:00Z", payload: {} }]
          },
          final_output: { content: "ok" },
          error_code: null,
          error_message: null
        }
      },
      "GET /executions/exec_1": {
        payload: {
          status: "success",
          execution_id: "exec_1",
          capability_id: "read_file",
          runtime: {
            status: "ready",
            logs: [{ event: "execution_finished", timestamp: "2026-01-01T00:00:01Z", payload: {} }]
          },
          final_output: { content: "ok" },
          error_code: null,
          error_message: null
        }
      },
      "GET /executions/exec_1/events": {
        payload: {
          execution_id: "exec_1",
          events: [
            { event: "execution_started", timestamp: "2026-01-01T00:00:00Z", payload: {} },
            { event: "execution_finished", timestamp: "2026-01-01T00:00:01Z", payload: {} }
          ]
        }
      }
    });

    const { container } = render(<App />);
    fireEvent.change(await screen.findByLabelText(/What do you want Capability OS to do/i), {
      target: { value: "read demo.txt" }
    });
    fireEvent.click(screen.getByRole("button", { name: /generate plan/i }));
    fireEvent.click(await screen.findByRole("button", { name: /run plan/i }));

    await waitFor(() => expect(screen.getByText("execution_started")).toBeInTheDocument());
    expect(screen.getByText("execution_finished")).toBeInTheDocument();
    expect(
      screen.getByText((_, element) => element?.textContent?.trim() === "status: success")
    ).toBeInTheDocument();
  });

  it("shows visible error when plan execution fails", async () => {
    global.fetch = createFetchMock({
      "GET /capabilities": { payload: capabilitiesPayload },
      "GET /status": { payload: statusPayload },
      "POST /plan": {
        payload: {
          type: "capability",
          suggest_only: true,
          valid: true,
          errors: [],
          steps: [{ step_id: "step_1", capability: "read_file", inputs: { path: "demo.txt" } }]
        }
      },
      "POST /execute": {
        payload: {
          status: "error",
          execution_id: "exec_2",
          capability_id: "read_file",
          runtime: { status: "error", logs: [] },
          final_output: {},
          error_code: "tool_execution_error",
          error_message: "boom"
        }
      },
      "GET /executions/exec_2": {
        payload: {
          status: "error",
          execution_id: "exec_2",
          capability_id: "read_file",
          runtime: { status: "error", logs: [] },
          final_output: {},
          error_code: "tool_execution_error",
          error_message: "boom"
        }
      },
      "GET /executions/exec_2/events": {
        payload: { execution_id: "exec_2", events: [] }
      }
    });

    const { container } = render(<App />);
    fireEvent.change(await screen.findByLabelText(/What do you want Capability OS to do/i), {
      target: { value: "read demo.txt" }
    });
    fireEvent.click(screen.getByRole("button", { name: /generate plan/i }));
    fireEvent.click(await screen.findByRole("button", { name: /run plan/i }));

    await waitFor(() => {
      const banner = container.querySelector(".error-banner");
      expect(banner).toBeInTheDocument();
      expect(banner?.textContent || "").toMatch(/boom/i);
    });
  });
});
