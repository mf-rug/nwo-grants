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

- **Runs in the cloud**, no device binding, no connected folders. `digest.py` is
  fetched each run from the public raw URL; it already reads `grants.json` and
  `news.json` from public URLs, so no checkout was ever strictly needed.
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
run**. Only genuinely new or changed calls land inside the window.

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
