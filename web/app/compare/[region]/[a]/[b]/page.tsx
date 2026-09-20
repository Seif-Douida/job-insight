import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { percent } from "@/lib/format";
import { getCohort, getSkills, listCohorts } from "@/lib/queries";
import { skillSlug } from "@/lib/slug";
import { REGION_ORDER, ROLE_ORDER, regionLabel, roleLabel } from "@/lib/taxonomy";

import styles from "./page.module.css";

/** Rows shown in the difference table. */
const SHOWN = 22;

/** A skill both roles name this often is common ground rather than a difference. */
const SHARED_FLOOR = 0.25;

type Params = { region: string; a: string; b: string };

/**
 * Prerender pairs where both cohorts are large enough to compare honestly. Every other
 * pair still works — it renders on request — it just is not worth building in advance.
 */
export async function generateStaticParams(): Promise<Params[]> {
  const cohorts = await listCohorts();
  const solid = cohorts.filter((c) => !c.lowConfidence);
  const params: Params[] = [];
  for (const region of REGION_ORDER) {
    const roles = solid
      .filter((c) => c.region === region)
      .map((c) => c.role)
      .sort((x, y) => ROLE_ORDER.indexOf(x) - ROLE_ORDER.indexOf(y));
    for (let i = 0; i < roles.length; i += 1) {
      for (let j = i + 1; j < roles.length; j += 1) {
        params.push({ region, a: roles[i], b: roles[j] });
      }
    }
  }
  return params;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { region, a, b } = await params;
  return {
    title: `${roleLabel(a)} or ${roleLabel(b)} in ${regionLabel(region)}`,
    description: `What separates a ${roleLabel(a)} from a ${roleLabel(
      b,
    )} in ${regionLabel(region)}, by what employers ask for.`,
  };
}

export default async function ComparePage({ params }: { params: Promise<Params> }) {
  const { region, a, b } = await params;
  if (a === b) notFound();

  const [cohortA, cohortB] = await Promise.all([getCohort(a, region), getCohort(b, region)]);
  if (!cohortA || !cohortB) notFound();

  const [skillsA, skillsB] = await Promise.all([getSkills(a, region), getSkills(b, region)]);

  const byName = new Map<string, { pctA: number; pctB: number; kind: string }>();
  for (const skill of skillsA) {
    byName.set(skill.skill, { pctA: skill.pct, pctB: 0, kind: skill.kind });
  }
  for (const skill of skillsB) {
    const entry = byName.get(skill.skill);
    if (entry) entry.pctB = skill.pct;
    else byName.set(skill.skill, { pctA: 0, pctB: skill.pct, kind: skill.kind });
  }

  const all = [...byName.entries()].map(([skill, v]) => ({ skill, ...v }));

  const shared = all
    .filter((s) => Math.min(s.pctA, s.pctB) >= SHARED_FLOOR)
    .sort((x, y) => Math.min(y.pctA, y.pctB) - Math.min(x.pctA, x.pctB));

  const differences = all
    .filter((s) => Math.max(s.pctA, s.pctB) >= 0.1)
    .sort((x, y) => Math.abs(y.pctA - y.pctB) - Math.abs(x.pctA - x.pctB))
    .slice(0, SHOWN);

  const thin = cohortA.lowConfidence || cohortB.lowConfidence;

  return (
    <>
      <nav className={`small ${styles.crumb}`} aria-label="Breadcrumb">
        <Link href={`/role/${a}/${region}`}>{roleLabel(a)}</Link> and{" "}
        <Link href={`/role/${b}/${region}`}>{roleLabel(b)}</Link> in {regionLabel(region)}
      </nav>

      <h1 className={styles.title}>
        {roleLabel(a)} or {roleLabel(b)}?
      </h1>
      <p className="lede">
        What separates the two in {regionLabel(region)}, read from {cohortA.nPostings} and{" "}
        {cohortB.nPostings} postings.
      </p>

      {thin && (
        <p className={`small ${styles.warning}`}>
          One of these cohorts is under 25 postings, so the gaps below move easily. Treat
          the direction as the finding and the size as a guess.
        </p>
      )}

      {shared.length > 0 && (
        <p className={styles.shared}>
          Both jobs want{" "}
          {shared.slice(0, 6).map((s, i) => (
            <span key={s.skill}>
              {i > 0 && (i === Math.min(shared.length, 6) - 1 ? " and " : ", ")}
              <Link href={`/skill/${skillSlug(s.skill)}`}>{s.skill}</Link>
            </span>
          ))}
          .
        </p>
      )}

      <h2 className={styles.sectionTitle}>Where they part</h2>
      <p className="small quiet">
        Ordered by the size of the gap. Each bar runs from the middle: left for{" "}
        {roleLabel(a)}, right for {roleLabel(b)}.
      </p>

      <div className={styles.legend} aria-hidden="true">
        <span className={styles.keyA} /> {roleLabel(a)}
        <span className={styles.keyB} /> {roleLabel(b)}
      </div>

      <div className={styles.scroller}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col" className={styles.numHead}>
                {roleLabel(a)}
              </th>
              <th scope="col" className={styles.barHead}>
                <span className="sr-only">Difference</span>
              </th>
              <th scope="col" className={styles.skillHead}>
                Skill
              </th>
              <th scope="col" className={styles.barHead}>
                <span className="sr-only">Difference</span>
              </th>
              <th scope="col" className={styles.numHead}>
                {roleLabel(b)}
              </th>
            </tr>
          </thead>
          <tbody>
            {differences.map((row) => (
              <tr key={row.skill}>
                <td className={styles.numA}>{row.pctA === 0 ? "—" : percent(row.pctA)}</td>
                <td className={styles.barCellA}>
                  {/* No bar at all for zero: a minimum-width stub reads as a small value. */}
                  {row.pctA > 0 && (
                    <span
                      className={styles.barA}
                      style={{ width: `${(row.pctA * 100).toFixed(1)}%` }}
                      aria-hidden="true"
                    />
                  )}
                </td>
                <th scope="row" className={styles.skill}>
                  <Link href={`/skill/${skillSlug(row.skill)}`}>{row.skill}</Link>
                </th>
                <td className={styles.barCellB}>
                  {row.pctB > 0 && (
                    <span
                      className={styles.barB}
                      style={{ width: `${(row.pctB * 100).toFixed(1)}%` }}
                      aria-hidden="true"
                    />
                  )}
                </td>
                <td className={styles.numB}>{row.pctB === 0 ? "—" : percent(row.pctB)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className={`small quiet ${styles.tail}`}>
        Both columns are shares of their own cohort, so they do not add up to anything. A
        dash means no posting for that role named the skill at all.
      </p>
    </>
  );
}
