// The one place that talks to the service. Every failure becomes an ApiError
// with a `kind`, because "the service is down" and "that question was refused"
// must never look the same to someone reading the screen.

const BASE = import.meta.env?.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(kind, message, status = null, detail = null) {
    super(message);
    this.name = "ApiError";
    this.kind = kind; // offline | unavailable | busy | rate_limited | not_found | invalid | server | aborted
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, { method = "GET", body, signal } = {}) {
  let response;
  try {
    response = await fetch(BASE + path, {
      method,
      signal,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (cause) {
    if (cause?.name === "AbortError") throw new ApiError("aborted", "Request cancelled.");
    throw new ApiError("offline", "Could not reach OWCS Muse.", null, cause?.message ?? null);
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  const detail = typeof payload?.detail === "string" ? payload.detail : null;

  if (response.ok) return payload;
  // Too many questions from this connection, or every database connection in use: both pass, and the service says
  // how long to wait. Neither is the database being down.
  if (response.status === 429) {
    throw new ApiError("rate_limited", detail ?? "Too many questions in a short time: wait a few seconds and ask again.", 429, detail);
  }
  if (response.status === 503 && payload?.reason === "busy") {
    throw new ApiError("busy", detail ?? "OWCS Muse is busy right now. Try again in a few seconds.", 503, detail);
  }
  if (response.status === 503) {
    throw new ApiError("unavailable", "OWCS Muse is running but its database is not answering.", 503, detail);
  }
  if (response.status === 404) {
    throw new ApiError("not_found", "That link does not point at a saved question.", 404, detail);
  }
  if (response.status === 422) {
    throw new ApiError("invalid", "That question could not be sent as written.", 422, detail);
  }
  throw new ApiError("server", `OWCS Muse failed to answer (HTTP ${response.status}).`, response.status, detail);
}

function evidenceParams({ page, pageSize, evidenceFor }) {
  const params = new URLSearchParams();
  if (page) params.set("page", String(page));
  if (pageSize) params.set("page_size", String(pageSize));
  if (evidenceFor) params.set("evidence_for", evidenceFor);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function ask({ question, page = 1, pageSize, evidenceFor = null, signal } = {}) {
  return request("/ask", {
    method: "POST",
    signal,
    body: {
      question,
      page,
      ...(pageSize ? { page_size: pageSize } : {}),
      ...(evidenceFor ? { evidence_for: evidenceFor } : {}),
    },
  });
}

/** A shared link: the same question, re-run against current data. */
export function askSlug(slug, { page = 1, pageSize, evidenceFor = null, signal } = {}) {
  return request(`/query/${encodeURIComponent(slug)}${evidenceParams({ page, pageSize, evidenceFor })}`, { signal });
}

export function getSuggestions({ signal } = {}) {
  return request("/suggestions", { signal });
}
