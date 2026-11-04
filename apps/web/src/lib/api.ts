/**
 * Typed client for the ML Forge API (same-origin, proxied by Next to FastAPI).
 * Errors always surface as ApiError with the server's stable `error_code`.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
    public requestId: string | null = null,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, {
      ...rest,
      headers: { ...(json !== undefined ? { "content-type": "application/json" } : {}), ...headers },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "network_error", "API is unreachable");
  }
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!res.ok) {
    const b = (body ?? {}) as { error_code?: string; message?: string; details?: Record<string, unknown>; request_id?: string };
    // A 5xx without our envelope means the Next proxy could not reach FastAPI.
    const code = b.error_code ?? (res.status >= 500 ? "api_unreachable" : "http_error");
    throw new ApiError(res.status, code, b.message ?? res.statusText, b.details ?? {}, b.request_id ?? null);
  }
  return body as T;
}

export const get = <T>(path: string) => api<T>(path);
export const post = <T>(path: string, json?: unknown) => api<T>(path, { method: "POST", json: json ?? {} });
export const put = <T>(path: string, json: unknown) => api<T>(path, { method: "PUT", json });
export const patch = <T>(path: string, json: unknown) => api<T>(path, { method: "PATCH", json });

export function newRequestId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(12)), (b) => b.toString(16).padStart(2, "0")).join("");
}
