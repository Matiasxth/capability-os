import React, { useEffect } from "react";
import {
  disableIntegration,
  enableIntegration,
  getSettings,
  getSystemHealth,
  listIntegrations,
  restartBrowserWorker,
  saveSettings,
  testLLMConnection,
  validateIntegration
} from "../api";
import SettingsSidebar from "../components/SettingsSidebar";
import BrowserSettings from "../components/settings/BrowserSettings";
import IntegrationsSettings from "../components/settings/IntegrationsSettings";
import LLMSettings from "../components/settings/LLMSettings";
import SystemHealth from "../components/settings/SystemHealth";
import WorkspaceSettings from "../components/settings/WorkspaceSettings";
import { useControlCenterState } from "../state/useControlCenterState";

export default function ControlCenter() {
  const {
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
  } = useControlCenterState();

  async function refreshAll() {
    const [settingsResponse, healthResponse, integrationsResponse] = await Promise.all([
      getSettings(),
      getSystemHealth(),
      listIntegrations()
    ]);
    setSettings(settingsResponse.settings || null);
    setHealth(healthResponse);
    setIntegrations(integrationsResponse.integrations || []);
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        await refreshAll();
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.payload?.error_message || loadError.message || "Failed to load control center.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSave(nextSettings = settings) {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await saveSettings(nextSettings);
      setSettings(response.settings || nextSettings);
      setMessage("Settings saved.");
      await refreshAll();
    } catch (saveError) {
      const payload = saveError.payload || {};
      const details = payload.details?.errors;
      const detailText = Array.isArray(details) && details.length > 0 ? ` (${details.join("; ")})` : "";
      setError((payload.error_message || saveError.message || "Failed to save settings.") + detailText);
    } finally {
      setSaving(false);
    }
  }

  async function handleTestLLM() {
    setTestingConnection(true);
    setError("");
    setMessage("");
    try {
      const response = await testLLMConnection();
      setLlmTestResult(response);
      if (response.status === "success") {
        setMessage("LLM connection successful.");
      } else {
        setError(response.error_message || "LLM connection failed.");
      }
      await refreshAll();
    } catch (testError) {
      const payload = testError.payload || {};
      setLlmTestResult({
        status: "error",
        error_message: payload.error_message || testError.message
      });
      setError(payload.error_message || testError.message || "LLM test failed.");
    } finally {
      setTestingConnection(false);
    }
  }

  async function handleRestartBrowser() {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await restartBrowserWorker();
      setMessage("Browser worker restarted.");
      await refreshAll();
    } catch (restartError) {
      const payload = restartError.payload || {};
      setError(payload.error_message || restartError.message || "Failed to restart browser worker.");
    } finally {
      setSaving(false);
    }
  }

  async function handleIntegrationAction(action, integrationId) {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      if (action === "validate") {
        await validateIntegration(integrationId);
      } else if (action === "enable") {
        await enableIntegration(integrationId);
      } else if (action === "disable") {
        await disableIntegration(integrationId);
      }
      setMessage(`Integration '${integrationId}' updated.`);
      await refreshAll();
    } catch (integrationError) {
      const payload = integrationError.payload || {};
      setError(payload.error_message || integrationError.message || "Integration action failed.");
    } finally {
      setSaving(false);
    }
  }

  function handleSettingsChange(nextSettings) {
    setSettings(nextSettings);
  }

  function renderSection() {
    if (!settings) {
      return (
        <section className="settings-section">
          <h3>Loading</h3>
          <p className="empty-block">{loading ? "Loading settings..." : "Settings unavailable."}</p>
        </section>
      );
    }
    if (activeSection === "llm") {
      return (
        <LLMSettings
          settings={settings}
          onChange={handleSettingsChange}
          onSave={() => handleSave(settings)}
          onTestConnection={handleTestLLM}
          saving={saving}
          testingConnection={testingConnection}
          testResult={llmTestResult}
        />
      );
    }
    if (activeSection === "browser") {
      return (
        <BrowserSettings
          browserHealth={health?.browser_worker}
          onRestart={handleRestartBrowser}
          restarting={saving}
        />
      );
    }
    if (activeSection === "integrations") {
      return (
        <IntegrationsSettings
          integrations={integrations}
          onValidate={(integrationId) => handleIntegrationAction("validate", integrationId)}
          onEnable={(integrationId) => handleIntegrationAction("enable", integrationId)}
          onDisable={(integrationId) => handleIntegrationAction("disable", integrationId)}
        />
      );
    }
    if (activeSection === "workspace") {
      return (
        <WorkspaceSettings
          settings={settings}
          onChange={handleSettingsChange}
          onSave={() => handleSave(settings)}
          saving={saving}
        />
      );
    }
    return <SystemHealth health={health} />;
  }

  return (
    <div className="control-center-root">
      <SettingsSidebar activeSection={activeSection} onSelectSection={setActiveSection} />
      <section className="control-center-content">
        <header className="control-center-header">
          <h1>System Control Center</h1>
          <p>Central configuration and runtime health monitoring.</p>
        </header>
        {message && <p className="status-banner success">{message}</p>}
        {error && <p className="status-banner error">{error}</p>}
        {renderSection()}
      </section>
    </div>
  );
}
