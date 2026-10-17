"use client";

// Client-wide setup: motion follows the OS "reduce motion" setting everywhere, and one clock
// (`now`, read on the server) drives every relative time.

import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";

import { NowProvider } from "@/components/shell/Now";

export function Providers({
  now,
  children,
}: {
  now: number;
  children: ReactNode;
}) {
  return (
    <MotionConfig reducedMotion="user">
      <NowProvider initial={now}>{children}</NowProvider>
    </MotionConfig>
  );
}
