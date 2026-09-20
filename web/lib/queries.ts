import { cacheLife } from "next/cache";

import { query } from "./db";

/**
 * Every read the dashboard makes.
 *
 * The marts are rebuilt once a day by the `transform` DAG, so each of these is cached for
 * hours rather than queried per request. That keeps the pages fast and, just as usefully,
 * keeps a free-tier Neon compute asleep instead of waking it for every visitor.
 *
 * Counts and shares are cast in SQL. node-postgres returns `numeric` and `bigint` as
 * strings to protect precision it cannot know is unneeded, and a percentage arriving as
 * "0.703" is the kind of thing that silently formats as NaN three files later.
 */

const SCHEMA = "analytics";

export type Cohort = {
  role: string;
  region: string;
  nPostings: number;
  nCompanies: number;
  lowConfidence: boolean;
  remoteShare: number;
  sponsorshipShare: number;
  nStatingSponsorship: number;
  medianYears: number | null;
  earliest: string;
  latest: string;
};

export type Skill = {
  skill: string;
  kind: string;
  nWithSkill: number;
  nTotal: number;
  pct: number;
  pctRequired: number | null;
  statesRequirement: boolean;
};

export type SalaryBand = {
  currency: string;
  nPostings: number;
  lowConfidence: boolean;
  p25: number;
  median: number;
  p75: number;
};

export type Corpus = {
  nPostings: number;
  nCompanies: number;
  latest: string;
};

const COHORT_COLUMNS = `
  role,
  region,
  n_postings::int              as "nPostings",
  n_companies::int             as "nCompanies",
  low_confidence               as "lowConfidence",
  remote_share::float8         as "remoteShare",
  sponsorship_share::float8    as "sponsorshipShare",
  n_stating_sponsorship::int   as "nStatingSponsorship",
  median_years_experience::float8 as "medianYears",
  earliest_posting::text       as earliest,
  latest_posting::text         as latest
`;

/** Every role and region that has postings behind it, largest sample first. */
export async function listCohorts(): Promise<Cohort[]> {
  "use cache";
  cacheLife("hours");
  return query<Cohort>(
    `select ${COHORT_COLUMNS} from ${SCHEMA}.mart_role_region_summary
     order by n_postings desc`,
  );
}

/** One role and region, or null when nothing was collected for it. */
export async function getCohort(role: string, region: string): Promise<Cohort | null> {
  "use cache";
  cacheLife("hours");
  const rows = await query<Cohort>(
    `select ${COHORT_COLUMNS} from ${SCHEMA}.mart_role_region_summary
     where role = $1 and region = $2`,
    [role, region],
  );
  return rows[0] ?? null;
}

/** Every skill named in a cohort, most asked for first. */
export async function getSkills(role: string, region: string): Promise<Skill[]> {
  "use cache";
  cacheLife("hours");
  return query<Skill>(
    `select
       skill,
       kind,
       n_with_skill::int    as "nWithSkill",
       n_total::int         as "nTotal",
       pct::float8          as pct,
       pct_required::float8 as "pctRequired",
       states_requirement   as "statesRequirement"
     from ${SCHEMA}.mart_skill_demand
     where role = $1 and region = $2
     order by pct desc, skill`,
    [role, region],
  );
}

/** Stated annual pay for a cohort, one row per currency. */
export async function getSalary(role: string, region: string): Promise<SalaryBand[]> {
  "use cache";
  cacheLife("hours");
  return query<SalaryBand>(
    `select
       currency,
       n_postings::int as "nPostings",
       low_confidence  as "lowConfidence",
       p25::float8     as p25,
       median::float8  as median,
       p75::float8     as p75
     from ${SCHEMA}.mart_salary
     where role = $1 and region = $2
     order by n_postings desc`,
    [role, region],
  );
}

export type RegionSkill = {
  skill: string;
  kind: string;
  group: string;
  pct: number;
  nWithSkill: number;
};

/** Every skill named for one role, tagged with the region that named it. */
export async function getRoleSkillsByRegion(role: string): Promise<RegionSkill[]> {
  "use cache";
  cacheLife("hours");
  return query<RegionSkill>(
    `select
       skill,
       kind,
       region            as "group",
       pct::float8       as pct,
       n_with_skill::int as "nWithSkill"
     from ${SCHEMA}.mart_skill_demand
     where role = $1`,
    [role],
  );
}

export type SeniorityLevel = {
  seniority: string;
  nPostings: number;
  lowConfidence: boolean;
};

/** The levels a role is hired at, with the sample behind each. Regions are pooled. */
export async function getSeniorityLevels(role: string): Promise<SeniorityLevel[]> {
  "use cache";
  cacheLife("hours");
  return query<SeniorityLevel>(
    `select distinct
       seniority,
       n_total::int   as "nPostings",
       low_confidence as "lowConfidence"
     from ${SCHEMA}.mart_skill_by_seniority
     where role = $1`,
    [role],
  );
}

/**
 * Every skill named for one role, tagged with the level that named it.
 *
 * `mart_skill_by_seniority` carries no `kind`: splitting by level already halves the
 * cohorts, and the question it answers is what changes with experience, not what type of
 * thing each skill is.
 */
export async function getSenioritySkills(role: string): Promise<RegionSkill[]> {
  "use cache";
  cacheLife("hours");
  return query<RegionSkill>(
    `select
       skill,
       ''                as kind,
       seniority         as "group",
       pct::float8       as pct,
       n_with_skill::int as "nWithSkill"
     from ${SCHEMA}.mart_skill_by_seniority
     where role = $1`,
    [role],
  );
}

export type SkillPresence = {
  role: string;
  region: string;
  kind: string;
  nWithSkill: number;
  nTotal: number;
  pct: number;
  lowConfidence: boolean;
};

/** Where one skill is asked for, across every role and region that named it. */
export async function getSkillPresence(skill: string): Promise<SkillPresence[]> {
  "use cache";
  cacheLife("hours");
  return query<SkillPresence>(
    `select
       role,
       region,
       kind,
       n_with_skill::int as "nWithSkill",
       n_total::int      as "nTotal",
       pct::float8       as pct,
       low_confidence    as "lowConfidence"
     from ${SCHEMA}.mart_skill_demand
     where skill = $1`,
    [skill],
  );
}

export type SkillSummary = {
  skill: string;
  kind: string;
  mentions: number;
  cohorts: number;
};

/**
 * Every skill in the marts, most named first.
 *
 * Cohorts are disjoint — a posting belongs to exactly one role and region — so summing
 * `n_with_skill` across them counts each posting once and gives a real total.
 */
export async function listSkills(): Promise<SkillSummary[]> {
  "use cache";
  cacheLife("hours");
  return query<SkillSummary>(
    `select
       skill,
       min(kind)              as kind,
       sum(n_with_skill)::int as mentions,
       count(*)::int          as cohorts
     from ${SCHEMA}.mart_skill_demand
     group by skill
     order by sum(n_with_skill) desc, skill`,
  );
}

/** The corpus behind the whole site, for the line that says how much evidence there is. */
export async function getCorpus(): Promise<Corpus> {
  "use cache";
  cacheLife("hours");
  const rows = await query<Corpus>(
    `select
       count(*)::int                  as "nPostings",
       count(distinct company)::int   as "nCompanies",
       max(posted_at)::date::text     as latest
     from ${SCHEMA}.int_postings_enriched
     where is_recent`,
  );
  return rows[0];
}
