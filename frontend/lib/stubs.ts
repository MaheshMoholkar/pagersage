// Stub data for building the UI without a backend: the pool-exhaustion scenario, in the API's
// own formats. The JSON in lib/stubs/ was generated from the real backend (seeded Kestrel Pay
// plus the injected scenario), with a hand-written agent timeline stopped mid-run (Historian
// working) so every pipeline state shows. Names and numbers are demo placeholders.

import askJson from "./stubs/ask-who-knows-payments-db.json";
import companyJson from "./stubs/company-graph.json";
import detailJson from "./stubs/incident-INC-051.json";
import incidentsJson from "./stubs/incidents.json";
import memoryJson from "./stubs/memory-INC-051.json";
import onCallJson from "./stubs/oncall.json";
import suspectsJson from "./stubs/suspects-INC-051.json";
import type {
  AskOut,
  GraphView,
  IncidentDetail,
  IncidentSummary,
  MemoryView,
  OnCallNow,
  SuspectsView,
} from "./types";

export const DEMO_INCIDENT = "INC-051";

export const incidents = incidentsJson as IncidentSummary[];
export const companyGraph = companyJson as unknown as GraphView;
export const askAnswer = askJson as AskOut;
export const onCall = onCallJson as OnCallNow[];

/** Every id gets INC-051's detail: there is one scripted incident. */
export const incidentDetail = (id: string): IncidentDetail => {
  const detail = detailJson as unknown as IncidentDetail;
  return id === DEMO_INCIDENT
    ? detail
    : { ...detail, incident: { ...detail.incident, id } };
};
// One scripted incident, so these take no id.
export const suspects = () => suspectsJson as SuspectsView;
export const memory = () => memoryJson as MemoryView;
