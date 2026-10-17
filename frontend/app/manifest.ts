import type { MetadataRoute } from "next";

// Web app manifest (/manifest.webmanifest). Icons come from `npm run brand`.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "PagerSage",
    short_name: "PagerSage",
    description:
      "Finds the likely root cause, pages the owner and remembers what fixed it.",
    start_url: "/",
    display: "standalone",
    background_color: "#121628",
    theme_color: "#121628",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
