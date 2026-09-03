import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

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

  constructor(status: number, data: unknown, message?: string) {
    super(message || `요청에 실패했습니다. (${status})`);
    this.status = status;
    this.data = data;
  }
}

export const authStorage = {
  async read() {
    const [token, rawUser] = await Promise.all([
      readAuthToken(),
      AsyncStorage.getItem(AUTH_USER_KEY),
    ]);
    try {
      return { token, user: rawUser ? JSON.parse(rawUser) : null };
    } catch {
      return { token, user: null };
    }
  },
  async write(token: string, user: unknown) {
    await Promise.all([
      writeAuthToken(token),
      AsyncStorage.setItem(AUTH_USER_KEY, JSON.stringify(user)),
    ]);
  },
  async clear() {
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
};

// Funnel 경유 첫 요청이나 큰 검색 응답도 정상적으로 받을 수 있게 하되,
// 연결이 끊긴 경우에는 무한 로딩으로 남지 않도록 상한을 둡니다.
const DEFAULT_TIMEOUT_MS = 30_000;

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
  const formData =
    typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !formData)
    headers.set("Content-Type", "application/json");
  if (auth) {
    const { token } = await authStorage.read();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  const requestController = new AbortController();
  let didTimeout = false;
  const abortFromExternalSignal = () =>
    requestController.abort(externalSignal?.reason);
  if (externalSignal?.aborted) abortFromExternalSignal();
  else externalSignal?.addEventListener("abort", abortFromExternalSignal);
  const timeoutId = setTimeout(() => {
    didTimeout = true;
    requestController.abort();
  }, timeoutMs);

  let response: Response;
  try {
    response = await fetch(url, {
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
    if (didTimeout)
      throw new ApiError(408, null, "서버 응답 시간이 초과되었습니다.");
    throw error;
  } finally {
    clearTimeout(timeoutId);
    externalSignal?.removeEventListener("abort", abortFromExternalSignal);
  }
  const contentType = response.headers.get("content-type") || "";
  const data =
    response.status === 204
      ? null
      : contentType.includes("application/json")
        ? await response.json()
        : await response.text();
  if (!response.ok) {
    if (response.status === 401 && auth)
      await authStorage.clear();
    const detail =
      data && typeof data === "object" && "detail" in data
        ? String((data as { detail?: unknown }).detail)
        : undefined;
    throw new ApiError(response.status, data, detail);
  }
  return data as T;
}
