import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The marts are rebuilt once a day by the `transform` DAG, so every page can be a
  // cached shell rather than a live query. `use cache` in lib/queries.ts sets the
  // lifetime; this is what turns it on.
  cacheComponents: true,
};

export default nextConfig;
