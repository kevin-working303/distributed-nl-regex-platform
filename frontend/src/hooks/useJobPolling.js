import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";

const TERMINAL = new Set(["SUCCESS", "FAILED", "CANCELLED"]);

// Polls a job every `intervalMs` until it reaches a terminal state.
export function useJobPolling(jobId, intervalMs = 1500) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const timer = useRef(null);

  useEffect(() => {
    if (!jobId) return;
    let active = true;

    const tick = async () => {
      try {
        const data = await api.getJob(jobId);
        if (!active) return;
        setJob(data);
        if (!TERMINAL.has(data.status)) {
          timer.current = setTimeout(tick, intervalMs);
        }
      } catch (err) {
        if (active) setError(err.message);
      }
    };
    tick();

    return () => {
      active = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [jobId, intervalMs]);

  return { job, error };
}
