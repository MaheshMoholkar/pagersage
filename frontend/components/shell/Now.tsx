"use client";

// One clock for relative times ("3 d ago"). The server reads the time once per request and
// the browser starts from that same value, so server and client render the same text (no
// hydration mismatch at a rounding edge); after that it moves on every 30 seconds.

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

const NowContext = createContext<number | null>(null);

export function NowProvider({
  initial,
  children,
}: {
  initial: number; // epoch seconds, read on the server
  children: ReactNode;
}) {
  const [now, setNow] = useState(initial);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), 30_000);
    return () => clearInterval(id);
  }, []);
  return <NowContext value={now}>{children}</NowContext>;
}

/** Epoch seconds: the request time at first, then ticking every 30 s. */
export function useNow(): number {
  const now = useContext(NowContext);
  if (now === null)
    throw new Error("useNow needs a <NowProvider> (app/providers.tsx)");
  return now;
}
