import { useState } from "react";

export function useWorkspaceState() {
  const [intent, setIntent] = useState("");
  const [plan, setPlan] = useState(null);
  const [planValidationErrors, setPlanValidationErrors] = useState([]);
  const [execution, setExecution] = useState(null);
  const [logs, setLogs] = useState([]);
  const [selectedStepId, setSelectedStepId] = useState("");

  return {
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
  };
}
