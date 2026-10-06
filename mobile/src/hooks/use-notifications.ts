import AsyncStorage from "@react-native-async-storage/async-storage";
import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { useFocusEffect } from "expo-router";
import { useAuth } from "@/auth/auth-context";
import { boardsApi } from "@/api/boards";
import { userErrorMessage } from "../../../shared/user-message";

export type UserNotification = { id: number; is_read?: boolean; notification_type?: string; title?: string; message?: string; content?: string; target_route?: string; created_at?: string };
export const notificationVisible = (item: UserNotification, settings: { commentNotifications?: boolean; inquiryNotifications?: boolean }) =>
  item.notification_type === "post_commented" ? settings.commentNotifications !== false
    : item.notification_type === "inquiry_answered" ? settings.inquiryNotifications !== false : true;

export function useNotifications() {
  const { ready, isLoggedIn, user } = useAuth();
  const accountKey = isLoggedIn ? String(user?.id || user?.username || "account") : "";
  const accountRef = useRef(accountKey);
  useLayoutEffect(() => { accountRef.current = accountKey; }, [accountKey]);
  const generation = useRef(0);
  const [stored, setStored] = useState<{ account: string; items: UserNotification[] }>({ account: "", items: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    const request = ++generation.current;
    if (!accountKey) { setStored({ account: "", items: [] }); setLoading(false); return; }
    setLoading(true);
    setError("");
    try {
      const [items, rawSettings] = await Promise.all([boardsApi.notifications(), AsyncStorage.getItem("lifeInfraSettings")]);
      if (request !== generation.current || accountRef.current !== accountKey) return;
      let settings = {};
      try { settings = JSON.parse(rawSettings || "{}"); } catch { /* Defaults remain enabled. */ }
      setStored({ account: accountKey, items: (items as UserNotification[]).filter((item) => notificationVisible(item, settings)) });
    } catch (cause) {
      if (request === generation.current && accountRef.current === accountKey) setError(userErrorMessage(cause));
    } finally { if (request === generation.current) setLoading(false); }
  }, [accountKey]);
  useFocusEffect(useCallback(() => {
    if (ready) void reload();
    return () => { generation.current += 1; };
  }, [ready, reload]));
  const items = stored.account === accountKey && accountKey ? stored.items : [];
  return { items, loading, error, reload, unreadCount: items.filter((item) => !item.is_read).length };
}
