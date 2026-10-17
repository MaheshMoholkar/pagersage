"use client";

// The answer, under the incident header: what broke it, how sure the Investigator is, and the
// two places to go next (why this change, review the fix). Before the Investigator decides it
// says what is happening; once resolved, how long it took.

import { ArrowRight, CircleCheck, ScanSearch, Sparkles } from "lucide-react";
import { motion } from "motion/react";

import { AgentBadge } from "@/components/incident/agents";
import { ButtonLink, EASE, Mono } from "@/components/ui";
import { minutes, shortId } from "@/lib/format";
import type { IncidentSummary } from "@/lib/types";

export type VerdictInfo = {
  cause: string | null; // change id
  title: string | null; // "max_pool_size 200 → 60"
  kind: string | null; // ConfigChange, Deploy
  service: string | null;
  author: string | null;
  confidence: number | null;
  rejected: string[];
  why: string | null;
};

/** A ring that fills to the confidence. */
function Confidence({ value }: { value: number }) {
  const r = 19;
  const c = 2 * Math.PI * r;
  return (
    <span
      className="relative flex size-12 flex-none items-center justify-center"
      title={`The Investigator is ${Math.round(value * 100)}% confident`}
    >
      <svg
        viewBox="0 0 48 48"
        className="absolute inset-0 -rotate-90"
        aria-hidden="true"
      >
        <circle
          cx="24"
          cy="24"
          r={r}
          fill="none"
          stroke="rgb(255 178 36 / 0.15)"
          strokeWidth="3.5"
        />
        <motion.circle
          cx="24"
          cy="24"
          r={r}
          fill="none"
          stroke="url(#ps-conf)"
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c * (1 - value) }}
          transition={{ duration: 1.2, delay: 0.35, ease: EASE }}
          style={{ filter: "drop-shadow(0 0 4px rgb(255 178 36 / 0.6))" }}
        />
        <defs>
          <linearGradient id="ps-conf" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#ffd27a" />
            <stop offset="1" stopColor="#ff9a2e" />
          </linearGradient>
        </defs>
      </svg>
      <span className="font-mono text-[11px] font-semibold text-on-amber-tint tabular">
        {Math.round(value * 100)}%
      </span>
    </span>
  );
}

const KIND: Record<string, string> = {
  ConfigChange: "Config change",
  Deploy: "Deploy",
};

export function Verdict({
  incident,
  info,
}: {
  incident: IncidentSummary;
  info: VerdictInfo;
}) {
  const base = `/incidents/${incident.id}`;
  const resolved = incident.status === "resolved";

  // The open states fade up into place; the resolved banner is simply there.
  const shell = (tone: string, children: React.ReactNode, still = false) => (
    <motion.section
      aria-label="Root cause"
      aria-live="polite"
      initial={still ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay: 0.08, ease: EASE }}
      className={`relative flex flex-none flex-wrap items-center gap-x-4 gap-y-3 overflow-hidden rounded-panel px-4 py-3 glass ${tone}`}
    >
      {children}
    </motion.section>
  );

  if (resolved) {
    return shell(
      "before:absolute before:inset-y-0 before:left-0 before:w-48 before:bg-[radial-gradient(ellipse_at_left,rgb(61_220_151/0.14),transparent_70%)]",
      <>
        <span className="relative flex size-10 flex-none items-center justify-center rounded-full bg-ok-bg text-ok ring-1 ring-ok/30">
          <CircleCheck aria-hidden="true" className="size-5" />
        </span>
        <div className="relative flex min-w-0 flex-1 flex-col">
          <span className="text-[11px] font-semibold tracking-[0.08em] text-ok-fg uppercase">
            Resolved
            {incident.resolved_at && incident.opened_at
              ? ` in ${minutes(incident.resolved_at - incident.opened_at)}`
              : ""}
          </span>
          <span className="truncate text-[15px] font-semibold">
            {info.title ?? "The incident is closed"}
            {info.service && (
              <span className="font-normal text-muted">
                {" "}
                on {shortId(info.service)}
              </span>
            )}
          </span>
        </div>
        <ButtonLink href={`${base}/actions`} size="sm" className="relative">
          Postmortem <ArrowRight aria-hidden="true" />
        </ButtonLink>
      </>,
      true,
    );
  }

  if (!info.cause) {
    return shell(
      "before:absolute before:inset-y-0 before:left-0 before:w-48 before:bg-[radial-gradient(ellipse_at_left,rgb(106_168_255/0.12),transparent_70%)]",
      <>
        <AgentBadge agent="investigator" state="active" size={40} />
        <div className="relative flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-[11px] font-semibold tracking-[0.08em] text-[#a9cbff] uppercase">
            Looking for the cause
          </span>
          <span className="ps-shimmer-text text-[15px] font-medium">
            Ranking every change in the last two hours against the graph…
          </span>
        </div>
        <ButtonLink
          href={`${base}/investigation`}
          size="sm"
          className="relative"
        >
          <ScanSearch aria-hidden="true" /> Suspects so far
        </ButtonLink>
      </>,
    );
  }

  return shell(
    "before:absolute before:inset-y-0 before:left-0 before:w-64 before:bg-[radial-gradient(ellipse_at_left,rgb(255_178_36/0.13),transparent_70%)] after:absolute after:inset-x-12 after:top-0 after:h-px after:bg-[linear-gradient(90deg,transparent,var(--amber),transparent)] after:opacity-70",
    <>
      {info.confidence != null ? (
        <Confidence value={info.confidence} />
      ) : (
        <span className="relative flex size-12 flex-none items-center justify-center rounded-full bg-amber-tint text-amber ring-1 ring-amber/30">
          <Sparkles aria-hidden="true" className="size-5" />
        </span>
      )}
      <div className="relative flex min-w-0 flex-1 basis-72 flex-col gap-0.5">
        <span className="flex items-center gap-1.5 text-[11px] font-semibold tracking-[0.08em] text-amber uppercase">
          <Sparkles aria-hidden="true" className="size-3" />
          Root cause found
        </span>
        <span className="truncate text-base leading-6 font-semibold tracking-[-0.01em]">
          {info.title ?? info.cause}
          {info.service && (
            <span className="font-normal text-muted">
              {" "}
              on {shortId(info.service)}
            </span>
          )}
        </span>
        <span
          className="truncate text-xs text-muted"
          title={info.why ?? undefined}
        >
          <Mono className="text-text-2">{info.cause}</Mono>
          {info.kind && KIND[info.kind] ? ` · ${KIND[info.kind]}` : ""}
          {info.author && <> by {shortId(info.author)}</>}
          {info.rejected.length > 0 && (
            <>
              {" "}
              · ruled out <Mono>{info.rejected.join(", ")}</Mono>
            </>
          )}
        </span>
      </div>
      <div className="relative flex flex-wrap items-center gap-2">
        <ButtonLink
          href={`${base}/investigation`}
          variant="ghost"
          size="md"
          transitionTypes={["nav-forward"]}
        >
          Why this change
        </ButtonLink>
        <ButtonLink
          href={`${base}/actions`}
          variant="primary"
          size="md"
          transitionTypes={["nav-forward"]}
        >
          Review the fix <ArrowRight aria-hidden="true" />
        </ButtonLink>
      </div>
    </>,
  );
}
