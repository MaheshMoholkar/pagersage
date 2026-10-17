"use client";

// U05 incident feed (GET /incidents): newest first, a severity rail, id, age, title and who
// is on it. Live: re-polls every few seconds (SSE is per incident); new incidents slide in.
// The selection glides to the row you pick; All/Open filters with the rows animating out.
// "Show more" pages in PAGE more.

import { Info, Inbox } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { AgentBadge } from "@/components/incident/agents";
import { useNow } from "@/components/shell/Now";
import { EASE, Empty, Mono, Panel, Segmented, SevPill } from "@/components/ui";
import { api } from "@/lib/api";
import { age, currentAgent } from "@/lib/format";
import { usePolling } from "@/lib/usePolling";
import type { IncidentSummary } from "@/lib/types";

export const FEED_POLL_MS = 5000;
export const PAGE = 20;

function rail(inc: IncidentSummary) {
  if (inc.status === "resolved") return "bg-white/[0.12]";
  if (inc.status === "mitigated") return "bg-amber";
  if (inc.severity === "sev1" || inc.status === "needs_human")
    return "bg-danger shadow-[0_0_10px_rgb(255_93_108/0.7)]";
  if (inc.severity === "sev2")
    return "bg-amber shadow-[0_0_10px_rgb(255_178_36/0.5)]";
  return "bg-blue";
}

export function IncidentFeed({
  initial,
  selected,
  live,
  className = "",
}: {
  initial: IncidentSummary[];
  selected: string;
  live: boolean;
  className?: string;
}) {
  const now = useNow();
  const [limit, setLimit] = useState(PAGE);
  const [show, setShow] = useState<"all" | "open">("all");
  const fetchFeed = useCallback(
    async () => (await api.incidents({ limit })).data,
    [limit],
  );
  const incidents = usePolling(initial, fetchFeed, FEED_POLL_MS, live);
  const open = incidents.filter((i) => i.status !== "resolved");
  const shown = show === "open" ? open : incidents;
  const more = live && show === "all" && incidents.length >= limit;

  // Keep the selected incident visible inside the scrolling list (only the list scrolls:
  // scrollIntoView would also move the page, and on phones the feed is at the bottom).
  const list = useRef<HTMLUListElement>(null);
  useEffect(() => {
    const box = list.current;
    const row = box?.querySelector<HTMLElement>('[aria-current="true"]');
    if (!box || !row) return;
    const top = row.offsetTop - box.offsetTop;
    if (top < box.scrollTop) box.scrollTop = top - 8;
    else if (top + row.offsetHeight > box.scrollTop + box.clientHeight)
      box.scrollTop = top + row.offsetHeight - box.clientHeight + 8;
  }, [selected]);

  return (
    <Panel
      label="Incidents"
      title="Incidents"
      icon={<Inbox />}
      count={incidents.length}
      flush
      className={`max-h-[60vh] xl:max-h-none ${className}`}
      actions={
        <Segmented
          label="Show"
          value={show}
          onChange={setShow}
          options={[
            { value: "all", label: "All" },
            { value: "open", label: `Open ${open.length}` },
          ]}
        />
      }
      footer={
        <span className="flex gap-2">
          <Info aria-hidden="true" className="mt-0.5 size-3.5 flex-none" />
          Alerts on related services within 10 minutes join the open incident.
        </span>
      }
    >
      <ul
        ref={list}
        className="m-0 flex min-h-0 flex-1 list-none flex-col gap-0.5 overflow-y-auto p-2"
      >
        <AnimatePresence initial={false}>
          {shown.map((inc, n) => {
            const isSelected = inc.id === selected;
            const working = !["resolved", "needs_human"].includes(inc.status);
            return (
              <motion.li
                key={inc.id}
                layout="position"
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, transition: { duration: 0.15 } }}
                transition={{
                  duration: 0.4,
                  ease: EASE,
                  delay: Math.min(n, 8) * 0.03,
                }}
              >
                <Link
                  href={`/?incident=${inc.id}`}
                  aria-current={isSelected ? "true" : undefined}
                  scroll={false}
                  className="group relative flex gap-3 rounded-xl px-3 py-3 text-text transition-colors hover:text-text"
                >
                  {isSelected ? (
                    <motion.span
                      layoutId="feed-selected"
                      transition={{
                        type: "spring",
                        bounce: 0.15,
                        duration: 0.45,
                      }}
                      className="absolute inset-0 rounded-xl bg-white/[0.06] shadow-[inset_0_1px_0_rgb(255_255_255/0.06),0_0_0_1px_rgb(255_255_255/0.07)]"
                    />
                  ) : (
                    <span className="absolute inset-0 rounded-xl bg-white/[0.035] opacity-0 transition-opacity group-hover:opacity-100" />
                  )}
                  <span
                    aria-hidden="true"
                    className={`relative w-[3px] flex-none self-stretch rounded-full ${rail(inc)}`}
                  />
                  <span className="relative flex min-w-0 flex-1 flex-col gap-1.5">
                    <span className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-2">
                        <SevPill severity={inc.severity} small />
                        <Mono className="text-xs text-muted">{inc.id}</Mono>
                      </span>
                      <span className="text-[11px] text-faint tabular">
                        {age(inc.opened_at, now)}
                      </span>
                    </span>
                    <span
                      className={`line-clamp-2 text-[13px] leading-[18px] ${inc.status === "resolved" ? "text-text-2" : "font-medium"}`}
                    >
                      {inc.title}
                    </span>
                    <span
                      className={`flex items-center gap-1.5 text-xs ${inc.status === "needs_human" ? "text-sev1-fg" : working ? "text-[#a9cbff]" : "text-muted"}`}
                    >
                      {working && inc.assigned_to ? (
                        <AgentBadge
                          agent={inc.assigned_to}
                          state="active"
                          size={16}
                        />
                      ) : (
                        <span
                          aria-hidden="true"
                          className={`mx-[5px] size-1.5 rounded-full ${inc.status === "resolved" ? "bg-ok" : "bg-danger"}`}
                        />
                      )}
                      {currentAgent(inc)}
                    </span>
                  </span>
                </Link>
              </motion.li>
            );
          })}
        </AnimatePresence>
        {shown.length === 0 && (
          <li>
            <Empty>No open incidents. All quiet.</Empty>
          </li>
        )}
        {more && (
          <li>
            <button
              type="button"
              onClick={() => setLimit(limit + PAGE)}
              className="h-9 w-full cursor-pointer rounded-xl border-none bg-transparent font-[inherit] text-[13px] text-muted transition-colors hover:bg-white/[0.04] hover:text-text"
            >
              Show {PAGE} more
            </button>
          </li>
        )}
      </ul>
    </Panel>
  );
}
