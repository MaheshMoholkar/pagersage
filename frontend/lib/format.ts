// Small display helpers shared by every screen.

import type {
  AgentEvent,
  AgentName,
  GraphView,
  Highlight,
  Severity,
} from "./types";

export const AGENTS: AgentName[] = [
  "triage",
  "investigator",
  "historian",
  "responder",
  "scribe",
];

/** Suggested questions for the Brain (Ask box, command palette). */
export const ASK_SUGGESTIONS = [
  "Who knows the payments DB?",
  "What breaks if checkout-api goes down?",
  "Who is our bus factor?",
  "Which services are fragile?",
];

export const agentLabel = (a: string | null | undefined) =>
  a ? a.charAt(0).toUpperCase() + a.slice(1) : "PagerSage";

/** "svc:payments-db" -> "payments-db", "person:priya" -> "priya". */
export const shortId = (id: string) =>
  id.replace(/^(svc|person|team|rb|pol):/, "");

export const sevLabel = (s: Severity | string | null) =>
  s ? `Sev ${s.replace("sev", "")}` : "Sev ?";

/** "12:40:05" in UTC (demo times are UTC). */
export const clock = (ts: number) =>
  new Date(ts * 1000).toISOString().slice(11, 19);

/** "12:40" in UTC. */
export const hhmm = (ts: number) => clock(ts).slice(0, 5);

/** A CSS width from a fraction, rounded: the server and the browser print it the same way
 *  (a full-precision float hydrates as a mismatch). */
export const pct = (fraction: number) => `${(fraction * 100).toFixed(2)}%`;

/** "4 min", "2 h", "3 d". */
export const age = (ts: number | null, now = Date.now() / 1000) => {
  if (ts == null) return "";
  const s = Math.max(0, now - ts);
  if (s < 3600) return `${Math.round(s / 60)} min`;
  if (s < 86400) return `${Math.round(s / 3600)} h`;
  return `${Math.round(s / 86400)} d`;
};

/** Team colours for the company graph, as hex because the graph is drawn on a
 *  <canvas>, which can't read CSS variables (the same values are --team-* in globals.css). */
export const TEAM_COLORS: Record<string, string> = {
  Payments: "#79b4ff",
  Checkout: "#c79bff",
  Platform: "#6fd3b0",
  Ledger: "#f2a0c8",
  "Risk & Identity": "#ffa96b",
  "Merchant Experience": "#e8d27a",
};
export const NO_TEAM_COLOR = "#8a93b3";
export const teamColor = (team: string | null | undefined) =>
  (team && TEAM_COLORS[team]) || NO_TEAM_COLOR;

/** The root-cause path: the newest timeline highlight that walks DEPENDS_ON edges (what
 *  root_cause_path returns), as tools.root_cause_highlight picks it on the backend. */
export function rootCausePath(timeline: AgentEvent[]): Highlight | null {
  for (let i = timeline.length - 1; i >= 0; i--) {
    const h = timeline[i].highlight;
    if (h.edges.some(([, rel]) => rel === "DEPENDS_ON")) return h;
  }
  return null;
}

/** The failing service: the cause's service if the agents found it, else the sickest one. */
export function failingNode(
  graph: GraphView,
  state: Record<string, unknown>,
): string | null {
  if (typeof state.cause_service === "string") return state.cause_service;
  const sick = graph.nodes
    .filter((n) => n.kind === "Service" && (n.health ?? 1) < 1)
    .sort((a, b) => (a.health ?? 1) - (b.health ?? 1));
  return sick[0]?.id ?? null;
}

/** The path as the demo shows it, Alert → services → change → commits → people: the root-cause
 *  path plus the alert that fired on its first service (FIRED_ON, from the incident graph). */
export function withAlert(
  path: Highlight | null,
  graph: GraphView,
): Highlight | null {
  if (!path?.nodes.length) return path;
  const first = path.nodes[0];
  const alert = graph.links.find(
    (l) => l.type === "FIRED_ON" && l.target === first,
  );
  if (!alert || path.nodes.includes(alert.source)) return path;
  return {
    nodes: [alert.source, ...path.nodes],
    edges: [[alert.source, "FIRED_ON", first], ...path.edges],
  };
}

/** The incident graph without the noise: services, plus only the non-service nodes that mean
 *  something here (the root-cause path, rejected suspects). Every tool call's highlight adds
 *  nodes to GraphView (deploys, past incidents); drawn together they bury the path. */
export function focusGraph(graph: GraphView, keep: string[]): GraphView {
  const wanted = new Set(keep);
  const nodes = graph.nodes.filter(
    (n) => n.kind === "Service" || wanted.has(n.id),
  );
  const ids = new Set(nodes.map((n) => n.id));
  return {
    ...graph,
    nodes,
    links: graph.links.filter((l) => ids.has(l.source) && ids.has(l.target)),
  };
}

/** Who is on an incident, in plain words ("Historian is working"). */
export function currentAgent(inc: {
  status: string;
  assigned_to: string | null;
}) {
  if (inc.status === "resolved") return "Resolved";
  if (inc.status === "needs_human") return "Waiting for a human";
  if (!inc.assigned_to) return "Waiting for Triage";
  return `${agentLabel(inc.assigned_to)} is working`;
}

/** "14 minutes" for a duration in seconds. */
export const minutes = (seconds: number) => {
  const m = Math.max(1, Math.round(seconds / 60));
  return `${m} ${m === 1 ? "minute" : "minutes"}`;
};
