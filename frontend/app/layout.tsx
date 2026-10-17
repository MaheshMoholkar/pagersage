import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";

import { CommandPalette } from "@/components/shell/CommandPalette";
import { TopBar } from "@/components/shell/TopBar";
import { api } from "@/lib/api";

import { Providers } from "./providers";
import "./globals.css";

// Geist for everything; Geist Mono only for ids, shas, tool calls, scores and times;
// Instrument Serif only for the few display moments (brain hero, resolved banner).
const geist = Geist({ variable: "--font-geist", subsets: ["latin"] });
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});
const instrument = Instrument_Serif({
  variable: "--font-instrument",
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
});

// Icons (app/icon.svg, favicon.ico, apple-icon.png, opengraph-image.png) and the manifest
// are picked up by file convention; regenerate them from docs/brand/ with `npm run brand`.
export const metadata: Metadata = {
  title: { default: "PagerSage", template: "%s · PagerSage" },
  description:
    "Finds the likely root cause, pages the owner and remembers what fixed it.",
  applicationName: "PagerSage",
};

export const viewport: Viewport = {
  themeColor: "#07080c",
  colorScheme: "dark",
};

// App shell: the top bar keeps its height and <main> takes the rest of the window and scrolls,
// so a page can fill exactly the space that's left (the War room) or scroll (everything else).
// The request's clock, read once on the server: every relative time on the page starts from it
// (components/shell/Now), so the server and the browser print the same "3 d".
const requestTime = () => Date.now() / 1000;

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const onCall = await api.onCall();
  const now = requestTime();
  return (
    <html
      lang="en"
      className={`${geist.variable} ${geistMono.variable} ${instrument.variable}`}
    >
      <body className="flex h-dvh flex-col overflow-hidden">
        <Providers now={now}>
          <div className="ps-ambient" aria-hidden="true" />
          <TopBar onCall={onCall.data} />
          <main className="relative min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex min-h-full max-w-[1600px] flex-col gap-5 px-4 py-5 sm:px-6 xl:has-[[data-fill]]:h-full">
              {children}
            </div>
          </main>
          <CommandPalette />
        </Providers>
      </body>
    </html>
  );
}
