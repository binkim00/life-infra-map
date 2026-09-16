export const CONNECTION_RETRY_DELAYS_MS = [350, 900] as const;
export const CONNECTION_ERROR_MESSAGE =
  "서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.\n계속 실패하면 Wi-Fi를 껐다 켜거나 모바일 데이터로 전환해 주세요.";
export const TIMEOUT_ERROR_MESSAGE =
  "서버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.";

export type RequestRetryInfo = {
  attempt: number;
  maxAttempts: number;
  delayMs: number;
};

type ConnectionRetryOptions<T> = {
  request: () => Promise<T>;
  method?: string;
  signal?: AbortSignal;
  retryDelaysMs?: readonly number[];
  shouldRetry: (error: unknown) => boolean;
  onRetry?: (info: RequestRetryInfo) => void;
};

export const isSafeRetryMethod = (method?: string) =>
  ["GET", "HEAD", "OPTIONS"].includes((method || "GET").toUpperCase());

const isSafeServerDetail = (detail: string) => {
  const normalized = detail.trim();
  if (!normalized || normalized.length > 240) return false;
  return !/(https?:\/\/|[a-z0-9.-]+\.ts\.net|exception|stack\s*trace|traceback|\bat\s+[\w.$]+\([^)]*:\d+\)|java\.|org\.|com\.[a-z])/i.test(
    normalized,
  );
};

export const httpErrorMessage = (status: number, data: unknown) => {
  const detail =
    data && typeof data === "object" && "detail" in data
      ? String((data as { detail?: unknown }).detail)
      : "";
  if (status < 500 && isSafeServerDetail(detail)) return detail;
  if (status === 401) return "로그인이 필요하거나 인증 정보가 만료되었습니다.";
  if (status === 403) return "이 요청을 수행할 권한이 없습니다.";
  if (status === 404) return "요청한 정보를 찾을 수 없습니다.";
  if (status >= 500)
    return "서버에서 요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
  return `요청을 처리하지 못했습니다. (${status})`;
};

const createAbortError = (reason?: unknown) => {
  if (reason instanceof Error) return reason;
  const error = new Error("요청이 취소되었습니다.");
  error.name = "AbortError";
  return error;
};

const waitForRetry = (delayMs: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(createAbortError(signal.reason));
      return;
    }
    const timeoutId = setTimeout(() => {
      signal?.removeEventListener("abort", abortWait);
      resolve();
    }, delayMs);
    const abortWait = () => {
      clearTimeout(timeoutId);
      signal?.removeEventListener("abort", abortWait);
      reject(createAbortError(signal?.reason));
    };
    signal?.addEventListener("abort", abortWait, { once: true });
  });

export async function runWithConnectionRetry<T>({
  request,
  method,
  signal,
  retryDelaysMs = CONNECTION_RETRY_DELAYS_MS,
  shouldRetry,
  onRetry,
}: ConnectionRetryOptions<T>): Promise<T> {
  const canRetry = isSafeRetryMethod(method);
  let attempt = 1;

  while (true) {
    if (signal?.aborted) throw createAbortError(signal.reason);
    try {
      return await request();
    } catch (error) {
      const delayMs = retryDelaysMs[attempt - 1];
      if (
        !canRetry ||
        signal?.aborted ||
        delayMs === undefined ||
        !shouldRetry(error)
      )
        throw error;

      onRetry?.({
        attempt: attempt + 1,
        maxAttempts: retryDelaysMs.length + 1,
        delayMs,
      });
      await waitForRetry(delayMs, signal);
      attempt += 1;
    }
  }
}
