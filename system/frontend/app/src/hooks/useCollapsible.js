import { useCallback, useState } from "react";

/**
 * Hook for collapsible panels with localStorage persistence.
 */
export function useCollapsible(storageKey = "capos_sidebar_collapsed", defaultCollapsed = false) {
  const [isCollapsed, setIsCollapsed] = useState(() => {
    const stored = localStorage.getItem(storageKey);
    return stored !== null ? stored === "true" : defaultCollapsed;
  });

  const toggle = useCallback(() => {
    setIsCollapsed(prev => {
      const next = !prev;
      localStorage.setItem(storageKey, String(next));
      return next;
    });
  }, [storageKey]);

  const collapse = useCallback(() => {
    setIsCollapsed(true);
    localStorage.setItem(storageKey, "true");
  }, [storageKey]);

  const expand = useCallback(() => {
    setIsCollapsed(false);
    localStorage.setItem(storageKey, "false");
  }, [storageKey]);

  return { isCollapsed, toggle, collapse, expand };
}
