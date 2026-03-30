import { useCallback, useMemo, useState } from "react";

/**
 * Command palette search logic.
 * Items: [{ id, label, subtitle?, shortcut?, group, action }]
 */
export function useCommandPalette(itemSources = []) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

  const allItems = useMemo(() => {
    const items = [];
    for (const source of itemSources) {
      const resolved = typeof source.items === "function" ? source.items() : source.items;
      for (const item of resolved || []) {
        items.push({ ...item, group: source.type });
      }
    }
    return items;
  }, [itemSources]);

  const results = useMemo(() => {
    if (!query.trim()) return allItems.slice(0, 12);
    const q = query.toLowerCase();
    return allItems
      .filter(item => {
        const text = `${item.label} ${item.subtitle || ""}`.toLowerCase();
        return text.includes(q);
      })
      .slice(0, 10);
  }, [query, allItems]);

  const grouped = useMemo(() => {
    const groups = {};
    for (const item of results) {
      const g = item.group || "other";
      if (!groups[g]) groups[g] = [];
      groups[g].push(item);
    }
    return groups;
  }, [results]);

  const open = useCallback(() => {
    setIsOpen(true);
    setQuery("");
    setSelectedIndex(0);
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
    setQuery("");
    setSelectedIndex(0);
  }, []);

  const selectNext = useCallback(() => {
    setSelectedIndex(i => Math.min(i + 1, results.length - 1));
  }, [results.length]);

  const selectPrev = useCallback(() => {
    setSelectedIndex(i => Math.max(i - 1, 0));
  }, []);

  const executeSelected = useCallback(() => {
    const item = results[selectedIndex];
    if (item?.action) {
      item.action();
      close();
    }
  }, [results, selectedIndex, close]);

  return {
    isOpen, query, setQuery, results, grouped, selectedIndex, setSelectedIndex,
    open, close, selectNext, selectPrev, executeSelected,
  };
}
