"use client";

// Re-fetch something every `ms` while the tab is visible. Used where the backend has no stream
// (the incident list: SSE is per incident).

import { useEffect, useState } from "react";

export function usePolling<T>(
  initial: T,
  fetcher: () => Promise<T>,
  ms: number,
  enabled = true,
) {
  const [value, setValue] = useState(initial);

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    const tick = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const next = await fetcher();
        if (!stopped) setValue(next);
      } catch {
        // backend blipped: keep showing the last good value
      }
    };
    tick(); // right away too, so a new fetcher (e.g. a bigger page) shows without waiting
    const timer = setInterval(tick, ms);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [fetcher, ms, enabled]);

  return value;
}
