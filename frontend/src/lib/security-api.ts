import type { SecurityOutcome } from "@/types";

const base = process.env.NEXT_PUBLIC_RAGSEC_API_URL || "http://127.0.0.1:8001";
// Protected demo credentials are tab-local and cleared on logout.
export function securityToken() { return sessionStorage.getItem("ragsec-token"); }
export function securityLogout() {
  const token = securityToken();
  sessionStorage.removeItem("ragsec-token");
  return token ? fetch(`${base}/api/v1/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${token}` } }) : Promise.resolve();
}

export async function securityRequest(path: string, init: RequestInit = {}) {
  const token = securityToken();
  const response = await fetch(`${base}${path}`, { ...init, cache: "no-store", headers: {
    ...(init.body ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers,
  }});
  if (!response.ok) {
    if (response.status === 401) securityLogout();
    throw new Error((await response.json().catch(() => ({}))).detail || "request_failed");
  }
  return response;
}

export async function securityLogin(email: string, password: string) {
  const result = await securityRequest("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
  const data = await result.json();
  sessionStorage.setItem("ragsec-token", data.access_token);
  return data.user;
}

export async function securityChat(question: string, language: string, stream: boolean, signal: AbortSignal,
                                   conversation_id: number | null): Promise<SecurityOutcome> {
  const response = await securityRequest(`/api/v1/chat${stream ? "/stream" : ""}`, { method: "POST", signal,
    body: JSON.stringify({ question, language, conversation_id }) });
  if (!stream) return response.json();
  const reader = response.body?.getReader();
  if (!reader) throw new Error("stream_unavailable");
  const decoder = new TextDecoder();
  let pending = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      pending += decoder.decode(value, { stream: !done });
      let boundary;
      while ((boundary = pending.indexOf("\n\n")) !== -1) {
        const event = pending.slice(0, boundary);
        pending = pending.slice(boundary + 2);
        if (event.startsWith("event: outcome\n")) {
          return JSON.parse(event.slice("event: outcome\ndata: ".length));
        }
      }
      if (done) throw new Error("incomplete_stream");
      if (pending.length > 131072) throw new Error("stream_size");
    }
  } finally { await reader.cancel(); reader.releaseLock(); }
}

export async function verifySecurityCitation(token: string) {
  return (await securityRequest(`/api/v1/citations/verify?${new URLSearchParams({ token })}`)).json();
}
