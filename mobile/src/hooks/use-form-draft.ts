import AsyncStorage from "@react-native-async-storage/async-storage";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/auth/auth-context";

// Store only the signed-in owner's draft. Serialize writes so clearing after
// a successful submission cannot be undone by an earlier save.
export function useFormDraft<T extends object>(scope: string, initial: T) {
  const { user } = useAuth();
  const key = user?.id ? `form-draft:v1:${user.id}:${scope}` : null;
  const initialRef = useRef(initial);
  const current = useRef(initial);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const [state, setState] = useState({ key: null as string | null, value: initial, stored: false });
  const [error, setError] = useState("");
  const ready = Boolean(key && state.key === key);
  useEffect(() => {
    let active = true;
    setError("");
    if (!key) return;
    void queue.current.then(() => AsyncStorage.getItem(key)).then(raw => {
      if (!active) return;
      let value = initialRef.current;
      if (raw) {
        try { value = { ...value, ...JSON.parse(raw) }; } catch { /* Ignore malformed local drafts. */ }
      }
      current.current = value;
      setState({ key, value, stored: Boolean(raw) });
    }).catch(() => {
      if (active) setError("작성 내용을 복원하지 못했습니다. 다시 열어 주세요.");
    });
    return () => { active = false; };
  }, [key]);
  const update = useCallback(<K extends keyof T>(field: K, next: T[K] | ((value: T[K]) => T[K])) => {
    if (!ready || !key) return;
    const value = { ...current.current, [field]: typeof next === "function"
      ? (next as (value: T[K]) => T[K])(current.current[field]) : next };
    current.current = value;
    setState({ key, value, stored: true });
    queue.current = queue.current.catch(() => undefined).then(() => AsyncStorage.setItem(key, JSON.stringify(value)));
    void queue.current.catch(() => setError("초안을 보관하지 못했습니다. 앱을 종료하기 전에 다시 확인해 주세요."));
  }, [key, ready]);
  const clear = useCallback(async () => {
    if (!key) return;
    queue.current = queue.current.catch(() => undefined).then(() => AsyncStorage.removeItem(key));
    await queue.current;
    current.current = initialRef.current;
    setState({ key, value: initialRef.current, stored: false });
  }, [key]);
  return { value: ready ? state.value : initialRef.current, ready, hasDraft: ready && state.stored, update, clear, error };
}
