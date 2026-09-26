import { clearAuth, readAccessToken, readUser } from "@/lib/authStorage";
import { config } from "@/lib/config";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code: string | undefined = undefined,
    /** True only when this response proved the app's own bearer credential expired or invalid. */
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

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  authenticated = true,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = authenticated ? readAccessToken() : null;
  if (authenticated) {
    if (token) headers.set("Authorization", "Bearer " + token);
    const tenantId = readUser()?.tenant_id;
    if (tenantId && !headers.has(config.tenantHeader))
      headers.set(config.tenantHeader, tenantId);
  }
  const response = await fetch(config.apiPrefix + path, { ...init, headers });
  if (!response.ok) {
    // End the session only when the credential that is still stored is the one just rejected.
    const sessionExpired =
      token !== null &&
      rejectsBearerCredential(response) &&
      readAccessToken() === token;
    if (sessionExpired) {
      clearAuth();
      if (window.location.pathname !== "/login") window.location.assign("/login");
    }
    const body = (await response.json().catch(() => ({}))) as {
      detail?: string;
      code?: string;
      message?: string | string[];
    };
    const message = Array.isArray(body.message)
      ? body.message.join(", ")
      : body.message;
    throw new ApiError(
      response.status,
      body.detail || message || "Request failed",
      body.code,
      sessionExpired,
    );
  }
  return (await response.json()) as T;
}
