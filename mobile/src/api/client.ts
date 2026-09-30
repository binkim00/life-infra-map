import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import { fetch as expoFetch } from "expo/fetch";
import { Platform } from "react-native";

import {
  CONNECTION_ERROR_MESSAGE,
  httpErrorMessage,
  runWithConnectionRetry,
  TIMEOUT_ERROR_MESSAGE,
  type RequestRetryInfo,
} from "./request-retry";

export const DJANGO_API = (
  process.env.EXPO_PUBLIC_DJANGO_API_BASE_URL ||
  "https://life-infra-map-db.taile29cc8.ts.net/django/api"
).replace(/\/$/, "");
export const SPRING_API = (
  process.env.EXPO_PUBLIC_SPRING_API_BASE_URL ||
  "https://life-infra-map-db.taile29cc8.ts.net/spring/api"
).replace(/\/$/, "");

const SPRING_PREFIXES = [
  "/accounts/",
  "/auth/",
  "/boards/",
  "/notifications",
  "/inquiries",
  "/admin/",
  "/tiers",
  "/recommendations/saved-places",
  "/recommendations/saved-place-groups",
];
const AUTH_TOKEN_KEY = "authToken";
const AUTH_USER_KEY = "authUser";
const REFRESH_TOKEN_KEY = "refreshToken";

const readSecretToken = async (key: string) => {
  if (Platform.OS === "web") return AsyncStorage.getItem(key);

  const secureToken = await SecureStore.getItemAsync(key);
  if (secureToken) return secureToken;

  // 기존 개발 빌드의 AsyncStorage 토큰을 한 번만 안전 저장소로 옮깁니다.
  const legacyToken = await AsyncStorage.getItem(key);
  if (legacyToken) {
    await SecureStore.setItemAsync(key, legacyToken);
    await AsyncStorage.removeItem(key);
  }
  return legacyToken;
};

const writeSecretToken = async (key: string, token: string) => {
  if (Platform.OS === "web") {
    await AsyncStorage.setItem(key, token);
    return;
  }
  await SecureStore.setItemAsync(key, token);
  await AsyncStorage.removeItem(key);
};

const clearSecretToken = async (key: string) => {
  await AsyncStorage.removeItem(key);
  if (Platform.OS !== "web") await SecureStore.deleteItemAsync(key);
};

export class ApiError extends Error {
  status: number;
  data: unknown;
  kind: "connection" | "timeout" | "client" | "server";

  constructor(
    status: number,
    data: unknown,
    message?: string,
    kind?: "connection" | "timeout" | "client" | "server",
  ) {
    super(message || `요청에 실패했습니다. (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
    this.kind =
      kind ||
      (status === 0
        ? "connection"
        : status === 408
          ? "timeout"
          : status >= 500
            ? "server"
            : "client");
  }
}

type StoredAuth = { token: string | null; refreshToken: string | null; user: any };
let authCache: StoredAuth | undefined;
let authRead: Promise<StoredAuth> | undefined;
let authRevision = 0;
const authListeners = new Set<(value: StoredAuth) => void>();

export const authStorage = {
  async read() {
    if (authCache) return authCache;
    if (!authRead) {
      const revision = authRevision;
      authRead = Promise.all([
        readSecretToken(AUTH_TOKEN_KEY),
        readSecretToken(REFRESH_TOKEN_KEY),
        AsyncStorage.getItem(AUTH_USER_KEY),
      ])
        .then(([token, refreshToken, rawUser]) => {
          let user = null;
          try {
            user = rawUser ? JSON.parse(rawUser) : null;
          } catch {
            /* ignore invalid user cache */
          }
          const value = { token, refreshToken, user };
          if (revision === authRevision) authCache = value;
          return authCache || value;
        })
        .finally(() => {
          authRead = undefined;
        });
    }
    return authRead;
  },
  subscribe(listener: (value: StoredAuth) => void) {
    authListeners.add(listener);
    return () => { authListeners.delete(listener); };
  },
  async write(token: string, user: unknown, refreshToken?: string | null) {
    const current = await this.read();
    const nextRefresh = refreshToken === undefined ? current.refreshToken : refreshToken;
    await Promise.all([
      writeSecretToken(AUTH_TOKEN_KEY, token),
      nextRefresh ? writeSecretToken(REFRESH_TOKEN_KEY, nextRefresh) : clearSecretToken(REFRESH_TOKEN_KEY),
      AsyncStorage.setItem(AUTH_USER_KEY, JSON.stringify(user)),
    ]);
    authRevision += 1;
    authCache = { token, refreshToken: nextRefresh, user };
    authListeners.forEach((listener) => listener(authCache!));
  },
  async clear() {
    authRevision += 1;
    authCache = { token: null, refreshToken: null, user: null };
    await Promise.all([
      clearSecretToken(AUTH_TOKEN_KEY),
      clearSecretToken(REFRESH_TOKEN_KEY),
      AsyncStorage.removeItem(AUTH_USER_KEY),
    ]);
    authListeners.forEach((listener) => listener(authCache!));
  },
};

let refreshInFlight: Promise<boolean> | null = null;
const renewAccess = async () => {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const stored = await authStorage.read();
      if (!stored.refreshToken) return false;
      const response = await fetch(`${SPRING_API}/auth/refresh`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: stored.refreshToken }),
      });
      if (!response.ok) {
        if (response.status === 401 && (await authStorage.read()).refreshToken === stored.refreshToken)
          await authStorage.clear();
        return false;
      }
      const data = await response.json();
      if (!data.access_token || !data.refresh_token) return false;
      if ((await authStorage.read()).refreshToken !== stored.refreshToken) return false;
      await authStorage.write(data.access_token, data.user || stored.user, data.refresh_token);
      return true;
    })().finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
};

const isSpringPath = (path: string) =>
  SPRING_PREFIXES.some((prefix) => path.startsWith(prefix));
const springPath = (path: string) =>
  path.length > 1 ? path.replace(/\/+$/, "") : path;

type RequestOptions = Omit<RequestInit, "body" | "signal"> & {
  body?: unknown;
  params?: Record<string, string | number | boolean | null | undefined>;
  auth?: boolean;
  signal?: AbortSignal;
  timeoutMs?: number;
  onRetry?: (info: RequestRetryInfo) => void;
  authRetried?: boolean;
};

// Funnel 경유 첫 요청이나 큰 검색 응답도 정상적으로 받을 수 있게 하되,
// 연결이 끊긴 경우에는 무한 로딩으로 남지 않도록 상한을 둡니다.
const DEFAULT_TIMEOUT_MS = 30_000;

class TransportError extends Error {
  kind: "connection" | "timeout";
  cause: unknown;

  constructor(kind: "connection" | "timeout", cause: unknown) {
    super(kind);
    this.name = "TransportError";
    this.kind = kind;
    this.cause = cause;
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    auth = true,
    body,
    headers: requestHeaders,
    params,
    signal: externalSignal,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    onRetry,
    authRetried = false,
    ...requestOptions
  } = options;
  const spring = isSpringPath(path);
  const normalizedPath = spring ? springPath(path) : path;
  const query = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "")
      query.set(key, String(value));
  });
  const url = `${spring ? SPRING_API : DJANGO_API}${normalizedPath}${query.size ? `?${query}` : ""}`;
  const headers = new Headers(requestHeaders);
  let requestToken: string | null = null;
  const formData = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !formData)
    headers.set("Content-Type", "application/json");
  if (auth) {
    const { token } = await authStorage.read();
    requestToken = token;
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  let response: Response;
  try {
    response = await runWithConnectionRetry({
      method: requestOptions.method,
      signal: externalSignal,
      onRetry,
      shouldRetry: (error) =>
        error instanceof TransportError && error.kind === "connection",
      request: async () => {
        const requestController = new AbortController();
        let didTimeout = false;
        const abortFromExternalSignal = () =>
          requestController.abort(externalSignal?.reason);
        if (externalSignal?.aborted) abortFromExternalSignal();
        else
          externalSignal?.addEventListener("abort", abortFromExternalSignal, {
            once: true,
          });
        const timeoutId = setTimeout(() => {
          didTimeout = true;
          requestController.abort();
        }, timeoutMs);
        try {
          const requestFetch = formData ? expoFetch : fetch;
          return await requestFetch(url, {
            ...requestOptions,
            headers,
            signal: requestController.signal,
            body:
              body === undefined
                ? undefined
                : formData
                  ? (body as FormData)
                  : JSON.stringify(body),
          });
        } catch (error) {
          if (didTimeout) throw new TransportError("timeout", error);
          if (externalSignal?.aborted) throw error;
          throw new TransportError("connection", error);
        } finally {
          clearTimeout(timeoutId);
          externalSignal?.removeEventListener("abort", abortFromExternalSignal);
        }
      },
    });
  } catch (error) {
    if (externalSignal?.aborted) throw error;
    if (error instanceof TransportError && error.kind === "timeout")
      throw new ApiError(408, null, TIMEOUT_ERROR_MESSAGE, "timeout");
    throw new ApiError(0, null, CONNECTION_ERROR_MESSAGE, "connection");
  }
  const contentType = response.headers.get("content-type") || "";
  const data =
    response.status === 204
      ? null
      : contentType.includes("application/json")
        ? await response.json()
        : await response.text();
  if (!response.ok) {
    if (response.status === 401 && auth && !authRetried && requestToken) {
      const current = await authStorage.read();
      try {
        if ((current.token && current.token !== requestToken) || await renewAccess())
          return apiRequest<T>(path, { ...options, authRetried: true });
      } catch {
        // A network failure during renewal does not prove the session expired.
        throw new ApiError(0, null, CONNECTION_ERROR_MESSAGE, "connection");
      }
    }
    if (
      response.status === 401 &&
      auth &&
      (await authStorage.read()).token === requestToken
    )
      await authStorage.clear();
    throw new ApiError(
      response.status,
      data,
      httpErrorMessage(response.status, data),
    );
  }
  return data as T;
}
