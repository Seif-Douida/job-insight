-- One row per role and region: the denominator behind every other figure.
--
-- Read this first. `n_postings` is what every percentage in mart_skill_demand divides by,
-- and `low_confidence` marks the cohorts too small to publish without a warning.

select
    role,
    region,
    count(*)                                                        as n_postings,
    count(*) < {{ var('min_cohort') }}                              as low_confidence,
    count(distinct company)                                         as n_companies,
    min(posted_at)::date                                            as earliest_posting,
    max(posted_at)::date                                            as latest_posting,
    avg((work_mode = 'remote')::int)                                as remote_share,
    avg((visa_sponsorship = 'offered')::int)                        as sponsorship_share,
    count(*) filter (where visa_sponsorship <> 'not_mentioned')     as n_stating_sponsorship,
    percentile_cont(0.5) within group (order by years_experience_min)
        filter (where years_experience_min is not null)             as median_years_experience,
    count(*) filter (where years_experience_min is not null)        as n_stating_years
from {{ ref('int_postings_enriched') }}
where is_recent
group by role, region
