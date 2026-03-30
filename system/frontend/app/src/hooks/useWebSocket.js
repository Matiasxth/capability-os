import { useCallback, useEffect, useRef, useState } from "react";

const DEFAULT_URL = import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8001";
const MAX_BACKOFF = 30000;

/**
 * React hook for WebSocket connection with auto-reconnect.
 *
 * @param {function} onEvent - Called with parsed JSON for each message.
 * @param {string}   [url]  - WebSocket URL (default ws://127.0.0.1:8001).
 * @returns {{ connected: boolean }}
 */
export function useWebSocket(onEvent, url) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const retriesRef = useRef(0);
  const timerRef = useRef(null);
  const onEventRef = useRef(onEvent);
  const unmountedRef = useRef(false);

  // Keep callback ref fresh without re-triggering effect
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

  const connect = useCallback(() => {
    if (unmountedRef.current) return;
    const wsUrl = url || DEFAULT_URL;

    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch {
      // WebSocket constructor can throw in some environments
      scheduleReconnect();
      return;
    }

    wsRef.current = ws;

    ws.onopen = () => {
      if (unmountedRef.current) { ws.close(); return; }
      retriesRef.current = 0;
      setConnected(true);
    };

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (onEventRef.current) onEventRef.current(data);
      } catch {
        // ignore non-JSON frames (ping etc)
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      if (!unmountedRef.current) scheduleReconnect();
    };

    ws.onerror = () => {
      // onclose will fire after onerror — reconnect happens there
    };

    function scheduleReconnect() {
      if (unmountedRef.current) return;
      const delay = Math.min(1000 * Math.pow(2, retriesRef.current), MAX_BACKOFF);
      retriesRef.current++;
      timerRef.current = setTimeout(() => {
        if (!unmountedRef.current) connect();
      }, delay);
    }
  }, [url]);

  useEffect(() => {
    unmountedRef.current = false;
    connect();
    return () => {
      unmountedRef.current = true;
      if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
      if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    };
  }, [connect]);

  return { connected };
}
