// OWCS Grid's calls to the service. The same base URL as the rest of the app; a failure becomes one sentence a
// player can read, and "no puzzle today" is told apart from "the service could not be reached".

const BASE = import.meta.env?.VITE_API_BASE ?? "";

export class GridError extends Error {
  constructor(kind, message, status = null) {
    super(message);
    this.name = "GridError";
    this.kind = kind; // offline | not_found | rate_limited | invalid | server | aborted
    this.status = status;
  }
}

async function request(path, { method = "GET", body, signal } = {}) {
  let response;
  try {
    response = await fetch(`${BASE}/api/grid${path}`, {
      method,
      signal,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (cause) {
    if (cause?.name === "AbortError") throw new GridError("aborted", "Request cancelled.");
    throw new GridError("offline", "Could not reach OWCS Muse. Check your connection and try again.");
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (response.ok) return payload;
  const detail = typeof payload?.detail === "string" ? payload.detail : null;
  if (response.status === 404) throw new GridError("not_found", detail ?? "That puzzle does not exist.", 404);
  if (response.status === 429) {
    throw new GridError("rate_limited", detail ?? "Slow down a little: wait a few seconds and try again.", 429);
  }
  if (response.status === 422) throw new GridError("invalid", detail ?? "That guess could not be sent.", 422);
  throw new GridError("server", `OWCS Grid could not answer (HTTP ${response.status}).`, response.status);
}

export const getPuzzle = (number, { signal } = {}) => request(number ? `/${number}` : "/today", { signal });
export const getArchive = ({ signal } = {}) => request("/archive", { signal });
export const searchPlayers = (q, { signal } = {}) => request(`/players?q=${encodeURIComponent(q)}`, { signal });
export const postGuess = (number, cell, playerId) =>
  request(`/${number}/guess`, { method: "POST", body: { cell, player_id: playerId } });
export const getReveal = (number, { signal } = {}) => request(`/${number}/reveal`, { signal });
