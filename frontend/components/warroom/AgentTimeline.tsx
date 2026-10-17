"use client";

// U04 agent run: the five agents as a pipeline, then the
// timeline on a rail, live over SSE (lib/useIncidentEvents). Pipeline state comes from the
// events themselves, so it moves as they stream in; new events slide onto the rail. Each event
// kind has its own look:
//   alert      amber bell, "Alert received", what fired
//   tool_call  blue terminal, tool_name(args) in mono (full text on hover), the result
//   finding    green check, what the agent wrote to the graph
//   decision   a card "{Agent} decided" + the reasoning; the newest one, while its agent is
//              still working, has a light running round its border and "is deciding"
//   handoff    the next agent's badge, "Handed to {Agent}" and the note it was given
//   action     page / issue / rollback, green when it went through
//   error      red cross with the reason
// "{Agent} is next" ends a running pipeline. The list follows new events while you're at
// the bottom; scroll up and "Jump to latest" appears.

import {
  Activity,
  ArrowDown,
  BellRing,
  Check,
  Terminal,
  Workflow,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import {
  AGENT_ROLE,
  AgentBadge,
  type StepState,
} from "@/components/incident/agents";
import { EASE, LiveDot, Panel } from "@/components/ui";
import { AGENTS, agentLabel, clock, pct, shortId } from "@/lib/format";
import { useIncidentEvents } from "@/lib/useIncidentEvents";
import type { AgentEvent, AgentName, IncidentSummary } from "@/lib/types";

/** Done = handed off (the Scribe: wrote the postmortem); active = started and not done. */
export function pipeline(events: AgentEvent[]): {
  steps: Record<string, StepState>;
  active: AgentName | null;
} {
  const done = new Set<string>();
  let active: AgentName | null = null;
  for (const e of events) {
    if (e.kind === "handoff" && e.agent) done.add(e.agent);
    if (e.kind === "finding" && e.data.tool === "write_postmortem")
      done.add("scribe");
    if (e.kind === "status" && e.agent && e.summary.endsWith("started"))
      active = e.agent;
    if (e.kind === "error" && !e.agent && e.summary.startsWith("Needs a human"))
      active = null;
  }
  if (active && done.has(active)) active = null;
  const steps = Object.fromEntries(
    AGENTS.map((a): [string, StepState] => [
      a,
      done.has(a) ? "done" : a === active ? "active" : "queued",
    ]),
  );
  return { steps, active };
}

const NEXT: Partial<Record<AgentName, AgentName>> = {
  triage: "investigator",
  investigator: "historian",
  historian: "responder",
  responder: "scribe",
};

function Pipeline({ steps }: { steps: Record<string, StepState> }) {
  return (
    <ol
      aria-label="Agent pipeline"
      className="m-0 grid flex-none list-none grid-cols-5 border-b border-white/[0.05] px-2 pt-3.5 pb-3"
    >
      {AGENTS.map((a, i) => {
        const prev = i > 0 ? steps[AGENTS[i - 1]] : null;
        const fill = prev === "done" ? (steps[a] === "queued" ? 0.5 : 1) : 0;
        return (
          <li
            key={a}
            className="relative flex min-w-0 flex-col items-center gap-1.5"
            title={`${agentLabel(a)}: ${AGENT_ROLE[a]}`}
          >
            {i > 0 && (
              <span
                aria-hidden="true"
                className="absolute top-[14px] right-[calc(50%+20px)] left-[calc(-50%+20px)] h-px bg-white/[0.08]"
              >
                <motion.span
                  className={`block h-full ${steps[a] === "active" ? "bg-[linear-gradient(90deg,var(--ok),var(--blue))]" : "bg-ok/70"}`}
                  initial={{ width: 0 }}
                  animate={{ width: pct(fill) }}
                  transition={{ duration: 0.8, ease: EASE }}
                />
              </span>
            )}
            <AgentBadge agent={a} state={steps[a]} />
            <span
              className={`max-w-full truncate px-0.5 text-[11px] ${steps[a] === "active" ? "font-medium text-text" : steps[a] === "done" ? "text-text-2" : "text-faint"}`}
            >
              {agentLabel(a)}
              <span className="sr-only">: {steps[a]}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function AgentTimeline({
  incident,
  initial,
  reasons,
  live,
  delay = 0,
}: {
  incident: IncidentSummary;
  initial: AgentEvent[];
  reasons: Record<string, string>; // decision id -> why (from the replay)
  live: boolean;
  delay?: number;
}) {
  const events = useIncidentEvents(incident.id, initial, live);
  const { steps, active } = pipeline(events);
  const latestDecision = events.findLast((e) => e.kind === "decision")?.seq;
  const next = active ? NEXT[active] : undefined;
  const [firstSeq] = useState(initial.at(-1)?.seq ?? 0); // later events arrived live
  // Agents after Triage get their badge from the handoff before them, not a "started" row.
  const rows = events.filter(
    (e) =>
      !(
        e.kind === "status" &&
        e.agent &&
        e.agent !== "triage" &&
        e.summary.endsWith("started")
      ),
  );

  const list = useRef<HTMLOListElement>(null);
  const [pinned, setPinned] = useState(true);
  useEffect(() => {
    const el = list.current;
    // Instant: a smooth scroll fires scroll events on the way that would unpin the list.
    if (el && pinned) el.scrollTop = el.scrollHeight;
  }, [events.length, pinned]);
  const onScroll = () => {
    const el = list.current;
    if (el) setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 32);
  };

  return (
    <Panel
      label="Agent run"
      title="Agent run"
      icon={<Workflow />}
      count={events.length}
      flush
      tone={live ? "agent" : "none"}
      still
      className="max-h-[75vh] xl:max-h-none"
      actions={
        live ? (
          <span className="flex h-6 items-center gap-1.5 rounded-full bg-blue-tint/70 px-2.5 text-[11px] font-medium text-[#a9cbff] ring-1 ring-blue/20 ring-inset">
            <LiveDot size={6} />
            Streaming
          </span>
        ) : (
          <span className="text-[11px] text-faint">Replay</span>
        )
      }
    >
      <Pipeline steps={steps} />

      <div className="relative flex min-h-0 flex-1 flex-col">
        <ol
          ref={list}
          onScroll={onScroll}
          aria-label="Timeline"
          aria-live="polite"
          className="m-0 flex min-h-0 flex-1 list-none flex-col overflow-y-auto px-4 pt-4 pb-2"
        >
          {rows.map((e, n) => (
            <motion.li
              key={e.seq}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: 0.45,
                ease: EASE,
                delay:
                  e.seq > firstSeq ? 0 : delay + 0.15 + Math.min(n, 14) * 0.035,
              }}
            >
              <EventItem
                event={e}
                incidentId={incident.id}
                why={reasons[String(e.data.decision_id ?? "")]}
                deciding={e.seq === latestDecision && e.agent === active}
                steps={steps}
              />
            </motion.li>
          ))}
          {next && (
            <motion.li
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: delay + 0.8 }}
              className="flex items-center gap-3 pt-1 pb-2"
            >
              <span className="flex w-7 flex-none justify-center opacity-60">
                <AgentBadge agent={next} state="queued" size={24} />
              </span>
              <span className="text-xs text-faint">
                {agentLabel(next)} is next
              </span>
              <svg
                aria-hidden="true"
                className="h-px flex-1"
                preserveAspectRatio="none"
              >
                <line
                  x1="0"
                  y1="0.5"
                  x2="100%"
                  y2="0.5"
                  stroke="var(--line-strong)"
                  className="ps-dash"
                />
              </svg>
            </motion.li>
          )}
        </ol>
        <AnimatePresence>
          {!pinned && (
            <motion.button
              type="button"
              onClick={() => setPinned(true)}
              initial={{ opacity: 0, y: 8, x: "-50%" }}
              animate={{ opacity: 1, y: 0, x: "-50%" }}
              exit={{ opacity: 0, y: 8, x: "-50%" }}
              className="absolute bottom-3 left-1/2 flex h-8 cursor-pointer items-center gap-1.5 rounded-full px-3.5 font-[inherit] text-xs text-text glass-float"
            >
              Jump to latest{" "}
              <ArrowDown aria-hidden="true" className="size-3.5" />
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </Panel>
  );
}

const TILE = {
  amber: "bg-amber-tint text-amber ring-amber/30",
  blue: "bg-blue-tint text-blue ring-blue/30",
  ok: "bg-ok-bg text-ok ring-ok/30",
  danger: "bg-sev1-bg text-danger ring-danger/30",
  neutral: "bg-white/[0.04] text-muted ring-white/10",
};

/** One step on the rail: a node, the line down to the next step, and the content. */
function Rail({
  node,
  ts,
  title,
  titleText,
  children,
}: {
  node: React.ReactNode;
  ts?: number;
  title: React.ReactNode;
  titleText?: string; // full text on hover when the title is cut to one line
  children?: React.ReactNode;
}) {
  return (
    <div className="flex gap-3">
      <div className="flex w-7 flex-none flex-col items-center">
        {node}
        <span aria-hidden="true" className="my-1 w-px flex-1 bg-white/[0.07]" />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1 pb-4">
        <div className="flex min-h-6 items-center justify-between gap-3">
          <span
            className="min-w-0 truncate text-[13px] leading-5"
            title={titleText}
          >
            {title}
          </span>
          {ts != null && (
            <time className="flex-none font-mono text-[11px] text-faint tabular">
              {clock(ts)}
            </time>
          )}
        </div>
        {children}
      </div>
    </div>
  );
}

function Tile({
  icon: Icon,
  tone,
}: {
  icon: LucideIcon;
  tone: keyof typeof TILE;
}) {
  return (
    <span
      aria-hidden="true"
      className={`flex size-6 items-center justify-center rounded-full ring-1 ${TILE[tone]}`}
    >
      <Icon className="size-3" strokeWidth={2.2} />
    </span>
  );
}

const Body = ({ children }: { children: React.ReactNode }) => (
  <div className="line-clamp-2 text-xs leading-[18px] [overflow-wrap:anywhere] text-muted">
    {children}
  </div>
);

/** blast_radius("payments-db"): the input values, short, as the design writes them. */
function callArgs(input: unknown): string {
  if (!input || typeof input !== "object") return "";
  return Object.values(input as Record<string, unknown>)
    .map((v) =>
      typeof v === "string"
        ? `"${shortId(v)}"`
        : Array.isArray(v)
          ? `[${v.length}]`
          : String(v),
    )
    .join(", ");
}

/** The result half of a tool_call summary: "blast_radius(...): 4 found. x, y" -> "4 found. x, y". */
function resultLine(e: AgentEvent): string {
  const tool = String(e.data.tool ?? "");
  const cut = e.summary.indexOf("): ");
  return e.summary.startsWith(`${tool}(`) && cut > 0
    ? e.summary.slice(cut + 3)
    : e.summary;
}

function EventItem({
  event: e,
  incidentId,
  why,
  deciding,
  steps,
}: {
  event: AgentEvent;
  incidentId: string;
  why?: string;
  deciding: boolean;
  steps: Record<string, StepState>;
}) {
  switch (e.kind) {
    case "status":
      if (e.data.alert_id) {
        return (
          <Rail
            node={<Tile icon={BellRing} tone="amber" />}
            ts={e.ts}
            title={
              <span className="font-medium">
                {e.data.merged ? "Alert joined" : "Alert received"}
              </span>
            }
          >
            <Body>
              {e.summary
                .replace(/^Alert alt-\d+: /, "")
                .replace(/ (Incident opened|Joined the open incident)\.$/, "")}
            </Body>
          </Rail>
        );
      }
      if (e.agent && e.summary.endsWith("started")) {
        return (
          <Rail
            node={
              <AgentBadge agent={e.agent} state={steps[e.agent]} size={24} />
            }
            ts={e.ts}
            title={
              <span className="font-medium">
                {agentLabel(e.agent)} picked it up
              </span>
            }
          />
        );
      }
      return (
        <Rail
          node={<Tile icon={Activity} tone="neutral" />}
          ts={e.ts}
          title={e.summary}
        />
      );
    case "tool_call":
    case "tool_result": {
      const tool = String(e.data.tool ?? "tool");
      const args = callArgs(e.data.input);
      return (
        <Rail
          node={<Tile icon={Terminal} tone="blue" />}
          ts={e.ts}
          titleText={`${tool}(${args})`}
          title={
            <span className="font-mono text-xs text-text">
              {tool}
              <span className="text-muted">({args})</span>
            </span>
          }
        >
          <Body>
            {resultLine(e)}
            {tool === "suspect_changes" && (
              <>
                {" "}
                <Link
                  href={`/incidents/${incidentId}/investigation`}
                  transitionTypes={["nav-forward"]}
                >
                  See the scores →
                </Link>
              </>
            )}
          </Body>
        </Rail>
      );
    }
    case "finding":
      return (
        <Rail
          node={<Tile icon={Check} tone="ok" />}
          ts={e.ts}
          title={
            <span className="font-mono text-xs text-text">
              {String(e.data.tool)}
            </span>
          }
        >
          <Body>{e.summary.replace(/^\w+: /, "")}</Body>
        </Rail>
      );
    case "decision":
      return (
        <Rail
          node={
            <span
              className={`flex size-6 items-center justify-center rounded-full ring-1 ${TILE.amber}`}
            >
              <span
                className={`size-2 rounded-full bg-amber ${deciding ? "ps-live" : ""}`}
              />
            </span>
          }
          title={
            <span className="flex items-center gap-1.5 text-[11px] font-semibold tracking-[0.06em] text-amber uppercase">
              {agentLabel(e.agent)} {deciding ? "is deciding" : "decided"}
            </span>
          }
          ts={e.ts}
        >
          <div
            className={`relative mt-0.5 flex flex-col gap-1.5 rounded-xl bg-[linear-gradient(180deg,rgb(255_178_36/0.07),rgb(255_178_36/0.02))] px-3 py-2.5 ring-1 ring-amber/20 ring-inset ${deciding ? "ps-beam" : ""}`}
          >
            <div className="text-[13px] leading-5 font-medium text-text">
              {String(e.data.what ?? e.summary)}
            </div>
            {why && (
              <div className="text-xs leading-[18px] text-text-2/80">{why}</div>
            )}
          </div>
        </Rail>
      );
    case "handoff": {
      const to = String(e.data.to ?? "");
      return (
        <Rail
          node={
            <AgentBadge agent={to} state={steps[to] ?? "queued"} size={24} />
          }
          ts={e.ts}
          title={
            <span className="text-text-2">
              Handed to{" "}
              <span className="font-medium text-text">{agentLabel(to)}</span>
            </span>
          }
        >
          <Body>{e.summary}</Body>
        </Rail>
      );
    }
    case "action": {
      const ok = e.data.ok !== false;
      const url = typeof e.data.url === "string" ? e.data.url : null;
      return (
        <Rail
          node={<Tile icon={Zap} tone={ok ? "ok" : "danger"} />}
          ts={e.ts}
          title={<span className="font-medium">{e.summary}</span>}
          titleText={e.summary}
        >
          {url && (
            <Body>
              <a href={url}>{url.replace(/^https:\/\//, "")}</a>
            </Body>
          )}
        </Rail>
      );
    }
    case "error":
      return (
        <Rail
          node={<Tile icon={X} tone="danger" />}
          ts={e.ts}
          titleText={e.summary}
          title={<span className="font-medium text-sev1-fg">{e.summary}</span>}
        />
      );
  }
}
