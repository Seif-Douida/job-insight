-- One row per real job opening: duplicates are linked in ingestion and dropped here, so
-- everything downstream can count rows without thinking about it.

select
    id                as posting_id,
    source,
    url,
    title,
    company,
    country,
    region,
    text_quality,
    posted_at,
    salary_min,
    salary_max,
    salary_currency,
    salary_is_predicted,
    ingested_at
from {{ source('raw', 'postings') }}
where duplicate_of is null
