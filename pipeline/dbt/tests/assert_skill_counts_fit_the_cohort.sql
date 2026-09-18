-- More postings naming a skill than exist in the cohort would mean the join fanned out,
-- which is the most likely way these numbers could silently inflate.

select role, region, skill, n_with_skill, n_total
from {{ ref('mart_skill_demand') }}
where n_with_skill > n_total or n_with_skill <= 0
