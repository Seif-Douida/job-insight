-- One row per extracted posting with everything a mart groups by.
--
-- `is_recent` carries the time window rather than filtering here: board postings can be
-- years old (the oldest is from 2019), so published counts use recent ones, while the
-- full history stays available for trends.

select
    p.posting_id,
    p.source,
    p.company,
    p.country,
    p.region,
    p.posted_at,
    p.salary_min,
    p.salary_max,
    p.salary_currency,
    p.salary_is_predicted,
    e.role,
    e.seniority,
    e.years_experience_min,
    e.work_mode,
    e.visa_sponsorship,
    p.posted_at >= current_date - interval '{{ var("recent_days") }} days' as is_recent
from {{ ref('stg_postings') }} p
join {{ ref('stg_extractions') }} e using (posting_id)
where e.role <> 'other'
