-- Every published figure has to carry its sample size, and the low-confidence flag has to
-- agree with it. A row that breaks this would be a number with no context.

select role, region, n_postings, low_confidence
from {{ ref('mart_role_region_summary') }}
where n_postings is null
   or n_postings <= 0
   or low_confidence <> (n_postings < {{ var('min_cohort') }})
