import { useCallback, useState } from "react";

let idCounter = 0;

const DURATIONS = { success: 2500, info: 3500, warning: 4500, error: 6000 };

export function useToast(maxToasts = 5) {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((text, type = "info") => {
    const id = ++idCounter;
    const duration = DURATIONS[type] || 3000;
    setToasts((prev) => [...prev.slice(-(maxToasts - 1)), { id, text, type, duration }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), duration);
    return id;
  }, [maxToasts]);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return { toasts, addToast, removeToast };
}
