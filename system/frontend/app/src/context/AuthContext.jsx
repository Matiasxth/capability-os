import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const API = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

function authHeaders(token) {
  const h = { "Content-Type": "application/json" };
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("capos_token") || null);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Validate token on mount
  useEffect(() => {
    let cancelled = false;
    async function validate() {
      const stored = localStorage.getItem("capos_token");
      if (!stored) {
        setLoading(false);
        return;
      }
      try {
        const res = await fetch(`${API}/auth/me`, { headers: authHeaders(stored) });
        if (!res.ok) throw new Error("invalid");
        const data = await res.json();
        if (!cancelled) {
          setUser(data.user || data);
          setToken(stored);
        }
      } catch {
        localStorage.removeItem("capos_token");
        if (!cancelled) {
          setToken(null);
          setUser(null);
        }
      }
      if (!cancelled) setLoading(false);
    }
    validate();
    return () => { cancelled = true; };
  }, []);

  const login = useCallback(async (username, password) => {
    const res = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || data.error_message || "Login failed");
    }
    const tk = data.access_token || data.token;
    localStorage.setItem("capos_token", tk);
    setToken(tk);
    setUser(data.user || null);
    return data;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("capos_token");
    setToken(null);
    setUser(null);
    window.location.replace("/login");
  }, []);

  const isAuthenticated = !!token && !!user;
  const isOwner = !!(user && user.role === "owner");
  const isAdmin = !!(user && (user.role === "owner" || user.role === "admin"));

  const value = useMemo(() => ({
    user,
    token,
    login,
    logout,
    loading,
    isAuthenticated,
    isOwner,
    isAdmin,
  }), [user, token, login, logout, loading, isAuthenticated, isOwner, isAdmin]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
