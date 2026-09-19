import Link from "next/link";

import { formatDate } from "@/lib/format";
import { getCorpus, listCohorts } from "@/lib/queries";
import { REGION_ORDER, REGION_SHORT, ROLE_ORDER, roleLabel, regionLabel } from "@/lib/taxonomy";

import styles from "./page.module.css";

export default async function Home() {
  const [cohorts, corpus] = await Promise.all([listCohorts(), getCorpus()]);
  const byKey = new Map(cohorts.map((c) => [`${c.role}/${c.region}`, c]));
  const thin = cohorts.filter((c) => c.lowConfidence).length;

  return (
    <>
      <h1 className={styles.title}>What companies ask for</h1>
      <p className="lede">
        Skill demand in data and AI job postings, counted from{" "}
        {corpus.nPostings.toLocaleString("en")} postings at {corpus.nCompanies} companies.
        Pick a role and a region to see what they name, and how often.
      </p>

      <table className={styles.matrix}>
        <caption className={`small quiet ${styles.caption}`}>
          Postings analysed, by role and region
        </caption>
        <thead>
          <tr>
            <th scope="col" className={styles.roleHead}>
              Role
            </th>
            {REGION_ORDER.map((region) => (
              <th scope="col" key={region} className={styles.cellHead}>
                {REGION_SHORT[region]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROLE_ORDER.map((role) => (
            <tr key={role}>
              <th scope="row" className={styles.roleName}>
                {roleLabel(role)}
              </th>
              {REGION_ORDER.map((region) => {
                const cohort = byKey.get(`${role}/${region}`);
                return (
                  <td key={region} className={styles.cell}>
                    {cohort ? (
                      <Link
                        href={`/role/${role}/${region}`}
                        className={cohort.lowConfidence ? styles.thinLink : styles.link}
                        aria-label={`${roleLabel(role)} in ${regionLabel(region)}, ${
                          cohort.nPostings
                        } postings${cohort.lowConfidence ? ", a thin sample" : ""}`}
                      >
                        {cohort.nPostings}
                      </Link>
                    ) : (
                      <span className="quiet" aria-label="no postings collected">
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

      <p className={`small quiet ${styles.note}`}>
        Greyed numbers are cohorts under 25 postings, where one unusual employer moves a
        percentage by several points. {thin} of {cohorts.length} are thin at the moment;
        they are published with the warning rather than hidden, and they grow as collection
        continues. Percentages come only from postings whose full text was available, and
        count postings from the last 180 days up to {formatDate(corpus.latest)}.
      </p>
    </>
  );
}
