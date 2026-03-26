import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
    active_session_id: null,
    known_sessions: [],
    transport: { alive: false, worker_failed: false, dead_reason: null }
  },
  integrations: { total: 0, enabled: 0, error: 0, items: [] }
};

const capabilitiesPayload = {
  capabilities: [{ id: "read_file", name: "Read file", description: "", domain: "archivos", type: "base", status: "ready" }]
};

describe("Workspace planning suggest_only flow", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders unknown plan without auto-executing", async () => {
    const executeSpy = vi.fn();
    global.fetch = createFetchMock({
      "GET /capabilities": { payload: capabilitiesPayload },
      "GET /status": { payload: statusPayload },
      "POST /plan": {
        payload: {
          type: "unknown",
          suggest_only: true,
          valid: false,
          errors: [{ code: "unknown_intent", message: "Intent could not be mapped." }],
          steps: []
        }
      },
      "POST /execute": executeSpy
    });

    render(<App />);
    fireEvent.change(await screen.findByLabelText(/What do you want Capability OS to do/i), {
      target: { value: "haz algo ambiguo" }
    });
    fireEvent.click(screen.getByRole("button", { name: /generate plan/i }));

    expect(await screen.findByText(/Type:/i)).toBeInTheDocument();
    expect(screen.getByText(/unknown/i)).toBeInTheDocument();
    expect(executeSpy).toHaveBeenCalledTimes(0);
  });

  it("shows sequence plan and waits for explicit run click", async () => {
    const executeSpy = vi.fn(() => ({
      status: 200,
      payload: {
        status: "success",
        execution_id: "exec_seq_1",
        capability_id: "read_file",
        runtime: { status: "ready", logs: [] },
        final_output: { content: "ok" },
        error_code: null,
        error_message: null
      }
    }));
    global.fetch = createFetchMock({
      "GET /capabilities": { payload: capabilitiesPayload },
      "GET /status": { payload: statusPayload },
      "POST /plan": {
        payload: {
          type: "sequence",
          suggest_only: true,
          valid: true,
          errors: [],
          steps: [
            { step_id: "step_1", capability: "read_file", inputs: { path: "a.txt" } },
            { step_id: "step_2", capability: "read_file", inputs: { path: "b.txt" } }
          ]
        }
      },
      "POST /execute": executeSpy,
      "GET /executions/exec_seq_1": {
        payload: {
          status: "success",
          execution_id: "exec_seq_1",
          capability_id: "read_file",
          runtime: { status: "ready", logs: [] },
          final_output: { content: "ok" },
          error_code: null,
          error_message: null
        }
      },
      "GET /executions/exec_seq_1/events": {
        payload: { execution_id: "exec_seq_1", events: [] }
      }
    });

    render(<App />);
    fireEvent.change(await screen.findByLabelText(/What do you want Capability OS to do/i), {
      target: { value: "leer dos archivos" }
    });
    fireEvent.click(screen.getByRole("button", { name: /generate plan/i }));

    expect(await screen.findByText("step_1")).toBeInTheDocument();
    expect(screen.getByText("step_2")).toBeInTheDocument();
    expect(executeSpy).toHaveBeenCalledTimes(0);

    fireEvent.click(screen.getByRole("button", { name: /run plan/i }));
    expect(executeSpy).toHaveBeenCalled();
  });
});
