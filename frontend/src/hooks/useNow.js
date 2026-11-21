import { useEffect, useState } from "react";

/** Hora actual que se renueva cada `intervalMs`, para que "hace X" no se congele. */
export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}
