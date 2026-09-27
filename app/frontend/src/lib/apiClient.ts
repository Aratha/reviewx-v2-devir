import { clearAuth, readAccessToken, readUser, writeSession } from "@/lib/authStorage";
import { config } from "@/lib/config";
import type { LoginResponse } from "@/types/auth";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code: string | undefined = undefined,
    /** True only when this response proved the app's own session expired or invalid. */
    public readonly sessionExpired = false,
  ) {
    super(message);
  }
}

/**
 * RFC 6750: a 401 whose `WWW-Authenticate` challenge names the `Bearer` scheme (without an error,
 * or with `error="invalid_token"`) rejects the bearer credential that was sent. Any other 401,
 * such as a proxy's `Basic` challenge or a bare 401, says nothing about the app session.
 */
function rejectsBearerCredential(response: Response): boolean {
  if (response.status !== 401) return false;
  const challenge = response.headers.get("WWW-Authenticate")?.trim();
  if (!challenge) return false;
  const match = /^(\S+)(?:\s+(.*))?$/.exec(challenge);
  if (match === null || match[1].toLowerCase() !== "bearer") return false;
  const error = /(?:^|[\s,])error="?([^",\s]+)"?/i.exec(match[2] ?? "")?.[1];
  return error === undefined || error === "invalid_token";
}

/** Read the single error envelope `{"detail":{"code","message"}}`; anything else has no code. */
async function toApiError(response: Response, sessionExpired: boolean): Promise<ApiError> {
  const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
  const detail = body.detail;
  let code: string | undefined;
  let message = "Request failed";
  if (detail !== null && typeof detail === "object" && !Array.isArray(detail)) {
    const envelope = detail as { code?: unknown; message?: unknown };
    if (typeof envelope.code === "string") code = envelope.code;
    if (typeof envelope.message === "string") message = envelope.message;
  } else if (typeof detail === "string") {
    message = detail;
  }
  return new ApiError(response.status, message, code, sessionExpired);
}

let refreshInFlight: Promise<LoginResponse> | null = null;

async function requestRefresh(): Promise<LoginResponse> {
  // The refresh cookie is HttpOnly and scoped to the auth path; the browser attaches it and the
  // Origin header, which the backend compares with the application address.
  const response = await fetch(config.apiPrefix + "/auth/refresh", {
    method: "POST",
    credentials: "same-origin",
  });
  if (!response.ok) {
    const sessionEnded = response.status === 401;
    if (sessionEnded) clearAuth();
    throw await toApiError(response, sessionEnded);
  }
  const issued = (await response.json()) as LoginResponse;
  writeSession(issued.access_token, issued.user);
  return issued;
}

/**
 * Rotate the refresh cookie once for every caller that asks at the same time. A second rotation
 * with the same cookie would look like token reuse and close the whole session family, so
 * concurrent requests in this tab share one call and other tabs wait on a Web Lock when the
 * browser offers one.
 */
export function refreshSession(): Promise<LoginResponse> {
  if (refreshInFlight === null) {
    const locks = typeof navigator === "undefined" ? undefined : navigator.locks;
    const run = locks
      ? locks.request("dwhcodereview-session-refresh", requestRefresh)
      : requestRefresh();
    refreshInFlight = run.finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

function sessionEndedError(): ApiError {
  return new ApiError(401, "Session ended", "session_expired", true);
}

function send(path: string, init: RequestInit, token: string | null, authenticated: boolean) {
  const headers = new Headers(init.headers);
  if (typeof init.body === "string" && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  if (authenticated) {
    if (token) headers.set("Authorization", "Bearer " + token);
    const tenantId = readUser()?.tenant_id;
    if (tenantId && !headers.has(config.tenantHeader)) headers.set(config.tenantHeader, tenantId);
  }
  return fetch(config.apiPrefix + path, { ...init, headers });
}

/**
 * Send one request through the shared client and return the successful response untouched, so
 * callers can read JSON, a file or an event stream. When the backend rejects the app's own bearer
 * token the client refreshes the session once and repeats the request; only a failed refresh ends
 * the session. Network, proxy, upstream and unrelated authorization failures keep it.
 */
export async function apiFetch(
  path: string,
  init: RequestInit = {},
  authenticated = true,
): Promise<Response> {
  const token = authenticated ? readAccessToken() : null;
  const response = await send(path, init, token, authenticated);
  if (response.ok) return response;
  if (token === null || !rejectsBearerCredential(response)) throw await toApiError(response, false);

  const current = readAccessToken();
  if (current === null) throw sessionEndedError();
  if (current === token) {
    try {
      await refreshSession();
    } catch (error) {
      if (error instanceof ApiError && error.sessionExpired) throw error;
      throw await toApiError(response, false);
    }
  }
  const renewed = readAccessToken();
  if (renewed === null) throw sessionEndedError();
  const retried = await send(path, init, renewed, authenticated);
  if (retried.ok) return retried;
  if (rejectsBearerCredential(retried) && readAccessToken() === renewed) {
    clearAuth();
    throw await toApiError(retried, true);
  }
  throw await toApiError(retried, false);
}

/** JSON request through the shared client; a 204 answer resolves to `undefined`. */
export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  authenticated = true,
): Promise<T> {
  const response = await apiFetch(path, init, authenticated);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
