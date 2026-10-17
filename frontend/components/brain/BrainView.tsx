"use client";

// U08 Ask: a centred question box with an amber Ask button and
// suggested questions, then the company graph. Asking opens the answer panel beside the
// graph: the question, the Brain walking the graph, then the answer (aria-live) and its
// evidence, each row a button that glides the graph to that node. The evidence lights up on
// the graph in amber. Only the graph moves; the page around it stays still.
// `initialQuestion` (?q= from the command palette) is asked on arrival.

import {
  ArrowRight,
  BrainCircuit,
  CornerDownLeft,
  Crosshair,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { AgentBadge } from "@/components/incident/agents";
import { Button, Kbd, Mono, StubBadge, spotlight } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { ASK_SUGGESTIONS, shortId } from "@/lib/format";
import type { AskOut, GraphView } from "@/lib/types";

import { CompanyGraph, kindOf } from "./CompanyGraph";

/** The first sentence is the headline; the rest is the paragraph under it. */
function split(answer: string): [string, string] {
  const m = answer.match(/^([\s\S]+?[.!?])\s+([\s\S]+)$/);
  return m ? [m[1], m[2]] : [answer, ""];
}

export function BrainView({
  graph,
  stub,
  initialQuestion = null,
}: {
  graph: GraphView;
  stub: boolean;
  initialQuestion?: string | null;
}) {
  const [draft, setDraft] = useState(initialQuestion ?? "");
  const [asked, setAsked] = useState<string | null>(null);
  const [answer, setAnswer] = useState<(AskOut & { stub: boolean }) | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);
  const [focus, setFocus] = useState<{ id: string; n: number } | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setDraft(q);
    setAsked(q);
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      const r = await api.ask(q);
      setAnswer({ ...r.data, stub: r.stub });
    } catch (e) {
      setError(
        e instanceof ApiError && e.message.includes("ANTHROPIC_API_KEY")
          ? "The Brain needs an Anthropic API key on the backend (ANTHROPIC_API_KEY) to answer."
          : e instanceof ApiError
            ? e.message
            : "The backend is not reachable.",
      );
    } finally {
      setBusy(false);
    }
  }

  // A question from the command palette (?q=) is asked as soon as the page is here.
  const askedInitial = useRef(false);
  useEffect(() => {
    if (initialQuestion && !askedInitial.current) {
      askedInitial.current = true;
      void ask(initialQuestion);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuestion]);

  const close = () => {
    setAsked(null);
    setAnswer(null);
    setError(null);
    input.current?.focus();
  };

  const open = asked !== null;
  const [headline, body] = answer ? split(answer.answer) : ["", ""];
  const names = new Map(graph.nodes.map((n) => [n.id, n.name]));
  const services = graph.nodes.filter((n) => n.kind === "Service").length;
  const teams = new Set(graph.nodes.map((n) => n.team).filter(Boolean)).size;

  return (
    <>
      <section
        aria-label="Ask about your systems"
        className="relative flex flex-col items-center gap-5 pt-6 pb-2 text-center sm:pt-10"
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-20 left-1/2 h-72 w-[min(900px,100%)] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgb(255_178_36/0.10),rgb(106_168_255/0.06)_55%,transparent)] blur-2xl"
        />
        <div className="relative flex flex-wrap items-center justify-center gap-2">
          <span className="inline-flex h-7 items-center gap-2 rounded-full bg-white/[0.04] px-3 text-xs text-text-2 ring-1 ring-white/10 ring-inset">
            <BrainCircuit aria-hidden="true" className="size-3.5 text-amber" />
            Company brain
            <span className="text-faint">·</span>
            <span className="text-muted">
              {services} services, {teams} teams
            </span>
          </span>
          <StubBadge show={stub} what="Stub data" />
        </div>
        <div className="relative">
          <h1 className="m-0 text-sheen font-serif text-[44px] leading-[1.02] font-normal tracking-[-0.02em] sm:text-[64px]">
            Ask about{" "}
            <em className="text-amber [-webkit-text-fill-color:var(--amber)]">
              your systems
            </em>
          </h1>
        </div>
        <div className="relative">
          <p className="m-0 max-w-xl text-[15px] leading-6 text-muted">
            Who owns what, who knows what, and what breaks if something goes
            down. Every answer shows where it came from.
          </p>
        </div>
        <div className="relative w-full max-w-2xl">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              ask(draft);
            }}
            className="flex flex-col gap-3"
          >
            <label htmlFor="ask" className="sr-only">
              Ask about your systems
            </label>
            <div
              className={`relative flex h-14 items-center gap-3 rounded-2xl pr-2 pl-4 glass-float ${focused ? "shadow-[0_0_0_4px_rgb(106_168_255/0.10),var(--shadow-float)]" : ""}`}
            >
              {/* Focused: a short blue light runs round the border. */}
              {focused && (
                <span
                  aria-hidden="true"
                  className="ps-runner"
                  style={{ "--beam": "var(--blue)" } as React.CSSProperties}
                />
              )}
              <Search
                aria-hidden="true"
                className="size-5 flex-none text-muted"
              />
              <input
                ref={input}
                id="ask"
                type="text"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onFocus={() => setFocused(true)}
                onBlur={() => setFocused(false)}
                placeholder="Who knows the payments DB?"
                maxLength={500}
                autoComplete="off"
                className="h-full min-w-0 flex-1 border-none bg-transparent text-left font-[inherit] text-base text-text outline-none placeholder:text-faint"
              />
              <span className="hidden items-center gap-1 text-[11px] text-faint sm:flex">
                <Kbd>
                  <CornerDownLeft className="size-3" />
                </Kbd>
              </span>
              <Button
                type="submit"
                variant="primary"
                size="lg"
                disabled={busy || !draft.trim()}
              >
                {busy ? "Asking…" : "Ask"}
                {!busy && <ArrowRight aria-hidden="true" />}
              </Button>
            </div>
            <ul
              aria-label="Suggested questions"
              className="m-0 flex list-none flex-wrap items-center justify-center gap-2 p-0"
            >
              {ASK_SUGGESTIONS.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    onClick={() => ask(s)}
                    disabled={busy}
                    className="h-8 cursor-pointer rounded-full border border-white/[0.08] bg-white/[0.03] px-3.5 font-[inherit] text-xs text-text-2 transition-all hover:-translate-y-px hover:border-white/20 hover:bg-white/[0.06] hover:text-text active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          </form>
        </div>
      </section>

      {/* The graph makes room for the answer: its column narrows while the panel is open. */}
      <div
        className={`grid items-start gap-4 ${open ? "lg:grid-cols-[minmax(0,1fr)_400px]" : ""}`}
      >
        <div className="min-w-0">
          <CompanyGraph
            graph={graph}
            evidence={answer?.evidence ?? []}
            focus={focus}
          />
        </div>
        {open && (
          <section
            aria-label="Answer"
            onPointerMove={spotlight}
            className={`ps-spotlight relative order-first flex min-w-0 flex-col overflow-hidden rounded-panel glass lg:order-none lg:max-h-[640px] ${answer ? "shadow-[inset_0_0_0_1px_rgb(255_178_36/0.25),var(--shadow-panel)]" : ""}`}
          >
            {answer && (
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-x-10 top-0 h-px bg-[linear-gradient(90deg,transparent,var(--amber),transparent)]"
              />
            )}
            <header className="relative flex h-12 flex-none items-center justify-between gap-3 border-b border-white/[0.05] pr-2 pl-4">
              <h2 className="m-0 flex items-center gap-2.5 text-[13px] font-medium">
                <span className="flex size-6 items-center justify-center rounded-lg border border-white/[0.07] bg-white/[0.04] text-amber">
                  <Sparkles aria-hidden="true" className="size-3.5" />
                </span>
                Answer
              </h2>
              <span className="flex items-center gap-1">
                {answer?.stub && <StubBadge show what="Stub answer" />}
                <button
                  type="button"
                  onClick={close}
                  title="Close the answer"
                  className="flex size-8 cursor-pointer items-center justify-center rounded-[9px] border-none bg-transparent text-muted transition-colors hover:bg-white/[0.07] hover:text-text"
                >
                  <X aria-hidden="true" className="size-4" />
                  <span className="sr-only">Close</span>
                </button>
              </span>
            </header>
            <div
              aria-live="polite"
              className="relative flex min-h-0 flex-col gap-4 overflow-y-auto p-4"
            >
              <div className="self-end rounded-2xl rounded-br-md bg-white/[0.06] px-3.5 py-2 text-left text-[13px] text-text ring-1 ring-white/[0.08] ring-inset">
                {asked}
              </div>
              {busy && (
                <div className="flex flex-col gap-3">
                  <span className="flex items-center gap-2.5 text-[13px]">
                    <AgentBadge agent="brain" state="active" size={26} />
                    <span className="ps-shimmer-text">
                      Checking services, owners and history…
                    </span>
                  </span>
                  <span className="ps-skeleton h-4 w-11/12 rounded" />
                  <span className="ps-skeleton h-3 w-full rounded" />
                  <span className="ps-skeleton h-3 w-4/5 rounded" />
                </div>
              )}
              {error && (
                <p
                  role="alert"
                  className="m-0 rounded-xl bg-sev1-bg px-3 py-2.5 text-[13px] text-sev1-fg ring-1 ring-danger/25 ring-inset"
                >
                  {error}
                </p>
              )}
              {answer && !busy && (
                <>
                  <div className="flex items-start gap-2.5">
                    <AgentBadge agent="brain" state="done" size={26} />
                    <h3 className="m-0 text-[17px] leading-6 font-semibold tracking-[-0.01em]">
                      {headline}
                    </h3>
                  </div>
                  {body && (
                    <p className="m-0 text-[13px] leading-5 text-text-2">
                      {body}
                    </p>
                  )}
                  {answer.evidence.length > 0 && (
                    <div className="flex flex-col gap-1">
                      <div className="pb-1 text-[11px] font-semibold tracking-[0.08em] text-muted uppercase">
                        Sources
                      </div>
                      {answer.evidence.map((id) => (
                        <button
                          key={id}
                          type="button"
                          onClick={() =>
                            setFocus({ id, n: (focus?.n ?? 0) + 1 })
                          }
                          title="Show on the map"
                          className="group flex cursor-pointer items-center justify-between gap-3 rounded-lg border-none bg-transparent px-2 py-2 text-left font-[inherit] text-[13px] text-text transition-colors hover:bg-white/[0.05]"
                        >
                          <span className="flex min-w-0 items-center gap-2.5">
                            <span className="size-1.5 flex-none rounded-full bg-amber shadow-[0_0_6px_var(--amber)]" />
                            <span className="w-16 flex-none text-xs text-faint">
                              {kindOf(id) === "Node" ? "Service" : kindOf(id)}
                            </span>
                            <span className="truncate">
                              {names.get(id) ?? shortId(id)}
                            </span>
                          </span>
                          <span className="flex flex-none items-center gap-1.5">
                            <Mono className="text-[11px] text-muted">{id}</Mono>
                            <Crosshair
                              aria-hidden="true"
                              className="size-3.5 text-faint opacity-0 transition-opacity group-hover:opacity-100"
                            />
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="text-[11px] text-faint">
                    Based on {answer.evidence.length}{" "}
                    {answer.evidence.length === 1 ? "source" : "sources"}.
                  </div>
                </>
              )}
            </div>
          </section>
        )}
      </div>
    </>
  );
}
