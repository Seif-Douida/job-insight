import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";

const here = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  // The marts are rebuilt once a day by the `transform` DAG, so every page can be a
  // cached shell rather than a live query. `use cache` in lib/queries.ts sets the
  // lifetime; this is what turns it on.
  cacheComponents: true,

  // Next infers the project root from the nearest lockfile, which on this machine finds a
  // stray one in the home directory. Saying where the app starts keeps the build reading
  // the same tree everywhere, rather than whatever happens to sit above it.
  turbopack: { root: here },
  outputFileTracingRoot: here,

  // The methodology page reads its markdown at runtime when the cached page revalidates.
  // A path built with `path.join` is not something the bundler can follow, so the file is
  // named here explicitly; without it the page works in development and 500s a day after
  // deploying, which is the worst moment to find out.
  outputFileTracingIncludes: {
    "/methodology": ["./content/**"],
  },
};

export default nextConfig;
