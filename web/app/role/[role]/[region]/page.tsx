import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Measure } from "@/components/Measure";
import { formatRange, money, percent } from "@/lib/format";
import { getCohort, getSalary, getSkills, listCohorts } from "@/lib/queries";
import { skillSlug } from "@/lib/slug";
import {
  REGION_ORDER,
  REGION_SHORT,
  ROLE_ORDER,
  regionLabel,
  roleLabel,
} from "@/lib/taxonomy";

import styles from "./page.module.css";

/** Skills shown before the tail turns into one-off mentions. */
const SHOWN = 30;

type Params = { role: string; region: string };

export async function generateStaticParams(): Promise<Params[]> {
  const cohorts = await listCohorts();
  return cohorts.map(({ role, region }) => ({ role, region }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { role, region } = await params;
  return {
    title: `${roleLabel(role)} in ${regionLabel(region)}`,
    description: `The skills companies name in ${roleLabel(
      role,
    )} postings in ${regionLabel(region)}.`,
  };
}

export default async function CohortPage({ params }: { params: Promise<Params> }) {
  const { role, region } = await params;

  const cohort = await getCohort(role, region);
  if (!cohort) notFound();

  const [skills, salary, cohorts] = await Promise.all([
    getSkills(role, region),
    getSalary(role, region),
    listCohorts(),
  ]);

  const shown = skills.slice(0, SHOWN);
  const siblings = new Map(
    cohorts.filter((c) => c.role === role).map((c) => [c.region, c]),
  );

  // Other roles hiring in this region, in the taxonomy's order rather than by size.
  const neighbours = cohorts
    .filter((c) => c.region === region && c.role !== role)
    .map((c) => c.role)
    .sort((x, y) => ROLE_ORDER.indexOf(x) - ROLE_ORDER.indexOf(y));

  return (
    <>
      <nav className={styles.regions} aria-label="Same role in other regions">
        {REGION_ORDER.map((other) => {
          const sibling = siblings.get(other);
          if (other === region) {
            return (
              <span key={other} className={styles.regionCurrent} aria-current="page">
                {REGION_SHORT[other]}
              </span>
            );
          }
          if (!sibling) {
            return (
              <span key={other} className={`${styles.regionOff} quiet`}>
                {REGION_SHORT[other]}
              </span>
            );
          }
          return (
            <Link key={other} href={`/role/${role}/${other}`} className={styles.region}>
              {REGION_SHORT[other]}{" "}
              <span className="quiet">{sibling.nPostings}</span>
            </Link>
          );
        })}
      </nav>

      <h1 className={styles.title}>
        <Link href={`/role/${role}`} className={styles.titleLink}>
          {roleLabel(role)}
        </Link>
        <span className={styles.titleRegion}>{regionLabel(region)}</span>
      </h1>

      <p className="lede">
        {cohort.nPostings} openings at {cohort.nCompanies} companies, posted between{" "}
        {formatRange(cohort.earliest, cohort.latest)}.
      </p>

      {cohort.lowConfidence && (
        <p className={`small ${styles.warning}`}>
          A thin sample. Under 25 postings, a single unusual employer moves any percentage
          on this page by several points. Read the counts, not the percentages.
        </p>
      )}

      <dl className={styles.facts}>
        <div>
          <dt className="small quiet">Experience asked for</dt>
          <dd>
            {cohort.medianYears === null ? (
              <span className="quiet">not stated</span>
            ) : (
              <>
                {cohort.medianYears}
                <span className={styles.factUnit}>
                  years, median of {cohort.nPostings} postings
                </span>
              </>
            )}
          </dd>
        </div>
        <div>
          <dt className="small quiet">Fully remote</dt>
          <dd>
            {percent(cohort.remoteShare)}
            <span className={styles.factUnit}>of postings</span>
          </dd>
        </div>
        <div>
          <dt className="small quiet">Offer visa sponsorship</dt>
          <dd>
            {percent(cohort.sponsorshipShare)}
            <span className={styles.factUnit}>
              {cohort.nStatingSponsorship} postings mention visas at all
            </span>
          </dd>
        </div>
      </dl>

      <h2 className={styles.sectionTitle}>What they ask for</h2>
      <p className="small quiet">
        Bar length is the share of the {cohort.nPostings} postings naming a skill. The solid
        part is the share of those mentions written as a requirement rather than a
        preference.
      </p>

      <table className={styles.skills}>
        <thead>
          <tr>
            <th scope="col">Skill</th>
            <th scope="col" className={styles.measureHead}>
              Share of postings
            </th>
            <th scope="col" className={styles.pctHead}>
              %
            </th>
          </tr>
        </thead>
        <tbody>
          {shown.map((skill) => (
            <tr key={skill.skill}>
              <th scope="row" className={styles.skillName}>
                <Link href={`/skill/${skillSlug(skill.skill)}`}>{skill.skill}</Link>
                <span className={`small quiet ${styles.skillMeta}`}>
                  {skill.kind}
                  {skill.pctRequired !== null &&
                    `, required in ${percent(skill.pctRequired)} of mentions`}
                </span>
              </th>
              <td className={styles.measureCell}>
                <Measure pct={skill.pct} pctRequired={skill.pctRequired} />
              </td>
              <td className={styles.pct}>
                {percent(skill.pct)}
                <span className={`small quiet ${styles.pctCount}`}>
                  {skill.nWithSkill} of {skill.nTotal}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {skills.length > SHOWN && (
        <p className={`small quiet ${styles.tail}`}>
          {skills.length - SHOWN} more skills were named in this cohort, each by{" "}
          {shown[SHOWN - 1].nWithSkill} postings or fewer.
        </p>
      )}

      <h2 className={styles.sectionTitle}>Pay</h2>
      {salary.length === 0 ? (
        <p className="small quiet">
          Too few postings here state pay to publish a figure. Most employers in this
          cohort leave it out.
        </p>
      ) : (
        <>
          <div className={styles.scroller}>
            <table className={styles.salary}>
              <thead>
                <tr>
                  <th scope="col">Currency</th>
                  <th scope="col">Lower quarter</th>
                  <th scope="col">Median</th>
                  <th scope="col">Upper quarter</th>
                  <th scope="col">Postings</th>
                </tr>
              </thead>
              <tbody>
                {salary.map((band) => (
                  <tr
                    key={band.currency}
                    className={band.lowConfidence ? styles.thinRow : ""}
                  >
                    <th scope="row">{band.currency}</th>
                    <td>{money(band.p25, band.currency)}</td>
                    <td>{money(band.median, band.currency)}</td>
                    <td>{money(band.p75, band.currency)}</td>
                    <td>{band.nPostings}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className={`small quiet ${styles.tail}`}>
            Stated annual pay only, never an estimate. The role here is matched from the job
            title rather than read from the description, because most postings that state
            pay are ones where only an excerpt was available.
          </p>
        </>
      )}

      {neighbours.length > 0 && (
        <>
          <h2 className={styles.sectionTitle}>How it differs from a neighbouring job</h2>
          <p className="small quiet">
            The titles overlap more than the postings do. These put two of them side by
            side in {regionLabel(region)}.
          </p>
          <ul className={styles.compareList}>
            {neighbours.map((other) => (
              <li key={other}>
                <Link href={`/compare/${region}/${role}/${other}`}>
                  {roleLabel(role)} or {roleLabel(other)}
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
