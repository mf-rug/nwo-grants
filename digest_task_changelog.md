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

### Possible backend follow-ups

Not done, your call:
- Scrape and store the eligibility/restriction prose for `in_preparation` calls once
  NWO publishes it, so the per-item WebFetch becomes a safety net rather than the
  primary source.
- Consider a `restrictions` or `invited_only` field — the Roadmap-consortia case is
  a category the current schema cannot express.

## 6. Operational note

A one-time `--backfill` send went out to the single consented subscriber
(m.j.l.j.furst@rug.nl) on 2026-10-06. Weekly runs do **not** pass `--backfill`.
