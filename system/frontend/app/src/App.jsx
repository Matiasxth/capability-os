import React, { useCallback, useEffect, useState } from "react";
import sdk from "./sdk";
import { AuthProvider, useAuth } from "./context/AuthContext";
import ControlCenter from "./pages/ControlCenter";
import EditorLayout from "./components/editor/EditorLayout";
import Login from "./pages/Login";
import Onboarding from "./pages/Onboarding";
import Workspace from "./pages/Workspace";
import WorkflowEditor from "./pages/WorkflowEditor";
import NotificationCenter from "./components/NotificationCenter";
import InstallPrompt from "./components/layout/InstallPrompt";
import { showLocalNotification, requestPermission } from "./sdk/notifications";

function EditorPage({ wsId, workspaces }) {
  return <div style={{ height: "100%", overflow: "hidden" }}><EditorLayout wsId={wsId} workspaces={workspaces} /></div>;
}

function normalizePath(p) {
  if (p.startsWith("/control-center")) return "/control-center";
  if (p.startsWith("/editor")) return "/editor";
  if (p.startsWith("/workflows")) return "/workflows";
  if (p.startsWith("/login")) return "/login";
  return "/";
}

function AuthenticatedApp() {
  const { user, isAuthenticated, loading: authLoading, logout } = useAuth();
  const [route, setRoute] = useState(normalizePath(window.location.pathname));
  const [apiOnline, setApiOnline] = useState(true);
  const [workspaces, setWorkspaces] = useState([]);
  const [defaultWsId, setDefaultWsId] = useState(null);
  const [userName, setUserName] = useState(() => localStorage.getItem("capos_username") || null);
  const [booting, setBooting] = useState(true);
  const [ncOpen, setNcOpen] = useState(false);
  const [ncEvents, setNcEvents] = useState([]);

  // Listen for real-time events via SDK event bus + push notifications
  useEffect(() => {
    // Request notification permission once on mount
    requestPermission();

    const NOTIFY_EVENTS = { telegram_message: "Telegram", whatsapp_message: "WhatsApp", slack_message: "Slack", discord_message: "Discord", supervisor_alert: "Supervisor", execution_complete: "Execution" };
    const handler = (event) => {
      if (!event || !event.type) return;
      setNcEvents(prev => [{ ...event, timestamp: event.timestamp || new Date().toISOString() }, ...prev].slice(0, 100));
      // Push notification when app is in background
      if (document.hidden && NOTIFY_EVENTS[event.type]) {
        const body = event.data?.text || event.data?.message || event.data?.action || event.type;
        showLocalNotification(NOTIFY_EVENTS[event.type], typeof body === "string" ? body.slice(0, 100) : event.type);
      }
    };
    sdk.events.on("*", handler);
    return () => sdk.events.off("*", handler);
  }, []);

  useEffect(() => {
    const h = () => setRoute(normalizePath(window.location.pathname));
    window.addEventListener("popstate", h);
    return () => window.removeEventListener("popstate", h);
  }, []);

  useEffect(() => {
    let off = false;
    async function check() {
      try { await sdk.system.health(); if (!off) setApiOnline(true); }
      catch { if (!off) setApiOnline(false); }
    }
    check(); const id = setInterval(check, 15000);
    return () => { off = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [prefs, ws] = await Promise.all([sdk.memory.preferences(), sdk.workspaces.list()]);
        const name = user?.display_name || (prefs.preferences || {}).name || localStorage.getItem("capos_username") || "";
        setUserName(name);
        if (name) localStorage.setItem("capos_username", name);
        setWorkspaces(ws.workspaces || []);
        setDefaultWsId(ws.default_id || null);
      } catch { setUserName(user?.display_name || ""); }
      setBooting(false);
    })();
  }, [user]);

  function navigate(path) {
    if (path !== normalizePath(window.location.pathname)) window.history.pushState({}, "", path);
    setRoute(path);
  }

  // Show login if auth is required and not authenticated
  if (authLoading) return <div style={{ minHeight: "100vh", background: "#0a0a0a" }} />;
  if (!isAuthenticated) return <Login onSuccess={() => { window.location.reload(); }} />;

  if (booting) return <div style={{ minHeight: "100vh", background: "#0a0a0a" }} />;
  if (!userName) return <Onboarding onComplete={name => { localStorage.setItem("capos_username", name); setUserName(name); }} />;

  const activeWs = workspaces.find(w => w.id === defaultWsId) || workspaces[0] || null;

  return (
    <div className="app-shell">
      {!apiOnline && <div className="connection-banner">Backend disconnected — retrying...</div>}
      <header className="app-header">
        <div className="app-header-left">
          <div className="app-logo"><div className="logo-icon" />CapOS</div>
          <nav className="app-nav">
            <button type="button" className={route === "/" ? "is-active" : ""} onClick={() => navigate("/")}>Workspace</button>
            <button type="button" className={route === "/editor" ? "is-active" : ""} onClick={() => navigate("/editor")}>Editor</button>
            <button type="button" className={route === "/workflows" ? "is-active" : ""} onClick={() => navigate("/workflows")}>Workflows</button>
            <button type="button" className={route === "/control-center" ? "is-active" : ""} onClick={() => navigate("/control-center")}>Control Center</button>
          </nav>
        </div>
        <div className="app-header-right">
          {activeWs && <div className="ws-selector" title={activeWs.path}><span className="ws-dot" style={{ background: activeWs.color || "#00ff88" }} /><span>{activeWs.name}</span></div>}
          <button className="notification-bell" onClick={() => setNcOpen(p => !p)} title="Activity feed" style={{background:"none",border:"none",cursor:"pointer",fontSize:14,padding:"2px 6px",position:"relative"}}>
            {"\uD83D\uDD14"}
            {ncEvents.length > 0 && <span style={{position:"absolute",top:0,right:0,width:6,height:6,borderRadius:"50%",background:"var(--accent)"}} />}
          </button>
          <div className={`dot ${apiOnline ? "dot-success" : "dot-error"}`} />
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#888", cursor: "pointer" }} onClick={logout} title="Logout">
            <div style={{ width: 22, height: 22, borderRadius: 6, background: "#1e1e2e", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 600, color: "#00ff88" }}>
              {userName.charAt(0).toUpperCase()}
            </div>
            <span>{userName}</span>
            {user?.role && <span style={{ fontSize: 9, opacity: 0.5 }}>{user.role}</span>}
          </div>
        </div>
      </header>
      <main className="app-main">
        {route === "/control-center" ? <ControlCenter /> : route === "/workflows" ? <WorkflowEditor /> : route === "/editor" ? <EditorPage wsId={defaultWsId} workspaces={workspaces} /> : <Workspace activeWorkspace={activeWs} userName={userName} />}
      </main>
      <NotificationCenter events={ncEvents} isOpen={ncOpen} onClose={() => setNcOpen(false)} />
      <InstallPrompt />
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AuthenticatedApp />
    </AuthProvider>
  );
}
