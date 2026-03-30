import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ThemeProvider } from "./context/ThemeContext";
import { ShortcutProvider } from "./context/ShortcutContext";
import { WebSocketProvider } from "./context/WebSocketContext";
import { ToastProvider } from "./context/ToastContext";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ThemeProvider>
      <ShortcutProvider>
        <WebSocketProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </WebSocketProvider>
      </ShortcutProvider>
    </ThemeProvider>
  </React.StrictMode>
);

// Unregister old service workers and clear cache to prevent stale UI
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => {
    for (const reg of regs) reg.unregister();
  });
  if ("caches" in window) {
    caches.keys().then((keys) => {
      for (const key of keys) caches.delete(key);
    });
  }
}
