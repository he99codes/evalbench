/**
 * Thin HTTP client for the EvalBench API. No business logic lives here;
 * it only sends requests and returns parsed JSON.
 */

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);
const API_PREFIX = `${API_BASE_URL}/api/v1`;

type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
}

interface ValidationIssue {
  loc?: unknown[];
  msg?: string;
}

/** Turns FastAPI error bodies ({detail: string | ValidationIssue[]}) into one readable line. */
function describeErrorBody(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return (detail as ValidationIssue[])
        .map((issue) => {
          const loc = Array.isArray(issue.loc) ? issue.loc.filter((p) => p !== "body").join(".") : "";
          return loc ? `${loc}: ${issue.msg ?? "invalid"}` : (issue.msg ?? "invalid");
        })
        .join("; ");
    }
  }
  return `Request failed with status ${status}`;
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(describeErrorBody(body, status));
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function buildUrl(base: string, query?: Record<string, QueryValue>): string {
  if (!query) return base;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}

async function request<T>(url: string, { method = "GET", body, signal }: RequestOptions): Promise<T> {
  const response = await fetch(url, {
    method,
    signal,
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, data);
  return data as T;
}

/** Call a versioned endpoint, e.g. apiRequest("/projects"). */
export function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return request<T>(buildUrl(`${API_PREFIX}${path}`, options.query), options);
}

/** Absolute URL for a versioned endpoint (used for file downloads). */
export function apiUrl(path: string): string {
  return `${API_PREFIX}${path}`;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  database: "ok" | "unavailable";
  app_env: string;
  llm_provider?: string;
  llm_model?: string;
}

/**
 * /health returns 503 with a JSON body when the DB is down. That body is still a
 * valid health report, so surface it instead of treating it as a network failure.
 */
export async function getHealth(): Promise<HealthResponse> {
  try {
    return await request<HealthResponse>(`${API_BASE_URL}/health`, {});
  } catch (error) {
    if (error instanceof ApiError && error.status === 503 && error.body) {
      return error.body as HealthResponse;
    }
    throw error;
  }
}
