import { ApiError, apiRequest } from "./client";
import type { MapSearchResponse } from "@/types/place";

export const recommendationApi = {
  mapSearch: (params: Record<string, unknown>, signal?: AbortSignal) =>
    apiRequest<MapSearchResponse>("/recommendations/place-search/", {
      params: params as Record<string, string | number>,
      signal,
      auth: false,
    }),
  aiSearch: (body: unknown) =>
    apiRequest<Record<string, unknown>>("/recommendations/ai-search/", {
      method: "POST",
      body,
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
  createPlaceReport: (body: FormData) =>
    apiRequest("/recommendations/place-reports/", { method: "POST", body }),
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
  limit = 30,
  signal,
}: {
  query: string;
  lat?: number | null;
  lng?: number | null;
  radius?: number;
  limit?: number;
  signal?: AbortSignal;
}) {
  const params = { q: query.trim(), source: "all", lat, lng, radius, limit };
  try {
    return await recommendationApi.mapSearch(params, signal);
  } catch (error) {
    if (!(error instanceof ApiError) || ![404, 405].includes(error.status))
      throw error;
    return apiRequest<MapSearchResponse>("/recommendations/map-search/", {
      params,
      signal,
      auth: false,
    });
  }
}
