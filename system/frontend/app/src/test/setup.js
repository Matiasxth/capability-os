import "@testing-library/jest-dom/vitest";

// Mock WebSocket globally for all tests (SDK events.js creates WS on import)
class MockWebSocket {
  constructor() {
    this.readyState = 0;
    setTimeout(() => { this.readyState = 1; this.onopen?.(); }, 0);
  }
  close() { this.readyState = 3; this.onclose?.(); }
  send() {}
}
globalThis.WebSocket = MockWebSocket;

// Mock matchMedia for PWA checks
if (!window.matchMedia) {
  window.matchMedia = () => ({ matches: false, addListener: () => {}, removeListener: () => {} });
}

// Mock Notification API
if (!globalThis.Notification) {
  globalThis.Notification = class {
    static permission = "default";
    static requestPermission() { return Promise.resolve("denied"); }
    constructor() {}
  };
}

// Mock navigator.serviceWorker
if (!navigator.serviceWorker) {
  Object.defineProperty(navigator, "serviceWorker", {
    value: { register: () => Promise.resolve({}), getRegistrations: () => Promise.resolve([]) },
    writable: true,
  });
}
