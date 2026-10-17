"use client";

// U03 root-cause path: the incident's services on the
// canvas with the path in amber and particles flowing along it (lib/format rootCausePath +
// withAlert), the failing service breathing red with its health, the rejected suspect dashed
// and struck through, fragile services ringed red, and Blast radius: dashed blue rings
// upstream of the failing service plus a ripple. Only services and the nodes that mean
// something here are drawn (lib/format focusGraph). Floating over the canvas: the legend, the
// tools (blast radius, fit, company graph) and the path as a trail of chips; a chip glides
// the view to its node.

import {
  BellRing,
  ChevronRight,
  CircleDot,
  GitCommitHorizontal,
  Maximize2,
  Network,
  Route,
  Settings2,
  User,
  type LucideIcon,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { EASE, Panel } from "@/components/ui";
import { focusGraph, shortId, teamColor } from "@/lib/format";
import type { GraphView, Highlight } from "@/lib/types";

import { GraphCanvas } from "./GraphCanvas";

const LEGEND = [
  [
    "h-0.5 w-4 rounded bg-amber shadow-[0_0_6px_var(--amber)]",
    "Root-cause path",
  ],
  ["size-2.5 rounded-full border border-amber bg-[#5a1d27]", "Failing"],
  ["size-2.5 rounded-full border-2 border-danger", "Fragile"],
  ["size-2.5 rounded-full border border-dashed border-blue", "Blast radius"],
  ["h-2.5 w-4 rounded-sm border border-dashed border-line-strong", "Rejected"],
];

const KIND_ICON: Record<string, LucideIcon> = {
  Alert: BellRing,
  Service: CircleDot,
  ConfigChange: Settings2,
  Deploy: GitCommitHorizontal,
  Commit: GitCommitHorizontal,
  Person: User,
};

function ToolButton({
  label,
  pressed,
  onClick,
  children,
}: {
  label: string;
  pressed?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      title={label}
      onClick={onClick}
      className={`flex h-8 cursor-pointer items-center gap-1.5 rounded-[9px] border-none px-2.5 font-[inherit] text-xs font-medium transition-all active:scale-95 [&_svg]:size-4 ${pressed ? "bg-blue-tint text-[#b5d2ff] shadow-[inset_0_0_0_1px_rgb(106_168_255/0.45),0_0_16px_rgb(106_168_255/0.25)]" : "bg-transparent text-muted hover:bg-white/[0.07] hover:text-text"}`}
    >
      {children}
    </button>
  );
}

export function IncidentGraph({
  graph,
  path: found,
  failing,
  rejected,
  cause,
  delay = 0,
}: {
  graph: GraphView;
  path: Highlight | null;
  failing: string | null;
  rejected: string[];
  cause?: string | null;
  delay?: number;
}) {
  const [blast, setBlast] = useState(false);
  const [fit, setFit] = useState(0);
  const [focus, setFocus] = useState<{ id: string; n: number } | null>(null);
  const path = useMemo(() => found?.nodes ?? [], [found]);
  const focused = useMemo(
    () => focusGraph(graph, [...path, ...rejected]),
    [graph, path, rejected],
  );
  const teams = useMemo(
    () =>
      [
        ...new Set(
          focused.nodes
            .filter((n) => n.kind === "Service")
            .map((n) => n.team)
            .filter((t): t is string => !!t),
        ),
      ].sort(),
    [focused],
  );
  const kinds = useMemo(
    () => new Map(graph.nodes.map((n) => [n.id, n.kind])),
    [graph],
  );
  const sentence = path.length
    ? `Root-cause path: ${path.map(shortId).join(", then ")}.` +
      (rejected.length ? ` Rejected suspects: ${rejected.join(", ")}.` : "")
    : failing
      ? `No root-cause path yet; ${shortId(failing)} is the sickest service.`
      : "No root-cause path yet.";

  return (
    <Panel
      label="Incident map"
      title="Root-cause path"
      icon={<Route />}
      flush
      still
      className="h-[520px] xl:h-auto"
      actions={
        <div className="flex items-center gap-0.5 rounded-[11px] border border-white/[0.06] bg-black/25 p-0.5">
          <ToolButton
            label="Blast radius: what else breaks if the failing service is down"
            pressed={blast}
            onClick={() => setBlast(!blast)}
          >
            <span
              aria-hidden="true"
              className={`size-2.5 rounded-full border border-dashed ${blast ? "border-blue" : "border-current"}`}
            />
            <span>Blast radius</span>
          </ToolButton>
          <ToolButton label="Fit to view" onClick={() => setFit(fit + 1)}>
            <Maximize2 aria-hidden="true" />
            <span className="sr-only">Fit</span>
          </ToolButton>
          <Link
            href="/brain"
            title="Open the Company brain"
            className="flex h-8 items-center rounded-[9px] px-2.5 text-muted transition-colors hover:bg-white/[0.07] hover:text-text"
          >
            <Network aria-hidden="true" className="size-4" />
            <span className="sr-only">Company graph</span>
          </Link>
        </div>
      }
    >
      <ul
        aria-label="Legend"
        className="m-0 flex flex-none list-none flex-wrap gap-x-4 gap-y-1 border-b border-white/[0.05] px-4 py-2 text-[11px] text-muted"
      >
        {teams.map((t) => (
          <li key={t} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-2 rounded-full"
              style={{ background: teamColor(t) }}
            />
            {t}
          </li>
        ))}
        {teams.length > 0 && (
          <li aria-hidden="true" className="h-3 w-px self-center bg-white/10" />
        )}
        {LEGEND.map(([swatch, text]) => (
          <li key={text} className="flex items-center gap-1.5">
            <span className={swatch} aria-hidden="true" />
            {text}
          </li>
        ))}
      </ul>
      <div
        role="img"
        aria-label={sentence}
        className="relative min-h-0 flex-1 dot-grid"
      >
        <GraphCanvas
          graph={focused}
          highlight={found}
          failing={failing}
          blast={blast}
          rejected={rejected}
          colorBy="team"
          sizeBy="role"
          fit={fit}
          focus={focus}
          height="fill"
        />
        {/* soft vignette at the edges */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_55%,rgb(5_6_10/0.65))]"
        />
      </div>
      {/* The path, repeated as text: a chip per step; a chip glides the graph to its node. */}
      <div className="relative flex-none border-t border-white/[0.05]">
        {path.length > 0 ? (
          <ol
            aria-label="Path"
            className="m-0 flex [scrollbar-width:none] list-none items-center gap-1 overflow-x-auto [mask-image:linear-gradient(90deg,#000_calc(100%-32px),transparent)] px-3 py-2.5"
          >
            {path.map((id, i) => {
              const Icon = KIND_ICON[kinds.get(id) ?? ""] ?? CircleDot;
              const isCause = id === cause;
              return (
                <motion.li
                  key={id}
                  className="flex flex-none items-center gap-1 last:pr-6"
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{
                    duration: 0.4,
                    ease: EASE,
                    delay: delay + 0.3 + i * 0.07,
                  }}
                >
                  {i > 0 && (
                    <ChevronRight
                      aria-hidden="true"
                      className="size-3.5 text-amber/50"
                    />
                  )}
                  <button
                    type="button"
                    title={`Show ${shortId(id)} on the graph`}
                    onClick={() => setFocus({ id, n: (focus?.n ?? 0) + 1 })}
                    className={`inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-lg border-none px-2 font-mono text-xs transition-all hover:-translate-y-px active:translate-y-0 ${isCause ? "bg-[linear-gradient(180deg,#ffc552,#ffa516)] font-medium text-on-amber shadow-[0_0_16px_rgb(255_178_36/0.45)]" : "bg-amber-tint text-on-amber-tint ring-1 ring-amber/25 ring-inset hover:ring-amber/50"}`}
                  >
                    <Icon aria-hidden="true" className="size-3.5 opacity-80" />
                    {shortId(id)}
                  </button>
                </motion.li>
              );
            })}
          </ol>
        ) : (
          <p className="ps-shimmer-text m-0 px-3 py-3.5 text-xs">
            The path appears once the Investigator walks it.
          </p>
        )}
      </div>
    </Panel>
  );
}
