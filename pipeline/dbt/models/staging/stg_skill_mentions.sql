-- One row per skill a posting names. The model returns them as a JSON array; this is the
-- flattening, and nothing else: names are still exactly as the model wrote them.

select
    e.posting_id,
    skill ->> 'name'        as skill_raw,
    skill ->> 'kind'        as kind,
    skill ->> 'requirement' as requirement
from {{ ref('stg_extractions') }} e,
    lateral jsonb_array_elements(e.skills) as skill
where nullif(trim(skill ->> 'name'), '') is not null
