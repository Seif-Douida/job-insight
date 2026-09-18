-- The summary is the denominator table; a duplicated cohort would double-count it.

select role, region, count(*)
from {{ ref('mart_role_region_summary') }}
group by role, region
having count(*) > 1
