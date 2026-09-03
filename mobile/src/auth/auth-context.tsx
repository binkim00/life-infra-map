import { router } from "expo-router";
import {
  createContext,
  PropsWithChildren,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { ApiError, apiRequest, authStorage } from "@/api/client";

export type AuthUser = {
  id?: number;
  username?: string;
  nickname?: string;
  email?: string;
  role?: string;
  is_staff?: boolean;
  profile_image?: string;
  profile_image_url?: string;
  tier?: Record<string, unknown> | string;
};

type AuthContextValue = {
  user: AuthUser | null;
  token: string | null;
  ready: boolean;
  isLoggedIn: boolean;
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<void>;
  signup: (payload: FormData) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
  setUser: (user: AuthUser | null) => Promise<void>;
  requireLogin: () => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const unwrapUser = (
  data: AuthUser | { user?: AuthUser },
): AuthUser | null => {
  if (Object.prototype.hasOwnProperty.call(data, "user")) {
    return (data as { user?: AuthUser }).user || null;
  }
  return data as AuthUser;
};

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUserState] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    const restore = async () => {
      const stored = await authStorage.read();
      if (!stored.token) {
        if (active) setReady(true);
        return;
      }
      try {
        const response = await apiRequest<AuthUser | { user?: AuthUser }>(
          "/accounts/me/",
        );
        const nextUser = unwrapUser(response);
        if (nextUser) await authStorage.write(stored.token, nextUser);
        if (active) {
          setToken(stored.token);
          setUserState(nextUser || stored.user);
        }
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          await authStorage.clear();
        } else if (active) {
          // 일시적인 네트워크 장애에서는 유효할 수 있는 세션을 지우지 않습니다.
          setToken(stored.token);
          setUserState(stored.user);
        }
      } finally {
        if (active) setReady(true);
      }
    };
    void restore();
    return () => {
      active = false;
    };
  }, []);

  const applyAuth = async (data: Record<string, unknown>) => {
    const nextToken = String(data.access_token || data.token || "");
    const nextUser = (data.user || null) as AuthUser | null;
    if (!nextToken) throw new Error("서버가 인증 토큰을 반환하지 않았습니다.");
    await authStorage.write(nextToken, nextUser);
    setToken(nextToken);
    setUserState(nextUser);
  };

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      ready,
      isLoggedIn: Boolean(token),
      isAdmin: Boolean(
        user?.is_staff || user?.role === "ADMIN" || user?.role === "admin",
      ),
      login: async (username, password) => {
        const data = await apiRequest<Record<string, unknown>>("/auth/login", {
          method: "POST",
          body: { username, password },
          auth: false,
        });
        await applyAuth(data);
      },
      signup: async (payload) => {
        const data = await apiRequest<Record<string, unknown>>(
          "/accounts/signup/",
          { method: "POST", body: payload, auth: false },
        );
        await applyAuth(data);
      },
      logout: async () => {
        try {
          if (token) await apiRequest("/accounts/logout/", { method: "POST" });
        } catch {
          /* local logout still proceeds */
        }
        await authStorage.clear();
        setToken(null);
        setUserState(null);
        router.replace("/");
      },
      refreshMe: async () => {
        if (!token) return;
        const data = await apiRequest<AuthUser | { user?: AuthUser }>(
          "/accounts/me/",
        );
        const nextUser = unwrapUser(data);
        if (!nextUser) return;
        await authStorage.write(token, nextUser);
        setUserState(nextUser);
      },
      setUser: async (nextUser) => {
        setUserState(nextUser);
        if (token && nextUser) await authStorage.write(token, nextUser);
      },
      requireLogin: () => {
        if (token) return true;
        router.push("/login");
        return false;
      },
    }),
    [ready, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
