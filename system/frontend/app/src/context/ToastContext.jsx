import React, { createContext, useContext } from "react";
import { useToast } from "../hooks/useToast";
import ToastContainer from "../components/ToastContainer";

const ToastContext = createContext();

export function ToastProvider({ children }) {
  const { toasts, addToast, removeToast } = useToast();

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={removeToast} />
    </ToastContext.Provider>
  );
}

export const useGlobalToast = () => useContext(ToastContext);
