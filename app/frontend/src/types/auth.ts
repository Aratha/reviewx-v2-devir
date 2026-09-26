import type { paths } from "./api";

/** Types are selected by endpoint, so both supported backend profiles stay interchangeable. */
export type AuthenticatedUser =
  paths["/api/dwhcodereview/v1/auth/me"]["get"]["responses"][200]["content"]["application/json"];

export type LoginResponse =
  paths["/api/dwhcodereview/v1/auth/login"]["post"]["responses"][200]["content"]["application/json"];
