import React, { useEffect, useState } from "react";
import AdvancedPanel from "./components/AdvancedPanel";
import ControlCenter from "./pages/ControlCenter";
import Workspace from "./pages/Workspace";

function normalizePath(pathname) {
  if (pathname.startsWith("/control-center")) {
    return "/control-center";
  }
  return "/";
}

export default function App() {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [route, setRoute] = useState(normalizePath(window.location.pathname));

  useEffect(() => {
    function handlePopState() {
      setRoute(normalizePath(window.location.pathname));
    }
    window.addEventListener("popstate", handlePopState);
    return () => {
      window.removeEventListener("popstate", handlePopState);
    };
  }, []);

  function navigate(path) {
    if (path !== normalizePath(window.location.pathname)) {
      window.history.pushState({}, "", path);
    }
    setRoute(path);
  }

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div>
          <strong>Capability OS</strong>
        </div>
        <div className="topbar-actions">
          <button
            type="button"
            className={route === "/" ? "is-active" : ""}
            onClick={() => navigate("/")}
          >
            Workspace
          </button>
          <button
            type="button"
            className={route === "/control-center" ? "is-active" : ""}
            onClick={() => navigate("/control-center")}
          >
            Control Center
          </button>
        </div>
      </header>

      {route === "/control-center" ? <ControlCenter /> : <Workspace />}

      <section className="advanced-panel-shell">
        <button
          type="button"
          className="advanced-toggle"
          onClick={() => setShowAdvanced((previous) => !previous)}
        >
          {showAdvanced ? "Hide Technical Mode" : "Show Technical Mode"}
        </button>
        {showAdvanced && (
          <div className="advanced-content">
            <AdvancedPanel />
          </div>
        )}
      </section>
    </div>
  );
}
