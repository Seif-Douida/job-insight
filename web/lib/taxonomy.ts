/**
 * Display names for the curated roles and regions.
 *
 * These mirror the `label` fields in `pipeline/taxonomy/roles.yaml` and `regions.yaml`,
 * which remain the source of truth: the pipeline decides what a role *is*, this file only
 * decides how to write it down. `pipeline/tests/test_taxonomy_labels.py` fails if the two
 * drift apart.
 *
 * Which cohorts exist is never hard-coded — that comes from the marts.
 */

export const ROLE_LABELS: Record<string, string> = {
  "ai-engineer": "AI Engineer",
  "analytics-engineer": "Analytics Engineer",
  "data-analyst": "Data Analyst",
  "data-engineer": "Data Engineer",
  "data-scientist": "Data Scientist",
  "ml-engineer": "ML Engineer",
  "mlops-engineer": "MLOps Engineer",
};

export const REGION_LABELS: Record<string, string> = {
  us: "United States",
  uk: "United Kingdom",
  eu: "European Union",
  gulf: "Gulf",
};

/** Column headings in the coverage matrix, where the full names do not fit. */
export const REGION_SHORT: Record<string, string> = {
  us: "US",
  uk: "UK",
  eu: "EU",
  gulf: "Gulf",
};

/** The form that reads correctly mid-sentence: "postings in the United States". */
export const REGION_IN: Record<string, string> = {
  us: "the United States",
  uk: "the United Kingdom",
  eu: "the European Union",
  gulf: "the Gulf",
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

export function regionLabel(region: string): string {
  return REGION_LABELS[region] ?? region;
}

/** Roles in the order the matrix lists them: closest to the data, then closest to the model. */
export const ROLE_ORDER = [
  "data-analyst",
  "analytics-engineer",
  "data-engineer",
  "data-scientist",
  "ml-engineer",
  "mlops-engineer",
  "ai-engineer",
];

export const REGION_ORDER = ["us", "uk", "eu", "gulf"];
