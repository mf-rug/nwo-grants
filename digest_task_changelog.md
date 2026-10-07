# Digest task — change log for the backend agent

Context for whoever maintains the scraper/backend: this file records changes made
from the **Cowork side** on 2026-10-06, and — more importantly — documents the part
of the system that lives in the **scheduled-task harness**, which you cannot read
from this repo. Code-level detail is omitted on purpose; read `digest.py` for that.

---

## 1. What is invisible to you (the harness)

The weekly digest is a Cowork **scheduled task** bound to Max's MacBook. Its
configuration is stored server-side, not in this repo. The parts that matter:

- **The task's shell is NOT macOS.** It is an isolated Linux VM on the Mac that can
  only see folders explicitly attached to the task. `$HOME` is a throwaway session
  dir (`/sessions/<id>`), wiped between runs. *Rationale for everything in §2: any
  path assumption of the form `~/something` is simply wrong in that shell.*
- **Two folders are attached**, mounted at `$HOME/mnt/<name>`:
  `~/Documents/work/nwo` → `$HOME/mnt/nwo`, and
  `~/Documents/work/nwo-secrets` → `$HOME/mnt/nwo-secrets`.
  Nothing else on the Mac is reachable — not the home dir, not `/Users`.
- **Schedule:** Mondays 09:15 Europe/Amsterdam. *Chosen over 09:00 because the data
  refresh lands ~07:00 UTC, and 09:00 Amsterdam IS 07:00 UTC under summer time —
  it would race the refresh half the year.*
- **Runs unattended with auto-approval**, push notification on completion.
- **Requires the Mac to be awake.** A device-bound task has no documented catch-up
  for a missed run; if the laptop is asleep at 09:15 Monday, that week is skipped.
- **The task prompt carries the matching contract** (shortlist → eligibility →
  timing → per-item page verification → no-invented-rationale). It is kept in sync
  with `digest_task.md` §"Task prompt", which is your readable copy.

## 2. Paths corrected

- Repo accessed as `$HOME/mnt/nwo`, never `~/Documents/work/nwo`.
- Postmark token moved **out of the home dir** to
  `~/Documents/work/nwo-secrets/.nwo-digest.env`, passed to `digest.py` via
  `NWO_DIGEST_ENV`. *Rationale: `~/.nwo-digest.env` is unreachable from the sandbox.
  A separate folder rather than the repo so the token can never be git-committed.*
- Profile cache likewise moved to `$HOME/mnt/nwo-secrets/.nwo-digest-profiles.json`.
  *Rationale: it must survive between runs, and the session home does not.*

## 3. Network

- `api.postmarkapp.com` had to be added to the organisation's egress allowlist.
  *Rationale: the sandbox and the cloud container both route through an
  allow-listing proxy; sends failed with `403 Forbidden` after CONNECT. If sends
  start failing wholesale, check this first — it is not a Postmark problem.*
- `github.com` and `raw.githubusercontent.com` were already allowed, so
  `git pull` and the public `grants.json` / `news.json` URLs work unchanged.

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
- `details_published` (bool) — *true when any purpose/who_can_apply text exists.
  Currently false for 10 of 50 open calls, and for essentially all
  `in_preparation` ones, where NWO has published no body text at all.*

`_purpose_snippet()` was generalised to `_section(g, key, limit)`.

## 5. Matching contract hardened (harness-side)

Driven by a real failure: the first digest recommended **LSRI National Roadmap**
with a confident rationale, when the available record was a title, a date and a
uniformly-high discipline vector. The call is in fact restricted to consortia
already named on the Roadmap 2026 — a restriction that appears **only on the call
page**, nowhere in `grants.json`. The task now:

- checks eligibility fields against the subscriber's stated Position;
- uses the **earliest** of `deadline_dates` for the ~3-week cutoff;
- **WebFetches each shortlisted item's call page** before writing about it (≤6 per
  subscriber per week) and drops what the page contradicts;
- never writes a rationale for a `details_published: false` item — drops it, or
  labels it "details not yet published — check the call page".

### Backend follow-ups — DONE (2026-10-07)

Both items implemented backend-side:

- **`restrictions` field added.** `process.py` now emits
  `restrictions: {invited_only, note}` per grant via a high-precision
  `detect_restrictions()` (reads `who_can_apply` + `purpose` + `what_to_apply_for`;
  deliberately ignores false friends like "invited to submit"/bare "restricted to").
  Backfilled into the current `grants.json` and recomputed every run. Currently
  flags LSRI-Upgrade and PhDs in the Humanities; zero false positives across 225 calls.
- **Eligibility prose capture.** Because the detector reads the eligibility sections,
  once NWO publishes an `in_preparation` call's body the next scrape both stores it
  and flags any restriction — so the per-item WebFetch drops to a *safety net* for
  still-unpublished calls (e.g. LSRI National Roadmap), rather than the primary source.
- `digest.py._grant_brief` now passes `restrictions` through.

**Cowork side:** the task prompt should drop `restrictions.invited_only` calls unless
the subscriber is clearly among the eligible set — already reflected in
`digest_task.md` §"Task prompt" step 4 and §"Matching rules".

**Cowork side: APPLIED (2026-10-07).** The live task prompt now reads `restrictions`
and drops `invited_only` calls unless the subscriber is clearly in the set, using
`note` to identify it. Two things made explicit in the prompt, because they are easy
to get wrong:

- `invited_only: false` is **not** evidence a call is open — it only means no
  restriction phrase was found in *published* prose. It never substitutes for the
  per-call page fetch.
- The page fetch is therefore still the **primary** guard, not a formality. Verified
  against current data: all 225 calls carry `restrictions`, 2 are flagged
  (LSRI-Upgrade 2025, PhDs in the Humanities 2026) with no false positives, but both
  are `closed`, so zero of the 50 currently-open candidates are affected — and LSRI
  National Roadmap, the case that prompted all this, is still unflagged because it
  has no scraped sections for the detector to read.

Net: the detector is correct and useful going forward, but this week it changes
nothing, and the original failure mode is still only caught by the page fetch.

## 6. Operational note

A one-time `--backfill` send went out to the single consented subscriber
(m.j.l.j.furst@rug.nl) on 2026-10-06. Weekly runs do **not** pass `--backfill`.

---

## 7. Architecture change (2026-10-07): device-bound → cloud-only

**The device-bound design was broken and is gone.** `digest_task.md` has been
rewritten; §1 of this file described the old harness and is now historical. What
replaced it, and why, is below.

### The bug that forced it

Folders declared on a scheduled task are recorded but **never granted inside the
task's runs**:

- the task config reports `folders_state: FOLDERS_STATE_PRESENT` with both paths;
- the run's own session reminder *lists* the folders as connected;
- `get_device_info.connectedFolders` nevertheless returns `[]`, and `device_bash`
  has no mounts, so every file step fails.

Reproduced twice — once at 03:00 unattended, once on demand with the Mac awake on a
newer app build (2.19675.1 → 2.26454.0 overnight, so it is not an update artifact).
The device itself was reachable both times; only the folder grant was missing.

**The run still recorded `ROUTINE_RUN_STATUS_SUCCEEDED`.** Run status reflects that
the session finished, not that the task worked. Do not treat a green run as
evidence the digest went out.

### What changed

Nothing in the scraper or the data contract. The move is entirely about where the
task runs and where mutable state lives:

- **Runs in the cloud**, no device binding, no connected folders. `digest.py` is
  fetched each run from the public raw URL; it already reads `grants.json` and
  `news.json` from public URLs, so no checkout was ever strictly needed.
- **Postmark secret** → private Google Sheet (`1H0bpMMi…`), read at send time and
  passed as env vars. It no longer lives only on one laptop. The repo still holds
  no secrets.
- **Profile cache** → private Google Sheet (`1rT9GBDe…`, tab `profiles`), replacing
  `~/.nwo-digest-profiles.json`. Read *and written* in place.
- **Requires the Google Sheets connector**, not just Drive. Drive's `update_file`
  changes title and parent only, so Drive alone cannot write the cache. This was
  the one genuine blocker to going cloud-only, and adding the connector removed it.
- The sleep-dependency caveat in §1 is moot: a cloud task does not need the Mac.

### Two storage traps, both hit for real

- **Sheets coerces written values like the UI.** The CSV that seeded the cache
  turned `2026-10-06` into the number `46301` with a date format. It displayed
  correctly *and* `get_values` returned `"2026-10-06"`, so only a grid read showed
  the real `userEnteredValue`. Fixed, and the task prompt now requires an
  apostrophe prefix on dates. If you ever write to these Sheets from backend code,
  do the same.
- **Google Docs cannot hold machine-readable text.** Through the connector a Doc
  reads back markdown-escaped (`\[`, `\_`) with blank lines injected, so JSON in a
  Doc will not parse. The cache was briefly a Doc for this reason and was moved to
  a Sheet. Sheets round-trip values exactly.

### Unchanged, and still your side

The matching contract from §5 and the `restrictions` handling from §6 carry over
verbatim into the new prompt, including that `invited_only: false` is not evidence
a call is open and that the per-call page fetch remains the primary guard. The
backend follow-ups you shipped in `b0b4b20` are unaffected — `detect_restrictions()`
and the widened `_grant_brief()` are exactly what the cloud task consumes.

Nothing here asks anything of the scraper. It is recorded so you are not debugging
a device-bound task that no longer exists.
