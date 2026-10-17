// Thin fetch wrapper.
//  - docker-compose / dev: VITE_API_BASE_URL is unset → relative /api, served
//    same-origin (nginx proxy in prod, Vite proxy in dev). No CORS.
//  - PaaS static site (e.g. Render): build with VITE_API_BASE_URL set to the
//    backend's public URL → the browser calls it directly (CORS allowed on the
//    backend via CORS_ALLOWED_ORIGINS).
const BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

async function request(path, { method = "GET", body } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    // no-op: some responses have no body
  }
  if (!res.ok) {
    const message =
      (data && data.error && data.error.message) ||
      (data && data.detail) ||
      `Request failed (${res.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return data;
}

// credentials = { access_key, secret_key, bucket, region }
export const api = {
  connect: (creds) => request("/api/s3/connect/", { method: "POST", body: creds }),
  listFiles: (creds, prefix = "") =>
    request("/api/s3/files/", { method: "POST", body: { ...creds, prefix } }),
  getColumns: (creds, key) =>
    request("/api/s3/columns/", { method: "POST", body: { ...creds, key } }),
  submitJob: (payload) => request("/api/jobs/", { method: "POST", body: payload }),
  getJob: (id) => request(`/api/jobs/${id}/`),
  getResults: (id, offset = 0, limit = 50) =>
    request(`/api/jobs/${id}/results/?offset=${offset}&limit=${limit}`),
  cancelJob: (id) => request(`/api/jobs/${id}/cancel/`, { method: "POST" }),
};
