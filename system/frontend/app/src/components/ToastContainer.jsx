import React from "react";

export default function ToastContainer({ toasts, onDismiss }) {
  if (!toasts.length) return null;
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.type}`} onClick={() => onDismiss?.(t.id)} title="Click to dismiss">
          {t.text}
        </div>
      ))}
    </div>
  );
}
