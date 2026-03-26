import React, { useEffect, useMemo, useState } from "react";
import {
  executeCapability,
  getExecution,
  getExecutionEvents,
  getSystemStatus,
  listCapabilities,
  planIntent
} from "../api";
import ExecutionPanel from "../components/ExecutionPanel";
import HeaderStatus from "../components/HeaderStatus";
import InspectorPanel from "../components/InspectorPanel";
import IntentBar from "../components/IntentBar";
import PlanPanel from "../components/PlanPanel";
import { useWorkspaceState } from "../state/useWorkspaceState";

const TEMPLATE_REGEX = /^\{\{([a-zA-Z0-9_.]+)\}\}$/;

function resolveTemplatePath(path, context) {
  const segments = path.split(".");
  const root = segments[0];
  if (!["inputs", "state", "steps", "runtime"].includes(root)) {
    throw new Error(`Template source '${root}' is not allowed.`);
  }

  let node = context[root];
  for (let index = 1; index < segments.length; index += 1) {
    const segment = segments[index];
    if (node === null || typeof node !== "object" || !(segment in node)) {
      throw new Error(`Template reference '{{${path}}}' could not be resolved.`);
    }
    node = node[segment];
  }
  return node;
}

function resolveTemplates(value, context) {
  if (typeof value === "string") {
    const match = value.match(TEMPLATE_REGEX);
    if (!match) {
      return value;
    }
    return resolveTemplatePath(match[1], context);
  }
  if (Array.isArray(value)) {
    return value.map((item) => resolveTemplates(item, context));
  }
  if (value && typeof value === "object") {
    const output = {};
    for (const [key, item] of Object.entries(value)) {
      output[key] = resolveTemplates(item, context);
    }
    return output;
  }
  return value;
}

export default function Workspace() {
  const {
    intent,
    setIntent,
    plan,
    setPlan,
    planValidationErrors,
    setPlanValidationErrors,
    execution,
    setExecution,
    logs,
    setLogs,
    selectedStepId,
    setSelectedStepId
  } = useWorkspaceState();

  const [status, setStatus] = useState(null);
  const [capabilities, setCapabilities] = useState([]);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [runningPlan, setRunningPlan] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const capabilitiesById = useMemo(() => {
    const map = {};
    for (const item of capabilities) {
      map[item.id] = item;
    }
    return map;
  }, [capabilities]);

  async function refreshCapabilities() {
    const response = await listCapabilities();
    setCapabilities(response.capabilities || []);
  }

  async function refreshStatus() {
    const response = await getSystemStatus();
    setStatus(response);
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setErrorMessage("");
        await Promise.all([refreshCapabilities(), refreshStatus()]);
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(error.message || "Failed to load workspace data.");
        }
      }
    }
    load();

    const timer = setInterval(() => {
      refreshStatus().catch(() => null);
    }, 4000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  async function handleGeneratePlan() {
    setLoadingPlan(true);
    setErrorMessage("");
    try {
      const response = await planIntent(intent);
      setPlan(response);
      setPlanValidationErrors(Array.isArray(response.errors) ? response.errors : []);
      const firstStepId = Array.isArray(response.steps) && response.steps.length > 0 ? response.steps[0].step_id : "";
      setSelectedStepId(firstStepId);
    } catch (error) {
      const apiError = error.payload || {};
      setErrorMessage(apiError.error_message || error.message || "Plan generation failed.");
    } finally {
      setLoadingPlan(false);
    }
  }

  function updateStep(stepId, patch) {
    if (!plan || !Array.isArray(plan.steps)) {
      return;
    }
    const nextSteps = plan.steps.map((step) => {
      if (step.step_id !== stepId) {
        return step;
      }
      return { ...step, ...patch };
    });
    setPlan({ ...plan, steps: nextSteps });
  }

  function deleteStep(stepId) {
    if (!plan || !Array.isArray(plan.steps)) {
      return;
    }
    const nextSteps = plan.steps.filter((step) => step.step_id !== stepId);
    setPlan({ ...plan, steps: nextSteps });
    if (selectedStepId === stepId) {
      setSelectedStepId(nextSteps.length > 0 ? nextSteps[0].step_id : "");
    }
  }

  function moveStep(stepId, direction) {
    if (!plan || !Array.isArray(plan.steps)) {
      return;
    }
    const index = plan.steps.findIndex((step) => step.step_id === stepId);
    if (index < 0) {
      return;
    }
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= plan.steps.length) {
      return;
    }
    const nextSteps = [...plan.steps];
    const [item] = nextSteps.splice(index, 1);
    nextSteps.splice(targetIndex, 0, item);
    setPlan({ ...plan, steps: nextSteps });
  }

  async function handleRunPlan() {
    if (!plan || !Array.isArray(plan.steps) || plan.steps.length === 0) {
      return;
    }
    setRunningPlan(true);
    setErrorMessage("");
    setLogs([]);

    const startedAt = new Date().toISOString();
    const stepRuns = [];
    const aggregateLogs = [];
    const context = {
      inputs: {},
      state: {},
      steps: {},
      runtime: {}
    };

    let statusValue = "running";
    let failedStep = null;
    let errorCode = null;
    let errorMessageValue = null;
    let finalOutput = {};

    setExecution({
      status: "running",
      current_step: plan.steps[0].step_id,
      started_at: startedAt,
      ended_at: null,
      duration_ms: 0,
      failed_step: null,
      error_code: null,
      error_message: null,
      final_output: {},
      step_runs: []
    });

    for (const step of plan.steps) {
      const runEntry = {
        step_id: step.step_id,
        capability: step.capability,
        status: "running",
        execution_id: null,
        final_output: {},
        error_code: null,
        error_message: null
      };
      stepRuns.push(runEntry);
      setExecution((previous) => ({
        ...previous,
        status: "running",
        current_step: step.step_id,
        step_runs: [...stepRuns]
      }));

      try {
        const resolvedInputs = resolveTemplates(step.inputs || {}, context);
        const executeResponse = await executeCapability(step.capability, resolvedInputs);
        runEntry.execution_id = executeResponse.execution_id || null;
        runEntry.status = executeResponse.status;
        runEntry.final_output = executeResponse.final_output || {};
        runEntry.error_code = executeResponse.error_code || null;
        runEntry.error_message = executeResponse.error_message || null;

        let latestExecution = executeResponse;
        if (executeResponse.execution_id) {
          latestExecution = await getExecution(executeResponse.execution_id);
          const eventPayload = await getExecutionEvents(executeResponse.execution_id);
          const events = Array.isArray(eventPayload.events) ? eventPayload.events : [];
          aggregateLogs.push(...events.map((event) => ({ ...event, step_id: step.step_id })));
          setLogs([...aggregateLogs]);
        } else {
          const runtimeLogs = Array.isArray(executeResponse.runtime?.logs) ? executeResponse.runtime.logs : [];
          aggregateLogs.push(...runtimeLogs.map((event) => ({ ...event, step_id: step.step_id })));
          setLogs([...aggregateLogs]);
        }

        context.steps[step.step_id] = { outputs: latestExecution.final_output || {} };
        Object.assign(context.state, latestExecution.final_output || {});
        finalOutput = latestExecution.final_output || {};

        if (executeResponse.status !== "success") {
          statusValue = "error";
          failedStep = step.step_id;
          errorCode = executeResponse.error_code || "execution_error";
          errorMessageValue = executeResponse.error_message || `Step '${step.step_id}' failed.`;
          runEntry.status = "error";
          break;
        }
      } catch (error) {
        const apiError = error.payload || {};
        statusValue = "error";
        failedStep = step.step_id;
        errorCode = apiError.error_code || "execution_error";
        errorMessageValue = apiError.error_message || error.message || `Step '${step.step_id}' failed.`;
        runEntry.status = "error";
        runEntry.error_code = errorCode;
        runEntry.error_message = errorMessageValue;
        break;
      }

      setExecution((previous) => ({
        ...previous,
        current_step: step.step_id,
        step_runs: [...stepRuns]
      }));
    }

    const endedAt = new Date().toISOString();
    const durationMs = new Date(endedAt).getTime() - new Date(startedAt).getTime();
    if (statusValue !== "error") {
      statusValue = "success";
    }
    const finalExecution = {
      status: statusValue,
      current_step: failedStep || "",
      started_at: startedAt,
      ended_at: endedAt,
      duration_ms: durationMs,
      failed_step: failedStep,
      error_code: errorCode,
      error_message: errorMessageValue,
      final_output: finalOutput,
      step_runs: [...stepRuns]
    };
    setExecution(finalExecution);
    if (errorMessageValue) {
      setErrorMessage(errorMessageValue);
    }
    setRunningPlan(false);
    refreshStatus().catch(() => null);
  }

  return (
    <div className="workspace-root">
      <HeaderStatus status={status} />
      <IntentBar
        intent={intent}
        onIntentChange={setIntent}
        onSubmit={handleGeneratePlan}
        loading={loadingPlan}
      />
      {errorMessage && <p className="error-banner">{errorMessage}</p>}
      <div className="workspace-grid">
        <PlanPanel
          plan={plan}
          capabilitiesById={capabilitiesById}
          selectedStepId={selectedStepId}
          onSelectStep={setSelectedStepId}
          onUpdateStep={updateStep}
          onDeleteStep={deleteStep}
          onMoveStep={moveStep}
          onRunPlan={handleRunPlan}
          running={runningPlan}
          validationErrors={planValidationErrors}
        />
        <ExecutionPanel
          execution={execution}
          logs={logs}
          selectedStepId={selectedStepId}
          onSelectStep={setSelectedStepId}
        />
        <InspectorPanel execution={execution} selectedStepId={selectedStepId} />
      </div>
    </div>
  );
}
