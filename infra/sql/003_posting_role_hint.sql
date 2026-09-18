-- The role a posting's title matches, decided at ingest by the taxonomy patterns.
--
-- Excerpt postings (Adzuna's 500 characters, many JSearch snippets) are company blurbs
-- that name no skills, so they are never sent to the model. They still count toward how
-- many postings a role and region has, and they carry salary data, so they need a role
-- from somewhere: this column. Full-text postings get their role from the extraction,
-- which reads the whole description.

alter table raw.postings add column if not exists role_hint text;

create index if not exists postings_role_hint_idx on raw.postings (role_hint, region);
