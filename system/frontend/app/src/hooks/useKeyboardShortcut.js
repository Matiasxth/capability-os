import { useEffect } from "react";
import { useShortcuts } from "../context/ShortcutContext";

/**
 * Register a keyboard shortcut. Automatically cleans up on unmount.
 * @param {string} combo - e.g. "mod+k", "?", "mod+shift+t"
 * @param {Function} handler
 * @param {string} scope - "global" | "workspace" | "input"
 */
export function useKeyboardShortcut(combo, handler, scope = "global") {
  const { register } = useShortcuts();
  useEffect(() => {
    if (!combo || !handler) return;
    return register(combo, handler, scope);
  }, [combo, handler, scope, register]);
}
