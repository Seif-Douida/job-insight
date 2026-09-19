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

`/methodology` renders `docs/methodology.md` from the repository root rather than keeping
a second copy of it. The build therefore needs the whole repository, not just this folder:
on Vercel, leave the root directory at the repository root and set the build command to
`cd web && npm run build`. If the file cannot be read, the build fails rather than
publishing percentages with no account of where they came from.
