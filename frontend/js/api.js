// Thin fetch wrapper around the REST API.
export class ApiError extends Error {
  constructor(status, message, details) {
    super(message);
    this.status = status;
    this.details = details;
  }
  get full() {
    const d = (this.details || []).map((x) => `${x.field}: ${x.message}`).join("; ");
    return d ? `${this.message} (${d})` : this.message;
  }
}

// Throws ApiError for HTTP errors; fetch's own TypeError (network failure) passes through,
// which is how callers tell "server said no" apart from "we're offline".
export async function api(path, opts = {}) {
  const res = await fetch("/api" + path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body?.error?.message || "Request failed", body?.error?.details);
  return body;
}
