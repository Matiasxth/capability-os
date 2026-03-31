/**
 * Unified event bus over WebSocket.
 * Single connection, pub/sub interface: sdk.events.on(type, fn) / off(type, fn).
 * Dynamic WS URL derived from VITE_API_BASE_URL (no more hardcoded ws://127.0.0.1:8001).
 */

const MAX_BACKOFF = 30000;

function resolveWsUrl() {
  const envUrl = import.meta.env.VITE_WS_URL;
  if (envUrl) return envUrl;

  const apiBase = import.meta.env.VITE_API_BASE_URL || "";
  if (apiBase) {
    try {
      const url = new URL(apiBase);
      const proto = url.protocol === "https:" ? "wss:" : "ws:";
      const port = parseInt(url.port || (url.protocol === "https:" ? "443" : "80"), 10) + 1;
      return `${proto}//${url.hostname}:${port}`;
    } catch { /* fall through */ }
  }

  // Derive from current page location
  const loc = window.location;
  const proto = loc.protocol === "https:" ? "wss:" : "ws:";
  const port = parseInt(loc.port || (loc.protocol === "https:" ? "443" : "80"), 10) + 1;
  return `${proto}//${loc.hostname}:${port}`;
}

/**
 * @typedef {Object} EventBus
 * @property {(type: string, fn: Function) => void} on
 * @property {(type: string, fn: Function) => void} off
 * @property {() => boolean} isConnected
 * @property {(fn: Function) => void} onConnectionChange
 * @property {() => void} destroy
 */

/** @returns {EventBus} */
export function createEventBus() {
  /** @type {Map<string, Set<Function>>} */
  const listeners = new Map();
  /** @type {Set<Function>} */
  const connectionListeners = new Set();
  let ws = null;
  let retries = 0;
  let timer = null;
  let connected = false;
  let destroyed = false;

  function notify(event) {
    if (!event || !event.type) return;
    const fns = listeners.get(event.type);
    if (fns) fns.forEach(fn => { try { fn(event); } catch { /* */ } });
    // Wildcard listeners
    const all = listeners.get("*");
    if (all) all.forEach(fn => { try { fn(event); } catch { /* */ } });
  }

  function setConnected(val) {
    if (connected === val) return;
    connected = val;
    connectionListeners.forEach(fn => { try { fn(val); } catch { /* */ } });
  }

  function connect() {
    if (destroyed) return;
    const url = resolveWsUrl();
    try { ws = new WebSocket(url); } catch { scheduleReconnect(); return; }

    ws.onopen = () => { retries = 0; setConnected(true); };
    ws.onmessage = (evt) => {
      try { notify(JSON.parse(evt.data)); } catch { /* non-JSON */ }
    };
    ws.onclose = () => { ws = null; setConnected(false); if (!destroyed) scheduleReconnect(); };
    ws.onerror = () => { /* onclose fires after */ };
  }

  function scheduleReconnect() {
    if (destroyed) return;
    const delay = Math.min(1000 * Math.pow(2, retries), MAX_BACKOFF);
    retries++;
    timer = setTimeout(connect, delay);
  }

  // Start immediately
  connect();

  return {
    on(type, fn) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(fn);
    },
    off(type, fn) {
      const fns = listeners.get(type);
      if (fns) { fns.delete(fn); if (fns.size === 0) listeners.delete(type); }
    },
    isConnected() { return connected; },
    onConnectionChange(fn) { connectionListeners.add(fn); return () => connectionListeners.delete(fn); },
    destroy() {
      destroyed = true;
      if (timer) { clearTimeout(timer); timer = null; }
      if (ws) { ws.close(); ws = null; }
      listeners.clear();
      connectionListeners.clear();
    },
  };
}
