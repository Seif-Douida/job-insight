-- p25 <= median <= p75 always holds for real percentiles. A row breaking it would mean the
-- grouping and the ordering disagree, which is the quiet way percentile bugs appear.

select role, region, currency, p25, median, p75
from {{ ref('mart_salary') }}
where p25 > median or median > p75 or p25 <= 0
