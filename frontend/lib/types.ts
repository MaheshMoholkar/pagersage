// API formats, mirrored from the backend contracts (docs/contracts.md). The Python models are
// the source of truth: when one changes there, change it here in the same commit.

export type AgentName =
  "triage" | "investigator" | "historian" | "responder" | "scribe" | "brain";
export type Severity = "sev1" | "sev2" | "sev3";
export type IncidentStatus =
  "open" | "investigating" | "mitigated" | "resolved" | "needs_human";
export type EventKind =
  | "status"
  | "tool_call"
  | "tool_result"
  | "finding"
  | "decision"
  | "handoff"
  | "action"
  | "error";

/** What the graph canvas lights up. Edges are [from_id, REL_TYPE, to_id]. */
export interface Highlight {
  nodes: string[];
  edges: [string, string, string][];
}

/** One timeline line (contracts/events.py). SSE `id` is `seq`, `event: agent`. */
export interface AgentEvent {
  incident_id: string;
  seq: number;
  ts: number; // epoch seconds
  agent: AgentName | null; // null = system event
  kind: EventKind;
  summary: string;
  data: Record<string, unknown>;
  highlight: Highlight;
}

/** GET /incidents rows (incidents.py IncidentSummary). */
export interface IncidentSummary {
  id: string;
  title: string;
  severity: Severity | null;
  status: IncidentStatus | string;
  opened_at: number | null;
  resolved_at: number | null;
  assigned_to: string | null; // agent name or person handle
  alerts: number;
  services: string[]; // AFFECTED service ids (set at triage)
}

export interface AlertOut {
  id: string;
  service_id: string;
  signal: string;
  value: number;
  threshold: number;
  severity: string;
  ts: number;
}

export interface DecisionRecord {
  id: string;
  agent: string;
  what: string;
  why: string;
  confidence: number;
  evidence: string[];
  precedents: string[];
  policies: string[];
}

export interface HandoffRecord {
  id: string;
  ts: number;
  from_agent: string;
  to_agent: string;
  note: string;
}

export interface IncidentReplay {
  incident_id: string;
  title: string;
  status: string;
  decisions: DecisionRecord[];
  handoffs: HandoffRecord[];
  event_count: number;
}

/** GET /graph (graphview.py), shaped for @falkordb/canvas. */
export interface GraphNode {
  id: string;
  name: string;
  kind: string; // Service, Alert, Deploy, Commit, Person, ConfigChange...
  team?: string | null;
  tier?: number | null;
  criticality?: number | null;
  fragility?: number | null;
  health?: number | null;
}

export interface GraphLink {
  source: string;
  target: string;
  type: string; // DEPENDS_ON, FIRED_ON, TARGETED...
  weight?: number | null;
  calls_per_min?: number | null;
}

/** GET /oncall: one row per team with a shift now (docs/contracts.md "On call now"). */
export interface OnCallNow {
  team: string;
  handle: string;
  name: string;
  until: number; // when the shift ends
}

export interface GraphView {
  nodes: GraphNode[];
  links: GraphLink[];
  highlight: Highlight;
}

/** GET /incidents/{id} (incidents.py IncidentDetail). */
export interface Postmortem {
  title: string;
  body: string; // markdown: ## What happened, ## Why, ## What fixed it, ## Follow-up
  ts: number | null;
}

export interface IncidentDetail {
  incident: IncidentSummary;
  summary: string;
  postmortem: Postmortem | null; // once the Scribe has written it (after resolve)
  state: Record<string, unknown>; // shared agent scratchpad: cause, path, runbook, ...
  alerts: AlertOut[];
  timeline: AgentEvent[];
  replay: IncidentReplay;
  graph: GraphView;
}

/** POST /ask (contracts/ask.py). */
export interface AskOut {
  answer: string;
  evidence: string[]; // node ids to light up
}

// ── Investigation screen: GET /incidents/{id}/suspects and /memory (investigation.py) ────

export interface Suspect {
  change_id: string; // dep-.... or cfg-....
  change_type: "deploy" | "config";
  service_id: string;
  ts: number;
  dist: number;
  fragility: number;
  commits: { sha: string; message: string; author: string | null }[];
  score: number;
  score_parts: {
    recency: number;
    distance: number;
    fragility: number;
    anomaly: number;
  };
}

export interface RunbookRef {
  id: string;
  title: string;
  success_count: number;
}

export interface SimilarIncident {
  id: string;
  title: string;
  score: number; // cosine similarity, higher is closer
  shared_services: number;
  runbooks: RunbookRef[];
  postmortem_titles: string[];
}

export interface SimilarIncidents {
  graph_ranked: SimilarIncident[];
  vector_only: SimilarIncident[];
}

export interface RunbookHit {
  id: string;
  title: string;
  steps: string[];
  success_count: number;
  fail_count: number;
  success_rate: number;
}

export interface ActionResult {
  action: "page" | "issue" | "rollback";
  ok: boolean;
  detail: string;
  url: string | null;
}

export interface SuspectsView {
  alerting_service_id: string | null; // where the ranking starts
  since: number; // first alert minus 2 h
  suspects: Suspect[]; // best first
  cause: string | null; // CAUSED_BY, once the Investigator has decided
  rejected: string[]; // change ids ruled out (Incident.state)
}

export interface MemoryView {
  path: string[]; // service ids the similar incidents are ranked against
  similar: SimilarIncidents | null; // null until triage stores the embedding
  runbook_service_id: string | null;
  runbooks: RunbookHit[];
}
