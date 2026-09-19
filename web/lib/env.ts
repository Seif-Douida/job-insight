/**
 * Make the repository-root `.env` visible to the web app.
 *
 * The pipeline and the dashboard read the same Neon database, so the connection string is
 * written once, at the repository root. Next only loads `.env*` files from its own
 * directory, so it is loaded here instead of being copied into a second file that would
 * then have to be kept in step.
 *
 * On Vercel there is no file to read: the variables are already in the environment, and a
 * missing `.env` is the normal case rather than an error.
 */

import path from "node:path";

let loaded = false;

export function loadRepoEnv(): void {
  if (loaded) return;
  loaded = true;
  try {
    process.loadEnvFile(path.join(process.cwd(), "..", ".env"));
  } catch {
    // No file, or no permission to read it. Either way the environment is the source.
  }
}
