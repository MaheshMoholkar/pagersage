"use client";

// U07 memory (design: Investigation.dc.html, "Has this happened before"): the same candidates
// in vector order and re-ranked with the graph. One list, two orderings: it opens on text
// similarity and, a beat later, re-ranks itself with the graph so you watch the incidents that
// broke the same way rise; the toggle switches back and forth. Each row says where it moved
// and why. Beside it, the runbook that worked: its success squares, its steps and "Use this
// runbook".

import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  History,
  Minus,
  Sparkles,
} from "lucide-react";
import {
  AnimatePresence,
  LayoutGroup,
  motion,
  useInView,
  useReducedMotion,
} from "motion/react";
import { useEffect, useRef, useState } from "react";

import {
  ButtonLink,
  Empty,
  Meter,
  Mono,
  Panel,
  SectionHeader,
  Segmented,
} from "@/components/ui";
import { shortId } from "@/lib/format";
import type { MemoryView, RunbookHit, SimilarIncident } from "@/lib/types";

const ordinal = (n: number) => ["1st", "2nd", "3rd"][n - 1] ?? `${n}th`;

type Order = "text" | "graph";

function Move({
  id,
  rank,
  vectorOnly,
}: {
  id: string;
  rank: number;
  vectorOnly: SimilarIncident[];
}) {
  const before = vectorOnly.findIndex((i) => i.id === id) + 1;
  const [Icon, text, look] = !before
    ? [
        Sparkles,
        "new in top 3",
        "text-on-amber-tint bg-amber-tint ring-amber/25",
      ]
    : before === rank
      ? [Minus, "same place", "text-muted bg-white/[0.04] ring-white/10"]
      : before > rank
        ? [
            ArrowUp,
            `up from ${ordinal(before)}`,
            "text-on-amber-tint bg-amber-tint ring-amber/25",
          ]
        : [
            ArrowDown,
            `down from ${ordinal(before)}`,
            "text-muted bg-white/[0.04] ring-white/10",
          ];
  return (
    <span
      className={`inline-flex h-5 items-center gap-1 rounded-md px-1.5 text-[11px] ring-1 ring-inset ${look}`}
    >
      <Icon aria-hidden="true" className="size-3" />
      {text}
    </span>
  );
}

const Tag = ({ children }: { children: React.ReactNode }) => (
  <span className="inline-flex h-5 items-center rounded-md bg-amber-tint px-1.5 text-[11px] text-on-amber-tint ring-1 ring-amber/25 ring-inset">
    {children}
  </span>
);

function Squares({
  ok,
  bad,
  fresh = false,
  delay = 0,
}: {
  ok: number;
  bad: number;
  fresh?: boolean;
  delay?: number;
}) {
  return (
    <span className="flex flex-none gap-1" aria-hidden="true">
      {[...Array(ok).fill("ok"), ...Array(bad).fill("bad")].map((k, i) => (
        <motion.span
          key={`${k}${i}`}
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{
            type: "spring",
            bounce: 0.5,
            duration: 0.5,
            delay: delay + i * 0.08,
          }}
          className={`size-4 rounded-[5px] ${k === "bad" ? "bg-danger" : fresh && i === ok - 1 ? "bg-amber shadow-[0_0_12px_rgb(255_178_36/0.7)]" : "bg-ok shadow-[0_0_8px_rgb(61_220_151/0.35)]"}`}
        />
      ))}
    </span>
  );
}
export { Squares as RunbookSquares };

export function RunbookCard({
  runbook,
  usedOn,
  actionsHref,
  delay = 0,
}: {
  runbook: RunbookHit;
  usedOn: string[];
  actionsHref: string;
  delay?: number;
}) {
  const total = runbook.success_count + runbook.fail_count;
  return (
    <Panel
      label="Best runbook"
      title="Runbook that worked"
      icon={<BookOpen />}
      tone="ok"
      delay={delay}
      bodyClassName="gap-4"
    >
      <div className="flex flex-col gap-2.5">
        <div className="text-base leading-6 font-semibold tracking-[-0.01em]">
          {runbook.title}
        </div>
        <div className="flex items-center gap-3">
          <Squares
            ok={runbook.success_count}
            bad={runbook.fail_count}
            delay={delay + 0.3}
          />
          <span className="text-[13px] text-text-2">
            {total
              ? `Worked ${runbook.success_count} of ${total} times`
              : "Not tried yet"}
          </span>
        </div>
      </div>
      <ol className="m-0 flex list-none flex-col p-0">
        {runbook.steps.slice(0, 4).map((s, i, all) => (
          <li key={s} className="flex gap-3">
            <span className="flex flex-none flex-col items-center">
              <span className="flex size-5 items-center justify-center rounded-full bg-white/[0.05] font-mono text-[10px] text-text-2 ring-1 ring-white/10">
                {i + 1}
              </span>
              {i < all.length - 1 && (
                <span
                  className="w-px flex-1 bg-white/[0.08]"
                  aria-hidden="true"
                />
              )}
            </span>
            <span className="line-clamp-2 pb-3 text-xs leading-[18px] text-muted">
              {s}
            </span>
          </li>
        ))}
      </ol>
      <div className="mt-auto flex flex-col gap-3">
        <p className="m-0 text-xs leading-[18px] text-faint">
          {usedOn.length ? <>Used on {usedOn.join(", ")}. </> : null}Resolving
          credits this incident.
        </p>
        <ButtonLink
          variant="primary"
          size="lg"
          href={actionsHref}
          transitionTypes={["nav-forward"]}
          className="w-full"
        >
          Use this runbook
        </ButtonLink>
      </div>
    </Panel>
  );
}

export function Memory({
  view,
  incidentId,
}: {
  view: MemoryView;
  incidentId: string;
}) {
  const similar = view.similar;
  const best = view.runbooks[0];
  const reduce = useReducedMotion();
  const [order, setOrder] = useState<Order>("text");
  const [touched, setTouched] = useState(false);
  const usedOn = best
    ? (similar?.graph_ranked ?? [])
        .filter((i) => i.runbooks.some((r) => r.id === best.id))
        .map((i) => i.id)
    : [];
  const pathSize = view.path.length;

  // The demonstration: open on text similarity, then, once the list is on screen, re-rank
  // it with the graph (straight away under reduced motion).
  const section = useRef<HTMLElement>(null);
  const seen = useInView(section, { once: true, amount: 0.35 });
  useEffect(() => {
    if (touched || !seen) return;
    const t = setTimeout(() => setOrder("graph"), reduce ? 0 : 1100);
    return () => clearTimeout(t);
  }, [touched, seen, reduce]);

  const rows = similar
    ? order === "graph"
      ? similar.graph_ranked
      : similar.vector_only
    : [];
  const graph = order === "graph";

  return (
    <section
      ref={section}
      aria-labelledby="memory-title"
      className="flex flex-col gap-4 pt-3"
    >
      <SectionHeader
        id="memory-title"
        eyebrow="Memory"
        title="Has this happened before"
        description="Matching the words finds incidents that sound alike. PagerSage keeps the ones that broke along the same services."
        actions={
          similar && (
            <Segmented
              label="Order"
              size="md"
              value={order}
              onChange={(v) => {
                setTouched(true);
                setOrder(v);
              }}
              options={[
                { value: "text", label: "Sounds similar" },
                {
                  value: "graph",
                  label: (
                    <span className="flex items-center gap-1.5">
                      <span
                        className={`size-1.5 rounded-full ${graph ? "bg-amber" : "bg-faint"}`}
                      />
                      Broke the same way
                    </span>
                  ),
                },
              ]}
            />
          )
        }
      />
      <div className="grid items-stretch gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <Panel
          label={graph ? "Broke the same way" : "Sounds similar"}
          title={
            <AnimatePresence mode="wait" initial={false}>
              <motion.span
                key={order}
                className="block"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2 }}
              >
                {graph ? "Broke the same way" : "Sounds similar"}
              </motion.span>
            </AnimatePresence>
          }
          icon={<History />}
          tone={graph ? "found" : "none"}
          flush
          delay={0.25}
          className="transition-[border-color] duration-500"
        >
          {!similar ? (
            <Empty icon={<History />}>
              Waiting for triage: similar incidents are searched from its text.
            </Empty>
          ) : (
            <LayoutGroup>
              <ol
                aria-live="polite"
                className="m-0 flex list-none flex-col gap-1 p-2"
              >
                <AnimatePresence initial={false}>
                  {rows.map((i, n) => (
                    <motion.li
                      key={i.id}
                      layout
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{
                        layout: { type: "spring", bounce: 0.2, duration: 0.8 },
                        duration: 0.3,
                      }}
                      className={`relative flex gap-4 rounded-xl px-3 py-3.5 ${graph && n === 0 ? "bg-[linear-gradient(90deg,rgb(255_178_36/0.08),transparent)] ring-1 ring-amber/20 ring-inset" : ""}`}
                    >
                      <motion.span
                        layout="position"
                        className={`w-5 flex-none pt-px text-center font-mono text-sm font-semibold ${graph && n === 0 ? "text-amber" : "text-faint"}`}
                      >
                        {n + 1}
                      </motion.span>
                      <span className="flex min-w-0 flex-1 flex-col gap-2">
                        <span className="flex items-baseline justify-between gap-3">
                          <span
                            className={`text-[13px] leading-[18px] ${graph && n === 0 ? "font-semibold" : "font-medium text-text-2"}`}
                          >
                            {i.title}
                          </span>
                          <Mono className="flex-none text-xs text-muted">
                            {i.id}
                          </Mono>
                        </span>
                        <span className="flex flex-wrap items-center gap-1.5">
                          {graph ? (
                            <>
                              <Move
                                id={i.id}
                                rank={n + 1}
                                vectorOnly={similar.vector_only}
                              />
                              {i.shared_services > 0 && (
                                <Tag>
                                  {i.shared_services === pathSize
                                    ? "same path"
                                    : `${i.shared_services} path services`}
                                </Tag>
                              )}
                              {i.runbooks.length > 0 && (
                                <Tag>runbook worked</Tag>
                              )}
                              {i.postmortem_titles[0] && (
                                <span className="truncate text-[11px] text-faint">
                                  “{i.postmortem_titles[0]}”
                                </span>
                              )}
                            </>
                          ) : (
                            <span className="flex w-full max-w-72 items-center gap-2.5">
                              <span className="flex-none text-[11px] text-faint">
                                similarity
                              </span>
                              <Meter value={i.score} className="h-1" />
                              <Mono className="flex-none text-[11px] text-text-2">
                                {i.score.toFixed(2)}
                              </Mono>
                            </span>
                          )}
                        </span>
                      </span>
                    </motion.li>
                  ))}
                </AnimatePresence>
              </ol>
            </LayoutGroup>
          )}
        </Panel>
        {best ? (
          <RunbookCard
            runbook={best}
            usedOn={usedOn}
            actionsHref={`/incidents/${incidentId}/actions`}
            delay={0.32}
          />
        ) : (
          <Panel
            label="Best runbook"
            title="Runbook"
            icon={<BookOpen />}
            delay={0.32}
          >
            <Empty icon={<BookOpen />}>
              No runbook for{" "}
              {view.runbook_service_id
                ? shortId(view.runbook_service_id)
                : "this service"}{" "}
              yet.
            </Empty>
          </Panel>
        )}
      </div>
    </section>
  );
}
