// Company brain (design: docs/ui-handoff/design/CompanyBrain.dc.html): U08 Ask box and U02
// company graph, the answer's evidence lit on it. `?q=` (from the command palette) asks on
// arrival. The insight panels (most fragile, one-person knowledge, no owner) and the "who
// actually ships together" toggle are optional in the handoff: ask before building them.
// No page transition here: only the graph animates on this page.

import { BrainView } from "@/components/brain/BrainView";
import { api } from "@/lib/api";

export const metadata = { title: "Company brain" };

export default async function CompanyBrain({
  searchParams,
}: PageProps<"/brain">) {
  const { q } = await searchParams;
  const graph = await api.graph();
  return (
    <BrainView
      key={typeof q === "string" ? q : ""}
      graph={graph.data}
      stub={graph.stub}
      initialQuestion={typeof q === "string" && q.trim() ? q : null}
    />
  );
}
