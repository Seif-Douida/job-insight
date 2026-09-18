-- What changes with seniority: the share of postings naming each skill, per role and level.
--
-- Regions are pooled here. Splitting by region as well would leave cohorts of five, and
-- the question this answers - what is expected of a senior that is not expected of a
-- junior - is not one where region is the interesting axis.
--
-- Postings that state no level are excluded rather than bucketed as junior.

with cohort as (
    select role, seniority, count(*) as n_postings
    from {{ ref('int_postings_enriched') }}
    where is_recent and seniority <> 'unclear'
    group by role, seniority
),

mentions as (
    select distinct p.role, p.seniority, m.canonical_skill, p.posting_id
    from {{ ref('int_postings_enriched') }} p
    join {{ ref('int_skill_mentions') }} m using (posting_id)
    where p.is_recent and p.seniority <> 'unclear' and m.is_mapped
)

select
    m.role,
    m.seniority,
    m.canonical_skill                                        as skill,
    count(distinct m.posting_id)                             as n_with_skill,
    c.n_postings                                             as n_total,
    count(distinct m.posting_id)::numeric / c.n_postings     as pct,
    c.n_postings < {{ var('min_cohort') }}                   as low_confidence
from mentions m
join cohort c on c.role = m.role and c.seniority = m.seniority
group by m.role, m.seniority, m.canonical_skill, c.n_postings
