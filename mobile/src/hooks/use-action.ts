import { useRef, useState } from "react";
import { userErrorMessage, errorDiagnostic } from "../../../shared/user-message";

export function useAction() {
  const active = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (action: () => Promise<unknown>) => {
    if (active.current) return;
    active.current = true;
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (cause) {
      console.warn("User action failed", errorDiagnostic(cause));
      setError(userErrorMessage(cause));
    } finally {
      active.current = false;
      setBusy(false);
    }
  };
  return { busy, error, run };
}
