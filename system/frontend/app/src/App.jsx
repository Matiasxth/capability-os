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
  const [userMenuOpen, setUserMenuOpen] = useState(false);

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
          <div style={{ position: "relative" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#888", cursor: "pointer" }} onClick={() => setUserMenuOpen(p => !p)}>
              <div style={{ width: 22, height: 22, borderRadius: 6, background: "#1e1e2e", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 600, color: "#00ff88" }}>
                {userName.charAt(0).toUpperCase()}
              </div>
              <span>{userName}</span>
              {user?.role && <span style={{ fontSize: 9, opacity: 0.5 }}>{user.role}</span>}
            </div>
            {userMenuOpen && <>
              <div style={{ position: "fixed", inset: 0, zIndex: 998 }} onClick={() => setUserMenuOpen(false)} />
              <div style={{ position: "absolute", top: "100%", right: 0, marginTop: 6, background: "var(--bg-elevated, #1a1a2e)", border: "1px solid var(--border, #333)", borderRadius: 8, padding: 4, minWidth: 160, zIndex: 999, boxShadow: "0 8px 24px rgba(0,0,0,0.5)" }}>
                <div style={{ padding: "8px 12px", fontSize: 11, color: "var(--text-dim, #888)", borderBottom: "1px solid var(--border, #333)" }}>
                  <div style={{ fontWeight: 600, color: "var(--text, #eee)" }}>{userName}</div>
                  <div style={{ marginTop: 2 }}>{user?.role || "user"}</div>
                </div>
                <button onClick={() => { setUserMenuOpen(false); logout(); }} style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", padding: "8px 12px", fontSize: 11, background: "none", border: "none", color: "var(--error, #ff4444)", cursor: "pointer", borderRadius: 4, textAlign: "left" }} onMouseEnter={e => e.target.style.background = "rgba(255,68,68,0.1)"} onMouseLeave={e => e.target.style.background = "none"}>
                  Logout
                </button>
              </div>
            </>}
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

class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false, error: null }; }
  static getDerivedStateFromError(error) { return { hasError: true, error }; }
  componentDidCatch(error, info) { console.error("App crash:", error, info); }
  render() {
    if (this.state.hasError) {
      return (<div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#0a0a0a", color: "#e0e0e0", fontFamily: "system-ui" }}>
        <div style={{ textAlign: "center", maxWidth: 400, padding: 32 }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>&#9888;</div>
          <h2 style={{ color: "#ff4444", margin: "0 0 12px" }}>Something went wrong</h2>
          <p style={{ fontSize: 13, color: "#888", marginBottom: 20 }}>{this.state.error?.message || "An unexpected error occurred"}</p>
          <button onClick={() => window.location.reload()} style={{ padding: "10px 24px", fontSize: 13, fontWeight: 600, background: "linear-gradient(135deg, #00f0ff, #00c8dd)", color: "#06060e", border: "none", borderRadius: 8, cursor: "pointer" }}>Reload App</button>
        </div>
      </div>);
    }
    return this.props.children;
  }
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <AuthenticatedApp />
      </AuthProvider>
    </ErrorBoundary>
  );
}
