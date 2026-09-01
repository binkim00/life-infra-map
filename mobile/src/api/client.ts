import AsyncStorage from "@react-native-async-storage/async-storage";

export const DJANGO_API = (
  process.env.EXPO_PUBLIC_DJANGO_API_BASE_URL ||
  "http://100.71.169.91:8000/api"
).replace(/\/$/, "");
export const SPRING_API = (
  process.env.EXPO_PUBLIC_SPRING_API_BASE_URL ||
  "http://100.71.169.91:8081/api"
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
      AsyncStorage.getItem(AUTH_TOKEN_KEY),
      AsyncStorage.getItem(AUTH_USER_KEY),
    ]);
    try {
      return { token, user: rawUser ? JSON.parse(rawUser) : null };
    } catch {
      return { token, user: null };
    }
  },
  async write(token: string, user: unknown) {
    await AsyncStorage.multiSet([
      [AUTH_TOKEN_KEY, token],
      [AUTH_USER_KEY, JSON.stringify(user)],
    ]);
  },
  async clear() {
    await AsyncStorage.multiRemove([AUTH_TOKEN_KEY, AUTH_USER_KEY]);
  },
};

const isSpringPath = (path: string) =>
  SPRING_PREFIXES.some((prefix) => path.startsWith(prefix));
const springPath = (path: string) =>
  path.length > 1 ? path.replace(/\/+$/, "") : path;

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  params?: Record<string, string | number | boolean | null | undefined>;
  auth?: boolean;
};

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const spring = isSpringPath(path);
  const normalizedPath = spring ? springPath(path) : path;
  const query = new URLSearchParams();
  Object.entries(options.params || {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "")
      query.set(key, String(value));
  });
  const url = `${spring ? SPRING_API : DJANGO_API}${normalizedPath}${query.size ? `?${query}` : ""}`;
  const headers = new Headers(options.headers);
  const formData =
    typeof FormData !== "undefined" && options.body instanceof FormData;
  if (options.body !== undefined && !formData)
    headers.set("Content-Type", "application/json");
  if (options.auth !== false) {
    const { token } = await authStorage.read();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(url, {
    ...options,
    headers,
    body:
      options.body === undefined
        ? undefined
        : formData
          ? (options.body as FormData)
          : JSON.stringify(options.body),
  });
  const contentType = response.headers.get("content-type") || "";
  const data =
    response.status === 204
      ? null
      : contentType.includes("application/json")
        ? await response.json()
        : await response.text();
  if (!response.ok) {
    if (response.status === 401 && options.auth !== false)
      await authStorage.clear();
    const detail =
      data && typeof data === "object" && "detail" in data
        ? String((data as { detail?: unknown }).detail)
        : undefined;
    throw new ApiError(response.status, data, detail);
  }
  return data as T;
}
