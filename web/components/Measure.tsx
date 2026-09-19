import styles from "./Measure.module.css";

/**
 * One skill's demand, drawn as a measured length.
 *
 * The bar carries two facts in one colour. Its length is the share of postings that named
 * the skill. Within it, the solid part is the share of those mentions written as a
 * requirement rather than a preference — so a long hatched bar means "often asked for,
 * rarely insisted on", which is a different message from a long solid one.
 *
 * It is decoration for a screen reader: the same numbers are in the cells beside it.
 */
export function Measure({ pct, pctRequired }: { pct: number; pctRequired: number | null }) {
  return (
    <div className={styles.track} aria-hidden="true">
      <div className={styles.fill} style={{ width: `${(pct * 100).toFixed(1)}%` }}>
        {pctRequired !== null && (
          <div
            className={styles.required}
            style={{ width: `${(pctRequired * 100).toFixed(1)}%` }}
          />
        )}
      </div>
    </div>
  );
}
