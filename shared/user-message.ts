/** Accept short user-facing Korean messages; diagnostics stay in error objects/logs. */
export const userText = (value: unknown, fallback = "요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요."): string => {
  if (typeof value !== "string") return fallback;
  const text = value.trim();
  if (!text || text.length > 1600 || !/[가-힣]/.test(text)
    || /(https?:\/\/|exception|traceback|stack\s*trace|django|spring|fastapi|\bHTTP\b|\bAPI\b|EXPO_PUBLIC|VITE_|OPENAI_|[A-Z][A-Z0-9]*_[A-Z0-9_]+|\b[a-z]+_[a-z_]+\b|\b[45]\d{2}\b|\bat\s+[\w.$]+\()/i.test(text)) return fallback;
  return text;
};

export const userErrorMessage = (error: any, fallback?: string): string => {
  const status = Number(error?.status ?? error?.response?.status);
  if (status === 401) return "로그인이 필요하거나 로그인 시간이 만료됐어요. 다시 로그인해 주세요.";
  if (status === 403) return "이 정보를 확인하거나 변경할 권한이 없어요.";
  if (status === 404) return "요청한 정보를 찾을 수 없어요. 목록에서 다시 확인해 주세요.";
  if (status === 409) return "처리 상태가 바뀌었어요. 잠시 후 같은 내용으로 다시 시도해 주세요.";
  if (status === 429) return "요청이 잠시 몰리고 있어요. 잠시 후 다시 시도해 주세요.";
  if (error?.kind === "timeout" || error?.code === "ECONNABORTED" || status === 408) return "응답이 늦어지고 있어요. 입력한 내용은 유지되니 다시 시도해 주세요.";
  if (status >= 500) return fallback || "지금 정보를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.";
  const detail = error?.response?.data?.detail || error?.data?.detail;
  if (detail) return userText(detail, fallback);
  if (!status && (error?.kind === "connection" || error?.isAxiosError)) return "연결을 확인할 수 없어요. 인터넷 연결을 확인하고 다시 시도해 주세요.";
  return userText(error?.message, fallback);
};

/** Diagnostics exclude request bodies, headers, tokens, and server exception text. */
export const errorDiagnostic = (error: any) => ({ status: error?.status ?? error?.response?.status ?? null, kind: error?.kind || (error?.code === "ECONNABORTED" ? "timeout" : "request_failed") });
