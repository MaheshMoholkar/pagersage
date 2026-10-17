"use client";

// The animated half of the UI kit (motion/react). Everything here explains something:
// panels and rows arrive in reading order, numbers count up to their value, bars fill to it,
// a selection slides to the option you picked. <MotionConfig reducedMotion="user"> in
// app/providers.tsx turns the movement off for people who ask for less.

import {
  animate,
  motion,
  useReducedMotion,
  type HTMLMotionProps,
} from "motion/react";
import {
  useEffect,
  useId,
  useRef,
  type PointerEvent,
  type ReactNode,
} from "react";

import { pct } from "@/lib/format";

export const EASE = [0.22, 1, 0.36, 1] as const;
export const SPRING = { type: "spring", bounce: 0.18, duration: 0.45 } as const;

/** Soft light under the pointer: put on an element with the `ps-spotlight` class. */
export function spotlight(e: PointerEvent<HTMLElement>) {
  const r = e.currentTarget.getBoundingClientRect();
  e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
  e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
}

const TONE = {
  none: "",
  found:
    "before:bg-[linear-gradient(90deg,transparent,var(--amber),transparent)] after:bg-[radial-gradient(60%_120px_at_50%_0%,rgb(255_178_36/0.09),transparent)]",
  agent:
    "before:bg-[linear-gradient(90deg,transparent,var(--blue),transparent)] after:bg-[radial-gradient(60%_120px_at_50%_0%,rgb(106_168_255/0.08),transparent)]",
  ok: "before:bg-[linear-gradient(90deg,transparent,var(--ok),transparent)] after:bg-[radial-gradient(60%_120px_at_50%_0%,rgb(61_220_151/0.08),transparent)]",
  danger:
    "before:bg-[linear-gradient(90deg,transparent,var(--danger),transparent)] after:bg-[radial-gradient(60%_120px_at_50%_0%,rgb(255_93_108/0.08),transparent)]",
};
export type Tone = keyof typeof TONE;

/** Every region: a glass surface, a 48px header (icon, title, count, actions), a body and an
 *  optional footer. `tone` lights the top edge in a meaning colour. Fades up on mount after
 *  `delay` seconds, unless `still` (the panel is simply there; only its contents animate). */
export function Panel({
  title,
  label,
  icon,
  count,
  actions,
  footer,
  flush = false,
  tone = "none",
  delay = 0,
  still = false,
  className = "",
  bodyClassName = "",
  children,
}: {
  title?: ReactNode;
  label: string; // aria-label for the region
  icon?: ReactNode;
  count?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  flush?: boolean; // no body padding (lists that run edge to edge)
  tone?: Tone;
  delay?: number;
  still?: boolean;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}) {
  return (
    <motion.section
      aria-label={label}
      initial={still ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay, ease: EASE }}
      className={`relative flex min-h-0 min-w-0 flex-col overflow-hidden rounded-panel glass ${tone !== "none" ? `before:pointer-events-none before:absolute before:inset-x-10 before:top-0 before:h-px before:opacity-80 after:pointer-events-none after:absolute after:inset-0 ${TONE[tone]}` : ""} ${className}`}
    >
      {(title || actions) && (
        <header className="relative z-[1] flex h-12 flex-none items-center justify-between gap-3 border-b border-white/[0.05] pr-3 pl-4">
          <h2 className="m-0 flex min-w-0 items-center gap-2.5 truncate text-[13px] font-medium text-text">
            {icon && (
              <span
                aria-hidden="true"
                className="flex size-6 flex-none items-center justify-center rounded-lg border border-white/[0.07] bg-white/[0.04] text-text-2 [&_svg]:size-3.5"
              >
                {icon}
              </span>
            )}
            <span className="truncate">{title}</span>
            {count != null && (
              <span className="rounded-full bg-white/[0.06] px-1.5 text-[11px] leading-[18px] font-medium text-muted tabular">
                {count}
              </span>
            )}
          </h2>
          {actions && (
            <div className="flex flex-none items-center gap-1.5">{actions}</div>
          )}
        </header>
      )}
      <div
        className={`relative z-[1] flex min-h-0 flex-1 flex-col ${flush ? "" : "p-4"} ${bodyClassName}`}
      >
        {children}
      </div>
      {footer && (
        <footer className="relative z-[1] flex-none border-t border-white/[0.05] px-4 py-2.5 text-xs text-muted">
          {footer}
        </footer>
      )}
    </motion.section>
  );
}

/** Fade up (and un-blur) on mount. */
export function Reveal({
  delay = 0,
  y = 10,
  className,
  children,
  ...rest
}: {
  delay?: number;
  y?: number;
  className?: string;
  children: ReactNode;
} & Omit<HTMLMotionProps<"div">, "children">) {
  return (
    <motion.div
      initial={{ opacity: 0, y, filter: "blur(4px)" }}
      animate={{
        opacity: 1,
        y: 0,
        filter: "blur(0px)",
        transitionEnd: { filter: "none" },
      }}
      transition={{ duration: 0.55, delay, ease: EASE }}
      className={className}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

/** A number that counts up to `value` (from the last value it showed). */
export function CountUp({
  value,
  decimals = 0,
  duration = 0.9,
  delay = 0,
  prefix = "",
  suffix = "",
  className = "",
}: {
  value: number;
  decimals?: number;
  duration?: number;
  delay?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const from = useRef(0);
  const reduce = useReducedMotion();
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const show = (v: number) =>
      (el.textContent = `${prefix}${v.toFixed(decimals)}${suffix}`);
    if (reduce) {
      show(value);
      from.current = value;
      return;
    }
    const controls = animate(from.current, value, {
      duration,
      delay,
      ease: EASE,
      onUpdate: show,
    });
    from.current = value;
    return () => controls.stop();
  }, [value, decimals, duration, delay, prefix, suffix, reduce]);
  return (
    <span ref={ref} className={`tabular ${className}`}>
      {prefix}
      {value.toFixed(decimals)}
      {suffix}
    </span>
  );
}

/** A bar that fills to `value` (0–1). */
export function Meter({
  value,
  tone = "neutral",
  delay = 0,
  className = "h-1",
}: {
  value: number;
  tone?: "found" | "neutral" | "ok" | "agent" | "danger";
  delay?: number;
  className?: string;
}) {
  const fill = {
    found:
      "bg-[linear-gradient(90deg,var(--amber-2),var(--amber))] shadow-[0_0_12px_rgb(255_178_36/0.5)]",
    neutral: "bg-white/25",
    ok: "bg-ok",
    agent: "bg-blue",
    danger: "bg-danger",
  }[tone];
  return (
    <span
      className={`block w-full overflow-hidden rounded-full bg-white/[0.06] ${className}`}
    >
      <motion.span
        className={`block h-full rounded-full ${fill}`}
        initial={{ width: 0 }}
        animate={{ width: pct(Math.max(0, Math.min(1, value))) }}
        transition={{ duration: 0.9, delay, ease: EASE }}
      />
    </span>
  );
}

/** Two or three options in a track; the selection slides between them. */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  size = "sm",
}: {
  label: string;
  value: T;
  options: { value: T; label: ReactNode }[];
  onChange: (v: T) => void;
  size?: "sm" | "md";
}) {
  const id = useId();
  return (
    <div
      role="group"
      aria-label={label}
      className="relative flex flex-none rounded-[10px] border border-white/[0.06] bg-black/30 p-0.5"
    >
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(o.value)}
            className={`relative cursor-pointer rounded-lg border-none bg-transparent font-[inherit] font-medium whitespace-nowrap transition-colors ${size === "sm" ? "h-6 px-2.5 text-xs" : "h-7 px-3 text-[13px]"} ${on ? "text-text" : "text-muted hover:text-text"}`}
          >
            {on && (
              <motion.span
                layoutId={`seg-${id}`}
                transition={SPRING}
                className="absolute inset-0 rounded-lg bg-white/[0.09] shadow-[inset_0_1px_0_rgb(255_255_255/0.08),0_1px_3px_rgb(0_0_0/0.4)]"
              />
            )}
            <span className="relative">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}
