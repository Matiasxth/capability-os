import React, { useEffect, useMemo, useState } from "react";
import {
  disableIntegration,
  enableIntegration,
  executeCapability,
  getCapability,
  getExecution,
  getExecutionEvents,
  getIntegration,
  interpretText,
  listCapabilities,
  listIntegrations,
  validateIntegration
} from "../api";

const VISIBLE_STATUS_BY_INTERNAL = {
  available: "listo",
  ready: "listo",
  not_configured: "no configurado",
  preparing: "limitado",
  running: "ejecutando",
  error: "error",
  experimental: "experimental",
  disabled: "deshabilitado"
};

function mapVisibleStatus(internalStatus) {
  return VISIBLE_STATUS_BY_INTERNAL[internalStatus] || internalStatus || "no configurado";
}

function parseInputValue(type, rawValue) {
  if (type === "integer") {
    return Number.parseInt(rawValue, 10);
  }
  if (type === "number") {
    return Number(rawValue);
  }
  if (type === "boolean") {
    return Boolean(rawValue);
  }
  if (type === "object" || type === "array") {
    return JSON.parse(rawValue);
  }
  return rawValue;
}

function buildInputs(capability, rawInputs) {
  const parsed = {};
  for (const [field, contract] of Object.entries(capability.inputs || {})) {
    const rawValue = rawInputs[field];
    const isMissing = rawValue === undefined || rawValue === null || rawValue === "";
    if (isMissing && contract.required !== true) {
      continue;
    }
    if (isMissing && contract.required === true) {
      throw new Error(`El campo '${field}' es obligatorio.`);
    }
    parsed[field] = parseInputValue(contract.type, rawValue);
  }
  return parsed;
}

export default function AdvancedPanel() {
  const [capabilities, setCapabilities] = useState([]);
  const [selectedCapabilityId, setSelectedCapabilityId] = useState("");
  const [selectedCapability, setSelectedCapability] = useState(null);
  const [rawInputs, setRawInputs] = useState({});
  const [execution, setExecution] = useState(null);
  const [events, setEvents] = useState([]);
  const [integrations, setIntegrations] = useState([]);
  const [selectedIntegrationId, setSelectedIntegrationId] = useState("");
  const [selectedIntegration, setSelectedIntegration] = useState(null);
  const [loadingCapabilities, setLoadingCapabilities] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadingIntegrations, setLoadingIntegrations] = useState(true);
  const [loadingIntegrationDetail, setLoadingIntegrationDetail] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [interpreting, setInterpreting] = useState(false);
  const [integrationActionRunning, setIntegrationActionRunning] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [nlText, setNlText] = useState("");
  const [suggestionResponse, setSuggestionResponse] = useState(null);

  useEffect(() => {
    async function loadInitialData() {
      setLoadingCapabilities(true);
      setLoadingIntegrations(true);
      setErrorMessage("");
      try {
        const [capabilityResponse, integrationResponse] = await Promise.all([
          listCapabilities(),
          listIntegrations()
        ]);
        setCapabilities(capabilityResponse.capabilities || []);
        setIntegrations(integrationResponse.integrations || []);
      } catch (error) {
        setErrorMessage(error.message || "No se pudieron cargar los datos iniciales.");
      } finally {
        setLoadingCapabilities(false);
        setLoadingIntegrations(false);
      }
    }

    loadInitialData();
  }, []);

  useEffect(() => {
    if (!selectedCapabilityId) {
      setSelectedCapability(null);
      setRawInputs({});
      return;
    }

    async function loadCapabilityDetail() {
      setLoadingDetail(true);
      setErrorMessage("");
      try {
        const response = await getCapability(selectedCapabilityId);
        const capability = response.capability;
        setSelectedCapability(capability);
        const nextInputs = {};
        for (const [field, contract] of Object.entries(capability.inputs || {})) {
          if (contract.type === "boolean") {
            nextInputs[field] = false;
          } else {
            nextInputs[field] = "";
          }
        }
        setRawInputs(nextInputs);
      } catch (error) {
        setErrorMessage(error.message || "No se pudo cargar el detalle.");
      } finally {
        setLoadingDetail(false);
      }
    }

    loadCapabilityDetail();
  }, [selectedCapabilityId]);

  useEffect(() => {
    if (!selectedIntegrationId) {
      setSelectedIntegration(null);
      return;
    }

    async function loadIntegrationDetail() {
      setLoadingIntegrationDetail(true);
      setErrorMessage("");
      try {
        const response = await getIntegration(selectedIntegrationId);
        setSelectedIntegration(response.integration || null);
      } catch (error) {
        setErrorMessage(error.message || "No se pudo cargar el detalle de integración.");
      } finally {
        setLoadingIntegrationDetail(false);
      }
    }

    loadIntegrationDetail();
  }, [selectedIntegrationId]);

  const groupedCapabilities = useMemo(() => {
    const grouped = {};
    for (const capability of capabilities) {
      if (!grouped[capability.domain]) {
        grouped[capability.domain] = [];
      }
      grouped[capability.domain].push(capability);
    }
    return grouped;
  }, [capabilities]);

  const suggestionType = suggestionResponse?.suggestion?.type || "unknown";
  const sequenceSteps =
    suggestionType === "sequence" && Array.isArray(suggestionResponse?.suggestion?.steps)
      ? suggestionResponse.suggestion.steps
      : [];
  const sequenceCapabilities = [...new Set(
    sequenceSteps
      .map((step) => step?.capability)
      .filter((capabilityId) => typeof capabilityId === "string" && capabilityId.length > 0)
  )];

  async function refreshExecution(executionId) {
    const [executionResponse, eventsResponse] = await Promise.all([
      getExecution(executionId),
      getExecutionEvents(executionId)
    ]);
    setExecution(executionResponse);
    setEvents(eventsResponse.events || []);
  }

  async function refreshIntegrations(selectedId = selectedIntegrationId) {
    const listResponse = await listIntegrations();
    const integrationItems = listResponse.integrations || [];
    setIntegrations(integrationItems);
    if (!selectedId) {
      return;
    }
    const detailResponse = await getIntegration(selectedId);
    setSelectedIntegration(detailResponse.integration || null);
  }

  async function handleIntegrationAction(action, integrationId) {
    setIntegrationActionRunning(true);
    setErrorMessage("");
    try {
      if (action === "validate") {
        await validateIntegration(integrationId);
      } else if (action === "enable") {
        await enableIntegration(integrationId);
      } else if (action === "disable") {
        await disableIntegration(integrationId);
      }
      await refreshIntegrations(integrationId);
      setSelectedIntegrationId(integrationId);
    } catch (error) {
      const apiError = error.payload || {};
      setErrorMessage(apiError.error_message || error.message || "Error en acción de integración.");
      await refreshIntegrations(integrationId);
    } finally {
      setIntegrationActionRunning(false);
    }
  }

  async function handleExecute(event) {
    event.preventDefault();
    if (!selectedCapability) {
      return;
    }

    setExecuting(true);
    setErrorMessage("");
    try {
      const parsedInputs = buildInputs(selectedCapability, rawInputs);
      const executeResponse = await executeCapability(selectedCapability.id, parsedInputs);
      setExecution(executeResponse);
      setEvents(executeResponse.runtime?.logs || []);

      if (executeResponse.execution_id) {
        await refreshExecution(executeResponse.execution_id);
      }
    } catch (error) {
      const apiError = error.payload || {};
      setErrorMessage(apiError.error_message || error.message || "Error al ejecutar capability.");
    } finally {
      setExecuting(false);
    }
  }

  async function handleInterpret(event) {
    event.preventDefault();
    setInterpreting(true);
    setErrorMessage("");
    try {
      const response = await interpretText(nlText);
      setSuggestionResponse(response);
      const suggestedCapability = response?.suggestion?.capability;
      if (response?.suggestion?.type === "capability" && typeof suggestedCapability === "string") {
        setSelectedCapabilityId(suggestedCapability);
      }
    } catch (error) {
      const apiError = error.payload || {};
      setErrorMessage(apiError.error_message || error.message || "Error al interpretar texto.");
    } finally {
      setInterpreting(false);
    }
  }

  async function handleConfirmSuggestion() {
    if (!suggestionResponse || suggestionResponse.suggest_only !== true) {
      return;
    }
    const suggestion = suggestionResponse.suggestion;
    if (!suggestion || suggestion.type !== "capability") {
      return;
    }

    setExecuting(true);
    setErrorMessage("");
    try {
      const executeResponse = await executeCapability(suggestion.capability, suggestion.inputs || {});
      setExecution(executeResponse);
      setEvents(executeResponse.runtime?.logs || []);
      if (executeResponse.execution_id) {
        await refreshExecution(executeResponse.execution_id);
      }
    } catch (error) {
      const apiError = error.payload || {};
      setErrorMessage(apiError.error_message || error.message || "Error al confirmar sugerencia.");
    } finally {
      setExecuting(false);
    }
  }

  const loginState =
    execution?.final_output?.login_state ||
    execution?.runtime?.final_output?.login_state ||
    null;

  function renderInputField(fieldName, fieldContract) {
    const value = rawInputs[fieldName];
    const required = fieldContract.required === true;
    const type = fieldContract.type;

    if (type === "boolean") {
      return (
        <label key={fieldName} className="field-row">
          <span>
            {fieldName} {required ? "*" : "(opcional)"}
          </span>
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(event) =>
              setRawInputs((previous) => ({ ...previous, [fieldName]: event.target.checked }))
            }
          />
        </label>
      );
    }

    if (type === "object" || type === "array") {
      return (
        <label key={fieldName} className="field-row">
          <span>
            {fieldName} {required ? "*" : "(opcional)"}
          </span>
          <textarea
            value={value}
            placeholder={fieldContract.description || "JSON"}
            onChange={(event) =>
              setRawInputs((previous) => ({ ...previous, [fieldName]: event.target.value }))
            }
          />
        </label>
      );
    }

    return (
      <label key={fieldName} className="field-row">
        <span>
          {fieldName} {required ? "*" : "(opcional)"}
        </span>
        <input
          type="text"
          value={value}
          placeholder={fieldContract.description || ""}
          onChange={(event) =>
            setRawInputs((previous) => ({ ...previous, [fieldName]: event.target.value }))
          }
        />
      </label>
    );
  }

  return (
    <main className="layout">
      <section className="panel">
        <h2>InterpretaciÃ³n NL</h2>
        <form onSubmit={handleInterpret} className="form-block">
          <label className="field-row">
            <span>Texto libre</span>
            <textarea
              value={nlText}
              placeholder="Ej: lee el archivo main.py"
              onChange={(event) => setNlText(event.target.value)}
            />
          </label>
          <button type="submit" disabled={interpreting}>
            {interpreting ? "Interpretando..." : "Interpretar"}
          </button>
        </form>
        {suggestionResponse && (
          <div className="suggestion-block">
            <p>
              <strong>Tipo de sugerencia:</strong> {suggestionType}
            </p>
            {suggestionType === "sequence" && (
              <>
                <p>Pasos detectados: {sequenceSteps.length}</p>
                <p>
                  Capabilities detectadas:{" "}
                  {sequenceCapabilities.length > 0 ? sequenceCapabilities.join(", ") : "-"}
                </p>
              </>
            )}
            <p>suggest_only: {String(suggestionResponse.suggest_only)}</p>
            <pre>{JSON.stringify(suggestionResponse.suggestion, null, 2)}</pre>
            {suggestionResponse.suggestion?.type === "capability" && (
              <button
                type="button"
                onClick={handleConfirmSuggestion}
                disabled={executing}
              >
                {executing ? "Ejecutando..." : "Confirmar y ejecutar sugerencia"}
              </button>
            )}
          </div>
        )}
        {errorMessage && <p className="error-text">{errorMessage}</p>}
      </section>

      <section className="panel">
        <h2>Capabilities</h2>
        {loadingCapabilities && <p>Cargando capabilities...</p>}
        {!loadingCapabilities &&
          Object.entries(groupedCapabilities).map(([domain, items]) => (
            <div key={domain} className="domain-block">
              <h3>{domain}</h3>
              <ul>
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={selectedCapabilityId === item.id ? "active-item" : ""}
                      onClick={() => setSelectedCapabilityId(item.id)}
                    >
                      <strong>{item.name}</strong>
                      <small>{item.id}</small>
                      <small>Estado visible: {mapVisibleStatus(item.status)}</small>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
      </section>

      <section className="panel">
        <h2>Integraciones</h2>
        {loadingIntegrations && <p>Cargando integraciones...</p>}
        {!loadingIntegrations && integrations.length === 0 && <p>No hay integraciones detectadas.</p>}
        {!loadingIntegrations && integrations.length > 0 && (
          <ul>
            {integrations.map((integration) => (
              <li key={integration.id}>
                <button
                  type="button"
                  className={selectedIntegrationId === integration.id ? "active-item" : ""}
                  onClick={() => setSelectedIntegrationId(integration.id)}
                >
                  <strong>{integration.name || integration.id}</strong>
                  <small>{integration.id}</small>
                  <small>type: {integration.type || "-"}</small>
                  <small>status: {integration.status || "-"}</small>
                </button>
              </li>
            ))}
          </ul>
        )}
        {loadingIntegrationDetail && <p>Cargando detalle de integración...</p>}
        {selectedIntegration && !loadingIntegrationDetail && (
          <div className="detail-block">
            <p><strong>{selectedIntegration.metadata?.name || selectedIntegration.id}</strong></p>
            <p>id: {selectedIntegration.id}</p>
            <p>type: {selectedIntegration.metadata?.type || selectedIntegration.manifest?.type || "-"}</p>
            <p>status: {selectedIntegration.status || "-"}</p>
            <p>validated: {String(selectedIntegration.validated)}</p>
            <p>error: {selectedIntegration.error || "-"}</p>
            <p>
              capabilities:{" "}
              {Array.isArray(selectedIntegration.capabilities) && selectedIntegration.capabilities.length > 0
                ? selectedIntegration.capabilities.join(", ")
                : "-"}
            </p>
            <div className="form-block">
              <button
                type="button"
                disabled={integrationActionRunning}
                onClick={() => handleIntegrationAction("validate", selectedIntegration.id)}
              >
                Validar
              </button>
              <button
                type="button"
                disabled={integrationActionRunning}
                onClick={() => handleIntegrationAction("enable", selectedIntegration.id)}
              >
                Habilitar
              </button>
              <button
                type="button"
                disabled={integrationActionRunning}
                onClick={() => handleIntegrationAction("disable", selectedIntegration.id)}
              >
                Deshabilitar
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Detalle / Inputs</h2>
        {loadingDetail && <p>Cargando detalle...</p>}
        {!selectedCapability && !loadingDetail && <p>Selecciona una capability.</p>}
        {selectedCapability && !loadingDetail && (
          <div className="detail-block">
            <p>
              <strong>{selectedCapability.name}</strong>
            </p>
            <p>ID: {selectedCapability.id}</p>
            <p>Dominio: {selectedCapability.domain}</p>
            <p>Tipo: {selectedCapability.type}</p>
            <p>{selectedCapability.description}</p>

            <form onSubmit={handleExecute} className="form-block">
              {Object.entries(selectedCapability.inputs || {}).map(([field, contract]) =>
                renderInputField(field, contract)
              )}
              <button type="submit" disabled={executing}>
                {executing ? "Ejecutando..." : "Ejecutar capability"}
              </button>
            </form>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Ejecución / Logs</h2>
        {!execution && <p>No hay ejecución todavía.</p>}
        {execution && (
          <div className="execution-block">
            <p>execution_id: {execution.execution_id}</p>
            <p>status: {execution.runtime?.status}</p>
            <p>current_step: {execution.runtime?.current_step || "-"}</p>
            <p>started_at: {execution.runtime?.started_at || "-"}</p>
            <p>ended_at: {execution.runtime?.ended_at || "-"}</p>
            <p>duration_ms: {execution.runtime?.duration_ms ?? 0}</p>
            <p>failed_step: {execution.runtime?.failed_step || "-"}</p>
            <p>error_code: {execution.runtime?.error_code || execution.error_code || "-"}</p>
            <p>error_message: {execution.runtime?.error_message || execution.error_message || "-"}</p>
            {loginState && <p>login_state: {loginState}</p>}
            <h3>final_output</h3>
            <pre>{JSON.stringify(execution.final_output || execution.runtime?.final_output || {}, null, 2)}</pre>
          </div>
        )}

        <h3>Eventos</h3>
        {events.length === 0 && <p>Sin eventos.</p>}
        {events.length > 0 && (
          <ul className="event-list">
            {events.map((event, index) => (
              <li key={`${event.timestamp}-${event.event}-${index}`}>
                <strong>{event.event}</strong> <small>{event.timestamp}</small>
                <pre>{JSON.stringify(event.payload || {}, null, 2)}</pre>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
