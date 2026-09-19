import type { Metadata } from "next";
import { Newsreader, Public_Sans } from "next/font/google";
import Link from "next/link";

import "./globals.css";
import styles from "./layout.module.css";

/**
 * Public Sans is the face of the US federal design system, drawn for statistical
 * publishing: it has the figures and the plain tone this material wants. Newsreader
 * carries the one sentence per page that is written rather than counted.
 */
const sans = Public_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const serif = Newsreader({
  subsets: ["latin"],
  variable: "--font-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Job Insight",
    template: "%s — Job Insight",
  },
  description:
    "What companies ask for in data and AI job postings, counted by role and region.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body>
        <header className={styles.masthead}>
          <div className={`wrap ${styles.mastheadInner}`}>
            <Link href="/" className={styles.wordmark}>
              Job Insight
            </Link>
            <nav>
              <Link href="/methodology" className="small">
                How this is counted
              </Link>
            </nav>
          </div>
        </header>

        <main className="wrap">{children}</main>

        <footer className={styles.footer}>
          <div className={`wrap small quiet ${styles.footerInner}`}>
            <p>
              Counted from public job postings. A percentage is the share of postings in
              that role and region naming a skill, never a share of hires.
            </p>
            <p>
              <a href="https://github.com/Seif-Douida/job-insight">Source and method</a>
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
