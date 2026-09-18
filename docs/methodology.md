# Methodology

How the numbers on this site are produced, and what they can and cannot tell you.
This page grows with the project; it is written to be read by someone deciding whether
to trust a percentage.

## Where postings come from

| Source | Role in the mix | Text available |
| ------ | --------------- | -------------- |
| Public ATS boards (Greenhouse, Lever, Ashby) | Primary source for skill extraction | Full description |
| SmartRecruiters | Reaches large non-tech employers the others miss | Full description |
| Adzuna | Breadth across the US/UK/EU, plus salary data | Excerpt only |
| JSearch (Google for Jobs) | Fills Gulf coverage, where no free official API exists | Full or snippet, by publisher |

Postings are collected by company (for ATS boards) or by role keyword and country
(for Adzuna and JSearch).

### What gets stored

A posting is kept only when both hold:

- **Its title is plausibly one of the curated roles.** Either it matches a role pattern
  ("Senior Data Engineer"), or it contains a relevant keyword ("Software Engineer, Data
  Infrastructure") and is left for the classifier to decide. Leadership, recruiting and
  sales titles are excluded outright.
- **Its location resolves to a curated country.** Free-text locations are matched against
  country names, cities and codes; when a posting lists several places, the first one
  named wins. A posting that says only "Remote", or names a place outside the four
  regions, is not stored rather than guessed.

### Full text or excerpt

Each posting is marked `full` or `excerpt`. Adzuna postings are always excerpts (the API
returns 500 characters). For every other source, a description under 1,000 characters is
an excerpt too: aggregators often return a short snippet of a longer posting.

### Duplicates

The same company, title and country is treated as the same job, with company names
compared without case, punctuation or legal suffixes ("Acme Ltd" = "ACME"). Duplicates
are linked rather than deleted, and only the canonical copy is counted. The canonical copy
is the company's own job board posting if one exists, otherwise a full-text copy, otherwise
the first one seen.

Two postings with the same title on one company's own board are counted separately —
companies often hire for several identical openings. Repeats of one job within an
aggregator are collapsed, since aggregators republish the same listing from several sites.

## How skills are counted

Each full-text posting is sent to an LLM (Gemma 4 through the Gemini API), which returns
structured data: skills and tools, whether each is required or merely preferred, the role,
seniority, years of experience, work mode, and visa sponsorship. Extracted skill names are
then mapped onto a canonical list, so "Postgres", "PostgreSQL" and "psql" count as one
skill rather than three.

Excerpt postings are not sent to the model. Their 500 characters are almost always an
"About us" paragraph that names no skills, so they contribute volume, salary and company
coverage, and take their role from the job title alone.

A percentage always means: *of the postings in this role and region, this share mentioned
this skill.* The denominator is shown next to every figure.

### How accurate is the extraction?

Accuracy is measured against a set of postings labelled by hand, by reading each posting
and recording what it states. The current model, Gemma 4 (26B), scores:

| What | Accuracy |
| ---- | -------- |
| Years of experience required | 100% |
| Visa sponsorship | 100% |
| Work mode | 100% |
| Seniority | 95% |
| Role | 84% |
| Skills | 81% precision, 80% recall |

Read this as: when the model lists a skill, it is in the posting about four times out of
five, and it finds about four fifths of the skills a careful reader would. The role
mistakes are all boundary cases — an "Applied AI Engineer" who mostly trains models, a
software engineer on an AI product — where two labels are defensible.

The labelled set is small (19 postings) and was labelled by a language model rather than
by the employers, so treat these figures as a guide, not a guarantee. Re-run them with
`python -m pipeline.eval.run_eval`.

## Limits worth knowing

- **Full text vs. excerpts.** Adzuna returns only an excerpt. Context-dependent figures
  (required vs. nice-to-have, seniority, sponsorship) are computed only over full-text
  postings and never mixed with excerpt-based counts.
- **The company list shapes coverage.** ATS boards are read per company, so the sample
  leans toward companies that publish on modern ATS platforms — in practice, tech and
  tech-adjacent employers. Traditional enterprises are under-represented, which is why
  SmartRecruiters was added: it is where large industrial and consumer employers post.
  The correction is partial, not complete.
- **Not every posting is written in English.** Descriptions are stored and analysed in the
  language the employer used. Skill names are largely language-independent ("Python",
  "Kubernetes"), but a German or Portuguese posting may yield fewer of the descriptive
  skills than an equivalent English one.
- **Gulf coverage is thinner** than US/UK/EU, because no free official API serves the
  region; the figures there rest on smaller samples and are marked accordingly.
- **Small samples are hidden.** Any role-and-region combination with fewer than 25
  postings is marked low-confidence and hidden by default.
- **Postings are not hires.** They show what employers ask for, which is not the same as
  what teams use day to day, nor what they will accept in a candidate.
- **Salary figures reflect only postings that state pay**, which skews toward the US and
  UK where disclosure is more common or legally required.
- **Trends need time.** There is no historical backfill, so trend views only appear once
  enough weeks of collection have accumulated.
