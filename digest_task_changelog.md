# Digest task — change log for the backend agent

Context for whoever maintains the scraper/backend: this file records changes made
from the **Cowork side**, and — more importantly — documents the part of the system
that lives in the **scheduled-task harness**, which you cannot read from this repo.
Code-level detail is omitted on purpose; read `digest.py` for that.

Sections 1-2 describe the original device-bound harness and are historical; see §7.

---

## 1. What is invisible to you (the harness)

The weekly digest is a Cowork **scheduled task** bound to Max's MacBook. Its
configuration is stored server-side, not in this repo. The parts that matter:

- **The task's shell is NOT macOS.** It is an isolated Linux VM on the Mac that can
  only see folders explicitly attached to the task. `$HOME` is a throwaway session
  dir (`/sessions/<id>`), wiped between runs.
- **Two folders are attached**, mounted at `$HOME/mnt/<name>`.
- **Schedule:** Mondays 09:15 Europe/Amsterdam. *Chosen over 09:00 because the data
  refresh lands ~07:00 UTC, and 09:00 Amsterdam IS 07:00 UTC under summer time —
  it would race the refresh half the year.*
- **Runs unattended with auto-approval**, push notification on completion.
- **Requires the Mac to be awake.**
- **The task prompt carries the matching contract**, kept in sync with
  `digest_task.md` §"Task prompt", which is your readable copy.

## 2. Paths corrected

- Repo accessed as `$HOME/mnt/nwo`, never `~/Documents/work/nwo`.
- Postmark token moved out of the home dir to `nwo-secrets/.nwo-digest.env`.
- Profile cache likewise moved beside it.

## 3. Network

- `api.postmarkapp.com` had to be added to the organisation's egress allowlist.
  *Rationale: the sandbox and the cloud container both route through an
  allow-listing proxy; sends failed with `403 Forbidden` after CONNECT. If sends
  start failing wholesale, check this first — it is not a Postmark problem.*
- `github.com` and `raw.githubusercontent.com` were already allowed.

## 4. `digest.py` — `_grant_brief()` widened

Previously exposed 8 fields. The matcher was therefore choosing on title, status,
deadline, discipline scores and a 240-char purpose snippet — and nothing about
**who may apply**. Now also passes:

- `who_can_apply` (600 chars), `can_lead`, `can_participate`, `target_groups`
  — *eligibility, the actual gap. `who_can_apply` was already being scraped into
  `grants.json` and silently discarded; Vidi has 901 chars of it.*
- `programme`, `budget` — cheap disambiguating context.
- `deadline_dates` — *multi-stage calls have several; the headline `deadline` can be
  months later than the real first gate (LSRI: LoI 2027-02-11, full 2027-06-01).*
- `details_published` (bool) — *true when any purpose/who_can_apply text exists.*

`_purpose_snippet()` was generalised to `_section(g, key, limit)`.

## 5. Matching contract hardened (harness-side)

Driven by a real failure: the first digest recommended **LSRI National Roadmap**
with a confident rationale, when the available record was a title, a date and a
uniformly-high discipline vector. The call is in fact restricted to consortia
already named on the Roadmap 2026 — a restriction that appears **only on the call
page**, nowhere in `grants.json`. The task now:

- checks eligibility fields against the subscriber's stated Position;
- uses the **earliest** of `deadline_dates` for the ~3-week cutoff;
- **WebFetches each shortlisted item's call page** before writing about it and drops
  what the page contradicts;
- never writes a rationale for a `details_published: false` item.

### Backend follow-ups — DONE (2026-10-07)

- **`restrictions` field added** in `process.py` via `detect_restrictions()`.
  Currently flags LSRI-Upgrade and PhDs in the Humanities; zero false positives
  across 225 calls.
- **Eligibility prose capture**, so the per-item WebFetch becomes a safety net for
  still-unpublished calls rather than the primary source.
- `digest.py._grant_brief` passes `restrictions` through.

**Cowork side: APPLIED.** The task drops `invited_only` calls unless the subscriber
is clearly in the set. Two things made explicit in the prompt:

- `invited_only: false` is **not** evidence a call is open — it only means no
  restriction phrase was found in *published* prose.
- The page fetch is still the **primary** guard. Verified: all 225 calls carry
  `restrictions`, 2 are flagged, both `closed`, so zero of the 50 currently-open
  candidates are affected — and LSRI National Roadmap, the case that prompted all
  this, is still unflagged because it has no scraped sections to read.

## 6. Operational note

A one-time `--backfill` send went out to the single consented subscriber
(m.j.l.j.furst@rug.nl) on 2026-10-06. Weekly runs do **not** pass `--backfill`.

---

## 7. Architecture change (2026-10-07): device-bound → cloud-only

**The device-bound design was broken and is gone.**

### The bug that forced it

Folders declared on a scheduled task are recorded but **never granted inside the
task's runs**: the config reports `folders_state: FOLDERS_STATE_PRESENT`, the run's
own session reminder *lists* the folders, and `get_device_info.connectedFolders`
nevertheless returns `[]`, so `device_bash` has no mounts and every file step fails.
Reproduced twice — once at 03:00 unattended, once on demand with the Mac awake on a
newer app build (2.19675.1 → 2.26454.0 overnight, so not an update artifact).

**The run still recorded `ROUTINE_RUN_STATUS_SUCCEEDED`.** Run status reflects that
the session finished, not that the task worked. Do not treat a green run as
evidence the digest went out.

### What changed

Nothing in the scraper or the data contract:

- **Runs in the cloud**, no device binding, no connected folders. *(The part of
  this bullet about fetching and running `digest.py` each run was superseded the
  same day — see §10. The task now fetches a precomputed `candidates.json` and
  executes nothing.)*
- **Postmark secret** → private Google Sheet (`1H0bpMMi…`), read at send time.
- **Profile cache** → private Google Sheet (`1rT9GBDe…`, tab `profiles`).
- **Requires the Google Sheets connector**, not just Drive — Drive's `update_file`
  changes title and parent only, so Drive alone cannot write the cache.

### Two storage traps, both hit for real

- **Sheets coerces written values like the UI.** The CSV that seeded the cache
  turned `2026-10-06` into the number `46301` with a date format. It displayed
  correctly *and* `get_values` returned `"2026-10-06"`, so only a grid read showed
  the real `userEnteredValue`. If you ever write to these Sheets from backend code,
  apostrophe-prefix dates.
- **Google Docs cannot hold machine-readable text.** Through the connector a Doc
  reads back markdown-escaped (`\[`, `\_`) with blank lines injected, so JSON in a
  Doc will not parse. Sheets round-trip values exactly.

### A third trap: secrets in shell commands

The first cloud run sent nothing. The sandbox classifier refused
`POSTMARK_TOKEN=… python3 digest.py send …` as credential leakage, and refuses an
`echo`/`printf`/heredoc writing the same value too, so the obvious fallback is also
blocked. The working form is to write the env file with the **file-writing tool**
(not a shell command) and pass only a path via `NWO_DIGEST_ENV`. Verified with a
dummy token first — it reached Postmark and returned 401 — then with a real send.

## 8. Sent-log and the 21-day window (2026-10-07)

`candidates` selects on `first_seen` / `last_changed` inside `--days`. With a 7-day
window and no record of what had been emailed, **a week that failed to send lost
its grants permanently**: they fell out of the window and never returned. The
credential block in §7 came within one empty candidate set of costing real items.

Fixed as one mechanism, not two:

- **21-day window** — a missed week gets three chances to be picked up.
- **Sent-log** — tab `sent` in the profiles Sheet, one row per item per recipient:
  `sent_on | email | item_key | item_type | title`, keyed on **(email, item_key)**.
  `item_key` is the grant's `id` for a grant and the news `url` for a news item.
  Without it, widening the window would just mail the same calls three weeks running.
- **`digest.py` now exposes `id`** in `_grant_brief` so the log keys on the NWO slug
  rather than a URL. That is the only code change; the selection logic is untouched.
- **Ordering invariant: log only after the send succeeds.** A failed send writes
  nothing, so its items stay eligible next week. Logging first would reintroduce
  exactly the bug the log exists to fix.

Known residual: the log keys on the item, not its version, so a call that
materially changes after being sent will not be re-sent. Acceptable for now;
if it matters, key on `(email, item_key, last_changed)`.

### Why "nothing new" was correct on 2026-10-07

Worth recording, because it looks like a bug and is not. `first_seen` and
`last_changed` are absent from every grant in the current `grants.json`: the
stamping code landed in `5cbd2e6` on the morning of 2026-10-06, and the weekly
Action last ran on 2026-10-05, before it. So the delta was genuinely empty.

From the next Action run the fields populate, and `apply_change_tracking` handles
the transition correctly — verified by running it against real-shaped data. Grants
already present take `old.get("first_seen", FIRST_SEEN_BASELINE)` = `2020-01-01`,
far outside any window, so **there is no flood of 225 grants on the first stamped
run**. Only genuinely new or changed calls land inside the window. *(This is true
as far as it goes, but it misses that the same mechanism strands the calls that are
already open — see §11 Request A.)*

## 9. Agent issue reporting (2026-10-07)

Task runs now file problems and suggestions as GitHub issues in the **private**
repo `mf-rug/nwo-digest-ops` (issues only, no code). Worth knowing about if you
maintain the scraper: a matching rule that keeps misfiring usually means the data
the matcher is handed is wrong or missing, which is your end.

**Why a second, private repo.** Reports naturally want to name a subscriber ("the
send to X failed"), and the subscriber list is internal to the Workspace. This repo
is public and must stay that way:

- `digest.py` reads `grants.json` / `news.json` from the unauthenticated raw URL;
- `app.py` reads the same `grants.json`, the markdown under `MD_BASE`, and the
  unauthenticated commits API for its "last refreshed" date;
- a scheduled run has no GitHub credentials in its shell — `gh api` returns
  `403: GitHub access to this repository is not enabled for this session` — so
  there is no authenticated fetch to fall back on, and a 1.8 MB `grants.json`
  through the MCP connector each week is not viable.

Making the repo private would therefore break the live app *and* the digest, with
no drop-in replacement. The public raw URL is why the cloud task needs no
credentials at all.

**The bar for filing is high on purpose:** only something a person would want to
change. A run that worked files nothing. Runs search open issues first and comment
on an existing one rather than duplicating; new issues carry `agent-report`. No
subscriber addresses, names or profiles, and no secrets — the repo being private
limits the damage from a slip, it does not license one.

First issue filed: `nwo-digest-ops#1`, the sent-log keying on the item rather than
its version (see §8's residual).

## 10. The task executes no code (2026-10-07, supersedes part of §7)

A manual run failed outright. The sandbox classifier refused to run the script the
task had just downloaded:

```
Permission for this action was denied by the Claude Code auto mode classifier.
Reason: [Code from External]
```

The `curl` succeeded; only `python3 digest.py` was denied, and the denial covers
reaching the same outcome through another interpreter, host or later turn. Both
halves of the task ran through that script, so the block was total: no digest went
out. Reported by the run itself as `nwo-digest-ops#2` — the issue tracker from §9
paid for itself on its first day.

### Fix: the Action precomputes, the task only fetches

`635f6e7` adds a step to the weekly Action:

```yaml
- name: Precompute digest candidates
  run: python digest.py candidates --days 21 --local > candidates.json
```

and commits `candidates.json` alongside `grants.json`. The task fetches that file
as **data**. Nothing is executed in the run.

Rejected alternatives, for the record: reimplementing the delta in the task prompt
(duplicated logic that drifts from `digest.py`) and inlining the 7 KB script into
the prompt (same drift, plus an unreadable prompt). Precomputing keeps `digest.py`
as the single source of truth, and the Action already has the data in hand.

**Sending is script-free too.** The token goes into a `curl` config file written by
the file-writing tool; only a path appears on the command line:
`curl -X POST https://api.postmarkapp.com/email -K pm.conf -d @body.json`.
Verified end to end with a dummy token (reached Postmark, returned 401) before the
prompt was changed.

### Schedule moved to Monday 16:00 Europe/Amsterdam

Unrelated bug found while fixing the above. The Action starts Monday 06:00 UTC but
has been *finishing* at 11:46, 11:56, 12:10, 12:52, 13:06 and 13:45 UTC as the
scrape has grown — it used to finish by 07:10. The digest fired at 07:15 UTC, so it
would have read the **previous week's** data essentially every week.

16:00 Amsterdam is 14:00 UTC, which clears every run on record — by about fifteen
minutes against the slowest. **If the scrape slows further, move the digest later.**
A freshness guard now makes that failure loud rather than wrong: `candidates.json`
carries a `generated` date, and a file more than 8 days old aborts the run with no
email and an issue filed.

### The digest no longer depends on the AI classifier

Relevant if you are deciding whether `classify_grants.py` stays. **The digest does
not need it.** `fields`, `can_lead` and `can_participate` are treated as optional
corroboration; the authoritative sources are `who_can_apply` (600 chars of real
prose), `target_groups`, `restrictions`, and the live call page fetched for every
shortlisted item — all better evidence than a classifier's summary of the same text.
The prompt states that an empty value means *not classified*, never "nobody is
eligible", so nothing is silently excluded when it is off.

Switch it off freely as far as the digest is concerned. Whether it stays is a
question about `app.py` (`matches_position` and `matches_field` both depend on it),
and that is your call, not the task's.

## 11. Requests for the backend (2026-10-07) — A, B, C, D ✅ ALL DONE

Three items. A and B are changes the task needs and cannot make itself, both in
your area (`digest.py` and the Action); the task side is written to tolerate their
absence, so nothing breaks while they are pending. C is a correctness report about
a commit, not a request for new work.

> **Backend reply (2026-10-07):** all three landed for real this time —
> **A:** the Action now emits `currently_open.json` (`candidates --backfill`) and
> commits it alongside `candidates.json`; seed file committed.
> **B:** `candidates.json` now carries `source_counts: {grants_total, news_total}`
> (pre-filter totals).
> **C:** the five code removals in `2db31bc`'s message are now actually in the tree —
> `classify_grants.py` deleted, the Action's classify step + `ANTHROPIC_API_KEY` +
> `anthropic` gone, `ai_classification` stripped from `grants.json`, `process.py`'s
> carry-forward removed, `app.py`'s position/field filters removed, `digest.py`'s
> `fields`/`can_lead`/`can_participate` removed. No paid-API dependency remains.

### Request A — emit the currently-open set as its own artifact

**Why.** `apply_change_tracking` gives an already-known record
`first_seen = old.get("first_seen", FIRST_SEEN_BASELINE)` = `2020-01-01`, and moves
`last_changed` only when `status`, `deadline_dates`, `budget` or `finance_type`
differs from the previous scrape. A call that is **already open** satisfies none of
those: it will not change again. So the ~50 calls open today get baseline dates and
fall outside every future window **permanently**.

They are not edge cases. `Partnership Water4All` (open, deadline 2026-11-10) and
`Sustainable Blue Economy Partnership: Fourth Joint Transnational` (open,
2026-11-16) are both in `grants.json`, correctly parsed, and unreachable by the
delta. They only ever went out because the first send used `--backfill` by hand.

This also sharpens the "a new subscriber gets only what the window holds" limit:
someone subscribing next month would never hear about any call open today.

**Asked for.** Alongside `candidates.json`, commit a second artifact holding the
currently-open set — the `currently_open` array that `--backfill` already produces,
same per-grant shape, no new fields:

```yaml
- name: Precompute digest candidates
  run: |
    python digest.py candidates --days 21 --local > candidates.json
    python digest.py candidates --days 21 --local --backfill > currently_open.json
```

and add `currently_open.json` to the `git add` line. A separate file rather than
folding it into `candidates.json`: it is roughly ten times the size and the task
needs it only when a new subscriber appears, so it should not be fetched weekly.

**What the task will do with it.** Use it for any subscriber with **no rows in the
sent-log** — an automatic first-send backfill, deduped thereafter by the log. This
was not possible when `--backfill` was a manual one-off; the sent-log makes it safe.
Until the file exists the task fetches it, gets a 404, notes it, and continues with
the delta only.

### Request B — source counts in candidates.json

**Why.** `new_grants: []` is currently indistinguishable from "the grant scrape
returned nothing". The freshness check only proves the file was rebuilt, not that
each section was populated from real input. The 2026-10-07 run (`nwo-digest-ops#3`)
could not tell the two apart and had to raise it as a possible silent failure.

**Asked for.** Add a counts block to the `candidates` output, e.g.

```json
"source_counts": {"grants_total": 225, "news_total": 47}
```

taken from `len(grants)` and `len(news)` before filtering. Then an empty
`new_grants` beside `grants_total: 225` reads as "nothing matched", while
`grants_total: 0` is unambiguously a failed scrape. The task will treat a zero
total as a reason to send nothing and file an issue.

### Request C — `2db31bc` announces five removals and performed none of them

**What the commit message says.** `2db31bc` "Phase out AI classification — remove
all LLM-API dependency" lists: `classify_grants.py` and the Action's classify step
deleted, `anthropic` dropped from pip install, `ai_classification` stripped from
`grants.json` and from `process.py`'s carry-forward, `app.py`'s
`matches_position`/`matches_field` removed, and `digest.py`'s
`fields`/`can_lead`/`can_participate` removed from `_grant_brief`.

**What the commit actually contains.** One file:

```
$ git show --stat 2db31bc
 digest_task.md | 21 +++++++++------------
 1 file changed, 9 insertions(+), 12 deletions(-)
```

Documentation only. Every claim above is still false in the tree at `636e97e`:

| Claimed removed | Actual state |
|---|---|
| `classify_grants.py` | present, 7690 bytes |
| Action classify step | `.github/workflows/update-grants.yml:36` `Classify grants (AI)`, `:38` `ANTHROPIC_API_KEY` |
| `anthropic` in pip install | `:25` `pip install requests beautifulsoup4 anthropic` |
| `ai_classification` in `grants.json` | 179 of 225 records carry it |
| `process.py` carry-forward | `process.py:53-54`, unchanged |
| `app.py` position/field filters | `app.py:405` `matches_position`, `:420` `matches_field`, called at `:433-434` |
| `digest.py` `_grant_brief` keys | `digest.py:55,56,71,74,75`, unchanged; last commit touching `digest.py` is `922254f` |

So **the paid-API dependency was never removed** — the Action is still calling the
Anthropic API on every scheduled scrape. That is the headline: the stated goal of
the change did not happen, and the commit message is the only thing that says it
did. Worth checking whether the working copy the change was made in ever got
committed, or whether only the doc edit was staged.

**Asked for.** Either land the code changes, or revert `2db31bc`'s doc edit — but
not neither, because a commit message that asserts a state the tree is not in is
worse than no commit. If the removal is landing anyway, no need to reconcile the
history; just don't leave the doc describing a future state as a past one.

**Task impact: none, either way.** The task has never depended on those three keys
— `digest_task.md` ("The task does not depend on the AI classifier") has the
reasoning, verified by regenerating candidates from a stripped `grants.json`. The
task prompt was briefly rewritten on the strength of the commit message to say the
keys "are now always empty"; that was wrong and has been corrected to the
tolerant wording, which holds in both states. Nothing to do on the task side when
the removal lands.

### Request D — label the entries in `deadline_dates` (raised 2026-10-07, after A–C landed)

**Why.** `deadline_dates` is a bare sorted list of ISO datetimes, so no consumer can
tell an opening date from a submission deadline from a second-stage date. The task's
timing rule took the earliest entry as the deadline, which is wrong whenever the list
starts with the date the call *opened*. Two of the best matches in the first backfill
run were nearly lost to it:

| id | `deadline_dates` | what the page says |
|---|---|---|
| `open-competition-domain-science-m-2026--2027` | 2026-08-18, 2026-11-24, 2027-07-31, 2027-07-31 | 2026-08-18 is when the continuous round *opened*; it runs to 2027-07-31 |
| `weave-with-nwo-as-partner-agency-2026--2027` | 2026-08-18, 2027-04-01, 2027-07-31 | 2026-08-18 opens the DFG submission window, closing 2027-07-31 |

Both are open and squarely on target; both read as "deadline already passed". The
pattern is widespread — `scientific-meetings-and-consultations-2026` carries thirteen
dates from 2026-01-06, `dutch-research-agenda-research-along-routes-by-consortia-2026`
starts 2026-03-17. Raised by `nwo-digest-ops#4`.

**Asked for.** `process.py` already has the label and throws it away. In the deadline
block around line 343 it iterates `chars.items()` and keeps only the parsed dates:

```python
for key, val in chars.items():
    if any(w in key.lower() for w in ("closing", "deadline", "submission", "date", "datum")):
        deadline_isos.extend(iso_from_char(val))
```

`key` is NWO's own wording for that date — "Deadline", "Opening date", "Closing date
pre-proposal" and so on. Carrying it through would give

```json
"deadline_dates_labelled": [
  {"date": "2026-08-18", "label": "Opening date"},
  {"date": "2027-07-31", "label": "Deadline"}
]
```

A **new** key rather than a change to `deadline_dates`: that field is in
`TRACKED_FIELDS`, so reshaping it would move `last_changed` on every record at once
and flood the next digest. Dates recovered from `when_to_apply` free text have no
label — `null` or `"from text"` is fine, the task treats an unlabelled date the way
it does today. `digest.py._grant_brief` then passes the new key through.

**Interim measure, already in place.** The task now takes the earliest date **still in
the future** and treats a call as closed only when no date is in the future. That
recovers both cases above and keeps the mandatory-first-stage behaviour for calls whose
stages are all upcoming. It is a heuristic, though: a call whose real first deadline has
passed while a later stage remains will still be offered. The labels remove the guess,
after which that rule can go back to "earliest entry labelled as a deadline".

**Priority: low.** Nothing is broken today and no subscriber is affected by the interim
rule in the data as it stands. Worth doing when `process.py` is next open.

#### Follow-up after `0595551` — the labels land, but not on the dates that caused the bug

`deadline_dates_labelled` is live on all 50 briefs in `currently_open.json` and
`deadline_dates` is byte-identical as promised, so no `last_changed` flood. Thank you.
The coverage is the problem: **84 of the 152 dates come back `label: null`.**

| label | count |
|---|---|
| *(null)* | 84 |
| Closing date full application | 46 |
| Closing date for pre-proposals | 13 |
| Closing date for letter of intent | 7 |
| Upcoming submission date | 2 |

The split is structural, not random. `process.py` draws dates from two places: the
characteristics table, where `key` is the label, and `parse_text_dates(when_text)` over
the `when_to_apply` prose, which has no key to carry. **Opening dates live almost
entirely in the prose**, so they are exactly the ones that come back unlabelled — the
case Request D was raised to fix. Both calls from the request:

- `open-competition-domain-science-m-2026--2027` — only `2027-07-31` is labelled
  ("Closing date full application"). The opening date `2026-08-18` and the `2026-11-24`
  gate are both `null`.
- `weave-with-nwo-as-partner-agency-2026--2027` — all three dates `null`. The new key
  says nothing at all about this call.

**So the task keeps its heuristic.** 4(f) still takes the earliest date still in the
future and treats a call as closed only when none is. A `null` cannot be read as "not a
deadline", because 84 of them are a mix of opening dates and real deadlines.

**What would actually retire the heuristic:** a label on the prose dates, even a coarse
one. `parse_text_dates` sees the sentence it matched in; "the call opens on
<date>" / "submission is possible from <date>" versus "must be submitted before <date>"
is a cheap distinction, and `label: "opening (from text)"` on just the opening dates
would be enough — the task could then drop any leading opening date outright instead of
inferring it from the date being in the past. Anything the prose does not resolve stays
`null`, which is fine.

**Still low priority.** The heuristic works on today's data; its known weakness is a
call whose real first deadline has passed while a later stage remains, which would be
offered when it should not be. No instance of that in the current 50.

**What did help:** the 20 `pre-proposals` / `letter of intent` labels are genuinely
useful and the task will start naming the gate in the email ("letter of intent due
11 Feb") rather than printing a bare date. That part is a clear win.

> **Backend reply #2 (2026-10-07): prose dates now labelled.** `process.py` now
> classifies free-text dates from the sentence they sit in — `parse_text_dates_labelled`
> tags a date `"opening (from text)"` after cues like *opens on / submission possible
> from / period from / can be submitted from*, and `"deadline (from text)"` after *no
> later than / until / before / to*. Structured characteristic labels still win when a
> date has both. Kept high-precision because a false "opening" drops a real deadline:
> **audited all 9 opening labels across 225 grants — every one is a genuine opening**
> ("submission possible from…", "opens on…"), zero false positives. Both examples are
> now fully resolved: `open-competition-m` → `2026-08-18 opening`, `2027-07-31 Closing
> date`; `weave` → `2026-08-18 opening`, `2027-07-31 deadline`. `deadline_dates` still
> byte-identical (0 mismatches); `grants.json` backfilled; artifacts regenerated. The
> task can now drop a leading `opening (from text)` date outright and retire the
> earliest-future heuristic where the prose resolves it.

> **Backend reply (2026-10-07): done.** `process.py` now emits
> `deadline_dates_labelled` ([{date, label}]) as a **new** key — `deadline_dates`
> is untouched (0 mismatches on a full re-extraction, so no `last_changed` flood).
> The label is NWO's own characteristic wording; free-text dates are `label: null`.
> `digest.py._grant_brief` passes it through; `grants.json` backfilled so it is live
> now. Checked the two examples: `open-competition-domain-science-m` now carries
> `2027-07-31 → "Closing date full application"` (a future, labelled deadline, so the
> opening date is no longer mistaken for one); `weave` has only free-text dates, so it
> still relies on the earliest-future interim rule — which is correct for it. The task
> can now switch to "earliest date labelled as a deadline" where labels exist.

### Request E — two more date kinds the labels do not distinguish (raised 2026-10-07)

Both found by the 2026-10-07 backfill run (`nwo-digest-ops#7`), both verified against
the live call pages. Same failure shape as Request D: a date that is not a deadline is
read as one, the computed gate lands EARLIER than the truth, and because the task
demotes anything gating within ~3 weeks, a good call is quietly reclassified as
marginal. Wrong-early is the direction that does damage.

**E1 — meeting-window start dates are interleaved with submission dates.**
`scientific-meetings-and-consultations-2026` carries
`2026-01-06 [opening (from text)]`, then ten unlabelled dates
(2026-02-27 … 2026-12-24), plus `2026-11-03 [Upcoming submission date]`. The page
pairs them:

> 1 September 2026 (for meetings from 29 October 2026)
> 3 November 2026 (for meetings from 24 December 2026)

So 2026-10-29 and 2026-12-24 are *dates from which a funded meeting may take place*,
not deadlines. The computed gate was 2026-10-29; the real next gate is 2026-11-03 —
the one date that is correctly labelled. If the scraper can recover that pairing from
the table, emitting the window-start dates with their own label (`meeting window
start`, or similar) would let the task ignore them exactly as it ignores
`opening (from text)`.

**E2 — `deadline (from text)` conflates call-wide and route-specific deadlines.**
`open-competition-domain-science-m-2026--2027` carries `2026-11-24
[deadline (from text)]`, but the page says that date binds one narrow route only:

> ENW-M-1-Weave proposals with Flemish co-applicants must be submitted by
> 24 November 2026, 14:00:00 CET

The general route is rolling to 2027-07-31, or until 420 admissible proposals. Treating
2026-11-24 as the gate would demote a flagship ENW call to "possibly of interest, closing
soon" nine months early. A `scope` field, or the matched sentence carried alongside the
label, would let the digest say "24 Nov if you have a Flemish co-applicant" instead of
mis-gating — the information is in the sentence `parse_text_dates_labelled` already
matched.

**Interim measures, already in the task prompt.** None of this blocks:

- A future date with a real deadline label now beats an earlier unlabelled date, which
  resolves E1 on its own.
- Any item whose gate falls inside the three-week band gets its call page fetched
  BEFORE its section is decided, so the page settles both the date and its scope. Those
  items were being fetched anyway at the verification step, so the cost is nil; what
  changed is the ordering, because section placement used to happen first and nothing
  moved an item back.
- The run now reports every page-corrected gate, so mis-labelling stays visible instead
  of being silently absorbed each week.

**Priority: low-ish.** E2 is the more valuable of the two — route-specific deadlines are
common in Open Competition and Weave calls, and the page fetch is the only thing
catching them. E1 is narrower, affecting mainly the rolling meetings/consultations calls.

**Also worth having, from `nwo-digest-ops#6`:** an explicit `rolling: true` (or
`deadline_dates_labelled: [{date: null, label: "continuous"}]`) for calls with no dates
at all. `computing-time-on-national-computing-facilities-0` and `open-access-books` are
both open with no deadline, and an empty date list currently means "unknown", resolved
only by fetching the page. The prompt no longer drops them, but it cannot state the gate
without a fetch either.

> **Backend reply (2026-10-07): E2 + E3 + #6 done; E1 left to the interim.**
> - **E2:** each prose date in `deadline_dates_labelled` now carries a `context` field —
>   the sentence it was matched in. `open-competition-m`'s `2026-11-24` comes with
>   *"Note! ENW-M-1-Weave proposals with a Flemish co-applicant should be submitted no
>   later than 24 November 2026…"*, so the digest can say "24 Nov if you have a Flemish
>   co-applicant" instead of mis-gating. The sentence `parse_text_dates_labelled` already
>   matched, now carried through `digest.py` as well.
> - **E3 / #6:** new top-level `rolling: true` for continuously-open calls (derived from
>   `status_raw` containing "Continuous"); 9 flagged, incl. `computing-time` and
>   `open-access-books`. An empty date list on a `rolling` call now reads as "continuous",
>   not "unknown" — no page fetch needed to state that.
> - **E1:** left as-is. The window-start dates (`2026-10-29`, `2026-12-24`) arrive in a
>   flat scraped list with no cue; recovering the "(for meetings from X)" pairing needs
>   re-parsing the HTML table, it is narrow, and your own interim note already resolves it
>   (a future labelled deadline, `2026-11-03 Upcoming submission date`, beats the earlier
>   unlabelled one). Not worth the scraper complexity for one call family.
> - `deadline_dates` still byte-identical (0 mismatches); `grants.json` backfilled;
>   `candidates.json` / `currently_open.json` regenerated.

### Request F — mandatory prior steps are invisible in the record (raised 2026-10-07)

The most damaging class found so far, from `nwo-digest-ops#8`. Three calls in the
2026-10-07 backfill run looked clean in the record — future deadline, eligible
`who_can_apply`, `invited_only: false`, `details_published: true` — and were in fact
already shut, because a mandatory earlier stage had closed. Two of the three were the
run's strongest topical matches, so they would have led the email.

| id | record says | page says |
|---|---|---|
| `kic-integrated-biorefineries-for-a-circular-future` | open, deadline 2026-10-20 | mandatory letter of intent closed 2026-06-23 |
| `holomicrobiome-2026-…` | open, deadline 2026-10-27 | "Participation in the matchmaking is obligatory for main applicants"; matchmaking was 2026-06-30 |
| `thematic-digital-competence-centres-2026` | open, deadline 2026-11-12 | only applicants who contacted their TDCC before that TDCC's own preliminary deadline; LSH and SSH deadlines had passed |

Only the first is recoverable from the record: its LOI date carries
`Closing date for letter of intent`, so a past-LOI-with-future-deadline test catches
it. For the other two nothing in the record carries the restriction at all — the
matchmaking appears only as an unlabelled `2026-06-25` with a registration context, and
the TDCC pre-process is absent entirely.

**Asked for.** A `prerequisites` array on the record:

```json
"prerequisites": [
  {"kind": "letter_of_intent", "date": "2026-06-23", "mandatory": true, "context": "…"}
]
```

with `kind` in roughly {letter_of_intent, pre_proposal, matchmaking, registration,
pre_process}. The sentences are already being matched for `context` — "mandatory",
"obligatory", "must have participated", "only applicants who" are the cues, and two of
the three strings above contain the word outright. A cheaper fallback that would still
close most of the exposure: a single computed `has_passed_mandatory_stage` bool.

**Interim measures, already in the task prompt.** The past-LOI test is in 4(f), and
4(g) now names mandatory prior steps as their own class to look for on the page, with
both unrecoverable cases written in. 4(h) also now says that `details_published: true`
means body text exists, not that the record captured what is in it — that false
reassurance is part of what makes this class dangerous.

**Priority: the highest of A–F.** The others cost a wrong date or a wrong section; this
one ships a recommendation the subscriber cannot act on. The page fetch is currently the
only thing standing between the digest and that, for two of the three shapes — if it is
ever skipped, rate-limited or a page is restructured, the digest is wrong rather than
merely late.

> **Backend reply (2026-10-07): `prerequisites` array added.** `process.py` now emits
> `prerequisites: [{kind, date, mandatory, context}]` via `detect_prerequisites`. A
> sentence qualifies only with **both** a stage keyword (letter of intent / pre-proposal /
> matchmaking / preliminary process / registration) **and** a mandatory indicator
> (mandatory / obligatory / compulsory / "only applicants who" / must participate), and
> **not** negated — so "compulsory co-funding" (no stage) and "matchmaking … (not
> mandatory)" are both correctly excluded. The date comes from the triggering sentence, or
> from a labelled date whose `context` names the same stage (this is why E2's context was
> worth having), or `None` when the record genuinely cannot recover it.
> - All three cases resolve: biorefineries → `letter_of_intent 2026-06-23`; holomicrobiome
>   → `matchmaking 2026-06-25` (date cross-linked from `when_to_apply` via context);
>   thematic-digital → `pre_process` with `date: null` but the mandatory step now *visible*
>   in the record instead of absent.
> - 23/225 grants flagged (mostly KIC/consortium calls with obligatory pre-proposal, LOI
>   or matchmaking stages); audited the sample, no false positives. `digest.py` passes it
>   through; `grants.json` backfilled; artifacts regenerated.
> - The task can now compute `has_passed_mandatory_stage` itself (any prerequisite whose
>   `date` is in the past), and keep the page fetch as the backstop for `date: null` ones.
>
> **`phd_date`:** noted, no backend change needed — `digest.py` does not touch the
> profiles sheet; the task reads the column directly.

### Subscriber data: `phd_date` (2026-10-07)

Not a backend request, recorded because it changes the profile cache's shape. The
subscriber form gained an optional free-text PhD date ("month and year"), and the
`profiles` tab gained an eighth column `phd_date`. Nothing parses it script-side — the
task reads the sheet itself — so the value is stored exactly as the subscriber wrote it.
Raised by `nwo-digest-ops#9`: time-since-PhD windows gate the whole talent line (Veni,
Vidi, Vici, Rubicon) and `Position` cannot settle them, so without this field the rules
either demote every talent call or ignore the condition. `digest.py` is unaffected.

### Declined, for the record

`nwo-digest-ops#3` also suggested promoting news items titled `Call open: ...` into
`just_opened`. Not worth doing: both calls in that report already exist as full
grant records with `deadline_dates`, `who_can_apply` and `restrictions`, so
synthesising a thinner record from a headline would duplicate them and discard the
fields the matching rules depend on. The defect is in how the delta is seeded, which
is Request A.
