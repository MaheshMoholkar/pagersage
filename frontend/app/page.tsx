// War room (design: docs/ui-handoff/design/Main.dc.html). On wide screens: the incident feed
// as a rail down the left (U05); beside it the selected incident's header and tabs, the
// verdict (what broke it, what to do), then the root-cause path (U02/U03) next to the live
// agent run (U04). Narrower: stacked, the incident first and the feed last.

import { ViewTransition } from "react";

import { IncidentGraph } from "@/components/graph/IncidentGraph";
import { IncidentHeader } from "@/components/incident/IncidentHeader";
import { PageTransition } from "@/components/shell/PageTransition";
import { Empty, StubBadge } from "@/components/ui";
import { AgentTimeline } from "@/components/warroom/AgentTimeline";
import { IncidentFeed } from "@/components/warroom/IncidentFeed";
import { Verdict, type VerdictInfo } from "@/components/warroom/Verdict";
import { api } from "@/lib/api";
import { failingNode, rootCausePath, withAlert } from "@/lib/format";

export default async function WarRoom({ searchParams }: PageProps<"/">) {
  const { incident: picked } = await searchParams;
  const feed = await api.incidents();
  const id = (typeof picked === "string" && picked) || feed.data[0]?.id;
  if (!id) {
    return (
      <PageTransition>
        <Empty>No incidents yet. Run `make inject` to start one.</Empty>
      </PageTransition>
    );
  }
  const detail = await api.incident(id);
  const { incident, timeline, graph, replay, state } = detail.data;
  const rejected = Array.isArray(state.rejected)
    ? state.rejected.map(String)
    : [];
  const reasons = Object.fromEntries(
    replay.decisions.map((d) => [d.id, d.why]),
  );
  const path = withAlert(rootCausePath(timeline), graph);
  const cause = typeof state.cause === "string" ? state.cause : null;
  const causeNode = graph.nodes.find((n) => n.id === cause);
  const decision = replay.decisions.findLast((d) => d.agent === "investigator");
  const verdict: VerdictInfo = {
    cause,
    title: causeNode?.name ?? null,
    kind: causeNode?.kind ?? null,
    service:
      typeof state.cause_service === "string" ? state.cause_service : null,
    author: path?.nodes.find((n) => n.startsWith("person:")) ?? null,
    confidence: decision?.confidence ?? null,
    rejected,
    why: decision?.why ?? null,
  };

  return (
    <PageTransition fill>
      <div className="flex flex-col gap-5 xl:grid xl:min-h-0 xl:flex-1 xl:grid-cols-[296px_minmax(0,1fr)]">
        <IncidentFeed
          initial={feed.data}
          selected={id}
          live={!feed.stub}
          className="order-last xl:order-none"
        />
        {/* Switching incidents crossfades the detail; the feed stays put. */}
        <ViewTransition key={id} enter="ps-page" exit="ps-page" default="none">
          <div className="flex min-w-0 flex-col gap-4 xl:min-h-0">
            <IncidentHeader
              incident={incident}
              tab="live"
              aside={
                <StubBadge show={feed.stub || detail.stub} what="Stub data" />
              }
            />
            <Verdict incident={incident} info={verdict} />
            <div className="flex flex-col gap-4 xl:grid xl:min-h-0 xl:flex-1 xl:grid-cols-[minmax(0,1fr)_368px]">
              <IncidentGraph
                graph={graph}
                path={path}
                failing={failingNode(graph, state)}
                rejected={rejected}
                cause={cause}
                delay={0.12}
              />
              <AgentTimeline
                key={id}
                incident={incident}
                initial={timeline}
                reasons={reasons}
                live={!detail.stub && incident.status !== "resolved"}
                delay={0.2}
              />
            </div>
          </div>
        </ViewTransition>
      </div>
    </PageTransition>
  );
}
