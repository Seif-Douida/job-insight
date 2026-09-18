-- The review queue: names the model returned that the alias seed does not know.
--
-- This is the loop that keeps percentages from fragmenting. Run it after each collection,
-- add the names worth counting to skill_aliases.csv, and leave the rest: most are one-off
-- phrasings that no published figure should rest on.

select
    lower(trim(skill_raw))                        as name,
    count(*)                                      as mentions,
    count(distinct posting_id)                    as postings,
    mode() within group (order by skill_raw)      as common_spelling,
    mode() within group (order by kind)           as kind
from {{ ref('int_skill_mentions') }}
where not is_mapped
group by 1
having count(*) > 1
order by mentions desc
