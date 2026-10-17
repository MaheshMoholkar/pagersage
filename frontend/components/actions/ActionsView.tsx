"use client";

// U09 actions and resolve (design: Resolve.dc.html), as the response it is: a flow of steps on
// a rail, the step that needs you lit amber with its one button, the ones behind it checked off
// in green and the line between them filling as they complete.
//   1 Paged the owner      the Responder's page (timeline `action` events)
//   2 Opened an issue      with the root-cause path
//   3 Owner's ack          only for a tier-1 service (policy pol:tier1-rollback-ack); kept in
//                          the browser
//   4 Revert the cause     simulated (POST /incidents/{id}/revert)
//   5 Resolve              then the Scribe writes the postmortem in the background; this view
//                          polls until it lands and the runbook counter goes up (the new
//                          square in amber)
// Beside the flow: the cause with its path, and the runbook. Resolved: a banner says how long
// it took and the postmortem fills in below.

import {
  ArrowUpRight,
  BookOpen,
  Check,
  CircleDot,
  FileText,
  Info,
  Loader,
  MessageSquare,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useState } from "react";

import { AgentBadge } from "@/components/incident/agents";
import { IncidentHeader } from "@/components/incident/IncidentHeader";
import { RunbookSquares } from "@/components/investigation/Memory";
import {
  Button,
  ButtonLink,
  Chip,
  CountUp,
  EASE,
  Mono,
  Panel,
  SectionHeader,
  StubBadge,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { clock, hhmm, minutes, shortId } from "@/lib/format";
import type { AgentEvent, IncidentDetail, RunbookHit } from "@/lib/types";

const POLL_MS = 3000;
const POLL_FOR_MS = 3 * 60 * 1000; // the Scribe usually takes well under a minute

type Phase = "done" | "current" | "upcoming" | "failed" | "waiting";

function lastAction(events: AgentEvent[], action: string) {
  return events.findLast(
    (e) => e.kind === "action" && e.data.action === action,
  );
}

/** "## What happened\n..." -> [{title, text}], in order. */
export function sections(body: string) {
  const parts = body.split(/^##\s+/m).slice(1);
  return parts.map((p) => {
    const [title, ...rest] = p.split("\n");
    return { title: title.trim(), text: rest.join("\n").trim() };
  });
}

const NODE: Record<Phase, string> = {
  done: "bg-ok text-bg shadow-[0_0_16px_rgb(61_220_151/0.45)]",
  current:
    "bg-amber-tint text-amber ring-2 ring-amber shadow-[0_0_0_6px_rgb(255_178_36/0.08),0_0_24px_rgb(255_178_36/0.35)]",
  upcoming: "bg-white/[0.03] text-faint ring-1 ring-white/10",
  failed: "bg-danger text-bg",
  waiting: "bg-blue-tint text-blue ring-1 ring-blue/40",
};

const TAG: Record<Phase, string> = {
  done: "text-ok-fg",
  current: "text-amber",
  upcoming: "text-faint",
  failed: "text-sev1-fg",
  waiting: "text-[#a9cbff]",
};

function Step({
  n,
  phase,
  title,
  tag,
  last = false,
  delay = 0,
  children,
}: {
  n: number;
  phase: Phase;
  title: string;
  tag: string;
  last?: boolean;
  delay?: number;
  children: React.ReactNode;
}) {
  return (
    <motion.li
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE, delay }}
      className="relative flex gap-4"
      aria-current={phase === "current" ? "step" : undefined}
    >
      <div className="flex w-8 flex-none flex-col items-center">
        <motion.span
          layout
          className={`relative z-[1] flex size-8 flex-none items-center justify-center rounded-full font-mono text-[13px] font-semibold transition-[background-color,box-shadow,color] duration-500 ${NODE[phase]}`}
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={phase}
              initial={{ scale: 0.4, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.4, opacity: 0 }}
              transition={{ type: "spring", bounce: 0.45, duration: 0.45 }}
              className="flex"
            >
              {phase === "done" ? (
                <Check className="size-4" strokeWidth={3} />
              ) : phase === "failed" ? (
                <X className="size-4" strokeWidth={3} />
              ) : phase === "waiting" ? (
                <Loader className="ps-spin size-4" />
              ) : (
                n
              )}
            </motion.span>
          </AnimatePresence>
          {phase === "current" && (
            <span className="ps-ping absolute inset-0 rounded-full ring-2 ring-amber/60" />
          )}
        </motion.span>
        {!last && (
          <span
            aria-hidden="true"
            className="relative my-1.5 w-0.5 flex-1 overflow-hidden rounded-full bg-white/[0.07]"
          >
            <motion.span
              className="absolute inset-x-0 top-0 bg-[linear-gradient(180deg,var(--ok),rgb(61_220_151/0.4))]"
              initial={{ height: 0 }}
              animate={{ height: phase === "done" ? "100%" : "0%" }}
              transition={{ duration: 0.7, ease: EASE, delay: delay + 0.2 }}
            />
          </span>
        )}
      </div>
      <div className="min-w-0 flex-1 pb-5">
        <div
          className={`relative flex flex-col gap-3 rounded-panel p-4 glass transition-[opacity,box-shadow] duration-500 ${phase === "current" ? "shadow-[inset_0_0_0_1px_rgb(255_178_36/0.35),0_0_40px_-12px_rgb(255_178_36/0.35),var(--shadow-panel)]" : ""} ${phase === "upcoming" ? "opacity-55" : ""}`}
        >
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h3 className="m-0 text-[15px] leading-6 font-semibold tracking-[-0.01em]">
              {title}
            </h3>
            <span className={`text-xs font-medium ${TAG[phase]}`}>{tag}</span>
          </div>
          {children}
        </div>
      </div>
    </motion.li>
  );
}

const Note = ({ children }: { children: React.ReactNode }) => (
  <p className="m-0 flex gap-1.5 text-xs leading-[18px] text-faint">
    <Info aria-hidden="true" className="mt-0.5 size-3.5 flex-none" />
    <span>{children}</span>
  </p>
);

const Pending = ({ children }: { children: React.ReactNode }) => (
  <p className="ps-shimmer-text m-0 text-[13px]">{children}</p>
);

export function ActionsView({
  initial,
  cause,
  path,
  causeService,
  runbook: runbookAtLoad,
  live,
  stub,
}: {
  initial: IncidentDetail;
  cause: string | null;
  causeService: { id: string; tier: number | null } | null;
  path: string[];
  runbook: RunbookHit | null;
  live: boolean;
  stub: boolean;
}) {
  const [detail, setDetail] = useState(initial);
  const [runbook, setRunbook] = useState(runbookAtLoad);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<null | "revert" | "resolve">(null);
  const [pollUntil, setPollUntil] = useState(0);
  const { incident, timeline, postmortem, graph } = detail;

  const page = lastAction(timeline, "page");
  const issue = lastAction(timeline, "issue");
  const reverted = timeline.findLast(
    (e) =>
      e.kind === "action" &&
      e.data.action === "rollback" &&
      e.data.change_id === cause,
  );
  const needsAck = causeService?.tier === 1;
  const [acked, setAcked] = useState(false);
  const onCall = String(page?.data.handle ?? "the on-call");
  const resolved = incident.status === "resolved";
  const causeName = graph.nodes.find((n) => n.id === cause)?.name ?? null;

  const refresh = useCallback(async () => {
    const [d, m] = await Promise.all([
      api.incident(incident.id),
      api.memory(incident.id),
    ]);
    setDetail(d.data);
    setRunbook(
      m.data.runbooks.find((r) => r.id === runbookAtLoad?.id) ??
        m.data.runbooks[0] ??
        null,
    );
    return d.data;
  }, [incident.id, runbookAtLoad?.id]);

  // After resolve: poll until the Scribe's postmortem lands (or give up after a few minutes).
  useEffect(() => {
    if (!pollUntil) return;
    const timer = setInterval(async () => {
      const d = await refresh().catch(() => null);
      if (d?.postmortem || Date.now() > pollUntil) {
        clearInterval(timer);
        setPollUntil(0);
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [pollUntil, refresh]);

  async function act(what: "revert" | "resolve", fn: () => Promise<unknown>) {
    setBusy(what);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "The backend is not reachable.",
      );
    } finally {
      setBusy(null);
    }
  }

  const revert = () => act("revert", () => api.revert(incident.id, cause!));
  const resolve = () =>
    act("resolve", async () => {
      await api.resolve(
        incident.id,
        `Reverted ${cause ?? "the cause"}${runbook ? ` and ran "${runbook.title}"` : ""}.`,
      );
      setPollUntil(Date.now() + POLL_FOR_MS);
    });

  const issueRef =
    typeof issue?.data.url === "string"
      ? issue.data.url.split("/").slice(-4)
      : [];
  const freshRunbook =
    !!runbook &&
    !!runbookAtLoad &&
    runbook.success_count > runbookAtLoad.success_count;
  const sectionsOf = postmortem
    ? sections(postmortem.body).length
      ? sections(postmortem.body)
      : [{ title: postmortem.title, text: postmortem.body }]
    : [];

  // Where each step stands.
  const sent = (e: AgentEvent | undefined, done: string, failed: string) =>
    e
      ? `${e.data.ok === false ? failed : done} · ${hhmm(e.ts)}`
      : "Waiting on the Responder";
  const auto = (e: AgentEvent | undefined): Phase =>
    !e ? "waiting" : e.data.ok === false ? "failed" : "done";
  const ackPhase: Phase =
    reverted || acked ? "done" : cause && !resolved ? "current" : "upcoming";
  const revertPhase: Phase = reverted
    ? "done"
    : cause && (!needsAck || acked) && !resolved
      ? "current"
      : "upcoming";
  const resolvePhase: Phase = resolved
    ? "done"
    : reverted || !cause
      ? "current"
      : "upcoming";
  let n = 0;

  return (
    <>
      <IncidentHeader
        incident={incident}
        tab="actions"
        aside={<StubBadge show={stub} what="Stub data · actions disabled" />}
      />

      <AnimatePresence>
        {error && (
          <motion.p
            role="alert"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="m-0 flex items-center gap-2 rounded-xl bg-sev1-bg px-4 py-2.5 text-[13px] text-sev1-fg ring-1 ring-danger/30 ring-inset"
          >
            <X aria-hidden="true" className="size-4 flex-none" />
            {error}
          </motion.p>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {resolved && (
          <motion.section
            aria-label="Resolved"
            initial={{ opacity: 0, scale: 0.98, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.7, ease: EASE }}
            className="relative overflow-hidden rounded-panel px-6 py-6 glass sm:px-8"
          >
            <motion.div
              aria-hidden="true"
              className="pointer-events-none absolute -top-24 -left-20 h-72 w-[70%] rounded-full bg-[radial-gradient(closest-side,rgb(61_220_151/0.22),transparent)] blur-2xl"
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 1.4, ease: EASE }}
            />
            <div className="relative flex flex-wrap items-center justify-between gap-6">
              <div className="flex flex-col gap-1.5">
                <span className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.1em] text-ok-fg uppercase">
                  <Check
                    aria-hidden="true"
                    className="size-3.5"
                    strokeWidth={3}
                  />{" "}
                  Incident resolved
                </span>
                <h2 className="m-0 text-sheen font-serif text-4xl leading-tight font-normal tracking-[-0.01em] sm:text-5xl">
                  {incident.resolved_at && incident.opened_at ? (
                    <>
                      Resolved in{" "}
                      <em>
                        {minutes(incident.resolved_at - incident.opened_at)}
                      </em>
                    </>
                  ) : (
                    "Resolved"
                  )}
                </h2>
                <p className="m-0 max-w-xl text-[13px] leading-5 text-muted">
                  The Scribe writes the postmortem and credits the runbook that
                  worked. This incident is in memory now: the next one like it
                  will be found faster.
                </p>
              </div>
              {incident.resolved_at && (
                <Mono className="text-xs text-faint">
                  {clock(incident.resolved_at)} UTC
                </Mono>
              )}
            </div>
          </motion.section>
        )}
      </AnimatePresence>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section
          aria-labelledby="response-title"
          className="flex min-w-0 flex-col gap-5"
        >
          <SectionHeader
            id="response-title"
            eyebrow="Response"
            title={
              resolved
                ? "What was done"
                : "What the Responder did, and what's left"
            }
            description="The page, the issue and the revert, each checked against policy. Resolve once the service recovers; the Scribe takes it from there."
          />
          <ol
            aria-label="Response steps"
            className="m-0 flex list-none flex-col p-0"
          >
            <Step
              n={++n}
              phase={auto(page)}
              title="Paged the owner"
              tag={sent(page, "Sent", "Not sent")}
              delay={0.1}
            >
              {page ? (
                <div className="flex gap-3 rounded-xl bg-black/25 p-3 ring-1 ring-white/[0.06] ring-inset">
                  <span className="flex size-8 flex-none items-center justify-center rounded-full bg-[#5865f2]/20 text-[#a8b0ff] ring-1 ring-[#5865f2]/40">
                    <MessageSquare aria-hidden="true" className="size-4" />
                  </span>
                  <div className="flex min-w-0 flex-col gap-1">
                    <span className="flex items-center gap-2 text-xs">
                      <span className="font-semibold text-text">PagerSage</span>
                      <span className="rounded bg-[#5865f2]/25 px-1 text-[10px] font-semibold text-[#c3c8ff]">
                        APP
                      </span>
                      <span className="text-faint">
                        Discord · {hhmm(page.ts)}
                      </span>
                    </span>
                    <span className="text-[13px] leading-5 text-text-2">
                      <span className="rounded bg-[#5865f2]/25 px-1 font-medium text-[#c3c8ff]">
                        @{String(page.data.handle)}
                      </span>{" "}
                      {String(page.data.message ?? "")}
                    </span>
                    {page.data.ok === false && (
                      <span className="text-xs text-sev1-fg">
                        {page.summary}
                      </span>
                    )}
                  </div>
                </div>
              ) : (
                <Pending>The Responder pages the on-call once it acts.</Pending>
              )}
              <Note>
                Chosen by who_to_page: the owning team&apos;s on-call, then the
                most recent authors.
              </Note>
            </Step>

            <Step
              n={++n}
              phase={auto(issue)}
              title="Opened an issue"
              tag={sent(issue, "Opened", "Not opened")}
              delay={0.16}
            >
              {issue ? (
                <div className="flex flex-col gap-2.5 rounded-xl bg-black/25 p-3 ring-1 ring-white/[0.06] ring-inset">
                  <span className="flex items-start gap-2.5">
                    <CircleDot
                      aria-hidden="true"
                      className="mt-0.5 size-4 flex-none text-ok"
                    />
                    <span className="flex min-w-0 flex-col gap-0.5">
                      {typeof issue.data.url === "string" ? (
                        <a
                          href={issue.data.url}
                          className="inline-flex items-center gap-1 text-[13px] font-medium"
                        >
                          {String(issue.data.title ?? issue.data.url)}
                          <ArrowUpRight
                            aria-hidden="true"
                            className="size-3.5"
                          />
                        </a>
                      ) : (
                        <span className="text-[13px] font-medium">
                          {String(issue.data.title ?? "Issue")}
                        </span>
                      )}
                      {issueRef.length === 4 && (
                        <Mono className="text-xs text-muted">
                          {issueRef[0]}/{issueRef[1]}#{issueRef[3]}
                        </Mono>
                      )}
                    </span>
                  </span>
                  {issue.data.ok === false && (
                    <span className="text-xs text-sev1-fg">
                      {issue.summary}
                    </span>
                  )}
                  <span className="flex flex-wrap gap-1">
                    {path.map((id) => (
                      <Chip key={id} found={id === cause}>
                        {shortId(id)}
                      </Chip>
                    ))}
                  </span>
                </div>
              ) : (
                <Pending>
                  The Responder opens one with the root-cause path.
                </Pending>
              )}
              <Note>
                The body holds the root-cause path, the suspect change and its
                author.
              </Note>
            </Step>

            {cause && needsAck && (
              <Step
                n={++n}
                phase={ackPhase}
                title={`Ack from ${onCall}`}
                tag={
                  {
                    done: "Acked",
                    current: "Waiting on owner",
                    upcoming: "Later",
                    failed: "",
                    waiting: "",
                  }[ackPhase]
                }
                delay={0.22}
              >
                <div className="flex gap-2.5 rounded-xl bg-black/25 p-3 text-xs leading-[18px] text-text-2 ring-1 ring-white/[0.06] ring-inset">
                  <ShieldCheck
                    aria-hidden="true"
                    className="size-4 flex-none text-blue"
                  />
                  <span>
                    <span className="font-semibold text-text">Policy</span> ·
                    Rolling back a tier-1 service needs the owner&apos;s ack.{" "}
                    {ackPhase === "done"
                      ? `${onCall.charAt(0).toUpperCase()}${onCall.slice(1)} acked.`
                      : `Ask ${onCall} in the page.`}
                  </span>
                </div>
                {ackPhase === "current" && (
                  <Button
                    onClick={() => setAcked(true)}
                    size="lg"
                    className="self-start"
                  >
                    <Check aria-hidden="true" /> Record ack from {onCall}
                  </Button>
                )}
              </Step>
            )}

            <Step
              n={++n}
              phase={cause ? revertPhase : "waiting"}
              title={cause ? `Revert ${cause}` : "Revert the cause"}
              tag={
                !cause
                  ? "Waiting on the Investigator"
                  : {
                      done: "Done",
                      current: "Ready",
                      upcoming: needsAck ? "After the ack" : "Later",
                      failed: "",
                      waiting: "",
                    }[revertPhase]
              }
              delay={0.28}
            >
              {!cause ? (
                <Pending>The Investigator has not named a cause yet.</Pending>
              ) : (
                <>
                  <div className="text-[13px] leading-5 text-text-2">
                    Undo{" "}
                    <span className="font-medium text-text">
                      {causeName ?? cause}
                    </span>{" "}
                    (<Mono>{cause}</Mono>) on{" "}
                    {causeService ? shortId(causeService.id) : "its service"}.
                  </div>
                  {revertPhase === "current" && (
                    <Button
                      variant="primary"
                      size="lg"
                      onClick={revert}
                      disabled={!!busy || !live}
                      title={!live ? "Actions are off on stub data" : undefined}
                      className="self-start"
                    >
                      {busy === "revert" ? (
                        <Loader aria-hidden="true" className="ps-spin" />
                      ) : (
                        <RotateCcw aria-hidden="true" />
                      )}
                      Revert the change
                    </Button>
                  )}
                  {revertPhase === "done" && reverted && (
                    <motion.div
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="flex gap-2 rounded-xl bg-ok-bg px-3 py-2.5 text-xs leading-[18px] text-ok-fg ring-1 ring-ok/25 ring-inset"
                    >
                      <Check aria-hidden="true" className="size-4 flex-none" />
                      Reverted at {hhmm(reverted.ts)}. {reverted.summary}
                    </motion.div>
                  )}
                </>
              )}
              <Note>
                Simulated: recorded in the graph, no live system is changed.
              </Note>
            </Step>

            <Step
              n={++n}
              phase={resolvePhase}
              title={resolved ? "Resolved" : "Resolve"}
              tag={
                resolved && incident.resolved_at
                  ? `${hhmm(incident.resolved_at)} UTC`
                  : resolvePhase === "current"
                    ? "Ready"
                    : "After the revert"
              }
              last
              delay={0.34}
            >
              <p className="m-0 text-[13px] leading-5 text-muted">
                {resolved
                  ? incident.opened_at && incident.resolved_at
                    ? `${minutes(incident.resolved_at - incident.opened_at)} after the first alert.`
                    : "The incident is closed."
                  : "Resolve when the service recovers. The Scribe then writes the postmortem, credits the runbook that worked and stores this incident so the next one is found faster."}
              </p>
              {!resolved && (
                <Button
                  variant={resolvePhase === "current" ? "primary" : "secondary"}
                  size="lg"
                  onClick={resolve}
                  disabled={!!busy || !live || resolvePhase !== "current"}
                  title={
                    !live
                      ? "Actions are off on stub data"
                      : resolvePhase !== "current"
                        ? "Revert the cause first"
                        : undefined
                  }
                  className="self-start"
                >
                  {busy === "resolve" ? (
                    <Loader aria-hidden="true" className="ps-spin" />
                  ) : (
                    <Check aria-hidden="true" />
                  )}
                  Resolve incident
                </Button>
              )}
            </Step>
          </ol>
        </section>

        <aside className="flex flex-col gap-4 lg:sticky lg:top-0">
          <Panel
            label="Root cause"
            title="Root cause"
            icon={<Sparkles />}
            tone={cause ? "found" : "none"}
            delay={0.15}
            bodyClassName="gap-3"
          >
            {cause ? (
              <>
                <div className="flex flex-col gap-0.5">
                  <span className="text-[15px] leading-6 font-semibold">
                    {causeName ?? cause}
                  </span>
                  <span className="text-xs text-muted">
                    <Mono className="text-text-2">{cause}</Mono>
                    {causeService && <> on {shortId(causeService.id)}</>}
                    {causeService?.tier != null && (
                      <> · tier {causeService.tier}</>
                    )}
                  </span>
                </div>
                {path.length > 0 && (
                  <span className="flex flex-wrap gap-1">
                    {path.map((id) => (
                      <Chip key={id} found>
                        {shortId(id)}
                      </Chip>
                    ))}
                  </span>
                )}
                <ButtonLink
                  href={`/incidents/${incident.id}/investigation`}
                  variant="ghost"
                  size="sm"
                  transitionTypes={["nav-back"]}
                  className="self-start"
                >
                  Why this change <ArrowUpRight aria-hidden="true" />
                </ButtonLink>
              </>
            ) : (
              <Pending>The Investigator is still looking.</Pending>
            )}
          </Panel>

          {runbook && (
            <Panel
              label="Runbook"
              title={freshRunbook ? "Runbook credited" : "Runbook"}
              icon={<BookOpen />}
              tone={freshRunbook ? "ok" : "none"}
              delay={0.22}
              bodyClassName="gap-3"
            >
              <span className="text-[13px] leading-5 font-semibold">
                {runbook.title}
              </span>
              <span className="flex items-center gap-3">
                <RunbookSquares
                  key={runbook.success_count}
                  ok={runbook.success_count}
                  bad={runbook.fail_count}
                  fresh={freshRunbook}
                  delay={0.3}
                />
                <span className="text-xs text-text-2">
                  <CountUp value={runbook.success_count} /> of{" "}
                  <CountUp value={runbook.success_count + runbook.fail_count} />
                  {freshRunbook && runbookAtLoad
                    ? ` · up from ${runbookAtLoad.success_count} of ${runbookAtLoad.success_count + runbookAtLoad.fail_count}`
                    : ""}
                </span>
              </span>
              <span className="text-xs leading-[18px] text-muted">
                {freshRunbook
                  ? "This incident is in memory now. The next one like it will find it first."
                  : "Resolving credits this incident to the runbook."}
              </span>
            </Panel>
          )}
        </aside>
      </div>

      {resolved && (
        <Panel
          label="Postmortem"
          title={postmortem ? postmortem.title : "Postmortem"}
          icon={<FileText />}
          delay={0.2}
          bodyClassName="gap-4"
          actions={
            postmortem ? (
              <span className="text-xs text-muted">Written by the Scribe</span>
            ) : undefined
          }
        >
          <div aria-live="polite">
            {postmortem ? (
              <div className="grid gap-x-8 gap-y-5 sm:grid-cols-2">
                {sectionsOf.map((s, i) => (
                  <motion.div
                    key={s.title}
                    className="flex flex-col gap-1.5"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{
                      duration: 0.5,
                      ease: EASE,
                      delay: 0.1 + i * 0.08,
                    }}
                  >
                    <span className="text-[11px] font-semibold tracking-[0.08em] text-muted uppercase">
                      {s.title}
                    </span>
                    <span className="text-[13px] leading-5 whitespace-pre-line text-text-2">
                      {s.text}
                    </span>
                  </motion.div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                <span className="flex items-center gap-2.5 text-[13px]">
                  <AgentBadge
                    agent="scribe"
                    state={pollUntil ? "active" : "queued"}
                    size={26}
                  />
                  <span
                    className={pollUntil ? "ps-shimmer-text" : "text-muted"}
                  >
                    {pollUntil
                      ? "The Scribe is writing the postmortem…"
                      : "No postmortem yet. Reload to check again."}
                  </span>
                </span>
                {pollUntil > 0 && (
                  <div
                    className="grid gap-x-8 gap-y-4 sm:grid-cols-2"
                    aria-hidden="true"
                  >
                    {[0, 1, 2, 3].map((i) => (
                      <div key={i} className="flex flex-col gap-2">
                        <span className="ps-skeleton h-3 w-28 rounded" />
                        <span className="ps-skeleton h-3 w-full rounded" />
                        <span className="ps-skeleton h-3 w-4/5 rounded" />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </Panel>
      )}
    </>
  );
}
