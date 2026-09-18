-- An extraction describes one version of a posting's text. Keying it on the content hash
-- as well as the model and prompt means a posting whose text changes is extracted again,
-- and earlier results stay as they were.

alter table raw.extractions add column if not exists content_hash text;

-- How many times this posting version has been sent to the model, so a posting that keeps
-- failing is given up on instead of being retried every day.
alter table raw.extractions add column if not exists attempts integer not null default 1;

alter table raw.extractions
    drop constraint if exists extractions_posting_id_model_prompt_version_key;

create unique index if not exists extractions_posting_model_prompt_content_idx
    on raw.extractions (posting_id, model, prompt_version, content_hash);
