import React, { createContext, useCallback, useContext, useRef, useState } from "react";
import { useWebSocket } from "../hooks/useWebSocket";

const WebSocketContext = createContext();

const MAX_EVENTS = 100;

export function WebSocketProvider({ children }) {
  const [events, setEvents] = useState([]);
  const listenersRef = useRef(new Set());

  const handleEvent = useCallback((event) => {
    if (!event || !event.type) return;
    setEvents(prev => [event, ...prev].slice(0, MAX_EVENTS));
    listenersRef.current.forEach(fn => {
      try { fn(event); } catch {}
    });
  }, []);

  const { connected } = useWebSocket(handleEvent);

  const subscribe = useCallback((fn) => {
    listenersRef.current.add(fn);
    return () => listenersRef.current.delete(fn);
  }, []);

  return (
    <WebSocketContext.Provider value={{ connected, events, subscribe }}>
      {children}
    </WebSocketContext.Provider>
  );
}

export const useGlobalWebSocket = () => useContext(WebSocketContext);
