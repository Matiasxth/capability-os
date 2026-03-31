import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import sdk from "../sdk";

const WebSocketContext = createContext();

const MAX_EVENTS = 100;

export function WebSocketProvider({ children }) {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(sdk.events.isConnected());

  useEffect(() => {
    const handler = (event) => {
      if (!event || !event.type) return;
      setEvents(prev => [event, ...prev].slice(0, MAX_EVENTS));
    };
    sdk.events.on("*", handler);
    const unsub = sdk.events.onConnectionChange(setConnected);
    return () => { sdk.events.off("*", handler); unsub(); };
  }, []);

  const subscribe = useCallback((fn) => {
    sdk.events.on("*", fn);
    return () => sdk.events.off("*", fn);
  }, []);

  return (
    <WebSocketContext.Provider value={{ connected, events, subscribe }}>
      {children}
    </WebSocketContext.Provider>
  );
}

export const useGlobalWebSocket = () => useContext(WebSocketContext);
