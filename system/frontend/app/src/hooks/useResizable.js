import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Hook for drag-to-resize panels.
 * Returns { width, handleProps, isResizing }.
 * handleProps should be spread onto the resize handle element.
 */
export function useResizable({ storageKey = "capos_sidebar_w", defaultWidth = 260, minWidth = 180, maxWidth = 400 } = {}) {
  const [width, setWidth] = useState(() => {
    const stored = localStorage.getItem(storageKey);
    return stored ? Math.max(minWidth, Math.min(maxWidth, parseInt(stored, 10) || defaultWidth)) : defaultWidth;
  });
  const [isResizing, setIsResizing] = useState(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);

  const onMouseDown = useCallback((e) => {
    e.preventDefault();
    startXRef.current = e.clientX;
    startWidthRef.current = width;
    setIsResizing(true);
  }, [width]);

  useEffect(() => {
    if (!isResizing) return;

    function onMouseMove(e) {
      const delta = e.clientX - startXRef.current;
      const newWidth = Math.max(minWidth, Math.min(maxWidth, startWidthRef.current + delta));
      setWidth(newWidth);
    }

    function onMouseUp() {
      setIsResizing(false);
      localStorage.setItem(storageKey, String(width));
    }

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    return () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, [isResizing, minWidth, maxWidth, storageKey, width]);

  const handleProps = { onMouseDown, style: { cursor: "col-resize" } };

  return { width, handleProps, isResizing };
}
