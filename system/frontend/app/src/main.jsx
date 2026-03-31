import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ThemeProvider } from "./context/ThemeContext";
import { ShortcutProvider } from "./context/ShortcutContext";
import { WebSocketProvider } from "./context/WebSocketContext";
import { ToastProvider } from "./context/ToastContext";
import { registerSW } from "./sdk/notifications";
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

// Register service worker for PWA + push notifications
registerSW();
