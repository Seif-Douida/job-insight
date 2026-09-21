/**
 * Refresh the published documents inside the app from the repository's originals.
 *
 * `/methodology` renders `docs/methodology.md` rather than restating it, because a
 * methodology page that has drifted from the method is worse than none. But the deployed
 * app is only the `web/` directory — Vercel needs `web/package.json` at its root to
 * recognise a Next.js project at all — so the page cannot read a file that lives a level
 * above it at runtime.
 *
 * So the copy under `content/` is committed, and this refreshes it whenever the original is
 * to hand. `pipeline/tests/test_published_docs.py` fails if the two ever differ, which is
 * what keeps the copy honest.
 */

import { access, copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.resolve(here, "..");
const repo = path.resolve(web, "..");

const DOCUMENTS = [["docs/methodology.md", "content/methodology.md"]];

const exists = async (file) =>
  access(file).then(
    () => true,
    () => false,
  );

for (const [from, to] of DOCUMENTS) {
  const source = path.join(repo, from);
  const target = path.join(web, to);
  await mkdir(path.dirname(target), { recursive: true });

  if (await exists(source)) {
    await copyFile(source, target);
    console.log(`synced ${from} → web/${to}`);
  } else if (await exists(target)) {
    // Building from `web/` alone, as the deployment does. The committed copy is the source.
    console.log(`using the committed web/${to} (${from} is outside this build)`);
  } else {
    // Neither one. Failing here is the point: a dashboard that publishes percentages with
    // no account of how they were reached is worse than one that did not deploy.
    throw new Error(`Neither ${from} nor web/${to} exists; /methodology would be empty.`);
  }
}
