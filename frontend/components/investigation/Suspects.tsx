"use client";

// U06 suspects and score breakdown. Left: one selectable row
// per change, best first: rank, verdict (Cause = amber, Decoy = red with the title struck
// through, Ruled out = grey), title, kind / id / service / author / time, the score counting
// up and a bar scaled to the top score; the selection glides between rows. Right: the four
// factors as the multiplication they are (recency × distance × fragility × anomaly = score),
// then each factor on a bar centred on ×1 (left dampens, right boosts, log scale) with its
// reason, and the Investigator's own reasoning.

import { Equal, ListOrdered, Sigma, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { Fragment, useState } from "react";

import { AgentBadge } from "@/components/incident/agents";
import {
  CountUp,
  EASE,
  Empty,
  Meter,
  Mono,
  Panel,
  SPRING,
} from "@/components/ui";
import { clock, hhmm, pct, shortId } from "@/lib/format";
import type { Suspect, SuspectsView } from "@/lib/types";

const LOOKBACK = 2 * 3600; // investigation.LOOKBACK: since = first alert - 2 h

type Verdict = "Cause" | "Decoy" | "Ruled out" | null;

function verdict(s: Suspect, view: SuspectsView): Verdict {
  if (s.change_id === view.cause) return "Cause";
  if (view.rejected.includes(s.change_id)) return "Decoy";
  return view.cause ? "Ruled out" : null;
}

const VERDICT_STYLE: Record<Exclude<Verdict, null>, string> = {
  Cause: "bg-amber-tint text-on-amber-tint ring-amber/35",
  Decoy: "bg-sev1-bg text-sev1-fg ring-danger/30",
  "Ruled out": "bg-white/[0.05] text-muted ring-white/10",
};

/** "max_pool_size 200 → 60" for config changes (from the incident graph), else the commit. */
function title(s: Suspect, names: Record<string, string>) {
  const name = names[s.change_id];
  if (s.change_type === "config")
    return name ?? `${shortId(s.service_id)} config change`;
  return s.commits[0]?.message ?? name ?? `${shortId(s.service_id)} deploy`;
}

function who(s: Suspect) {
  const authors = [...new Set(s.commits.map((c) => c.author).filter(Boolean))];
  return authors.length ? authors.join(", ") : null;
}

function factors(s: Suspect, view: SuspectsView) {
  const p = s.score_parts;
  const firstAlert = view.since + LOOKBACK;
  const minutes = Math.round((firstAlert - s.ts) / 60);
  const hops = Math.round(1 / p.distance - 1);
  const from = view.alerting_service_id
    ? shortId(view.alerting_service_id)
    : "the alert";
  const svc = shortId(s.service_id);
  return [
    {
      name: "Recency",
      short: "Recency",
      value: p.recency,
      why:
        minutes >= 0
          ? `Changed ${minutes} min before the first alert; halves every 6 hours.`
          : `Changed ${-minutes} min after the first alert.`,
    },
    {
      name: "Distance from the alert",
      short: "Distance",
      value: p.distance,
      why:
        hops === 0
          ? `On ${from} itself, the service that alerted.`
          : `${svc} is ${hops} ${hops === 1 ? "service" : "services"} downstream of ${from}.`,
    },
    {
      name: "Fragility",
      short: "Fragility",
      value: p.fragility,
      why:
        p.fragility > 1.001
          ? `${svc} sits on many dependency paths (betweenness ${s.fragility.toFixed(1)}).`
          : `${svc} sits on few dependency paths.`,
    },
    {
      name: "Anomaly now",
      short: "Anomaly",
      value: p.anomaly,
      why:
        p.anomaly > 1.001
          ? `${svc} is sicker than everything it depends on: a likely cause.`
          : `${svc} is no sicker than what it depends on: a victim, not a cause.`,
    },
  ];
}

/** A bar centred on ×1: left of centre dampens the score, right boosts it (log10, ±1). */
function Lever({ value, delay }: { value: number; delay: number }) {
  const v = Math.max(-1, Math.min(1, Math.log10(Math.max(value, 1e-6))));
  const boost = v > 0.001;
  return (
    <span className="relative block h-1.5 w-full rounded-full bg-white/[0.05]">
      <span
        className="absolute top-[-3px] left-1/2 h-3 w-px bg-white/25"
        aria-hidden="true"
      />
      <motion.span
        className={`absolute top-0 h-full rounded-full ${boost ? "left-1/2 bg-[linear-gradient(90deg,var(--amber-2),var(--amber))] shadow-[0_0_10px_rgb(255_178_36/0.5)]" : "right-1/2 bg-white/30"}`}
        initial={{ width: 0 }}
        animate={{ width: pct(Math.abs(v) / 2) }}
        transition={{ duration: 0.8, delay, ease: EASE }}
      />
    </span>
  );
}

export function Suspects({
  view,
  names,
  reasons,
}: {
  view: SuspectsView;
  names: Record<string, string>; // node id -> display name (incident graph)
  reasons: Record<string, string>; // change id -> the agent's reasoning, when it gave one
}) {
  const [picked, setPicked] = useState(view.suspects[0]?.change_id);
  const top = view.suspects[0]?.score || 1;
  const sel =
    view.suspects.find((s) => s.change_id === picked) ?? view.suspects[0];
  const cause = view.suspects.find((s) => s.change_id === view.cause);

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
      <Panel
        label="Suspects"
        title="Suspects"
        icon={<ListOrdered />}
        count={view.suspects.length}
        flush
        delay={0.1}
        actions={
          <span className="text-xs text-muted">
            Changes since{" "}
            <Mono className="text-text-2">{hhmm(view.since)}</Mono> UTC
          </span>
        }
      >
        {view.suspects.length === 0 && (
          <Empty icon={<ListOrdered />}>
            No deploys or config changes in the window.
          </Empty>
        )}
        <ul className="m-0 flex max-h-[600px] list-none flex-col gap-1 overflow-y-auto p-2">
          {view.suspects.map((s, n) => {
            const v = verdict(s, view);
            const selected = s.change_id === sel?.change_id;
            return (
              <motion.li
                key={s.change_id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  duration: 0.45,
                  ease: EASE,
                  delay: 0.2 + n * 0.06,
                }}
              >
                <button
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setPicked(s.change_id)}
                  className="group relative grid w-full cursor-pointer grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 rounded-xl border-none bg-transparent px-3 py-3.5 text-left font-[inherit] text-text sm:grid-cols-[28px_minmax(0,1fr)_auto] sm:gap-x-4"
                >
                  {selected ? (
                    <motion.span
                      layoutId="suspect-selected"
                      transition={SPRING}
                      className={`absolute inset-0 rounded-xl ${v === "Cause" ? "bg-[linear-gradient(90deg,rgb(255_178_36/0.09),rgb(255_255_255/0.03))] shadow-[inset_0_0_0_1px_rgb(255_178_36/0.28)]" : "bg-white/[0.05] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]"}`}
                    />
                  ) : (
                    <span className="absolute inset-0 rounded-xl bg-white/[0.03] opacity-0 transition-opacity group-hover:opacity-100" />
                  )}
                  <Mono
                    className={`relative text-center text-sm font-semibold ${v === "Cause" ? "text-amber" : "text-faint"}`}
                  >
                    {n + 1}
                  </Mono>
                  <span className="relative flex min-w-0 flex-col gap-1.5">
                    <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 sm:flex-nowrap">
                      {v && (
                        <span
                          className={`flex-none rounded-md px-1.5 py-px text-[10px] font-semibold tracking-[0.06em] uppercase ring-1 ring-inset ${VERDICT_STYLE[v]}`}
                        >
                          {v}
                        </span>
                      )}
                      <span
                        className={`line-clamp-2 text-[13px] font-medium sm:line-clamp-1 ${v === "Decoy" ? "text-muted line-through decoration-danger/60" : ""}`}
                      >
                        {title(s, names)}
                      </span>
                    </span>
                    <span className="line-clamp-2 text-xs text-muted sm:line-clamp-1">
                      {s.change_type === "config" ? "Config change" : "Deploy"}{" "}
                      <Mono className="text-text-2">{s.change_id}</Mono> ·{" "}
                      {shortId(s.service_id)}
                      {who(s) && <> · {who(s)}</>} · <Mono>{clock(s.ts)}</Mono>
                    </span>
                  </span>
                  <span className="relative flex w-20 flex-col items-end gap-2 sm:w-28">
                    <CountUp
                      value={s.score}
                      decimals={2}
                      delay={0.25 + n * 0.06}
                      className={`font-mono text-base font-semibold ${v === "Cause" ? "text-on-amber-tint" : "text-text-2"}`}
                    />
                    <Meter
                      value={s.score / top}
                      tone={v === "Cause" ? "found" : "neutral"}
                      delay={0.3 + n * 0.06}
                    />
                  </span>
                </button>
              </motion.li>
            );
          })}
        </ul>
        {cause && reasons[cause.change_id] && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: EASE, delay: 0.5 }}
            className="mx-2 mb-2 flex gap-3 rounded-xl bg-white/[0.03] p-3.5 ring-1 ring-white/[0.07] ring-inset"
          >
            <AgentBadge agent="investigator" state="done" size={28} />
            <span className="flex min-w-0 flex-col gap-1">
              <span className="text-[11px] font-semibold tracking-[0.06em] text-faint uppercase">
                Why the Investigator picked{" "}
                <Mono className="text-on-amber-tint">{cause.change_id}</Mono>
              </span>
              <span className="text-[13px] leading-5 text-text-2">
                {reasons[cause.change_id]}
              </span>
            </span>
          </motion.div>
        )}
      </Panel>

      {sel && (
        <Panel
          label="Score breakdown"
          title={
            <>
              Why it scored{" "}
              <CountUp
                value={sel.score}
                decimals={2}
                className="font-mono text-text"
              />
            </>
          }
          icon={<Sigma />}
          flush
          delay={0.18}
          tone={sel.change_id === view.cause ? "found" : "none"}
          className="lg:sticky lg:top-0"
          footer={
            <span className="text-[11px] text-faint">
              How it&apos;s calculated:{" "}
              <Mono>recency × 1/(1+hops) × (1 + fragility/max) × anomaly</Mono>
            </span>
          }
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={sel.change_id}
              aria-live="polite"
              className="flex flex-col"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.25, ease: EASE }}
            >
              <div className="border-b border-white/[0.05] px-4 pt-3.5 pb-3 text-[13px] leading-5 font-medium">
                {title(sel, names)}
              </div>

              {/* The multiplication, factor by factor. */}
              <div
                className="flex items-center justify-between gap-1 border-b border-white/[0.05] px-3 py-4"
                aria-label={`${factors(sel, view)
                  .map((f) => `${f.short} ${f.value.toFixed(2)}`)
                  .join(" times ")} equals ${sel.score.toFixed(2)}`}
              >
                {factors(sel, view).map((f, i) => (
                  <Fragment key={f.name}>
                    {i > 0 && (
                      <X
                        aria-hidden="true"
                        className="size-3 flex-none text-faint"
                      />
                    )}
                    <span
                      className={`flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-lg px-1 py-1.5 ${f.value > 1.001 ? "bg-amber-tint ring-1 ring-amber/25 ring-inset" : ""}`}
                    >
                      <Mono
                        className={`text-[13px] font-semibold ${f.value > 1.001 ? "text-on-amber-tint" : "text-text-2"}`}
                      >
                        <CountUp
                          value={f.value}
                          decimals={2}
                          delay={0.1 + i * 0.08}
                        />
                      </Mono>
                      <span className="truncate text-[10px] text-faint">
                        {f.short}
                      </span>
                    </span>
                  </Fragment>
                ))}
                <Equal
                  aria-hidden="true"
                  className="size-3 flex-none text-faint"
                />
                <span className="flex flex-col items-center gap-0.5 rounded-lg bg-white/[0.06] px-2 py-1.5 ring-1 ring-white/10 ring-inset">
                  <Mono className="text-[13px] font-semibold text-text">
                    {sel.score.toFixed(2)}
                  </Mono>
                  <span className="text-[10px] text-faint">Score</span>
                </span>
              </div>

              {factors(sel, view).map((f, i) => (
                <div
                  key={f.name}
                  className="flex flex-col gap-2 border-b border-white/[0.05] px-4 py-3"
                >
                  <span className="flex items-baseline justify-between gap-3">
                    <span className="text-[13px]">{f.name}</span>
                    <Mono
                      className={`text-[13px] ${f.value > 1.001 ? "text-on-amber-tint" : f.value < 0.999 ? "text-muted" : "text-text-2"}`}
                    >
                      × {f.value.toFixed(2)}
                    </Mono>
                  </span>
                  <Lever value={f.value} delay={0.15 + i * 0.07} />
                  <span className="text-xs leading-[18px] text-muted">
                    {f.why}
                  </span>
                </div>
              ))}

              <p className="m-0 px-4 py-3.5 text-[13px] leading-5 text-text-2">
                {cause && sel.change_id !== cause.change_id
                  ? `Scored ${sel.score.toFixed(2)} against ${cause.score.toFixed(2)} for ${cause.change_id}: ${(cause.score / sel.score).toFixed(1)}× less likely.`
                  : `The top score: ${(sel.score / (view.suspects[1]?.score || sel.score)).toFixed(1)}× the runner-up.`}
              </p>
            </motion.div>
          </AnimatePresence>
        </Panel>
      )}
    </div>
  );
}
