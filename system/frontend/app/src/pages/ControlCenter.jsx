import React, { useCallback, useEffect, useRef, useState } from "react";
import sdk from "../sdk";
import CCLayout from "../components/control-center/CCLayout";
import KPIBar from "../components/control-center/KPIBar";
import ToastContainer from "../components/ToastContainer";
import { useToast } from "../hooks/useToast";
import sections from "../components/control-center/sections";
import { SECTION_FOR_EVENT, EVENT_LABELS } from "../sdk/eventTypes";

export default function ControlCenter() {
  const [activeSection, setActiveSection] = useState("system");
  const [settings, setSettings] = useState(null);
  const [health, setHealth] = useState(null);
  const [integrations, setIntegrations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [testingConnection, setTestingConnection] = useState(false);
  const [llmTestResult, setLlmTestResult] = useState(null);
  const { toasts, addToast, removeToast } = useToast();

  function toast(t, ty = "success") { addToast(t, ty); }

  async function refreshAll() {
    const [sR, hR, iR] = await Promise.all([sdk.system.settings.get(), sdk.system.health(), sdk.integrations.list()]);
    setSettings(sR.settings || null);
    setHealth(hR);
    setIntegrations(iR.integrations || []);
  }

  async function act(fn, msg) {
    setSaving(true); setError(""); setMessage("");
    try { await fn(); if (msg) toast(msg); await refreshAll(); }
    catch (e) { setError(e.payload?.error_message || e.message || "Failed."); }
    finally { setSaving(false); }
  }

  // ── Initial load ──
  useEffect(() => {
    let off = false;
    (async () => {
      setLoading(true); setError("");
      try { await refreshAll(); }
      catch (e) { if (!off) setError(e.payload?.error_message || e.message || "Load failed."); }
      finally { if (!off) setLoading(false); }
    })();
    return () => { off = true; };
  }, []);

  // ── Event-driven updates via SDK event bus ──
  const [highlightSection, setHighlightSection] = useState(null);
  const [wsConnected, setWsConnected] = useState(sdk.events.isConnected());
  const highlightTimer = useRef(null);
  const activeSectionRef = useRef(activeSection);
  useEffect(() => { activeSectionRef.current = activeSection; }, [activeSection]);

  useEffect(() => {
    const handler = (event) => {
      if (!event || !event.type) return;
      const section = SECTION_FOR_EVENT[event.type];
      if (section) {
        toast((EVENT_LABELS[event.type] || event.type) + (event.data?.action ? " — " + event.data.action : ""), "info");
        if (section === activeSectionRef.current) refreshAll();
        setHighlightSection(section);
        if (highlightTimer.current) clearTimeout(highlightTimer.current);
        highlightTimer.current = setTimeout(() => setHighlightSection(null), 3000);
      }
      if (event.type === "error" && event.data?.message) toast("Error: " + event.data.message.slice(0, 80), "error");
    };
    sdk.events.on("*", handler);
    const unsubConn = sdk.events.onConnectionChange(setWsConnected);
    return () => { sdk.events.off("*", handler); unsubConn(); };
  }, []);

  // ── Derived values ──
  const bw = health?.browser_worker || {};
  const tr = bw.transport || {};
  const bwSt = bw.status || (tr.alive ? "ready" : tr.worker_failed ? "error" : "available");

  // ── Section props ──
  const sectionProps = {
    settings, setSettings, health, integrations, saving, setSaving,
    testingConnection, setTestingConnection, llmTestResult, setLlmTestResult,
    error, setError, bwSt, bw, toast, act, refreshAll,
  };

  const SectionComponent = sections[activeSection] || sections.system;

  return (<>
    <CCLayout activeSection={activeSection} onSelectSection={setActiveSection} wsConnected={wsConnected} highlightSection={highlightSection}>
      <KPIBar health={health} integrations={integrations} workspaceCount={0} />
      {message && <div className="status-banner success">{message}</div>}
      {error && <div className="status-banner error">{error}</div>}
      {loading
        ? <div style={{ display: "flex", flexDirection: "column", gap: 6 }}><div className="skeleton skeleton-block" /><div className="skeleton skeleton-block" /></div>
        : <SectionComponent {...sectionProps} />
      }
    </CCLayout>
    <ToastContainer toasts={toasts} onDismiss={removeToast} />
  </>);
}
