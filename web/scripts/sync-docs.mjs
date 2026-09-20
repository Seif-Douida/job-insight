/**
 * Copy the published documents into the app before a build.
 *
 * `/methodology` renders `docs/methodology.md` rather than keeping a second copy of it, but
 * reading it from outside the app directory only works while the whole repository is on
 * disk. On a serverless host the deployment holds the app, so a cached page revalidating a
 * day later would look for a file that was never shipped — a failure that appears long
 * after the deploy, on a page whose entire job is to be trustworthy.
 *
 * Copying at build time keeps one editable source and puts the file where the runtime can
 * reach it. The copy is generated and gitignored; `docs/methodology.md` stays the original.
 */

import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "..", "..");

const DOCUMENTS = [["docs/methodology.md", "content/methodology.md"]];

for (const [from, to] of DOCUMENTS) {
  const source = path.join(repo, from);
  const target = path.join(here, "..", to);
  await mkdir(path.dirname(target), { recursive: true });
  try {
    await copyFile(source, target);
  } catch (error) {
    // Failing the build is the point. A dashboard that publishes percentages with no
    // account of how they were reached is worse than one that did not deploy.
    console.error(`Could not read ${from}. The build needs the whole repository, not just web/.`);
    throw error;
  }
  console.log(`synced ${from} → web/${to}`);
}
