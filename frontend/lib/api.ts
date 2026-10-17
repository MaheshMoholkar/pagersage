// The PagerSage API client. Every screen gets its data from here, never with its own fetch.
//
// NEXT_PUBLIC_API_URL   backend base URL (default http://127.0.0.1:8000: Node resolves
//                       localhost to ::1, and uvicorn listens on 127.0.0.1)
// NEXT_PUBLIC_USE_STUBS "1" = always use lib/stubs.ts (no backend needed)
//
// Without the stub switch, a failed request falls back to the stubs too and the result says
// so (`stub: true`), so the UI can be built before the backend is up. Errors from a running
// backend (400/422/503 with {"error"}) are thrown as ApiError.

import * as stubs from "./stubs";
import type {
  ActionResult,
  AskOut,
  GraphView,
  IncidentDetail,
  IncidentSummary,
  MemoryView,
  OnCallNow,
  SuspectsView,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const USE_STUBS = process.env.NEXT_PUBLIC_USE_STUBS === "1";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export interface Loaded<T> {
  data: T;
  stub: boolean; // true when the data came from lib/stubs.ts
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    cache: "no-store",
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(
      res.status,
      body.error ?? JSON.stringify(body.detail ?? res.statusText),
    );
  }
  return res.json() as Promise<T>;
}

/** Read from the API; on a network failure (backend down) or USE_STUBS, use the stub. */
async function load<T>(path: string, stub: () => T): Promise<Loaded<T>> {
  if (USE_STUBS) return { data: stub(), stub: true };
  try {
    return { data: await request<T>(path), stub: false };
  } catch (e) {
    if (e instanceof ApiError) throw e;
    return { data: stub(), stub: true };
  }
}

export const api = {
  /** U05 feed. */
  incidents: ({
    status,
    limit = 20,
  }: { status?: string; limit?: number } = {}) =>
    load<IncidentSummary[]>(
      `/incidents?limit=${limit}${status ? `&status=${encodeURIComponent(status)}` : ""}`,
      () => stubs.incidents,
    ),
  /** U02/U03/U04: alerts, timeline, decisions, handoffs, state and the incident graph. */
  incident: (id: string) =>
    load<IncidentDetail>(`/incidents/${encodeURIComponent(id)}`, () =>
      stubs.incidentDetail(id),
    ),
  /** Top bar: each team's on-call person now. */
  onCall: () => load<OnCallNow[]>("/oncall", () => stubs.onCall),
  /** U02 company graph, or one incident's neighbourhood with what to highlight. */
  graph: (incident?: string) =>
    load<GraphView>(
      `/graph${incident ? `?incident=${encodeURIComponent(incident)}` : ""}`,
      () =>
        incident ? stubs.incidentDetail(incident).graph : stubs.companyGraph,
    ),
  /** U08 Ask. Backend down: the stub answer. A 503 (no API key, no answer) throws ApiError. */
  ask: async (question: string): Promise<Loaded<AskOut>> => {
    if (USE_STUBS) return { data: stubs.askAnswer, stub: true };
    try {
      const body = JSON.stringify({ question });
      return {
        data: await request<AskOut>("/ask", { method: "POST", body }),
        stub: false,
      };
    } catch (e) {
      if (e instanceof ApiError) throw e;
      return { data: stubs.askAnswer, stub: true };
    }
  },
  /** U09: a person reverts the cause, deploy or config change (simulated); incident mitigated. */
  revert: (id: string, change_id: string) =>
    request<ActionResult>(`/incidents/${encodeURIComponent(id)}/revert`, {
      method: "POST",
      body: JSON.stringify({ change_id }),
    }),
  /** A person approved the Responder's deploy rollback (simulated in the graph). */
  rollback: (id: string, service_id: string, deploy_id: string) =>
    request<ActionResult>(`/incidents/${encodeURIComponent(id)}/rollback`, {
      method: "POST",
      body: JSON.stringify({ service_id, deploy_id }),
    }),
  /** U09: resolve; the Scribe then writes the postmortem in the background. */
  resolve: (id: string, summary: string) =>
    request<{ incident_id: string; status: string }>(
      `/incidents/${encodeURIComponent(id)}/resolve`,
      { method: "POST", body: JSON.stringify({ summary }) },
    ),

  /** U06 suspects with score_parts, the cause and what was ruled out. */
  suspects: (id: string) =>
    load<SuspectsView>(`/incidents/${encodeURIComponent(id)}/suspects`, () =>
      stubs.suspects(),
    ),
  /** U07 memory: vector-only vs graph re-ranked, and the cause service's runbooks. */
  memory: (id: string) =>
    load<MemoryView>(`/incidents/${encodeURIComponent(id)}/memory`, () =>
      stubs.memory(),
    ),
};

/** U04: the incident's live timeline URL for EventSource (see lib/useIncidentEvents.ts). */
export const eventsUrl = (id: string, afterSeq = 0) =>
  `${API_URL}/incidents/${encodeURIComponent(id)}/events${afterSeq ? `?after=${afterSeq}` : ""}`;
