"use client";

// The incident's header on its three screens: severity, id, status, when it opened, the title,
// who is on it, and the incident's tabs: Live (the war room), Investigation, Actions. A soft
// glow behind it takes the incident's state colour. Moving between tabs slides the page in the
// tab's direction; the header itself morphs into place (a shared view-transition name).

import { Radar, ScanSearch, Zap } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { ViewTransition, type ReactNode } from "react";

import { useNow } from "@/components/shell/Now";
import { Mono, SevPill, SPRING, StatusPill } from "@/components/ui";
import { age, currentAgent, hhmm, minutes } from "@/lib/format";
import type { IncidentSummary } from "@/lib/types";

import { AgentBadge } from "./agents";

export type IncidentTab = "live" | "investigation" | "actions";

const TABS: { tab: IncidentTab; label: string; icon: typeof Radar }[] = [
  { tab: "live", label: "Live", icon: Radar },
  { tab: "investigation", label: "Investigation", icon: ScanSearch },
  { tab: "actions", label: "Actions", icon: Zap },
];

const href = (id: string, tab: IncidentTab) =>
  tab === "live" ? `/?incident=${id}` : `/incidents/${id}/${tab}`;

function glow(inc: IncidentSummary) {
  if (inc.status === "resolved") return "rgb(61 220 151 / 0.10)";
  if (inc.status === "mitigated") return "rgb(255 178 36 / 0.10)";
  if (inc.severity === "sev1" || inc.status === "needs_human")
    return "rgb(255 93 108 / 0.13)";
  return "rgb(106 168 255 / 0.12)";
}

export function IncidentTabs({
  id,
  current,
}: {
  id: string;
  current: IncidentTab;
}) {
  const at = TABS.findIndex((t) => t.tab === current);
  return (
    <nav
      aria-label="Incident"
      className="flex flex-none rounded-xl border border-white/[0.07] bg-black/30 p-1"
    >
      {TABS.map((t, i) => {
        const on = t.tab === current;
        return (
          <Link
            key={t.tab}
            href={href(id, t.tab)}
            scroll={false}
            aria-current={on ? "page" : undefined}
            transitionTypes={
              on ? undefined : [i > at ? "nav-forward" : "nav-back"]
            }
            className={`relative flex h-8 items-center gap-2 rounded-[9px] px-3 text-[13px] font-medium transition-colors ${on ? "text-text hover:text-text" : "text-muted hover:text-text"}`}
          >
            {on && (
              <motion.span
                layoutId={`incident-tab-${id}`}
                transition={SPRING}
                className="absolute inset-0 rounded-[9px] bg-white/[0.09] shadow-[inset_0_1px_0_rgb(255_255_255/0.08),0_2px_8px_rgb(0_0_0/0.35)]"
              />
            )}
            <t.icon aria-hidden="true" className="relative size-4" />
            <span className="relative">{t.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

/** Who is on it now, after the status pill ("Historian is working"), or how long it took. */
function AgentStatus({ incident }: { incident: IncidentSummary }) {
  if (incident.status === "resolved") {
    return incident.resolved_at && incident.opened_at ? (
      <span className="text-ok-fg">
        in {minutes(incident.resolved_at - incident.opened_at)}
      </span>
    ) : null;
  }
  if (incident.status === "needs_human") return null;
  return (
    <span className="flex items-center gap-1.5 font-medium text-[#a9cbff]">
      <AgentBadge
        agent={incident.assigned_to ?? "triage"}
        state="active"
        size={18}
      />
      {currentAgent(incident)}
    </span>
  );
}

export function IncidentHeader({
  incident,
  tab,
  aside,
}: {
  incident: IncidentSummary;
  tab: IncidentTab;
  aside?: ReactNode; // e.g. the stub badge
}) {
  const now = useNow();
  const services = incident.services?.length ?? 0;
  return (
    <ViewTransition name="incident-header" share="ps-morph" default="none">
      <section
        aria-label="Incident"
        className="relative flex flex-none flex-wrap items-center justify-between gap-x-6 gap-y-3"
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-28 -left-16 h-60 w-[min(720px,90%)] rounded-full blur-3xl"
          style={{
            background: `radial-gradient(closest-side, ${glow(incident)}, transparent)`,
          }}
        />
        <div className="relative flex min-w-0 flex-1 basis-[min(100%,560px)] flex-col gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1.5 text-xs text-muted">
            <SevPill severity={incident.severity} />
            <Mono className="text-[13px] text-text-2">{incident.id}</Mono>
            <StatusPill status={incident.status} />
            {/* On Live the feed and the agent run already say who is working. */}
            {tab !== "live" && <AgentStatus incident={incident} />}
            <span className="text-faint" aria-hidden="true">
              ·
            </span>
            <span>
              Opened{" "}
              {incident.opened_at ? (
                <Mono>{hhmm(incident.opened_at)} UTC</Mono>
              ) : (
                "?"
              )}
              , {age(incident.opened_at, now)} ago
            </span>
            <span className="text-faint" aria-hidden="true">
              ·
            </span>
            <span>
              {incident.alerts} {incident.alerts === 1 ? "alert" : "alerts"}
              {services > 0 &&
                `, ${services} ${services === 1 ? "service" : "services"}`}
            </span>
            {aside}
          </div>
          <h1 className="m-0 text-[22px] leading-[30px] font-semibold tracking-[-0.02em] text-pretty sm:text-2xl sm:leading-8">
            {incident.title}
          </h1>
        </div>
        <div className="relative">
          <IncidentTabs id={incident.id} current={tab} />
        </div>
      </section>
    </ViewTransition>
  );
}
