import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { useFocusEffect } from "expo-router";

/** Ignore stale responses and refresh when returning from a child screen. */
export function useResource<T>(
  fetcher: () => Promise<T>,
  initial: T,
  enabled = true,
  resourceKey = "",
) {
  const fetchRef = useRef(fetcher);
  useLayoutEffect(() => {
    fetchRef.current = fetcher;
  });
  const generation = useRef(0);
  const [data, setData] = useState(initial);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    const request = ++generation.current;
    setLoading(true);
    setError("");
    try {
      const value = await fetchRef.current();
      if (request === generation.current) setData(value);
    } catch (cause) {
      if (request === generation.current)
        setError(
          cause instanceof Error ? cause.message : "불러오지 못했습니다.",
        );
    } finally {
      if (request === generation.current) setLoading(false);
    }
  }, []);
  useFocusEffect(
    useCallback(() => {
      // Changing the resource key invalidates the focused screen's request.
      void resourceKey;
      if (enabled) void reload();
      return () => {
        generation.current += 1;
      };
    }, [reload, enabled, resourceKey]),
  );
  return { data, setData, loading, error, reload };
}
