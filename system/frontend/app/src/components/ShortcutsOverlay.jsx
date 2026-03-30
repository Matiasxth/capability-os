import React from "react";

const SHORTCUTS = [
  ["Ctrl+K", "Command palette"],
  ["?", "Show shortcuts"],
  ["Esc", "Close overlay / panel"],
  ["Ctrl+[", "Toggle sidebar"],
  ["Ctrl+N", "New session"],
  ["Ctrl+Enter", "Send message"],
  ["Ctrl+Shift+T", "Toggle theme"],
  ["Ctrl+/", "Focus chat input"],
];

export default function ShortcutsOverlay({ isOpen, onClose }) {
  if (!isOpen) return null;

  return (
    <div className="shortcuts-overlay" onClick={onClose}>
      <div className="shortcuts-panel" onClick={e => e.stopPropagation()}>
        <h3 className="shortcuts-title">Keyboard Shortcuts</h3>
        <div className="shortcuts-grid">
          {SHORTCUTS.map(([key, desc]) => (
            <React.Fragment key={key}>
              <span className="shortcut-key">{key}</span>
              <span className="shortcut-desc">{desc}</span>
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}
