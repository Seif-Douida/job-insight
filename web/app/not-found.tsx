import Link from "next/link";

export default function NotFound() {
  return (
    <div style={{ paddingTop: "3rem" }}>
      <h1 className="lede" style={{ fontSize: "var(--step-3)" }}>
        There is no page here.
      </h1>
      <p>
        Job Insight covers seven roles across four regions. The table on the front page
        shows every one of them, and how many postings sit behind each.
      </p>
      <p>
        <Link href="/">See what is covered</Link>
      </p>
    </div>
  );
}
