import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PivotTable, type PivotColumn } from "@/components/PivotTable";
import { pivotBySkill, rankByDisagreement } from "@/lib/pivot";
import {
  getRoleSkillsByRegion,
  getSeniorityLevels,
  getSenioritySkills,
  listCohorts,
} from "@/lib/queries";
import { REGION_ORDER, ROLE_ORDER, regionLabel, roleLabel } from "@/lib/taxonomy";

import styles from "./page.module.css";

/** Levels in the order a career runs, not the order the database returns them. */
const SENIORITY_ORDER = ["intern", "junior", "mid", "senior", "lead", "principal"];

const SENIORITY_LABELS: Record<string, string> = {
  intern: "Intern",
  junior: "Junior",
  mid: "Mid",
  senior: "Senior",
  lead: "Lead",
  principal: "Principal",
};

type Params = { role: string };

export function generateStaticParams(): Params[] {
  return ROLE_ORDER.map((role) => ({ role }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { role } = await params;
  return {
    title: roleLabel(role),
    description: `How ${roleLabel(role)} postings differ by region and by level.`,
  };
}

export default async function RolePage({ params }: { params: Promise<Params> }) {
  const { role } = await params;
  if (!ROLE_ORDER.includes(role)) notFound();

  const [cohorts, regionSkills, levels, senioritySkills] = await Promise.all([
    listCohorts(),
    getRoleSkillsByRegion(role),
    getSeniorityLevels(role),
    getSenioritySkills(role),
  ]);

  const mine = cohorts.filter((c) => c.role === role);
  if (mine.length === 0) notFound();

  const totalPostings = mine.reduce((sum, c) => sum + c.nPostings, 0);

  const regionColumns: PivotColumn[] = REGION_ORDER.flatMap((region) => {
    const cohort = mine.find((c) => c.region === region);
    return cohort
      ? [
          {
            key: region,
            label: regionLabel(region),
            nPostings: cohort.nPostings,
            thin: cohort.lowConfidence,
          },
        ]
      : [];
  });

  const reliableRegions = new Set(
    regionColumns.filter((c) => !c.thin).map((c) => c.key),
  );
  const regionRows = rankByDisagreement(pivotBySkill(regionSkills, reliableRegions));

  const levelColumns: PivotColumn[] = SENIORITY_ORDER.flatMap((level) => {
    const found = levels.find((l) => l.seniority === level);
    return found
      ? [
          {
            key: level,
            label: SENIORITY_LABELS[level] ?? level,
            nPostings: found.nPostings,
            thin: found.lowConfidence,
          },
        ]
      : [];
  });

  const reliableLevels = new Set(levelColumns.filter((c) => !c.thin).map((c) => c.key));
  const levelRows = rankByDisagreement(pivotBySkill(senioritySkills, reliableLevels));

  return (
    <>
      <h1 className={styles.title}>{roleLabel(role)}</h1>
      <p className="lede">
        {totalPostings.toLocaleString("en")} openings across {mine.length}{" "}
        {mine.length === 1 ? "region" : "regions"}. Where employers agree, and where they do
        not.
      </p>

      <nav className={styles.cohorts} aria-label="This role by region">
        {regionColumns.map((column) => (
          <Link
            key={column.key}
            href={`/role/${role}/${column.key}`}
            className={column.thin ? styles.cohortThin : styles.cohort}
          >
            {column.label}
            <span className={styles.cohortCount}>{column.nPostings} postings</span>
          </Link>
        ))}
      </nav>

      <h2 className={styles.sectionTitle}>Where the job differs by region</h2>
      {regionRows.length === 0 || reliableRegions.size < 2 ? (
        <p className="small quiet">
          Only {reliableRegions.size} region has enough postings for this role to compare
          against another. The regional pages still show what each one asks for.
        </p>
      ) : (
        <>
          <p className="small quiet">
            Ordered by how far apart the regions are, counting only those with a large
            enough sample to rank on. A dash means nobody in that region named it.
          </p>
          <PivotTable
            rows={regionRows}
            columns={regionColumns}
            caption={`Share of ${roleLabel(role)} postings naming each skill, by region`}
          />
        </>
      )}

      <h2 className={styles.sectionTitle}>What changes with experience</h2>
      {levelRows.length === 0 || levelColumns.length < 2 ? (
        <p className="small quiet">
          Too few postings state a level for this role to show how expectations change.
        </p>
      ) : (
        <>
          <p className="small quiet">
            Regions are pooled here. Splitting by region as well would leave cohorts of
            five, and what a senior is expected to know that a junior is not does not vary
            much by country. Postings that state no level are left out rather than counted
            as junior.
          </p>
          <PivotTable
            rows={levelRows}
            columns={levelColumns}
            caption={`Share of ${roleLabel(role)} postings naming each skill, by level`}
          />
        </>
      )}

      <p className={`small quiet ${styles.tail}`}>
        <Link href="/">Back to every role and region</Link>
      </p>
    </>
  );
}
