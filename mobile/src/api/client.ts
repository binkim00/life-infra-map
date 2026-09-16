import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
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

const readAuthToken = async () => {
  if (Platform.OS === "web") return AsyncStorage.getItem(AUTH_TOKEN_KEY);

  const secureToken = await SecureStore.getItemAsync(AUTH_TOKEN_KEY);
  if (secureToken) return secureToken;

  // 기존 개발 빌드의 AsyncStorage 토큰을 한 번만 안전 저장소로 옮깁니다.
  const legacyToken = await AsyncStorage.getItem(AUTH_TOKEN_KEY);
  if (legacyToken) {
    await SecureStore.setItemAsync(AUTH_TOKEN_KEY, legacyToken);
    await AsyncStorage.removeItem(AUTH_TOKEN_KEY);
  }
  return legacyToken;
};

const writeAuthToken = async (token: string) => {
  if (Platform.OS === "web") {
    await AsyncStorage.setItem(AUTH_TOKEN_KEY, token);
    return;
  }
  await SecureStore.setItemAsync(AUTH_TOKEN_KEY, token);
  await AsyncStorage.removeItem(AUTH_TOKEN_KEY);
};

const clearAuthToken = async () => {
  await AsyncStorage.removeItem(AUTH_TOKEN_KEY);
  if (Platform.OS !== "web") await SecureStore.deleteItemAsync(AUTH_TOKEN_KEY);
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

type StoredAuth = { token: string | null; user: any };
let authCache: StoredAuth | undefined;
let authRead: Promise<StoredAuth> | undefined;
let authRevision = 0;

export const authStorage = {
  async read() {
    if (authCache) return authCache;
    if (!authRead) {
      const revision = authRevision;
      authRead = Promise.all([
        readAuthToken(),
        AsyncStorage.getItem(AUTH_USER_KEY),
      ])
        .then(([token, rawUser]) => {
          let user = null;
          try {
            user = rawUser ? JSON.parse(rawUser) : null;
          } catch {
            /* ignore invalid user cache */
          }
          const value = { token, user };
          if (revision === authRevision) authCache = value;
          return authCache || value;
        })
        .finally(() => {
          authRead = undefined;
        });
    }
    return authRead;
  },
  async write(token: string, user: unknown) {
    await Promise.all([
      writeAuthToken(token),
      AsyncStorage.setItem(AUTH_USER_KEY, JSON.stringify(user)),
    ]);
    authRevision += 1;
    authCache = { token, user };
  },
  async clear() {
    authRevision += 1;
    authCache = { token: null, user: null };
    await Promise.all([
      clearAuthToken(),
      AsyncStorage.removeItem(AUTH_USER_KEY),
    ]);
  },
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
          return await fetch(url, {
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
