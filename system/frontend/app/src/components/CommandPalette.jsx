import React, { useEffect, useRef } from "react";

const GROUP_LABELS = {
  navigation: "Navigation",
  settings: "Settings",
  action: "Actions",
  session: "Sessions",
  capability: "Capabilities",
};

export default function CommandPalette({
  isOpen, query, setQuery, grouped, results, selectedIndex, setSelectedIndex,
  close, selectNext, selectPrev, executeSelected,
}) {
  const inputRef = useRef(null);

  useEffect(() => {
    if (isOpen && inputRef.current) inputRef.current.focus();
  }, [isOpen]);

  if (!isOpen) return null;

  function onKeyDown(e) {
    if (e.key === "Escape") { close(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); selectNext(); return; }
    if (e.key === "ArrowUp") { e.preventDefault(); selectPrev(); return; }
    if (e.key === "Enter") { e.preventDefault(); executeSelected(); return; }
  }

  let flatIndex = 0;

  return (
    <div className="cmd-palette-overlay" onClick={close}>
      <div className="cmd-palette" onClick={e => e.stopPropagation()} onKeyDown={onKeyDown}>
        <input
          ref={inputRef}
          className="cmd-palette-input"
          value={query}
          onChange={e => { setQuery(e.target.value); setSelectedIndex(0); }}
          placeholder="Search commands, settings, capabilities..."
        />
        <div className="cmd-palette-body">
          {results.length === 0 && (
            <div className="cmd-palette-empty">No results found</div>
          )}
          {Object.entries(grouped).map(([group, items]) => (
            <div key={group} className="cmd-palette-group">
              <div className="cmd-palette-group-label">{GROUP_LABELS[group] || group}</div>
              {items.map((item) => {
                const idx = flatIndex++;
                return (
                  <div
                    key={item.id}
                    className={`cmd-palette-item${idx === selectedIndex ? " is-selected" : ""}`}
                    onClick={() => { item.action?.(); close(); }}
                    onMouseEnter={() => setSelectedIndex(idx)}
                  >
                    <span>{item.label}</span>
                    {item.shortcut && <span className="cmd-palette-shortcut">{item.shortcut}</span>}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
