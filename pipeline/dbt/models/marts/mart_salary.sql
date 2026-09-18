-- Stated annual pay per role, region and currency.
--
-- Three deliberate exclusions, each of which would otherwise publish a wrong number:
--
-- 1. **Predicted salaries.** Adzuna estimates pay for postings that do not state it.
--    Republishing an estimate as a market figure would be inventing data.
-- 2. **Figures that are not annual.** The sources give no pay period, and about one in
--    nine stated salaries is an hourly or monthly rate (seen: "10-10" EUR, "18-25" GBP).
--    There is no way to tell a low annual salary from an hourly one except magnitude, so
--    anything below a plausible annual floor is dropped rather than guessed at. Rows with
--    a zero minimum are dropped for the same reason: that is "not stated", not "free".
-- 3. **Minor currencies.** Only USD, EUR and GBP have the volume to be worth publishing,
--    and converting would need exchange rates we do not have. Currency is part of the
--    grain because a median across currencies means nothing.
--
-- Roles here come from `role_hint`, the title matcher, not from the model: most postings
-- that state pay are excerpts that are never extracted. That is a weaker signal than the
-- classifier, and the dashboard says so wherever these figures appear.

with stated as (
    select
        p.role_hint as role,
        p.region,
        p.salary_currency as currency,
        (p.salary_min + coalesce(p.salary_max, p.salary_min)) / 2.0 as salary
    from {{ ref('stg_postings') }} p
    where not p.salary_is_predicted
      and p.salary_currency in ('USD', 'EUR', 'GBP')
      and p.salary_min >= {{ var('min_annual_salary') }}
      and p.salary_min <= {{ var('max_annual_salary') }}
      and coalesce(p.salary_max, p.salary_min) <= {{ var('max_annual_salary') }}
      and p.role_hint is not null
      and p.role_hint <> 'other'
      and p.posted_at >= current_date - interval '{{ var("recent_days") }} days'
)

select
    role,
    region,
    currency,
    count(*)                                                     as n_postings,
    count(*) < {{ var('min_salaries') }}                         as low_confidence,
    round(percentile_cont(0.25) within group (order by salary))  as p25,
    round(percentile_cont(0.50) within group (order by salary))  as median,
    round(percentile_cont(0.75) within group (order by salary))  as p75
from stated
group by role, region, currency
