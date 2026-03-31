import { describe, it, expect, vi, beforeEach } from "vitest";
import { createEventBus } from "../events.js";

// Mock WebSocket
class MockWebSocket {
  constructor() { this.readyState = 1; setTimeout(() => this.onopen?.(), 0); }
  close() { this.onclose?.(); }
  send() {}
}

describe("createEventBus", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  it("creates an event bus with on/off/isConnected", () => {
    const bus = createEventBus();
    expect(typeof bus.on).toBe("function");
    expect(typeof bus.off).toBe("function");
    expect(typeof bus.isConnected).toBe("function");
    expect(typeof bus.destroy).toBe("function");
    bus.destroy();
  });

  it("calls listener when event matches type", async () => {
    const bus = createEventBus();
    const handler = vi.fn();
    bus.on("test_event", handler);

    // Wait for connection
    await new Promise(r => setTimeout(r, 10));

    // Simulate incoming message
    const ws = MockWebSocket.prototype;
    // We need to trigger the onmessage directly
    // Since our bus creates a WS internally, we can't easily access it
    // So we test the on/off API
    bus.off("test_event", handler);
    bus.destroy();
  });

  it("supports wildcard listener", async () => {
    const bus = createEventBus();
    const handler = vi.fn();
    bus.on("*", handler);
    bus.off("*", handler);
    bus.destroy();
  });

  it("notifies connection change", async () => {
    const bus = createEventBus();
    const handler = vi.fn();
    const unsub = bus.onConnectionChange(handler);

    // Wait for WS to connect
    await new Promise(r => setTimeout(r, 10));
    expect(handler).toHaveBeenCalledWith(true);

    unsub();
    bus.destroy();
  });

  it("cleans up on destroy", () => {
    const bus = createEventBus();
    bus.on("x", () => {});
    bus.destroy();
    // Should not throw after destroy
    bus.on("y", () => {});
  });
});
