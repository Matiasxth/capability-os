import React, { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import sdk from "../sdk";

export default function Login() {
  const { login } = useAuth();

  const [mode, setMode] = useState("loading"); // "loading" | "login" | "setup"
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [focusedField, setFocusedField] = useState(null);

  // Check if owner exists to determine mode
  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const data = await sdk.auth.status();
        if (!cancelled) {
          setMode(data.owner_exists ? "login" : "setup");
        }
      } catch {
        // If endpoint unavailable, default to login
        if (!cancelled) setMode("login");
      }
    }
    check();
    return () => { cancelled = true; };
  }, []);

  async function handleLogin(e) {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setError("");
    setBusy(true);
    try {
      await login(username.trim(), password);
      window.location.replace("/");
    } catch (err) {
      setError(err.message || "Login failed");
    }
    setBusy(false);
  }

  async function handleSetup(e) {
    e.preventDefault();
    if (!username.trim() || !password || !displayName.trim()) return;
    setError("");
    setBusy(true);
    try {
      await sdk.auth.setup(username.trim(), password, displayName.trim());
      // Auto-login after setup
      await login(username.trim(), password);
      window.location.replace("/");
    } catch (err) {
      setError(err.message || "Setup failed");
    }
    setBusy(false);
  }

  const isSetup = mode === "setup";
  const canSubmit = isSetup
    ? !!(username.trim() && password && displayName.trim())
    : !!(username.trim() && password);

  // ── Styles ──
  const s = {
    wrap: {
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "var(--bg-root)",
      backgroundImage:
        "radial-gradient(ellipse at 30% 20%, rgba(0,240,255,0.06) 0%, transparent 50%), " +
        "radial-gradient(ellipse at 70% 80%, rgba(255,45,111,0.04) 0%, transparent 50%)",
      fontFamily: "var(--font-sans)",
    },
    card: {
      maxWidth: 400,
      width: "100%",
      padding: 32,
      margin: "0 16px",
      background: "var(--bg-surface)",
      border: "1px solid var(--border)",
      borderRadius: 14,
      boxShadow: "0 8px 40px rgba(0,0,0,0.5), 0 0 1px rgba(0,240,255,0.1)",
      animation: "login-in .5s cubic-bezier(0.16,1,0.3,1)",
    },
    logoRow: {
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      gap: 10,
      marginBottom: 24,
    },
    logoBox: {
      width: 32,
      height: 32,
      borderRadius: 8,
      background: "linear-gradient(135deg, #00f0ff, #7b2dff)",
      boxShadow: "0 0 20px rgba(0,240,255,0.25)",
      flexShrink: 0,
    },
    logoText: {
      fontSize: 18,
      fontWeight: 800,
      letterSpacing: 2,
      background: "linear-gradient(90deg, #00f0ff, #7b2dff)",
      WebkitBackgroundClip: "text",
      WebkitTextFillColor: "transparent",
    },
    title: {
      fontSize: 20,
      fontWeight: 300,
      color: "var(--text)",
      textAlign: "center",
      margin: "0 0 20px 0",
      letterSpacing: "-0.01em",
    },
    label: {
      display: "block",
      fontSize: 11,
      fontWeight: 600,
      color: "var(--text-dim)",
      marginBottom: 6,
      letterSpacing: "0.04em",
      textTransform: "uppercase",
    },
    input: (field) => ({
      width: "100%",
      height: 44,
      fontSize: 14,
      fontFamily: "inherit",
      background: "var(--bg-input, var(--bg-root))",
      border: `1px solid ${focusedField === field ? "var(--accent)" : "var(--border)"}`,
      borderRadius: 8,
      color: "var(--text)",
      padding: "0 14px",
      outline: "none",
      transition: "all .2s",
      boxSizing: "border-box",
      boxShadow: focusedField === field ? "0 0 10px rgba(0,240,255,0.1)" : "none",
    }),
    fieldGroup: {
      marginBottom: 14,
    },
    btn: {
      width: "100%",
      height: 46,
      fontSize: 14,
      fontWeight: 700,
      fontFamily: "inherit",
      letterSpacing: 1,
      textTransform: "uppercase",
      background: canSubmit
        ? "linear-gradient(135deg, #00f0ff, #00c8dd)"
        : "rgba(20,20,30,0.6)",
      color: canSubmit ? "#06060e" : "#444",
      border: canSubmit
        ? "1px solid var(--accent)"
        : "1px solid rgba(255,255,255,0.06)",
      borderRadius: 10,
      cursor: canSubmit ? "pointer" : "not-allowed",
      transition: "all .2s",
      boxShadow: canSubmit ? "0 0 20px rgba(0,240,255,0.2)" : "none",
      marginTop: 6,
    },
    error: {
      fontSize: 12,
      color: "var(--error)",
      background: "var(--error-dim, rgba(255,45,111,0.08))",
      border: "1px solid rgba(255,45,111,0.2)",
      borderRadius: 8,
      padding: "10px 14px",
      marginBottom: 14,
      textAlign: "center",
    },
    hbar: {
      height: 1,
      width: "60%",
      background:
        "linear-gradient(90deg, transparent, rgba(0,240,255,0.3), rgba(123,45,223,0.3), transparent)",
      margin: "0 auto 20px",
    },
    modeHint: {
      fontSize: 11,
      color: "var(--text-muted, #5a6080)",
      textAlign: "center",
      marginTop: 16,
    },
  };

  // Loading state
  if (mode === "loading") {
    return (
      <div style={s.wrap}>
        <div style={{ ...s.card, textAlign: "center", padding: 48 }}>
          <div style={s.logoRow}>
            <div style={s.logoBox} />
            <span style={s.logoText}>CAPABILITY OS</span>
          </div>
          <div style={{ color: "var(--text-dim)", fontSize: 13 }}>Loading...</div>
        </div>
        <style>{`@keyframes login-in{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}`}</style>
      </div>
    );
  }

  return (
    <div style={s.wrap}>
      <div style={s.card}>
        {/* Logo */}
        <div style={s.logoRow}>
          <div style={s.logoBox} />
          <span style={s.logoText}>CAPABILITY OS</span>
        </div>
        <div style={s.hbar} />

        {/* Title */}
        <h1 style={s.title}>
          {isSetup ? "Create Owner Account" : "Log In"}
        </h1>

        {/* Error */}
        {error && <div style={s.error}>{error}</div>}

        {/* Form */}
        <form onSubmit={isSetup ? handleSetup : handleLogin}>
          {isSetup && (
            <div style={s.fieldGroup}>
              <label style={s.label}>Display Name</label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                onFocus={() => setFocusedField("displayName")}
                onBlur={() => setFocusedField(null)}
                placeholder="Your name"
                autoFocus
                style={s.input("displayName")}
              />
            </div>
          )}

          <div style={s.fieldGroup}>
            <label style={s.label}>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onFocus={() => setFocusedField("username")}
              onBlur={() => setFocusedField(null)}
              placeholder="username"
              autoFocus={!isSetup}
              autoComplete="username"
              style={s.input("username")}
            />
          </div>

          <div style={s.fieldGroup}>
            <label style={s.label}>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onFocus={() => setFocusedField("password")}
              onBlur={() => setFocusedField(null)}
              placeholder="********"
              autoComplete={isSetup ? "new-password" : "current-password"}
              style={s.input("password")}
            />
          </div>

          <button type="submit" disabled={!canSubmit || busy} style={s.btn}>
            {busy ? "..." : isSetup ? "Create Account" : "Log In"}
          </button>
        </form>

        {/* Mode hint */}
        <div style={s.modeHint}>
          {isSetup
            ? "First time? Create the owner account to get started."
            : "Enter your credentials to access CapabilityOS."}
        </div>
      </div>

      <style>{`@keyframes login-in{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}`}</style>
    </div>
  );
}
