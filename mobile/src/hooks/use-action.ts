import { useRef, useState } from "react";

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
      setError(
        cause instanceof Error
          ? cause.message
          : "처리하지 못했습니다. 다시 시도해 주세요.",
      );
    } finally {
      active.current = false;
      setBusy(false);
    }
  };
  return { busy, error, run };
}
