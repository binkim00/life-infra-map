import { ApiError, apiRequest } from "./client";
import type { RequestRetryInfo } from "./request-retry";
import type { MapSearchResponse } from "@/types/place";

export const recommendationApi = {
  evidenceQueue: (params: Record<string, string | number>) =>
    apiRequest<Record<string, unknown>>("/recommendations/admin/evidence/", {
      params,
    }),
  evidenceReview: (id: number, body: { status: string; note: string }) =>
    apiRequest(`/recommendations/admin/evidence/${id}/`, {
      method: "POST",
      body,
    }),
  mapSearch: (
    params: Record<string, unknown>,
    signal?: AbortSignal,
    onRetry?: (info: RequestRetryInfo) => void,
  ) =>
    apiRequest<MapSearchResponse>("/recommendations/place-search/", {
      params: params as Record<string, string | number>,
      signal,
      auth: false,
      onRetry,
    }),
  aiSearch: (body: unknown) =>
    apiRequest<Record<string, unknown>>("/recommendations/ai-search/", {
      method: "POST",
      body,
    }),
  createConversationSession: () =>
    apiRequest<Record<string, unknown>>(
      "/recommendations/conversation-sessions/",
      { method: "POST", body: {} },
    ),
  sendConversationTurn: (
    sessionId: string,
    conversationToken: string,
    body: unknown,
  ) =>
    apiRequest<Record<string, unknown>>(
      `/recommendations/conversation-sessions/${sessionId}/turns/`,
      {
        method: "POST",
        body,
        headers: conversationToken
          ? { "X-Conversation-Token": conversationToken }
          : undefined,
        timeoutMs: 45_000,
      },
    ),
  closeConversationSession: (sessionId: string, conversationToken: string) =>
    apiRequest(`/recommendations/conversation-sessions/${sessionId}/`, {
      method: "DELETE",
      headers: conversationToken
        ? { "X-Conversation-Token": conversationToken }
        : undefined,
    }),
  aiWebSearch: (body: unknown) =>
    apiRequest<Record<string, unknown>>("/recommendations/ai-web-search/", {
      method: "POST",
      body,
    }),
  searchSafety: (query: string) =>
    apiRequest<Record<string, unknown>>("/recommendations/search-safety/", {
      method: "POST",
      body: { query },
    }),
  places: (params: Record<string, unknown> = {}) =>
    apiRequest<Record<string, unknown>>("/recommendations/places/", {
      params: params as Record<string, string | number>,
    }),
  searchLogs: (params: Record<string, unknown> = {}) =>
    apiRequest<Record<string, unknown>>("/recommendations/search-logs/", {
      params: params as Record<string, string | number>,
    }),
  deleteSearchLog: (id: number | string) =>
    apiRequest(`/recommendations/search-logs/${id}/`, { method: "DELETE" }),
  saveSearchLog: (body: unknown) =>
    apiRequest("/recommendations/search-logs/", { method: "POST", body }),
  interactions: (events: unknown[]) =>
    apiRequest("/recommendations/interactions/", {
      method: "POST",
      body: { events },
    }),
  preferences: (params: Record<string, unknown> = {}) =>
    apiRequest<Record<string, unknown>>("/recommendations/preferences/", {
      params: params as Record<string, string | number>,
    }),
  preferenceTags: () =>
    apiRequest<{ results?: unknown[] } | unknown[]>(
      "/recommendations/preference-tags/",
    ),
  createPreference: (body: unknown) =>
    apiRequest("/recommendations/preferences/", { method: "POST", body }),
  deletePreference: (id: number | string) =>
    apiRequest(`/recommendations/preferences/${id}/`, { method: "DELETE" }),
  rebuildPreferences: () =>
    apiRequest("/recommendations/preferences/rebuild/", { method: "POST" }),
  savedPlaces: (params: Record<string, unknown> = {}) =>
    apiRequest<Record<string, unknown>>("/recommendations/saved-places/", {
      params: params as Record<string, string | number>,
    }),
  savePlace: (body: unknown) =>
    apiRequest("/recommendations/saved-places/", { method: "POST", body }),
  updateSavedPlace: (id: number | string, body: unknown) =>
    apiRequest(`/recommendations/saved-places/${id}/`, {
      method: "PATCH",
      body,
    }),
  deleteSavedPlace: (id: number | string) =>
    apiRequest(`/recommendations/saved-places/${id}/`, { method: "DELETE" }),
  savedPlaceGroups: () =>
    apiRequest<Record<string, unknown>>("/recommendations/saved-place-groups/"),
  createSavedPlaceGroup: (body: unknown) =>
    apiRequest("/recommendations/saved-place-groups/", {
      method: "POST",
      body,
    }),
  updateSavedPlaceGroup: (id: number | string, body: unknown) =>
    apiRequest(`/recommendations/saved-place-groups/${id}/`, {
      method: "PATCH",
      body,
    }),
  deleteSavedPlaceGroup: (id: number | string) =>
    apiRequest(`/recommendations/saved-place-groups/${id}/`, {
      method: "DELETE",
    }),
  moveSavedPlaceToGroup: (id: number | string, groupId: number | null) =>
    apiRequest(`/recommendations/saved-places/${id}/group/`, {
      method: "PATCH",
      body: { group_id: groupId },
    }),
  createPlaceReport: (body: FormData) =>
    apiRequest<{
      report: { id: number; created_at: string };
      idempotent_replay: boolean;
    }>("/recommendations/place-reports/", { method: "POST", body }),
  myPlaceReport: (id: string | number) =>
    apiRequest<Record<string, unknown>>(
      `/recommendations/place-reports/${id}/`,
    ),
  myPlaceReports: (params: Record<string, unknown> = {}) =>
    apiRequest<Record<string, unknown>>("/recommendations/place-reports/", {
      params: params as Record<string, string | number>,
    }),
  adminPlaceReports: (params: Record<string, unknown> = {}) =>
    apiRequest<Record<string, unknown>>(
      "/recommendations/admin/place-reports/",
      { params: params as Record<string, string | number> },
    ),
  adminPlaceReport: (id: number | string) =>
    apiRequest<Record<string, unknown>>(
      `/recommendations/admin/place-reports/${id}/`,
    ),
  approvePlaceReport: (id: number | string, body: unknown = {}) =>
    apiRequest(`/recommendations/admin/place-reports/${id}/approve/`, {
      method: "POST",
      body,
    }),
  rejectPlaceReport: (id: number | string, body: unknown = {}) =>
    apiRequest(`/recommendations/admin/place-reports/${id}/reject/`, {
      method: "POST",
      body,
    }),
  adminOperations: (params: Record<string, unknown> = {}) =>
    apiRequest<Record<string, unknown>>("/recommendations/admin/operations/", {
      params: params as Record<string, string | number>,
    }),
};

export async function searchMapPlaces({
  query,
  lat,
  lng,
  radius,
  centerMode,
  limit = 30,
  signal,
  onRetry,
}: {
  query: string;
  lat?: number | null;
  lng?: number | null;
  radius?: number;
  centerMode?: "auto" | "map";
  limit?: number;
  signal?: AbortSignal;
  onRetry?: (info: RequestRetryInfo) => void;
}) {
  const params = {
    detail_level: "summary",
    q: query.trim(),
    source: "all",
    lat,
    lng,
    radius,
    center_mode: centerMode,
    limit,
  };
  try {
    return await recommendationApi.mapSearch(params, signal, onRetry);
  } catch (error) {
    if (!(error instanceof ApiError) || ![404, 405].includes(error.status))
      throw error;
    return apiRequest<MapSearchResponse>("/recommendations/map-search/", {
      params,
      signal,
      auth: false,
      onRetry,
    });
  }
}
