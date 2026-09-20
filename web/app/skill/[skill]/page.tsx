import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PivotTable, type PivotColumn } from "@/components/PivotTable";
import { percent } from "@/lib/format";
import { pivotBySkill } from "@/lib/pivot";
import { getSkillPresence, listCohorts, listSkills } from "@/lib/queries";
import { skillSlug } from "@/lib/slug";
import { REGION_ORDER, ROLE_ORDER, regionLabel, roleLabel } from "@/lib/taxonomy";

import styles from "./page.module.css";

/** Prerender the skills people actually look up; the long tail renders on request. */
const PRERENDER = 60;

type Params = { skill: string };

export async function generateStaticParams(): Promise<Params[]> {
  const skills = await listSkills();
  return skills.slice(0, PRERENDER).map((s) => ({ skill: skillSlug(s.skill) }));
}

/** Slugs are one-way, so the name is recovered by matching against the marts. */
async function resolve(slug: string) {
  const skills = await listSkills();
  return skills.find((s) => skillSlug(s.skill) === slug) ?? null;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { skill } = await params;
  const found = await resolve(skill);
  if (!found) return { title: "Unknown skill" };
  return {
    title: found.skill,
    description: `Which roles and regions ask for ${found.skill}, and how often.`,
  };
}

export default async function SkillPage({ params }: { params: Promise<Params> }) {
  const { skill: slug } = await params;
  const found = await resolve(slug);
  if (!found) notFound();

  const [presence, cohorts] = await Promise.all([
    getSkillPresence(found.skill),
    listCohorts(),
  ]);

  const analysed = cohorts.reduce((sum, c) => sum + c.nPostings, 0);
  const share = analysed === 0 ? 0 : found.mentions / analysed;

  // One table per region, roles down the side: the question is which job wants this.
  const columns: PivotColumn[] = REGION_ORDER.flatMap((region) => {
    const inRegion = cohorts.filter((c) => c.region === region);
    if (inRegion.length === 0) return [];
    const nPostings = inRegion.reduce((sum, c) => sum + c.nPostings, 0);
    return [
      {
        key: region,
        label: regionLabel(region),
        nPostings,
        thin: inRegion.every((c) => c.lowConfidence),
      },
    ];
  });

  // Rows are roles here rather than skills; the pivot groups by whatever it is given.
  const rows = pivotBySkill(
    presence.map((p) => ({
      skill: p.role,
      kind: "",
      group: p.region,
      pct: p.pct,
      nWithSkill: p.nWithSkill,
      thin: p.lowConfidence,
    })),
    new Set(columns.filter((c) => !c.thin).map((c) => c.key)),
  ).sort((a, b) => ROLE_ORDER.indexOf(a.skill) - ROLE_ORDER.indexOf(b.skill));

  const strongest = [...presence]
    .filter((p) => !p.lowConfidence)
    .sort((a, b) => b.pct - a.pct)
    .slice(0, 3);

  return (
    <>
      <h1 className={styles.title}>{found.skill}</h1>
      <p className="lede">
        Named in {found.mentions.toLocaleString("en")} of the{" "}
        {analysed.toLocaleString("en")} postings read, {percent(share)} of the whole
        corpus, across {found.cohorts} of 28 role-and-region cohorts.
      </p>

      {strongest.length > 0 && (
        <p className={styles.strongest}>
          Asked for most by{" "}
          {strongest.map((p, i) => (
            <span key={`${p.role}/${p.region}`}>
              {i > 0 && (i === strongest.length - 1 ? " and " : ", ")}
              <Link href={`/role/${p.role}/${p.region}`}>
                {roleLabel(p.role)} in {regionLabel(p.region)}
              </Link>{" "}
              <span className="quiet">({percent(p.pct)})</span>
            </span>
          ))}
          .
        </p>
      )}

      <h2 className={styles.sectionTitle}>Who asks for it</h2>
      <p className="small quiet">
        The share of each role&apos;s postings naming {found.skill}. A dash means no posting
        in that cohort named it. Greyed figures come from cohorts under 25 postings, where a
        single employer moves the number several points — most of the Gulf column, at
        present.
      </p>
      <PivotTable
        rows={rows}
        columns={columns}
        caption={`Share of postings naming ${found.skill}, by role and region`}
        rowHead="Role"
        rowLabel={roleLabel}
        rowHref={(role) => `/role/${role}`}
      />

      <p className={`small quiet ${styles.tail}`}>
        There is no trend line here yet. Collection started recently and the archive holds
        no history, so a month-on-month chart would be drawn from one month. It appears once
        enough weeks have accumulated to mean something.
      </p>

      <p className={`small quiet ${styles.tail}`}>
        <Link href="/">Back to every role and region</Link>
      </p>
    </>
  );
}
