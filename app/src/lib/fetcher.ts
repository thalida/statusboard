import { auth } from "./auth";
import { config } from "./config";

type Call = {
  url: string;
  method: string;
  params?: Record<string, unknown>;
  data?: unknown;
  headers?: HeadersInit;
  signal?: AbortSignal;
};

function query(params?: Record<string, unknown>): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function send(call: Call, token?: string): Promise<Response> {
  const headers = new Headers(call.headers);
  if (call.data !== undefined) headers.set("Content-Type", "application/json");
  // A signed-out reader sends no header at all. The catalog is public,
  // and an empty Authorization is a 401 rather than an anonymous read.
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${config.apiUrl}${call.url}${query(call.params)}`, {
    method: call.method,
    headers,
    body: call.data === undefined ? undefined : JSON.stringify(call.data),
    signal: call.signal,
  });
}

async function refresh(): Promise<boolean> {
  const held = auth.tokens();
  if (!held) return false;
  const response = await fetch(`${config.apiUrl}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: held.refresh }),
  });
  if (!response.ok) return false;
  auth.signIn(await response.json());
  return true;
}

export async function fetcher<T>(call: Call): Promise<T> {
  let response = await send(call, auth.tokens()?.access);

  // The access token rotates every fifteen minutes, so a signed-in
  // reader meets a 401 mid-session. One retry, then out: a revoked
  // refresh token would otherwise loop from every open tab.
  if (response.status === 401 && auth.tokens()) {
    if (await refresh()) {
      response = await send(call, auth.tokens()?.access);
    } else {
      auth.signOut();
    }
  }

  if (!response.ok) {
    if (response.status === 401) auth.signOut();
    throw new Error(`${call.method} ${call.url} answered ${response.status}`);
  }
  return response.status === 204 ? (undefined as T) : await response.json();
}
