import { Pool } from "pg";

import { loadRepoEnv } from "./env";

/**
 * A read connection to the Neon database holding the dbt marts.
 *
 * The pool is kept on `globalThis` so that a dev server reloading a module does not leave
 * a pool behind on every edit. It is small on purpose: each serverless instance opens its
 * own, and Neon's pooled endpoint is what multiplexes them.
 */

declare global {
  var __jobInsightPool: Pool | undefined;
}

/**
 * Take `sslmode` out of the connection string and state the TLS policy here instead.
 *
 * The URL is shared with the Python pipeline, which needs `sslmode=require`. node-postgres
 * reads that as full certificate and hostname verification today, but has announced that a
 * future major version will downgrade it to libpq semantics, which verify nothing. That is
 * exactly the kind of change that alters behaviour without altering any code we wrote, so
 * the strict policy is written down rather than inherited from a string.
 */
function connection(url: string): { connectionString: string; ssl: { rejectUnauthorized: boolean } } {
  const parsed = new URL(url);
  parsed.searchParams.delete("sslmode");
  return { connectionString: parsed.toString(), ssl: { rejectUnauthorized: true } };
}

function pool(): Pool {
  if (!globalThis.__jobInsightPool) {
    loadRepoEnv();
    const url = process.env.DATABASE_URL;
    if (!url) {
      throw new Error("DATABASE_URL is not set. The dashboard reads the marts from Neon.");
    }
    globalThis.__jobInsightPool = new Pool({
      ...connection(url),
      max: 3,
      idleTimeoutMillis: 10_000,
      // A page should fail fast rather than hang while Neon wakes a suspended compute.
      connectionTimeoutMillis: 15_000,
    });
  }
  return globalThis.__jobInsightPool;
}

/** Run a read-only query and return its rows. */
export async function query<T>(text: string, params: unknown[] = []): Promise<T[]> {
  const result = await pool().query(text, params);
  return result.rows as T[];
}
