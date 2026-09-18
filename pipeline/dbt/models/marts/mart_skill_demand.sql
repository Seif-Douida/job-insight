-- How often each skill is asked for, per role and region.
--
-- `pct` is the share of postings in the cohort that named the skill - not the share of
-- mentions - so it answers "how many employers want this" directly. `pct_required` is the
-- share of those mentions marked required rather than nice-to-have, and is null when the
-- postings were not explicit.

with cohort as (
    select role, region, n_postings, low_confidence
    from {{ ref('mart_role_region_summary') }}
),

mentions as (
    select distinct
        p.role,
        p.region,
        m.canonical_skill,
        m.kind,
        p.posting_id,
        m.requirement
    from {{ ref('int_postings_enriched') }} p
    join {{ ref('int_skill_mentions') }} m using (posting_id)
    where p.is_recent and m.is_mapped
)

select
    m.role,
    m.region,
    m.canonical_skill                                        as skill,
    min(m.kind)                                              as kind,
    count(distinct m.posting_id)                             as n_with_skill,
    c.n_postings                                             as n_total,
    count(distinct m.posting_id)::numeric / c.n_postings     as pct,
    nullif(count(*) filter (where m.requirement <> 'unclear'), 0) is not null as states_requirement,
    case
        when count(*) filter (where m.requirement <> 'unclear') > 0
        then count(*) filter (where m.requirement = 'required')::numeric
             / count(*) filter (where m.requirement <> 'unclear')
    end                                                      as pct_required,
    c.low_confidence
from mentions m
join cohort c on c.role = m.role and c.region = m.region
group by m.role, m.region, m.canonical_skill, c.n_postings, c.low_confidence
