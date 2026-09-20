import fs from "node:fs/promises";
import path from "node:path";

import type { Metadata } from "next";
import { cacheLife } from "next/cache";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "How this is counted",
  description:
    "Where the postings come from, how skills are extracted, and what these numbers cannot tell you.",
};

/**
 * The published methodology is `docs/methodology.md`, rendered rather than retyped.
 *
 * Keeping one copy matters more than avoiding the file read: a methodology page that has
 * drifted from the method is worse than no methodology page. `scripts/sync-docs.mjs` copies
 * it into `content/` before each build, so the runtime reads a file inside the deployment
 * rather than reaching up out of the app directory for one that was never shipped.
 */
async function methodology(): Promise<string> {
  "use cache";
  cacheLife("days");
  return fs.readFile(path.join(process.cwd(), "content", "methodology.md"), "utf8");
}

export default async function MethodologyPage() {
  const source = await methodology();

  return (
    <article className={styles.prose}>
      <Markdown remarkPlugins={[remarkGfm]}>{source}</Markdown>
    </article>
  );
}
