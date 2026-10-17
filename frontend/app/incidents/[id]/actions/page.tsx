// Actions and Resolve, U09: the page sent,
// the issue opened, reverting the cause (simulated), then Resolve, the Scribe's postmortem and
// the runbook counter.

import { ActionsView } from "@/components/actions/ActionsView";
import { PageTransition } from "@/components/shell/PageTransition";
import { api } from "@/lib/api";
import { rootCausePath } from "@/lib/format";

export const metadata = { title: "Actions" };

export default async function Actions({
  params,
}: PageProps<"/incidents/[id]/actions">) {
  const { id } = await params;
  const [detail, suspects, memory] = await Promise.all([
    api.incident(id),
    api.suspects(id),
    api.memory(id),
  ]);
  const { incident, timeline, state, graph } = detail.data;
  const cause =
    suspects.data.cause ??
    (typeof state.cause === "string" ? state.cause : null);
  const causeSid =
    suspects.data.suspects.find((s) => s.change_id === cause)?.service_id ??
    (typeof state.cause_service === "string" ? state.cause_service : null);
  const causeService = causeSid
    ? {
        id: causeSid,
        tier: graph.nodes.find((n) => n.id === causeSid)?.tier ?? null,
      }
    : null;
  const path = rootCausePath(timeline)?.nodes ?? memory.data.path;
  const stub = detail.stub || suspects.stub || memory.stub;

  return (
    <PageTransition>
      <ActionsView
        key={incident.id}
        initial={detail.data}
        cause={cause}
        causeService={causeService}
        path={path}
        runbook={memory.data.runbooks[0] ?? null}
        live={!stub}
        stub={stub}
      />
    </PageTransition>
  );
}
