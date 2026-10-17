import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The route badge sits over the War room's feed; compile and runtime errors still show.
  devIndicators: false,
};

export default nextConfig;
