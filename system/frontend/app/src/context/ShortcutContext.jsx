import React, { createContext, useCallback, useContext, useEffect, useRef } from "react";

const ShortcutContext = createContext();

function buildCombo(e) {
  const parts = [];
  if (e.ctrlKey || e.metaKey) parts.push("mod");
  if (e.shiftKey) parts.push("shift");
  if (e.altKey) parts.push("alt");
  const key = e.key.toLowerCase();
  if (!["control", "meta", "shift", "alt"].includes(key)) parts.push(key);
  return parts.join("+");
}

export function ShortcutProvider({ children }) {
  const registryRef = useRef(new Map());

  const register = useCallback((combo, handler, scope = "global") => {
    registryRef.current.set(combo, { handler, scope });
    return () => registryRef.current.delete(combo);
  }, []);

  useEffect(() => {
    function onKeyDown(e) {
      const combo = buildCombo(e);
      const entry = registryRef.current.get(combo);
      if (!entry) return;
      const inInput = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
      if (inInput && entry.scope !== "global" && entry.scope !== "input") return;
      e.preventDefault();
      entry.handler(e);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <ShortcutContext.Provider value={{ register }}>
      {children}
    </ShortcutContext.Provider>
  );
}

export const useShortcuts = () => useContext(ShortcutContext);
