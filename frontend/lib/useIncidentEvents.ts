"use client";

// U04: an incident's timeline, live. Starts from the events the page already loaded, then
// follows the SSE stream (GET /incidents/{id}/events, B04) from the last seq it has. The browser
// reconnects on its own and sends Last-Event-ID, so nothing is lost or repeated.

import { useEffect, useState } from "react";

import { eventsUrl } from "./api";
import type { AgentEvent } from "./types";

export function useIncidentEvents(
  incidentId: string,
  initial: AgentEvent[],
  live = true,
) {
  const [events, setEvents] = useState(initial);
  const lastSeq = initial.at(-1)?.seq ?? 0;

  useEffect(() => {
    if (!live) return;
    const source = new EventSource(eventsUrl(incidentId, lastSeq));
    source.addEventListener("agent", (msg) => {
      const event = JSON.parse(
        (msg as MessageEvent<string>).data,
      ) as AgentEvent;
      setEvents((prev) =>
        prev.some((e) => e.seq === event.seq) ? prev : [...prev, event],
      );
    });
    return () => source.close();
  }, [incidentId, lastSeq, live]);

  return events;
}
