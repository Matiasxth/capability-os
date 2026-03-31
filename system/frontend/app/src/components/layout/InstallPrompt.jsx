import React, { useEffect, useState } from "react";
import { isInstalled } from "../../sdk/notifications";

/**
 * PWA install prompt banner.
 * Shows when the browser fires `beforeinstallprompt` and the app is not already installed.
 */
export default function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [dismissed, setDismissed] = useState(() => sessionStorage.getItem("capos_install_dismissed") === "1");

  useEffect(() => {
    if (isInstalled()) return;
    const handler = (e) => { e.preventDefault(); setDeferredPrompt(e); };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  if (!deferredPrompt || dismissed) return null;

  async function handleInstall() {
    deferredPrompt.prompt();
    const result = await deferredPrompt.userChoice;
    if (result.outcome === "accepted") setDeferredPrompt(null);
  }

  function handleDismiss() {
    setDismissed(true);
    sessionStorage.setItem("capos_install_dismissed", "1");
  }

  return (
    <div style={{
      position: "fixed", bottom: 16, left: "50%", transform: "translateX(-50%)", zIndex: 9999,
      display: "flex", alignItems: "center", gap: 12, padding: "10px 18px",
      background: "var(--bg-elevated)", border: "1px solid var(--accent)",
      borderRadius: 12, boxShadow: "0 4px 24px rgba(0,0,0,0.4)",
      fontSize: 12, color: "var(--text)", animation: "slideUp .3s ease",
    }}>
      <span style={{ fontSize: 18 }}>&#128241;</span>
      <span>Install CapOS as an app</span>
      <button className="btn-primary" style={{ height: 28, fontSize: 11, padding: "0 14px" }} onClick={handleInstall}>Install</button>
      <button style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 14, padding: 0 }} onClick={handleDismiss}>&times;</button>
      <style>{`@keyframes slideUp{from{opacity:0;transform:translateX(-50%) translateY(20px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}`}</style>
    </div>
  );
}
