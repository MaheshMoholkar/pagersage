"use client";

// U02 company graph: every service,
// coloured by owning team, sized by criticality (pageRank), fragile ones ringed red (top
// betweenness), unowned ones dashed. `evidence` (U08 Ask) lights its nodes and edges in amber
// with particles flowing (see withEvidence); `focus` glides the view to one of them. The "Who
// actually ships together" toggle (G18) is a stretch goal: not built.

import { Maximize2, Network } from "lucide-react";
import { useMemo, useState } from "react";

import { GraphCanvas } from "@/components/graph/GraphCanvas";
import { Panel } from "@/components/ui";
import { NO_TEAM_COLOR, shortId, teamColor } from "@/lib/format";
import type { GraphView, Highlight } from "@/lib/types";

const KINDS: Record<string, string> = {
  person: "Person",
  team: "Team",
  rb: "Runbook",
  pol: "Policy",
  pm: "Postmortem",
  INC: "Incident",
};
export const kindOf = (id: string) => KINDS[id.split(/[:-]/)[0]] ?? "Node";

/** Ask evidence on the company graph. Evidence services are lit with the DEPENDS_ON edges
 *  between them. Evidence the graph doesn't hold (people, incidents, runbooks) is added next
 *  to the evidence services with EVIDENCE links, so the answer's trail is visible. */
export function withEvidence(
  graph: GraphView,
  evidence: string[],
): { graph: GraphView; highlight: Highlight | null } {
  if (!evidence.length) return { graph, highlight: null };
  const have = new Set(graph.nodes.map((n) => n.id));
  const ids = new Set(evidence);
  const services = evidence.filter((id) => have.has(id));
  const extra = evidence.filter((id) => !have.has(id));
  const links = extra.flatMap((id) =>
    services.map((sid) => ({ source: id, target: sid, type: "EVIDENCE" })),
  );
  return {
    graph: {
      ...graph,
      nodes: [
        ...graph.nodes,
        ...extra.map((id) => ({ id, name: shortId(id), kind: kindOf(id) })),
      ],
      links: [...graph.links, ...links],
    },
    highlight: {
      nodes: evidence,
      edges: [
        ...graph.links.filter((l) => ids.has(l.source) && ids.has(l.target)),
        ...links,
      ].map((l) => [l.source, l.type, l.target] as [string, string, string]),
    },
  };
}

export function CompanyGraph({
  graph,
  evidence = [],
  focus = null,
}: {
  graph: GraphView;
  evidence?: string[];
  focus?: { id: string; n: number } | null;
}) {
  const [fit, setFit] = useState(0);
  const teams = useMemo(
    () =>
      [
        ...new Set(
          graph.nodes.map((n) => n.team).filter((t): t is string => !!t),
        ),
      ].sort(),
    [graph],
  );
  const unowned = graph.nodes.some((n) => n.kind === "Service" && !n.team);
  const lit = useMemo(() => withEvidence(graph, evidence), [graph, evidence]);
  const services = graph.nodes.filter((n) => n.kind === "Service");
  const label =
    `Service map: ${services.length} services owned by ${teams.length} teams.` +
    (evidence.length
      ? ` Highlighted: ${evidence.map(shortId).join(", ")}.`
      : "");

  return (
    <Panel
      label="Service map"
      title="Services"
      icon={<Network />}
      count={services.length}
      flush
      still
      className="h-[540px] lg:h-[640px]"
      actions={
        <>
          <span className="hidden text-xs text-muted sm:inline">
            Size = criticality
          </span>
          <button
            type="button"
            title="Fit to view"
            onClick={() => setFit(fit + 1)}
            className="flex size-8 cursor-pointer items-center justify-center rounded-[9px] border-none bg-transparent text-muted transition-colors hover:bg-white/[0.07] hover:text-text active:scale-95"
          >
            <Maximize2 aria-hidden="true" className="size-4" />
            <span className="sr-only">Fit</span>
          </button>
        </>
      }
      footer={
        <ul
          aria-label="Legend"
          className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1.5 p-0"
        >
          {teams.map((t) => (
            <li key={t} className="flex items-center gap-1.5">
              <span
                className="size-2 rounded-full"
                style={{
                  background: teamColor(t),
                  boxShadow: `0 0 8px ${teamColor(t)}`,
                }}
              />
              {t}
            </li>
          ))}
          {unowned && (
            <li className="flex items-center gap-1.5">
              <span
                className="size-2 rounded-full border border-dashed"
                style={{ borderColor: NO_TEAM_COLOR }}
              />
              No owning team
            </li>
          )}
          <li className="flex items-center gap-1.5">
            <span className="size-2 rounded-full border-2 border-danger" />
            Fragile
          </li>
          {evidence.length > 0 && (
            <li className="flex items-center gap-1.5">
              <span className="h-0.5 w-3 rounded bg-amber shadow-[0_0_6px_var(--amber)]" />
              Evidence
            </li>
          )}
        </ul>
      }
    >
      <div
        role="img"
        aria-label={label}
        className="relative min-h-0 flex-1 dot-grid"
      >
        <GraphCanvas
          graph={lit.graph}
          highlight={lit.highlight}
          colorBy="team"
          height="fill"
          fit={fit}
          focus={focus}
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_60%,rgb(5_6_10/0.6))]"
        />
      </div>
    </Panel>
  );
}
