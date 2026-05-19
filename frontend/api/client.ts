// In production on Vercel, API calls go to /api/* which Vercel proxies to Railway.
// In local dev, VITE_API_URL points to localhost:8000 directly.
const BASE = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");

type Method = "GET" | "POST" | "PATCH" | "DELETE";

async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
  token?: string
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  // Strip trailing slash before query string to avoid FastAPI 307 redirects
  // breaking the Vercel proxy (redirect loses the /api/ prefix)
  const cleanPath = path.replace(/\/(\?|$)/, "$1");
  const res = await fetch(`${BASE}${cleanPath}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let detail: string;
    try {
      const err = JSON.parse(text);
      if (typeof err.detail === "string") detail = err.detail;
      else if (Array.isArray(err.detail)) detail = err.detail.map((e: { msg?: string }) => e.msg).join(", ");
      else detail = text || res.statusText || `HTTP ${res.status}`;
    } catch {
      detail = text || res.statusText || `HTTP ${res.status}`;
    }
    throw new Error(detail || `HTTP ${res.status} error`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  post: <T>(path: string, body: unknown, token?: string) =>
    request<T>("POST", path, body, token),
  get: <T>(path: string, token?: string) =>
    request<T>("GET", path, undefined, token),
  patch: <T>(path: string, body: unknown, token?: string) =>
    request<T>("PATCH", path, body, token),
  delete: <T>(path: string, token?: string) =>
    request<T>("DELETE", path, undefined, token),
};

// ── Token storage ────────────────────────────────────────────────────────────

export const auth = {
  save(access: string, refresh: string, email?: string) {
    localStorage.setItem("access_token", access);
    localStorage.setItem("refresh_token", refresh);
    if (email) localStorage.setItem("user_email", email);
  },
  accessToken: () => localStorage.getItem("access_token") ?? undefined,
  refreshToken: () => localStorage.getItem("refresh_token") ?? undefined,
  clear() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  },
  isLoggedIn: () => !!localStorage.getItem("access_token"),
};
