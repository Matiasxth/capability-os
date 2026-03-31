import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import sdk from "../sdk";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => sdk.session.getToken());
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Validate token on mount
  useEffect(() => {
    let cancelled = false;
    async function validate() {
      const stored = sdk.session.getToken();
      if (!stored) {
        setLoading(false);
        return;
      }
      try {
        const data = await sdk.auth.me();
        if (!cancelled) {
          setUser(data.user || data);
          setToken(stored);
        }
      } catch {
        sdk.session.clearToken();
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
    const data = await sdk.auth.login(username, password);
    const tk = data.access_token || data.token;
    sdk.session.setToken(tk);
    setToken(tk);
    setUser(data.user || null);
    return data;
  }, []);

  const logout = useCallback(() => {
    sdk.session.clearToken();
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
