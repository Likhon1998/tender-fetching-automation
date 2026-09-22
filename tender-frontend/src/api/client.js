/**
 * Thin wrapper around fetch for talking to the FastAPI backend.
 *
 * Responsibilities:
 *  - prefix every path with the API base URL
 *  - attach the bearer token when we have one
 *  - turn non-2xx responses into thrown ApiError objects with a readable
 *    message, so components can just try/catch instead of inspecting status
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8001";
const TOKEN_KEY = "tender_access_token";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

/** FastAPI returns `detail` as either a string or a list of validation errors. */
function readErrorDetail(body, status) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  // Some errors carry structured context, such as which sites clashed.
  if (detail && typeof detail === "object" && !Array.isArray(detail) && detail.message) {
    return detail.message;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((e) => {
        const field = Array.isArray(e.loc) ? e.loc[e.loc.length - 1] : "";
        const msg = (e.msg || "").replace(/^Value error,\s*/, "");
        return field && field !== "body" ? `${field}: ${msg}` : msg;
      })
      .join("\n");
  }
  return `Request failed (${status})`;
}

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";

  if (auth) {
    const token = tokenStore.get();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }

  if (response.status === 204) return null;

  const text = await response.text();
  const parsed = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new ApiError(response.status, readErrorDetail(parsed, response.status));
  }
  return parsed;
}

export const api = {
  login: (identifier, password) =>
    request("/api/v1/authenticate", {
      method: "POST",
      body: { identifier, password },
      auth: false,
    }),

  me: () => request("/api/v1/me"),
  changePassword: (payload) =>
    request("/api/v1/change-password", { method: "POST", body: payload }),

  listCapabilities: () => request("/api/v1/users/capabilities"),

  listSchedules: () => request("/api/v1/schedules"),
  siteAvailability: () => request("/api/v1/schedules/site-availability"),
  createSchedule: (payload) =>
    request("/api/v1/schedules", { method: "POST", body: payload }),
  updateSchedule: (id, payload) =>
    request(`/api/v1/schedules/${id}`, { method: "PATCH", body: payload }),
  deleteSchedule: (id) => request(`/api/v1/schedules/${id}`, { method: "DELETE" }),

  reclassify: () => request("/api/v1/admin/reclassify", { method: "POST" }),
  startIngest: () => request("/api/v1/admin/ingest", { method: "POST" }),
  clearPreview: () => request("/api/v1/admin/clear"),
  clearData: (scope) =>
    request("/api/v1/admin/clear", {
      method: "POST",
      body: { scope, confirm: "CLEAR" },
    }),
  listUsers: () => request("/api/v1/users"),
  createUser: (payload) => request("/api/v1/users", { method: "POST", body: payload }),
  updateUser: (id, payload) =>
    request(`/api/v1/users/${id}`, { method: "PATCH", body: payload }),
  deleteUser: (id) => request(`/api/v1/users/${id}`, { method: "DELETE" }),

  listSites: () => request("/api/v1/sites"),
  createSite: (payload) => request("/api/v1/sites", { method: "POST", body: payload }),
  updateSite: (id, payload) =>
    request(`/api/v1/sites/${id}`, { method: "PATCH", body: payload }),
  deleteSite: (id) => request(`/api/v1/sites/${id}`, { method: "DELETE" }),

  listCategories: () => request("/api/v1/categories"),
  createCategory: (payload) =>
    request("/api/v1/categories", { method: "POST", body: payload }),
  updateCategory: (id, payload) =>
    request(`/api/v1/categories/${id}`, { method: "PATCH", body: payload }),
  deleteCategory: (id) => request(`/api/v1/categories/${id}`, { method: "DELETE" }),

  /** params is a plain object; empty and null values are dropped. */
  listTenders: (params = {}) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        query.set(key, value);
      }
    }
    return request(`/api/v1/tenders?${query.toString()}`);
  },
  tenderIds: (params = {}) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        query.set(key, value);
      }
    }
    return request(`/api/v1/tenders/ids?${query.toString()}`);
  },
  keepTenders: (payload) =>
    request("/api/v1/searches/from-tenders", { method: "POST", body: payload }),
  tenderSummary: (scope = "saved") =>
    request(`/api/v1/tenders/summary?scope=${scope}`),
  setTenderStatus: (id, status) =>
    request(`/api/v1/tenders/${id}`, { method: "PATCH", body: { status } }),

  createSearch: (payload) =>
    request("/api/v1/searches", { method: "POST", body: payload }),
  listSearches: () => request("/api/v1/searches"),
  getSearch: (id) => request(`/api/v1/searches/${id}`),
  deleteSearch: (id) => request(`/api/v1/searches/${id}`, { method: "DELETE" }),
  searchTenderIds: (id) => request(`/api/v1/searches/${id}/tender-ids`),
  saveSelection: (id, tenderIds) =>
    request(`/api/v1/searches/${id}/save`, {
      method: "POST",
      body: { tender_ids: tenderIds },
    }),
  searchResults: (id, params = {}) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        query.set(key, value);
      }
    }
    return request(`/api/v1/searches/${id}/tenders?${query.toString()}`);
  },
};
