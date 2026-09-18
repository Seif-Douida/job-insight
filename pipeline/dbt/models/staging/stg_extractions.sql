-- One row per posting: whatever the model most recently read out of it.
--
-- A posting can have several extractions (a different model, a newer prompt, or text that
-- changed), so the newest successful one wins. Only `full` postings are ever extracted,
-- which is why no text_quality filter is needed here.

with ranked as (
    select
        posting_id,
        model,
        prompt_version,
        payload,
        extracted_at,
        row_number() over (partition by posting_id order by extracted_at desc) as recency
    from {{ source('raw', 'extractions') }}
    where status = 'ok'
)

select
    posting_id,
    model,
    prompt_version,
    extracted_at,
    payload ->> 'role'                        as role,
    payload ->> 'seniority'                   as seniority,
    (payload ->> 'years_experience_min')::int as years_experience_min,
    payload ->> 'work_mode'                   as work_mode,
    payload ->> 'visa_sponsorship'            as visa_sponsorship,
    payload -> 'skills'                       as skills
from ranked
where recency = 1
