-- A percentage outside 0..1 means the numerator and denominator disagree about what they
-- are counting. Returns the offending rows; the test passes when there are none.

select role, region, skill, pct, pct_required
from {{ ref('mart_skill_demand') }}
where pct <= 0 or pct > 1
   or (pct_required is not null and (pct_required < 0 or pct_required > 1))
