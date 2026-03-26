import { useState } from "react";

export function useControlCenterState() {
  const [activeSection, setActiveSection] = useState("llm");
  const [settings, setSettings] = useState(null);
  const [health, setHealth] = useState(null);
  const [integrations, setIntegrations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [llmTestResult, setLlmTestResult] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  return {
    activeSection,
    setActiveSection,
    settings,
    setSettings,
    health,
    setHealth,
    integrations,
    setIntegrations,
    loading,
    setLoading,
    saving,
    setSaving,
    testingConnection,
    setTestingConnection,
    llmTestResult,
    setLlmTestResult,
    message,
    setMessage,
    error,
    setError
  };
}

