-- Raw layer: everything ingestion and extraction write to.
-- Idempotent: safe to run repeatedly. dbt owns the staging/mart schemas.

create schema if not exists raw;

-- One row per posting per source. Cross-source duplicates are linked, not deleted,
-- so coverage per source stays measurable.
create table if not exists raw.postings (
    id                  bigserial primary key,
    source              text        not null,          -- greenhouse | lever | ashby | smartrecruiters | adzuna | jsearch
    source_id           text        not null,
    url                 text        not null,
    title               text        not null,
    company             text,
    location_raw        text,
    country             char(2),
    region              text,                          -- us | uk | eu | gulf | other
    description_text    text,                          -- trimmed to 1000 chars after extraction
    text_quality        text        not null check (text_quality in ('full', 'excerpt')),
    posted_at           timestamptz,
    salary_min          numeric,
    salary_max          numeric,
    salary_currency     char(3),
    salary_is_predicted boolean     not null default false,
    content_hash        text        not null,          -- detects changed text on re-ingest
    dedupe_key          text        not null,          -- normalized company + title + country
    duplicate_of        bigint      references raw.postings (id),
    ingested_at         timestamptz not null default now(),
    unique (source, source_id)
);

create index if not exists postings_dedupe_key_idx on raw.postings (dedupe_key);
create index if not exists postings_region_posted_idx on raw.postings (region, posted_at);
create index if not exists postings_canonical_idx on raw.postings (id) where duplicate_of is null;

-- One row per (posting, model, prompt version): re-extraction with a better model
-- never destroys earlier results, and taxonomy changes never require a new LLM call.
create table if not exists raw.extractions (
    id             bigserial primary key,
    posting_id     bigint      not null references raw.postings (id) on delete cascade,
    model          text        not null,
    prompt_version text        not null,
    payload        jsonb,                              -- validated extraction, null when status <> 'ok'
    status         text        not null check (status in ('ok', 'invalid_json', 'error')),
    error          text,
    input_tokens   integer,
    output_tokens  integer,
    latency_ms     integer,
    extracted_at   timestamptz not null default now(),
    unique (posting_id, model, prompt_version)
);

create index if not exists extractions_status_idx on raw.extractions (status);
create index if not exists extractions_pending_idx on raw.extractions (posting_id) where status = 'ok';

-- Daily request counter, persisted so a restart cannot double-spend the free quota.
create table if not exists raw.quota_usage (
    day      date    not null,
    model    text    not null,
    requests integer not null default 0,
    primary key (day, model)
);
