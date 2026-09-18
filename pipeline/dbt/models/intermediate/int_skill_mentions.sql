-- Skill mentions with a canonical name attached.
--
-- The join is case-insensitive, so "Python" and "python" need no entry in the seed; only
-- genuine differences of wording do. A mention with no entry keeps its raw name and is
-- marked unmapped: it is never published, but it is counted in `unmapped_skills` so the
-- seed can be grown where it matters.

select
    m.posting_id,
    m.skill_raw,
    a.canonical_skill,
    coalesce(a.kind, m.kind) as kind,
    m.requirement,
    a.canonical_skill is not null as is_mapped
from {{ ref('stg_skill_mentions') }} m
left join {{ ref('skill_aliases') }} a
    on lower(trim(m.skill_raw)) = a.alias
