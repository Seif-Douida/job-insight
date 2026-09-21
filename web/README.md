# Dashboard

The published face of Job Insight: a coverage matrix on the front page, and one page per
role and region showing which skills employers name and how often.

```bash
npm install
npm run dev        # http://localhost:3000
npm run build      # prerenders every cohort; fails if the database is unreachable
npm run lint
```

## How it reads data

Pages are React Server Components that query the `analytics` schema in Neon directly
through `pg`. There is no API layer, because nothing outside these pages consumes the
data — if something ever does, a route handler can be added then.

`DATABASE_URL` comes from the repository-root `.env`, loaded by `lib/env.ts`. On Vercel it
comes from the project's environment variables instead, and the file is simply absent.

Every query in `lib/queries.ts` is wrapped in `use cache` with an hourly lifetime. The
marts are rebuilt once a day by the `transform` DAG, so a live query per request would
add latency and keep a free-tier database awake for nothing.

## A note on deployment

On Vercel the **root directory is `web`**, so this folder deploys on its own. Vercel reads
the `package.json` at the root directory to decide which framework a project uses, and
pointing it at the repository root instead fails with `No Next.js version detected` however
the build command is configured.

That means nothing above this folder exists at build or run time, which is why
`content/methodology.md` is committed rather than generated. `scripts/sync-docs.mjs`
refreshes it from `docs/methodology.md` whenever the original is present — locally, and in
CI — and `pipeline/tests/test_published_docs.py` fails if the two drift apart. With neither
file available the build stops rather than publishing percentages with no account of where
they came from.
