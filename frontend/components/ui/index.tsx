// Shared building blocks. One look everywhere (frontend/README.md, "Design system"):
// glass panels with a light top edge, pills that carry meaning in colour and words, buttons
// that press, and Geist Mono for anything you might copy. Animated pieces (Panel, Reveal,
// CountUp, Meter, Segmented) live in ./motion and are re-exported here.

import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { sevLabel } from "@/lib/format";

export * from "./motion";

/** A section title inside a page: title, one line of description, actions on the right. */
export function SectionHeader({
  eyebrow,
  title,
  description,
  actions,
  id,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  id?: string;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="flex max-w-3xl min-w-0 flex-col gap-1">
        {eyebrow && (
          <div className="text-[11px] font-medium tracking-[0.08em] text-muted uppercase">
            {eyebrow}
          </div>
        )}
        <h2
          id={id}
          className="m-0 text-lg leading-7 font-semibold tracking-[-0.015em]"
        >
          {title}
        </h2>
        {description && (
          <p className="m-0 text-[13px] leading-5 text-muted">{description}</p>
        )}
      </div>
      {actions && (
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      )}
    </div>
  );
}

const SEV_STYLE: Record<string, string> = {
  sev1: "bg-sev1-bg text-sev1-fg ring-danger/30",
  sev2: "bg-sev2-bg text-sev2-fg ring-amber/25",
  sev3: "bg-white/[0.05] text-text-2 ring-white/10",
};

export function SevPill({
  severity,
  small = false,
}: {
  severity: string | null;
  small?: boolean;
}) {
  return (
    <span
      className={`inline-flex flex-none items-center gap-1 rounded-md font-semibold tracking-[0.06em] uppercase ring-1 ring-inset ${small ? "h-[18px] px-1.5 text-[10px]" : "h-6 px-2 text-[11px]"} ${SEV_STYLE[severity ?? ""] ?? SEV_STYLE.sev3}`}
    >
      {sevLabel(severity).replace(" ", "")}
    </span>
  );
}

const STATUS: Record<string, [string, string, string]> = {
  open: ["Open", "bg-danger", "bg-sev1-bg/70 text-sev1-fg ring-danger/25"],
  investigating: [
    "Investigating",
    "bg-blue",
    "bg-blue-tint/80 text-[#a9cbff] ring-blue/25",
  ],
  mitigated: [
    "Mitigated",
    "bg-amber",
    "bg-sev2-bg/80 text-sev2-fg ring-amber/25",
  ],
  resolved: ["Resolved", "bg-ok", "bg-ok-bg text-ok-fg ring-ok/25"],
  needs_human: [
    "Needs a human",
    "bg-danger",
    "bg-sev1-bg/70 text-sev1-fg ring-danger/25",
  ],
};

/** Dot + word: Open → Investigating → Mitigated → Resolved, or Needs a human. */
export function StatusPill({ status }: { status: string }) {
  const [label, dot, look] = STATUS[status] ?? [
    status,
    "bg-muted",
    "bg-white/5 text-text-2 ring-white/10",
  ];
  const live = status === "investigating" || status === "open";
  return (
    <span
      className={`inline-flex h-6 flex-none items-center gap-1.5 rounded-full px-2.5 text-xs font-medium ring-1 ring-inset ${look}`}
    >
      <Dot className={dot} ping={live} />
      {label}
    </span>
  );
}

/** A status dot; `ping` adds a ring that ripples out (live things only). */
export function Dot({
  className = "bg-blue",
  ping = false,
  size = 6,
}: {
  className?: string;
  ping?: boolean;
  size?: number;
}) {
  return (
    <span
      aria-hidden="true"
      className="relative inline-flex flex-none"
      style={{ width: size, height: size }}
    >
      {ping && (
        <span
          className={`ps-ping absolute inset-0 rounded-full ${className}`}
        />
      )}
      <span
        className={`relative inline-flex size-full rounded-full ${className}`}
      />
    </span>
  );
}

/** Rippling dot: blue = an agent is working, green = the graph is live. */
export function LiveDot({
  tone = "blue",
  size = 7,
}: {
  tone?: "blue" | "ok" | "amber";
  size?: number;
}) {
  const color = { blue: "bg-blue", ok: "bg-ok", amber: "bg-amber" }[tone];
  return <Dot className={color} ping size={size} />;
}

/** Ids, shas, tool calls, scores and timestamps. */
export function Mono({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <span className={`font-mono tabular ${className}`}>{children}</span>;
}

/** Node id chip; `found` = amber (only for what PagerSage found). */
export function Chip({
  children,
  found = false,
  className = "",
}: {
  children: ReactNode;
  found?: boolean;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex h-6 flex-none items-center gap-1 rounded-chip px-2 font-mono text-xs ring-1 ring-inset ${found ? "bg-amber-tint text-on-amber-tint ring-amber/30" : "bg-white/[0.04] text-text-2 ring-white/[0.08]"} ${className}`}
    >
      {children}
    </span>
  );
}

/** A keyboard key. */
export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded-[5px] border border-white/10 bg-white/[0.04] px-1 font-mono text-[10px] leading-none text-muted shadow-[inset_0_-1px_0_rgb(255_255_255/0.06)]">
      {children}
    </kbd>
  );
}

const VARIANT = {
  primary:
    "ps-sheen border-transparent bg-[linear-gradient(180deg,#ffc552,#ffa516)] font-semibold text-on-amber shadow-[inset_0_1px_0_rgb(255_255_255/0.45),0_0_0_1px_rgb(255_170_30/0.6),0_8px_24px_-8px_rgb(255_178_36/0.6)] hover:text-on-amber hover:shadow-[inset_0_1px_0_rgb(255_255_255/0.5),0_0_0_1px_rgb(255_190_60/0.8),0_10px_32px_-6px_rgb(255_178_36/0.75)] disabled:shadow-none",
  secondary:
    "border-white/[0.09] bg-white/[0.04] text-text shadow-[inset_0_1px_0_rgb(255_255_255/0.05)] hover:border-white/[0.16] hover:bg-white/[0.08] hover:text-text",
  ghost:
    "border-transparent bg-transparent text-muted hover:bg-white/[0.06] hover:text-text",
};
const SIZE = {
  sm: "h-7 px-2.5 text-xs [&_svg]:size-3.5",
  md: "h-8 px-3 text-[13px] [&_svg]:size-4",
  lg: "h-10 px-4 text-sm [&_svg]:size-4",
};

type Look = { variant?: keyof typeof VARIANT; size?: keyof typeof SIZE };
const look = ({ variant = "secondary", size = "md" }: Look, extra: string) =>
  `inline-flex flex-none cursor-pointer select-none items-center justify-center gap-1.5 rounded-button border font-[inherit] font-medium whitespace-nowrap no-underline transition-[transform,background-color,border-color,box-shadow,color,opacity] duration-150 ease-out active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100 ${VARIANT[variant]} ${SIZE[size]} ${extra}`;

export function ButtonLink({
  variant,
  size,
  className = "",
  ...props
}: ComponentProps<typeof Link> & Look) {
  return <Link {...props} className={look({ variant, size }, className)} />;
}

export function Button({
  variant,
  size,
  className = "",
  ...props
}: ComponentProps<"button"> & Look) {
  return (
    <button
      type="button"
      {...props}
      className={look({ variant, size }, className)}
    />
  );
}

/** Shown when a screen is on stub data (backend down, NEXT_PUBLIC_USE_STUBS=1). */
export function StubBadge({
  show,
  what = "Stub data",
}: {
  show: boolean;
  what?: string;
}) {
  if (!show) return null;
  return (
    <span
      title="The backend is not reachable, so this screen shows the scripted demo incident."
      className="inline-flex h-6 flex-none items-center gap-1.5 rounded-full border border-dashed border-white/15 px-2.5 text-[11px] text-muted"
    >
      <span className="size-1.5 rounded-full bg-faint" aria-hidden="true" />
      {what}
    </span>
  );
}

export function Empty({
  icon,
  children,
}: {
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-10 text-center">
      {icon && (
        <span className="flex size-10 items-center justify-center rounded-xl border border-white/[0.07] bg-white/[0.03] text-muted [&_svg]:size-5">
          {icon}
        </span>
      )}
      <p className="m-0 max-w-xs text-[13px] leading-5 text-muted">
        {children}
      </p>
    </div>
  );
}
