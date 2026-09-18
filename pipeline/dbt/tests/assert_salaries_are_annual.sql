-- Every published median should read as annual pay. A median under the floor means a
-- non-annual figure slipped through the filter and the numbers would mislead.

select role, region, currency, n_postings, median
from {{ ref('mart_salary') }}
where median < {{ var('min_annual_salary') }} or median > {{ var('max_annual_salary') }}
