import React from "react";
import CCSidebar from "./CCSidebar";

export default function CCLayout({ activeSection, onSelectSection, wsConnected, highlightSection, children }) {
  return (
    <div className="cc-layout">
      <CCSidebar
        activeSection={activeSection}
        onSelectSection={onSelectSection}
        wsConnected={wsConnected}
        highlightSection={highlightSection}
      />
      <div className="cc-content">
        {children}
      </div>
    </div>
  );
}
