import { useCallback, useState } from "react";
import sdk from "../sdk";

/**
 * Hook for streaming capability execution events via SSE.
 * Returns real-time step progress as events arrive.
 */
export function useExecutionStream() {
  const [events, setEvents] = useState([]);
  const [status, setStatus] = useState("idle"); // idle | running | done | error
  const [result, setResult] = useState(null);

  const startExecution = useCallback(async (capabilityId, inputs) => {
    setEvents([]);
    setResult(null);
    setStatus("running");
    try {
      for await (const event of sdk.capabilities.streamExecution(capabilityId, inputs)) {
        if (event.done) {
          setResult(event.result);
          setStatus(event.result?.status === "error" ? "error" : "done");
          return event.result;
        }
        if (event.event === "error") {
          setStatus("error");
          return null;
        }
        setEvents((prev) => [...prev, event]);
      }
    } catch (err) {
      setStatus("error");
      return null;
    }
  }, []);

  const reset = useCallback(() => {
    setEvents([]);
    setStatus("idle");
    setResult(null);
  }, []);

  return { events, status, result, startExecution, reset };
}
