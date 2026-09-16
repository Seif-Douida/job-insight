# Methodology

How the numbers on this site are produced, and what they can and cannot tell you.
This page grows with the project; it is written to be read by someone deciding whether
to trust a percentage.

## Where postings come from

| Source | Role in the mix | Text available |
|--------|-----------------|----------------|
| Public ATS boards (Greenhouse, Lever, Ashby) | Primary source for skill extraction | Full description |
| Adzuna | Breadth across the US/UK/EU, plus salary data | Excerpt only |
| JSearch (Google for Jobs) | Fills Gulf coverage, where no free official API exists | Full description |

Postings are collected by company (for ATS boards) or by role keyword and country
(for Adzuna and JSearch), then deduplicated across sources: the same job advertised in
two places is counted once, keeping the record with the richest text.

## How skills are counted

Each posting's text is sent to an LLM (Gemma 4) that returns structured data: skills and
tools, whether each is required or merely preferred, seniority, years of experience,
work mode, and visa sponsorship. Extracted skill names are then mapped onto a canonical
list, so "Postgres", "PostgreSQL" and "psql" count as one skill rather than three.

A percentage always means: *of the postings in this role and region, this share mentioned
this skill.* The denominator is shown next to every figure.

## Limits worth knowing

- **Full text vs. excerpts.** Adzuna returns only an excerpt. Context-dependent figures
  (required vs. nice-to-have, seniority, sponsorship) are computed only over full-text
  postings and never mixed with excerpt-based counts.
- **The company list shapes coverage.** ATS boards are read per company, so the sample
  leans toward companies that publish on modern ATS platforms — in practice, tech and
  tech-adjacent employers. Traditional enterprises are under-represented.
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
