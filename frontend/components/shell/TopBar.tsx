"use client";

// U01 app shell: logo, the two places (War room, Company brain), search / ask (⌘K), the
// workspace, "Live" and who is on call (one person per team, GET /oncall; hover or
// focus for the list). Investigation and Actions belong to an
// incident: they are tabs in its header (components/incident/IncidentHeader), not here.
// The bar keeps still during route transitions (view-transition-name ps-topbar).

import { BrainCircuit, Radar, Search } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Kbd, LiveDot, SPRING } from "@/components/ui";
import { teamColor } from "@/lib/format";
import type { OnCallNow } from "@/lib/types";

import { Logo, Wordmark } from "./Logo";
import { openPalette } from "./CommandPalette";

export function TopBar({ onCall }: { onCall: OnCallNow[] }) {
  const pathname = usePathname();
  const links = [
    {
      href: "/",
      label: "War room",
      icon: Radar,
      current: pathname === "/" || pathname.startsWith("/incidents/"),
    },
    {
      href: "/brain",
      label: "Company brain",
      icon: BrainCircuit,
      current: pathname === "/brain",
    },
  ];

  return (
    <header
      style={{ viewTransitionName: "ps-topbar" }}
      className="relative z-20 flex-none after:absolute after:inset-x-0 after:bottom-0 after:h-px after:bg-[linear-gradient(90deg,transparent,rgb(255_255_255/0.08)_20%,rgb(255_255_255/0.08)_80%,transparent)]"
    >
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-3 px-4 sm:gap-5 sm:px-6">
        <Link
          href="/"
          className="group flex flex-none items-center gap-2.5 text-text hover:text-text"
        >
          <span className="transition-transform duration-300 ease-out group-hover:scale-105 group-hover:rotate-[-8deg]">
            <Logo size={26} />
          </span>
          <span className="hidden sm:inline">
            <Wordmark />
          </span>
        </Link>

        <nav aria-label="Main" className="flex min-w-0 items-center gap-1">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              aria-current={l.current ? "page" : undefined}
              className={`relative flex h-8 flex-none items-center gap-2 rounded-[9px] px-3 text-[13px] font-medium transition-colors ${l.current ? "text-text hover:text-text" : "text-muted hover:text-text"}`}
            >
              {l.current && (
                <motion.span
                  layoutId="topnav"
                  transition={SPRING}
                  className="absolute inset-0 rounded-[9px] bg-white/[0.07] shadow-[inset_0_1px_0_rgb(255_255_255/0.07)]"
                />
              )}
              <l.icon
                aria-hidden="true"
                className={`relative size-4 ${l.current ? "text-text" : ""}`}
              />
              <span className="relative hidden md:inline">{l.label}</span>
              <span className="sr-only md:hidden">{l.label}</span>
            </Link>
          ))}
        </nav>

        <div className="flex-1" />

        <button
          type="button"
          onClick={openPalette}
          className="group flex h-8 w-auto flex-none cursor-pointer items-center gap-2 rounded-[10px] border border-white/[0.08] bg-white/[0.03] px-2.5 font-[inherit] text-[13px] text-muted shadow-[inset_0_1px_0_rgb(255_255_255/0.04)] transition-colors hover:border-white/[0.14] hover:bg-white/[0.06] hover:text-text lg:w-64"
        >
          <Search aria-hidden="true" className="size-4" />
          <span className="hidden flex-1 truncate text-left lg:inline">
            Search or ask a question…
          </span>
          <span className="sr-only lg:hidden">Search or ask the graph</span>
          <span className="hidden items-center gap-0.5 sm:flex">
            <Kbd>⌘</Kbd>
            <Kbd>K</Kbd>
          </span>
        </button>

        <div className="hidden flex-none items-center gap-3 text-xs text-muted md:flex">
          <span className="h-5 w-px bg-white/[0.08]" aria-hidden="true" />
          <span className="flex items-center gap-2" title="Workspace">
            <span className="flex size-5 items-center justify-center rounded-md bg-[linear-gradient(135deg,#2a3350,#151a2a)] text-[10px] font-semibold text-text-2 ring-1 ring-white/10">
              K
            </span>
            <span className="hidden xl:inline">Kestrel Pay</span>
          </span>
          <span
            className="flex items-center gap-1.5"
            title="Services, deploys and owners are up to date"
          >
            <LiveDot tone="ok" size={6} />
            <span className="hidden xl:inline">Live</span>
          </span>
          {onCall.length > 0 && <OnCall people={onCall} />}
        </div>
      </div>
    </header>
  );
}

const initials = (name: string) =>
  name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

// UTC so the server and the browser print the same day.
const day = (ts: number) =>
  new Date(ts * 1000).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });

/** Avatars of everyone on call (ringed in their team's colour); the list on hover or focus. */
function OnCall({ people }: { people: OnCallNow[] }) {
  const shown = people.slice(0, 4);
  return (
    <div className="group relative">
      <button
        type="button"
        aria-label={`On call now: ${people.map((p) => `${p.name} (${p.team})`).join(", ")}`}
        className="flex cursor-default items-center gap-2 rounded-lg border-none bg-transparent p-0 font-[inherit] text-xs text-muted"
      >
        <span className="flex -space-x-1" aria-hidden="true">
          {shown.map((p) => (
            <span
              key={p.team}
              className="flex size-7 items-center justify-center rounded-full border-2 border-bg bg-[linear-gradient(135deg,#3a3f52,#1c2030)] text-[10px] font-semibold text-text"
              style={{ boxShadow: `0 0 0 1.5px ${teamColor(p.team)}` }}
            >
              {initials(p.name)}
            </span>
          ))}
        </span>
        <span className="hidden flex-col text-left leading-tight lg:flex">
          <span className="text-[10px] tracking-wide text-faint uppercase">
            On call
          </span>
          <span className="text-xs text-text-2">
            {people.length === 1 ? people[0].name : `${people.length} teams`}
          </span>
        </span>
      </button>
      <div
        role="tooltip"
        className="invisible absolute top-full right-0 z-30 mt-2 w-[340px] rounded-xl border border-white/10 bg-[#0f1118] p-1.5 opacity-0 shadow-[var(--shadow-float)] group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
      >
        <div className="px-2 pt-1 pb-1.5 text-[10px] tracking-wide text-faint uppercase">
          On call now
        </div>
        <ul className="m-0 flex list-none flex-col p-0">
          {people.map((p) => (
            <li
              key={p.team}
              className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-xs"
            >
              <span
                aria-hidden="true"
                className="size-2 flex-none rounded-full"
                style={{ background: teamColor(p.team) }}
              />
              <span className="w-[132px] flex-none truncate text-muted">
                {p.team}
              </span>
              <span className="min-w-0 flex-1 truncate text-text">
                {p.name}
              </span>
              <span className="flex-none text-[11px] text-faint">
                to {day(p.until)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
