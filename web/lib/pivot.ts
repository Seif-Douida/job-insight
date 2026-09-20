export type Cell = {
  pct: number;
  nWithSkill: number;
  /** Set when this particular cell rests on too small a sample, whatever its column does. */
  thin?: boolean;
};

export type PivotRow = {
  skill: string;
  kind: string;
  cells: Record<string, Cell | undefined>;
  /** How far apart the reliable groups are. The ranking question: where do they disagree? */
  spread: number;
  /** The highest share any group gives this skill, reliable or not. */
  peak: number;
};

type Input = {
  skill: string;
  kind: string;
  group: string;
  pct: number;
  nWithSkill: number;
  thin?: boolean;
};

/**
 * One row per skill, with a column per group, ranked by how much the groups disagree.
 *
 * A skill missing from a group is a real zero — nobody in that group named it — so it
 * counts as 0% when measuring disagreement rather than being skipped, which is what makes
 * "everyone here asks for it, nobody there does" rank as the largest difference.
 *
 * Only `reliable` groups decide the order. A cohort of sixteen postings swings by six
 * points when one employer changes their mind, and letting it sort the table would fill
 * the top with noise. Thin groups are still shown; they just do not get a vote.
 */
export function pivotBySkill(rows: Input[], reliable: Set<string>): PivotRow[] {
  const bySkill = new Map<string, PivotRow>();

  for (const row of rows) {
    let entry = bySkill.get(row.skill);
    if (!entry) {
      entry = { skill: row.skill, kind: row.kind, cells: {}, spread: 0, peak: 0 };
      bySkill.set(row.skill, entry);
    }
    entry.cells[row.group] = {
      pct: row.pct,
      nWithSkill: row.nWithSkill,
      thin: row.thin,
    };
    entry.peak = Math.max(entry.peak, row.pct);
  }

  for (const entry of bySkill.values()) {
    const shares = [...reliable].map((group) => entry.cells[group]?.pct ?? 0);
    entry.spread = shares.length > 1 ? Math.max(...shares) - Math.min(...shares) : 0;
  }

  return [...bySkill.values()];
}

/**
 * The skills worth putting in a comparison: common enough somewhere to be a real
 * difference, ordered by how much the groups disagree about them.
 */
export function rankByDisagreement(rows: PivotRow[], minPeak = 0.1, limit = 20): PivotRow[] {
  return rows
    .filter((row) => row.peak >= minPeak)
    .sort((a, b) => b.spread - a.spread || b.peak - a.peak)
    .slice(0, limit);
}
