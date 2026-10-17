"use client";

// ⌘K / Ctrl+K anywhere (or the search button in the top bar): jump to an incident or a screen,
// or ask a question (the Company brain). Arrow keys move, Enter opens, Esc closes. Incidents load the first
// time it opens (lib/api, so stubs when the backend is down).

import {
  ArrowRight,
  BrainCircuit,
  CornerDownLeft,
  Radar,
  ScanSearch,
  Search,
  Sparkles,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Kbd, SevPill } from "@/components/ui";
import { api } from "@/lib/api";
import { ASK_SUGGESTIONS, age, currentAgent } from "@/lib/format";
import type { IncidentSummary } from "@/lib/types";

const OPEN_EVENT = "ps:palette";
export const openPalette = () => window.dispatchEvent(new Event(OPEN_EVENT));

type Item = {
  id: string;
  group: string;
  text: string; // what the query matches
  label: React.ReactNode;
  icon?: LucideIcon;
  lead?: React.ReactNode;
  hint?: React.ReactNode;
  href: string;
};

const matches = (text: string, q: string) => {
  const t = text.toLowerCase();
  return q
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((w) => t.includes(w));
};

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const [incidents, setIncidents] = useState<IncidentSummary[] | null>(null);
  const [current, setCurrent] = useState<string | null>(null);
  const router = useRouter();
  const returnFocus = useRef<HTMLElement | null>(null);

  const show = useCallback(() => {
    returnFocus.current = document.activeElement as HTMLElement | null;
    // The incident in view: from the path, or the war room's ?incident=.
    const fromPath = window.location.pathname.match(/^\/incidents\/([^/]+)/);
    const fromQuery = new URLSearchParams(window.location.search).get(
      "incident",
    );
    setCurrent(fromPath?.[1] ?? fromQuery ?? null);
    setQ("");
    setActive(0);
    setOpen(true);
  }, []);
  const hide = useCallback(() => {
    setOpen(false);
    returnFocus.current?.focus?.();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) hide();
        else show();
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_EVENT, show);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_EVENT, show);
    };
  }, [open, show, hide]);

  useEffect(() => {
    if (open && !incidents)
      api
        .incidents({ limit: 50 })
        .then((r) => setIncidents(r.data))
        .catch(() => setIncidents([]));
  }, [open, incidents]);

  const items = useMemo(() => {
    const focus = current ?? incidents?.[0]?.id ?? null;
    const goto: Item[] = [
      {
        id: "go-warroom",
        group: "Go to",
        text: "war room incidents live",
        label: "War room",
        icon: Radar,
        href: focus ? `/?incident=${focus}` : "/",
      },
      {
        id: "go-brain",
        group: "Go to",
        text: "company brain graph ask",
        label: "Company brain",
        icon: BrainCircuit,
        href: "/brain",
      },
      ...(focus
        ? [
            {
              id: "go-investigation",
              group: "Go to",
              text: `investigation suspects scores memory ${focus}`,
              label: (
                <>
                  Investigation <span className="text-muted">· {focus}</span>
                </>
              ),
              icon: ScanSearch,
              href: `/incidents/${focus}/investigation`,
            },
            {
              id: "go-actions",
              group: "Go to",
              text: `actions revert resolve page issue ${focus}`,
              label: (
                <>
                  Actions <span className="text-muted">· {focus}</span>
                </>
              ),
              icon: Zap,
              href: `/incidents/${focus}/actions`,
            },
          ]
        : []),
    ];
    const incidentItems: Item[] = (incidents ?? []).map((i) => ({
      id: `inc-${i.id}`,
      group: "Incidents",
      text: `${i.id} ${i.title} ${i.status} ${i.severity ?? ""}`,
      lead: <SevPill severity={i.severity} small />,
      label: (
        <span className="flex min-w-0 items-baseline gap-2">
          <span className="flex-none font-mono text-xs text-muted">{i.id}</span>
          <span className="truncate">{i.title}</span>
        </span>
      ),
      hint: (
        <span className="text-[11px] text-faint">
          {i.status === "resolved" ? "Resolved" : currentAgent(i)} ·{" "}
          {age(i.opened_at)}
        </span>
      ),
      href: `/?incident=${i.id}`,
    }));
    const query = q.trim();
    const ask: Item[] = query
      ? [
          {
            id: "ask-query",
            group: "Ask a question",
            text: query,
            icon: Sparkles,
            label: (
              <>
                Ask <span className="text-text">“{query}”</span>
              </>
            ),
            href: `/brain?q=${encodeURIComponent(query)}`,
          },
        ]
      : ASK_SUGGESTIONS.map((s, n) => ({
          id: `ask-${n}`,
          group: "Ask a question",
          text: s,
          icon: Sparkles,
          label: s,
          href: `/brain?q=${encodeURIComponent(s)}`,
        }));
    if (!query) return [...goto, ...incidentItems.slice(0, 6), ...ask];
    return [
      ...goto.filter((i) => matches(i.text, query)),
      ...incidentItems.filter((i) => matches(i.text, query)),
      ...ask,
    ];
  }, [incidents, current, q]);

  const go = (item: Item | undefined) => {
    if (!item) return;
    setOpen(false);
    router.push(item.href);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Tab") {
      // The input is the dialog's only stop: results are picked with the arrow keys.
      e.preventDefault();
    } else if (e.key === "Escape") {
      e.preventDefault();
      hide();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const n = items.length;
      const next = (active + (e.key === "ArrowDown" ? 1 : -1) + n) % n;
      setActive(next);
      document
        .getElementById(`palette-${items[next]?.id}`)
        ?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(items[active]);
    }
  };

  let lastGroup = "";
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="palette"
          className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh]"
          initial={{ opacity: 1 }}
          exit={{ opacity: 1 }}
        >
          <motion.div
            aria-hidden="true"
            onClick={hide}
            className="absolute inset-0 bg-[rgb(3_4_8/0.6)] backdrop-blur-[3px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Search and ask"
            onKeyDown={onKeyDown}
            initial={{ opacity: 0, scale: 0.96, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: -6 }}
            transition={{ type: "spring", bounce: 0.2, duration: 0.38 }}
            className="relative flex w-full max-w-[640px] flex-col overflow-hidden rounded-2xl glass-float"
          >
            <div className="flex h-14 items-center gap-3 border-b border-white/[0.07] px-4">
              <Search aria-hidden="true" className="size-[18px] text-muted" />
              <input
                autoFocus
                role="combobox"
                aria-expanded="true"
                aria-controls="palette-list"
                aria-activedescendant={
                  items[active] ? `palette-${items[active].id}` : undefined
                }
                aria-label="Search incidents and screens, or ask a question"
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setActive(0);
                }}
                placeholder="Search incidents, jump to a screen, or ask a question…"
                className="h-full min-w-0 flex-1 border-none bg-transparent font-[inherit] text-[15px] text-text outline-none placeholder:text-faint"
              />
              <Kbd>esc</Kbd>
            </div>
            <ul
              id="palette-list"
              role="listbox"
              aria-label="Results"
              className="m-0 max-h-[min(60vh,460px)] list-none overflow-y-auto p-2"
            >
              {items.map((item, n) => {
                const head = item.group !== lastGroup;
                lastGroup = item.group;
                const on = n === active;
                return (
                  <li key={item.id} role="presentation">
                    {head && (
                      <div className="px-2.5 pt-2.5 pb-1.5 text-[11px] font-medium tracking-[0.06em] text-faint uppercase">
                        {item.group}
                      </div>
                    )}
                    <div
                      id={`palette-${item.id}`}
                      role="option"
                      aria-selected={on}
                      onMouseMove={() => n !== active && setActive(n)}
                      onClick={() => go(item)}
                      className={`relative flex h-10 cursor-pointer items-center gap-3 rounded-[10px] px-2.5 text-[13px] ${on ? "text-text" : "text-text-2"}`}
                    >
                      {on && (
                        <motion.span
                          layoutId="palette-active"
                          transition={{
                            type: "spring",
                            bounce: 0.15,
                            duration: 0.3,
                          }}
                          className="absolute inset-0 rounded-[10px] bg-white/[0.07] shadow-[inset_0_1px_0_rgb(255_255_255/0.06)]"
                        />
                      )}
                      <span className="relative flex w-9 flex-none justify-center">
                        {item.lead ??
                          (item.icon && (
                            <item.icon
                              aria-hidden="true"
                              className={`size-4 ${item.group.startsWith("Ask") ? "text-amber" : "text-muted"}`}
                            />
                          ))}
                      </span>
                      <span className="relative min-w-0 flex-1 truncate">
                        {item.label}
                      </span>
                      {item.hint && (
                        <span className="relative hidden flex-none sm:block">
                          {item.hint}
                        </span>
                      )}
                      <span
                        className={`relative flex-none transition-opacity ${on ? "opacity-100" : "opacity-0"}`}
                        aria-hidden="true"
                      >
                        {item.group.startsWith("Ask") ? (
                          <ArrowRight className="size-4 text-amber" />
                        ) : (
                          <CornerDownLeft className="size-3.5 text-muted" />
                        )}
                      </span>
                    </div>
                  </li>
                );
              })}
              {items.length === 0 && (
                <li className="px-3 py-8 text-center text-[13px] text-muted">
                  Nothing matches.
                </li>
              )}
            </ul>
            <footer className="flex h-10 items-center gap-4 border-t border-white/[0.07] px-4 text-[11px] text-faint">
              <span className="flex items-center gap-1.5">
                <Kbd>↑</Kbd>
                <Kbd>↓</Kbd> move
              </span>
              <span className="flex items-center gap-1.5">
                <Kbd>↵</Kbd> open
              </span>
              <span className="ml-auto flex items-center gap-1.5">
                <Sparkles aria-hidden="true" className="size-3 text-amber" />
                Every answer shows its sources
              </span>
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
