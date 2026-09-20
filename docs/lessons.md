# What went wrong, and what it taught

A record of the mistakes made building this project, kept because the fixes are less
useful than the reasons. Each entry is what happened, why it happened, and the rule it
produced. Ordered by theme, not by date; the phase is noted so it can be traced back to
[PROGRESS.md](PROGRESS.md).

---

## Measuring the wrong thing

### The rate limiter limited the wrong quantity (phase 3)

Extraction paced itself at 25 requests per minute, under the documented 30 RPM free-tier
limit, and still collected 429s on 18% of calls. The pace was set by a number that was
not the binding constraint.

Asking the API directly settled it. The error body says:

```text
Quota exceeded for metric: generate_content_free_tier_input_token_count
limit: 16000,  quotaId: GenerateContentInputTokensPerModelPerMinute-FreeTier
Please retry in 22.201215248s
```

The limit that binds is **16,000 input tokens per minute**. A posting costs about 2,000,
so the budget runs out at roughly 8 requests — no setting of a request-per-minute pacer
could have held it. `Pacer` now tracks a rolling minute of input tokens as well.

**Rule:** a provider's error body names the quota you actually hit. Read it before tuning
anything. "Under the documented limit" means nothing if it is the wrong limit.

### A quality number that looked broken was measuring the wrong rows (phase 3)

The first live extraction averaged 1.8 skills per posting, which reads like a broken
prompt or a weak model. Reading the actual inputs showed most were Adzuna excerpts: 500
characters of "About us" blurb naming no skills at all. The model was right; the input had
nothing in it.

Extraction is now restricted to `text_quality = 'full'`, and excerpts take their role from
the job title instead.

**Rule:** when a metric looks wrong, look at the rows behind it before touching the thing
that produced it. The bug is often in what was selected, not in what was done to it.

### The fix made the problem invisible, and I read that as the problem being solved (phase 3)

After the pacer was corrected, rate-limited postings stopped being written to
`raw.extractions` — that was the point, so a 429 would not spend a posting's retry budget.
The monitoring query still counted rows with `status = 'error'`, so it reported zero
failures, and it was reported as "zero rejections across the whole run".

The run's own return value said `rate_limited: 20` — 5.4% of requests. The true result was
still good (throughput up from 7.0 to 8.7 per minute, and the refusals now harmless) but
it was not what was claimed.

**Rule:** when a change alters *what gets recorded*, every metric built on those records
changes meaning at the same moment. Check what the new code reports about itself, rather
than watching the old signal go quiet and calling it success.

### One example of someone else's API is not the API (coverage work)

The Workday client was written against NVIDIA's board and broke twice on other employers,
both times by succeeding and returning a wrong number rather than by raising:

- **`total` is reported on the first page only**; later pages return `total: 0`. The loop
  stopped when `len(items) >= total`, so it read two pages and reported 40 postings from a
  board holding 1,530.
- **The country facet is named per employer.** NVIDIA nests `locationHierarchy1` inside a
  location group, GSK exposes `Location_Country` at the top level, AstraZeneca offers no
  country level at all. The code required the facet it knew, so nine of eleven boards
  reported zero postings — including one with 1,198 jobs.

The second fix was the more useful one, and it was a design change rather than a patch:
filtering by country is an *economy*, not a requirement, because every posting states its
own country anyway. A board with no usable facet is now listed in full.

Neither bug raised an exception, and unit tests written from the same single example would
have passed. What caught both was a number that could not be true: 40 in-scope postings
from a 2,000-job board, then 0 from 1,198.

**Rule:** when integrating someone else's API, check a second and third provider before
believing the shape of the first. And treat an implausible-but-successful result as a
failure — it is the kind that tests built from one sample cannot see.

### "Running" is not the same as working (phase 4)

The `transform` DAG was reported as still running, twice, when it had already failed. Two
different states look identical from the outside:

- **A paused DAG accepts a trigger and queues forever.** Airflow pauses new DAGs by
  default, so the first run sat in `queued` indefinitely. That reads as "busy", not as
  "will never start".
- **A run stays `running` while a failed task waits out its retry delay.** `dbt_build`
  failed after 90 seconds and then sat in a ten-minute backoff. The run-level state said
  `running` the whole time.

The task-level states said `up_for_retry` immediately, which is the thing to look at.

**Rule:** a run's state answers "is anything still pending", not "is anything going well".
When something takes longer than it should, read the task states and the task log before
reporting progress, rather than taking the optimistic reading of an ambiguous signal.

### The deduplication table was not itself deduplicated (phase 5)

`skill_aliases.csv` exists to stop one skill being counted as several: it maps every
spelling onto a canonical name, so "Postgres" and "PostgreSQL" are one row. It contained
`Hugging Face` and `HuggingFace` as two *canonical* names, and `Infrastructure as code`
and `infrastructure-as-code` as two more. Both skills had their postings split across two
entries, and both therefore showed roughly half their real demand.

Nothing could have caught it. The dbt tests check that percentages are fractions and that
counts fit their cohort, and two half-sized rows pass all of that happily. It only surfaced
when the skill pages needed one URL per skill and two skills resolved to the same slug.

The fix was four characters. The useful part was the test that came with it: canonical
names are now compared with case and punctuation removed, so any future pair that differs
only in spelling fails the suite. Real distinctions survive because the comparison keeps
`#` and `+`, which is the whole difference between C, C# and C++.

**Rule:** a table whose job is to merge duplicates needs a test that it contains none
itself. And a data error that halves a number rather than breaking it will pass every
validity check you have — the tests that find those compare rows to each other, not each
row to a rule.

### Grepping rendered HTML is not checking the page (phase 5)

A line was added to the front page, the app was rebuilt, and `curl | grep "up to 18
September 2026"` found nothing — so the conclusion was that a stale build was being
served. The line was in fact there. React server-renders interpolated values as separate
text nodes with markers between them, so a sentence assembled from `{corpus.latest}` never
appears contiguously in the HTML and that phrase could not have matched whatever the server
was serving.

Underneath it there was a real second fault: the restart had failed with `EADDRINUSE` and
the old process was still holding the port. Two problems at once, one of them imaginary,
and the imaginary one was the one being debugged.

What settled it was looking at the page in a browser and at the failed restart's own exit
code, rather than at a string that could not have matched either way.

**Rule:** a search that finds nothing has two explanations, and "the thing is absent" is
only one of them. Before believing a negative result, check that the search could have
succeeded. For rendered output, assert against the DOM or the screenshot, not the markup.

### Two environments are not one environment (phase 4)

`dbt build` worked on the host and failed inside the Airflow container with
`KeyError: 'dbt_postgres://macros/catalog.sql'`, thrown from deep inside dbt's parser
rather than anywhere that named the cause.

The repo is mounted into the container, so `pipeline/dbt/target/` is shared. Running dbt on
the host wrote `partial_parse.msgpack` there, under Python 3.14 and a separate dbt install,
and the container's dbt tried to reuse it. The DAG now passes `--no-partial-parse`.

**Rule:** a mounted directory is shared mutable state between two machines. Caches and
build artifacts written by one are not safe input for the other, however identical the
tool version looks.

### A counter can measure intent rather than fact (phase 3)

`raw.quota_usage` read 1,779 while only 320 extractions existed, which looked like a
runaway. It was not: the run reserves its whole batch up front, so the counter meant
"claimed", not "spent".

**Rule:** before drawing a conclusion from a counter, check whether it counts what was
reserved, attempted or completed. The three diverge exactly when you are debugging.

---

## Retries and failure handling

### Retries bypassed the rate limiter that existed (phase 3)

The HTTP layer retried a 429 five times with growing waits. Those retries never passed
through the pacer, so each rate-limit incident fired six unpaced requests, and with five
workers doing it at once the retries caused the next refusal. The error rate climbed from
11% to 18% as the run went on — a feedback loop, not bad luck.

The model backend now excludes 429 from its retryable statuses and the run pauses every
worker for exactly the delay the server states.

**Rule:** a retry is another request. If something governs your request rate, retries have
to go through it too, or the governor is decorative. And a rate limit is never fixed by
retrying harder in the same place.

### A transient failure was charged to the wrong thing (phase 3)

Each rate-limited posting was stored with `status = 'error'`, which consumed one of its
three attempts. 143 postings were penalised for a fact about the minute they happened to
be sent in. After three unlucky minutes a posting would have been abandoned permanently.

Rate-limited postings are no longer written at all; they stay pending, unmarked, and the
reserved quota is given back.

**Rule:** separate "this item is bad" from "the system was busy". Only the first should
count against an item's retry budget.

### Patient retries were the right answer once, which is why the wrong answer looked right (phase 2)

Adzuna dropped roughly half of new connections. Five retries with growing waits recovered
7 of 10 failed queries, and the same policy was then applied to the model API, where it
made things actively worse. The policies look identical and differ completely: a connection
that never opens costs no quota, while a rejected request is the server telling you to stop.

**Rule:** retry policy follows the failure's cause, not its shape. Copying a policy across
services carries an assumption that usually goes unstated.

---

## Diagnosing before fixing

### Proving whose fault a network failure is (phase 2)

Adzuna calls failed with `ReadError` and `ConnectError`. Rather than guess, the same
requests were tried with `urllib` (also failed), and TLS handshakes were compared across
hosts from the same machine: 6/10 to `api.adzuna.com`, 10/10 to S3, DynamoDB, Greenhouse
and `adzuna.co.uk`. That isolated the fault to Adzuna's API endpoint and justified retries
instead of a code change.

**Rule:** before working around a network failure, establish whether it is yours, theirs,
or the path between. A control host and a second client library answer it in minutes.

### An estimator's safety margin needs measuring too (phase 3)

The token estimator was first calibrated to the densest prompt seen, so it could never
undercount. Checked against 800 real prompts it never did — but ran 22% high on average,
which would have left a fifth of the quota unused. It is now calibrated to the median, with
the occasional overshoot absorbed by the server's own stated backoff.

**Rule:** a conservative estimate is not free. Measure the bias, and price the caution
against what it costs you.

---

## Tests, fixtures and labels

### Fixtures chosen by pattern matching tested the wrong thing (phase 2)

The Greenhouse fixtures were selected with a regex that matched "AI" inside "Account
Executive, AI Sales", so the recorded sample was mostly sales roles. The fixture set now
deliberately mixes clearly relevant, ambiguous and clearly irrelevant postings.

**Rule:** a fixture set is an argument that the code handles reality. Pick the cases on
purpose, including the ones that should be rejected, and read what you recorded.

### Several test failures were faults in the tests (phase 2)

A fixture with a trailing space failed against a model that strips whitespace; a helper
passed `description_text` twice; a signature was mangled during an edit. Time went into
the production code before the test was suspected.

**Rule:** test code is code. When a test fails, read the test first — it changed more
recently than the thing it tests.

### Labels can drift toward the model they judge (phase 3)

While reviewing evaluation results, two hand-written labels turned out to be wrong
(postings 5057 and 5534, both leadership roles labelled "unclear"). Correcting them is
legitimate; correcting a label *because the model disagreed* would quietly turn the
benchmark into a mirror.

The written rule now sits in `labels.json`: corrections are made only when re-reading the
posting shows the first label was wrong, never to agree with a model. The provenance block
also records that the labels were written by a language model reading 19 postings, so the
scores are a guide rather than ground truth.

**Rule:** write down the standard for changing a benchmark before you have a reason to
change one, and record who made the labels and how.

### Measure before tuning, then measure again (phase 3)

Prompt v1 scored 68% precision on skills and 79% on seniority. Those numbers named what to
fix; prompt v2 (skill-naming rules, explicit exclusions, seniority mapping) reached 81%
precision and 95%. Without the golden set both prompts would have looked fine.

**Rule:** build the measurement before the thing it measures is worth arguing about.

---

## Orchestration and tooling

### A DAG can report success while ten tasks failed (phase 2)

Airflow takes a run's state from its leaf tasks. `link_duplicates` runs with `all_done`, so
it succeeded and marked the whole run green while 10 Adzuna queries had failed. Every
ingest DAG now ends with a task that fires only on failure and fails the run.

**Rule:** know which task determines the state your alerting reads. A cleanup step that
always runs will hide everything upstream of it.

### A pipe swallowed a failure (phase 1)

`docker compose up -d | tail` reported exit 0 while Docker Desktop was not running: in a
pipeline the exit status is the *last* command's. The failure was invisible until the next
step broke.

**Rule:** do not pipe a command whose success you care about, or set `pipefail`.

### Watchers that stop on a guess (phase 3)

Two monitoring scripts were written to poll a fixed number of times, and both exited while
the job was still running, which reads exactly like "the job finished". The third stops on
a condition — pending work reaching zero with no run active.

**Rule:** a watcher should terminate on the condition it is watching for, never on a
guess at how long that takes. Otherwise its exit is ambiguous at best and misleading at
worst.

### Tool defaults drift with the interpreter (phase 1)

black warned about Python 3.15 syntax while running under 3.14, because no target version
was pinned. Both black and ruff now pin `target-version = py311`.

**Rule:** pin the language target for formatters and linters, or their output changes
underneath you when the interpreter does.

### Local editor state reached the repository (phase 1)

`.claude/settings.local.json` was committed before anyone noticed. `git rm --cached`
untracks a file without deleting it.

**Rule:** add local tool state to `.gitignore` when the tool first creates it, not when
you notice it in a diff.

---

## Reading someone else's API

### A key identifies its vendor, not the service you expected (phase 2)

JSearch calls returned 403 "not subscribed" against RapidAPI. The key was an OpenWeb Ninja
key for the same underlying data, wanting a different host and a different header. The
client now calls `api.openwebninja.com/jsearch/search-v2` with `x-api-key`.

**Rule:** confirm which vendor issued a credential, and make one live call, before writing
a client against anybody's documentation.

### Free-text fields contain whatever the employer typed (phase 2)

Cloudflare yielded zero in-scope postings because its location field held the work
arrangement — "Hybrid", "In-Office" — for 268 jobs, and the fallback to office names had
been applied in the wrong order. Fixing the ordering recovered 24 postings.

**Rule:** a field's name is a claim about its contents, not a guarantee. Look at the real
distribution before trusting it, especially when a filter returns nothing.
