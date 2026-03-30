import React from "react";

/**
 * App shell layout: header (44px) + main content (1fr) + status bar (24px).
 * Uses CSS grid for the 3-row layout.
 */
export default function AppLayout({ header, statusBar, children }) {
  return (
    <div className="app-shell">
      {header}
      <main className="app-main">
        {children}
      </main>
      {statusBar}
    </div>
  );
}
