// Tiny fetch wrapper + SWR fetcher. All calls go through Next.js rewrites
// (/api/* -> FastAPI), so the browser stays same-origin.

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

// --- Demo mode ---
// A localStorage flag routes all reads to the isolated demo DB (?demo=1).
// Toggling reloads the page, so SWR's in-memory cache resets cleanly.
export function isDemo(): boolean {
  return typeof window !== "undefined" && window.localStorage.getItem("demo") === "1";
}

export function setDemo(on: boolean) {
  if (typeof window === "undefined") return;
  if (on) window.localStorage.setItem("demo", "1");
  else window.localStorage.removeItem("demo");
}

/** Append ?demo=1 to a path when demo mode is on (for fetches and hrefs). */
export function withDemo(path: string): string {
  if (!isDemo()) return path;
  return path + (path.includes("?") ? "&" : "?") + "demo=1";
}

export async function fetcher<T>(path: string): Promise<T> {
  const res = await fetch(withDemo(path), { headers: { Accept: "application/json" } });
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(withDemo(path), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Request failed: ${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export async function putJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(withDemo(path), {
    method: "PUT",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Request failed: ${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export async function deleteJSON<T>(path: string): Promise<T> {
  const res = await fetch(withDemo(path), {
    method: "DELETE",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    let detail = `Request failed: ${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

import type { CoachEvent } from "./types";

export interface ChatPayload {
  message: string;
  chat_id?: string | null;
  context_days?: number;
  provider?: string;
}

// POST /api/coach/chat and parse the Server-Sent Events stream, invoking
// onEvent for each parsed event. Resolves when the stream ends.
export async function streamCoachChat(
  payload: ChatPayload,
  onEvent: (e: CoachEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(withDemo("/api/coach/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, `Chat request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const json = line.slice(5).trim();
      if (!json) continue;
      try {
        onEvent(JSON.parse(json) as CoachEvent);
      } catch {
        // ignore malformed frame
      }
    }
  }
}
