// The agents' faces: one icon each, and a badge that shows where an agent is in its run
// (queued, working = blue with a turning ring, done = green check).

import {
  BrainCircuit,
  Check,
  History,
  PenLine,
  ScanSearch,
  Siren,
  Stethoscope,
  type LucideIcon,
} from "lucide-react";

export const AGENT_ICON: Record<string, LucideIcon> = {
  triage: Stethoscope,
  investigator: ScanSearch,
  historian: History,
  responder: Siren,
  scribe: PenLine,
  brain: BrainCircuit,
};

/** What each agent does, one line (tooltips, the pipeline). */
export const AGENT_ROLE: Record<string, string> = {
  triage: "Sizes the blast radius and sets severity",
  investigator: "Ranks recent changes and walks to the cause",
  historian: "Finds incidents that broke the same way",
  responder: "Pages the owner, opens the issue, proposes the fix",
  scribe: "Writes the postmortem and credits the runbook",
  brain: "Answers questions about services, owners and past incidents",
};

export type StepState = "done" | "active" | "queued";

export function AgentBadge({
  agent,
  state = "queued",
  size = 28,
}: {
  agent: string;
  state?: StepState;
  size?: number;
}) {
  const Icon = AGENT_ICON[agent] ?? BrainCircuit;
  const look = {
    done: "bg-ok-bg text-ok-fg ring-ok/30",
    active:
      "bg-blue-tint text-[#b5d2ff] ring-blue/40 shadow-[0_0_18px_rgb(106_168_255/0.35)]",
    queued: "bg-white/[0.03] text-faint ring-white/[0.08]",
  }[state];
  return (
    <span
      aria-hidden="true"
      className={`relative flex flex-none items-center justify-center rounded-full ring-1 transition-colors duration-500 ${look}`}
      style={{ width: size, height: size }}
    >
      {state === "active" && (
        <span className="ps-spin absolute -inset-[3px] rounded-full bg-[conic-gradient(from_0deg,transparent_0deg,var(--blue)_90deg,transparent_160deg)] [mask:radial-gradient(farthest-side,transparent_calc(100%-2px),#000_calc(100%-1.5px))]" />
      )}
      <Icon
        style={{ width: size * 0.5, height: size * 0.5 }}
        strokeWidth={1.8}
      />
      {state === "done" && (
        <span className="absolute -right-1 -bottom-1 flex size-3.5 items-center justify-center rounded-full bg-ok text-bg ring-2 ring-bg">
          <Check className="size-2.5" strokeWidth={3.5} />
        </span>
      )}
    </span>
  );
}
