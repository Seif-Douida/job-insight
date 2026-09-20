import Link from "next/link";

import { percent } from "@/lib/format";
import type { PivotRow } from "@/lib/pivot";
import { skillSlug } from "@/lib/slug";

import styles from "./PivotTable.module.css";

export type PivotColumn = {
  key: string;
  label: string;
  nPostings: number;
  thin: boolean;
};

/**
 * One skill per row, one group per column, each cell a share with a rule under it.
 *
 * The rule is the same measure used everywhere else on the site, shrunk to fit a cell: it
 * turns a grid of numbers into something you can read down a column without comparing
 * digits. Thin columns keep their figures but are set in the quiet colour, so a reader can
 * see them without being invited to trust them.
 */
export function PivotTable({
  rows,
  columns,
  caption,
  rowHead = "Skill",
  rowLabel = (key) => key,
  rowHref = (key) => `/skill/${skillSlug(key)}`,
}: {
  rows: PivotRow[];
  columns: PivotColumn[];
  caption: string;
  /** What the first column contains. Rows are skills unless a page says otherwise. */
  rowHead?: string;
  rowLabel?: (key: string) => string;
  rowHref?: (key: string) => string;
}) {
  return (
    <div className={styles.scroller}>
      <table className={styles.table}>
        <caption className={`small quiet ${styles.caption}`}>{caption}</caption>
        <thead>
          <tr>
            <th scope="col" className={styles.skillHead}>
              {rowHead}
            </th>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={column.thin ? styles.headThin : styles.head}
              >
                {column.label}
                <span className={styles.headCount}>
                  {column.nPostings}
                  {column.thin && " thin"}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.skill}>
              <th scope="row" className={styles.skill}>
                <Link href={rowHref(row.skill)}>{rowLabel(row.skill)}</Link>
              </th>
              {columns.map((column) => {
                const cell = row.cells[column.key];
                // A cell is quiet when its own sample is thin, even in a solid column:
                // on a skill page the columns pool regions while each cell is one cohort.
                const thin = column.thin || cell?.thin;
                return (
                  <td key={column.key} className={thin ? styles.cellThin : styles.cell}>
                    {cell ? (
                      <>
                        {percent(cell.pct)}
                        <span
                          className={styles.rule}
                          style={{ width: `${(cell.pct * 100).toFixed(1)}%` }}
                          aria-hidden="true"
                        />
                      </>
                    ) : (
                      <span className="quiet" title="not named in this group">
                        &mdash;
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
