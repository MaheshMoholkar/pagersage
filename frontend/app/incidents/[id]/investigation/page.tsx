// Investigation: U06 suspects and the
// score breakdown, U07 memory (text similarity vs re-ranked with the graph) and the runbook.

import { IncidentHeader } from "@/components/incident/IncidentHeader";
import { Memory } from "@/components/investigation/Memory";
import { Suspects } from "@/components/investigation/Suspects";
import { PageTransition } from "@/components/shell/PageTransition";
import { Reveal, SectionHeader, StubBadge } from "@/components/ui";
import { api } from "@/lib/api";

export const metadata = { title: "Investigation" };

export default async function Investigation({
  params,
}: PageProps<"/incidents/[id]/investigation">) {
  const { id } = await params;
  const [detail, suspects, memory] = await Promise.all([
    api.incident(id),
    api.suspects(id),
    api.memory(id),
  ]);
  const { incident, graph, replay } = detail.data;
  const names = Object.fromEntries(graph.nodes.map((n) => [n.id, n.name]));
  // The Investigator's reasoning, shown for the change it picked.
  const decided = replay.decisions.find((d) => d.agent === "investigator");
  const reasons: Record<string, string> =
    decided && suspects.data.cause
      ? { [suspects.data.cause]: decided.why }
      : {};

  return (
    <PageTransition>
      <IncidentHeader
        incident={incident}
        tab="investigation"
        aside={
          <StubBadge
            show={detail.stub || suspects.stub || memory.stub}
            what="Stub data"
          />
        }
      />
      <Reveal delay={0.05} className="pt-2">
        <SectionHeader
          eyebrow="Suspects"
          title="Which change broke it"
          description="Every change in the last two hours, scored by how recent it is, how close it sits to the failing service, how fragile that service is and how abnormal it looks now."
        />
      </Reveal>
      <Suspects view={suspects.data} names={names} reasons={reasons} />
      <Memory view={memory.data} incidentId={incident.id} />
    </PageTransition>
  );
}
