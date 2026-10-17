// Route transitions (React <ViewTransition>): pages fade up into place; moving between an
// incident's tabs slides in the direction of the tab (Link transitionTypes "nav-forward" /
// "nav-back", see components/incident/IncidentHeader). The CSS is in app/globals.css.
// Layouts persist across navigations, so every page wraps its own content in this.

import { ViewTransition, type ReactNode } from "react";

const TYPES = {
  "nav-forward": "nav-forward",
  "nav-back": "nav-back",
  default: "ps-page",
};

export function PageTransition({
  fill = false,
  children,
}: {
  fill?: boolean; // the page fills the window on wide screens (see app/layout.tsx)
  children: ReactNode;
}) {
  return (
    <ViewTransition enter={TYPES} exit={TYPES} default="none">
      <div
        data-fill={fill || undefined}
        className={`flex flex-col gap-5 ${fill ? "xl:min-h-0 xl:flex-1" : ""}`}
      >
        {children}
      </div>
    </ViewTransition>
  );
}
