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
 * drifted from the method is worse than no methodology page. If the file is missing the
 * build fails here, which is the right moment to find out — a dashboard that quietly
 * publishes percentages without saying how they were reached is the thing to avoid.
 */
async function methodology(): Promise<string> {
  "use cache";
  cacheLife("days");
  return fs.readFile(path.join(process.cwd(), "..", "docs", "methodology.md"), "utf8");
}

export default async function MethodologyPage() {
  const source = await methodology();

  return (
    <article className={styles.prose}>
      <Markdown remarkPlugins={[remarkGfm]}>{source}</Markdown>
    </article>
  );
}
