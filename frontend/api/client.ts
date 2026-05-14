const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
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
  save(access: string, refresh: string) {
    localStorage.setItem("access_token", access);
    localStorage.setItem("refresh_token", refresh);
  },
  accessToken: () => localStorage.getItem("access_token") ?? undefined,
  refreshToken: () => localStorage.getItem("refresh_token") ?? undefined,
  clear() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  },
  isLoggedIn: () => !!localStorage.getItem("access_token"),
};
