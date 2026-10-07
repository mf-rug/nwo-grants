# Weekly NWO digest — scheduled task

A personalized weekly email of *new* NWO grant opportunities and pre-announcements,
matched to each subscriber's interests by an LLM, sent via Postmark.

**The task runs entirely in the cloud.** It needs no local checkout, no connected
folder, and nobody's laptop to be awake. An earlier device-bound design is gone;
§"Why cloud" says why.

## Storage map

Everything the task needs is reachable from a cloud run:

| What | Where |
| --- | --- |
| code | `digest.py`, fetched each run from the **public** raw URL on `main` |
| grant data | `grants.json` / `news.json`, read by `digest.py` from public raw URLs |
| subscribers | Google Sheet `15D1PibZUdL2JrpZcl08dxV9aW0Spr_4QIYLdaLSSZJI` (Form responses) |
| profile cache | Google Sheet `1rT9GBDefOBAj9hufVOm5YGvF3jvrKkwtu7fnQR6freg`, tab `profiles` |
| sent-log | the same Sheet, tab `sent` |
| Postmark secret | Google Sheet `1H0bpMMiAt8ks9s0G54zYjMBBTOhUyn5Bs8JMYnjWMJ4`, `Sheet1` A1/B1, A2/B2 |
| issue tracker | private repo `mf-rug/nwo-digest-ops` — see §"Reporting problems" |

The repo stays public and holds **no** secrets and **no** subscriber data. The two
private Sheets hold everything that must not be public, and both the profile cache
and the sent-log are read *and written* in place via the Google Sheets connector.

The local checkout at `~/Documents/work/nwo` is now only a developer convenience.
`~/Documents/work/nwo-secrets/.nwo-digest.env` is kept as a fallback and for manual
sends; the scheduled task no longer reads it.

## Why cloud (read before proposing a device-bound variant)

The task was originally bound to one Mac so the Postmark token never left it. That
does not work:

- **Folders declared on a scheduled task are never granted inside its runs.**
  The task config reports `folders_state: FOLDERS_STATE_PRESENT`, the run's own
  session reminder lists the folders, and `get_device_info.connectedFolders` still
  comes back `[]`. The device shell then has no mounts and every file step fails.
  Reproduced twice, on two app builds, with the machine awake.
- **The failed run still records `SUCCEEDED`.** Run status reflects "the session
  finished", not "the task worked", so a silently broken digest looks healthy.
- Going cloud-only also removes the requirement that the laptop be awake at 09:15
  on a Monday, which was a separate standing risk.

If the folder-grant bug is fixed upstream, moving back is still not obviously
worth it: the cloud design has fewer moving parts and no sleep dependency.

## Why this repo must stay public

Making `nwo-grants` private looks tempting and breaks three things:

- `digest.py` reads `grants.json` / `news.json` from the unauthenticated raw URL;
- `app.py` reads the same `grants.json`, the per-grant markdown under `MD_BASE`,
  and the unauthenticated commits API for its "last refreshed" date;
- a scheduled run has **no** GitHub credentials in its shell — `gh api` returns
  `403: GitHub access to this repository is not enabled for this session` — so
  there is no authenticated fetch to fall back on. Pulling a 1.8 MB `grants.json`
  through the MCP connector into context every week is not viable either.

The public raw URL is load-bearing, and it is precisely why the cloud task needs no
credentials at all. Anything that must be private goes in a Sheet or in the ops repo.

## The window and the sent-log

These two are one mechanism; changing either alone breaks it.

`digest.py candidates` selects grants whose `first_seen` or `last_changed` falls
inside `--days`. With a 7-day window and no memory of what was emailed, **a week
that fails to send loses its grants for good** — they drop out of the window and
never come back. That is not hypothetical: a send was blocked on 2026-10-07 and
only an empty candidate set saved it from costing real items.

So the task runs a **21-day window** and keeps a **sent-log**:

- the window gives a missed week three chances to be picked up;
- the log stops the overlap turning into repeats.

The `sent` tab is one row per item per recipient:
`sent_on | email | item_key | item_type | title`, keyed on **(email, item_key)**.
`item_key` is the grant's `id` (the NWO slug, exposed by `_grant_brief`) for a
grant, and the news item's `url` for a news item.

**Ordering invariant: log only after the send succeeds.** If a send fails nothing
is written, so those items stay eligible next week — which is the entire point. A
log written before the send would reintroduce the bug it exists to fix.

## Reporting problems

Task runs file issues into the **private** repo `mf-rug/nwo-digest-ops` (issues
only, no code). Separate because this repo is public and a report naturally wants
to name a subscriber; private because the subscriber list is internal.

The bar is deliberately high: **only something a person would want to change.** A
run that worked files nothing. Runs search open issues first and comment on an
existing one rather than duplicating. New issues carry the `agent-report` label.
No subscriber addresses, names or profiles; no secrets, ever.

If you maintain the scraper, it is worth watching — a matching rule that keeps
misfiring usually means the data the matcher is given is wrong or missing, which is
your end.

## Gotchas that have already bitten

- **A secret must never appear in a shell command.** The sandbox classifier refuses
  an inline `POSTMARK_TOKEN=… python3 …` as credential leakage, and refuses an
  `echo`, `printf`, `export` or heredoc carrying the value just the same, so the
  obvious fallback is blocked too. Write the env file with the **file-writing tool**,
  which is not a shell command, and put only a *path* on the command line
  (`NWO_DIGEST_ENV=/tmp/nwo.env`). The inline form was denied on 2026-10-07 and a
  whole week's send was skipped; the file-plus-path form sends normally.
- **Sheets parses written values like the UI.** Writing `2026-10-06` stores the
  number `46301` with a date format: it *displays* correctly and `get_values` even
  returns `"2026-10-06"`, so nothing looks wrong until something does arithmetic on
  it. Prefix dates, IDs and anything formula-shaped with an apostrophe on write.
  The CSV import that seeded the cache did exactly this; it has been corrected.
- **Google Docs are not a machine-readable container.** Read back through the
  connector, a Doc returns markdown-escaped text (`\[`, `\_`) with blank lines
  injected, so JSON stored in one will not parse. Sheets round-trip values exactly.
  Use a Sheet for anything a program reads.

## Matching rules (why they exist)

The scraped record is thinner than the call page. `digest.py` passes `who_can_apply`,
`can_lead`, `can_participate`, `target_groups`, `programme`, `budget`,
`deadline_dates` and `restrictions` so the matcher can judge *eligibility*, not just
topic, plus `details_published: false` for calls NWO has not written up yet.

Three failure modes this guards against:

- Recommending a call the subscriber **cannot apply to**. Restrictions often appear
  only on the call page, so every shortlisted item gets fetched and checked.
- Recommending an **invited-only / pre-selected** call. `restrictions.invited_only`
  flags the *published* cases; unpublished ones are caught by the page fetch.
  A `false` value is not evidence a call is open.
- Writing a confident rationale for a call with **no published text**, where the
  only inputs are a title and a date. Dropped or labelled, never rationalized.

## Task prompt

The live task's prompt is authoritative; this is its shape.

1. `curl` `digest.py` from the public raw URL into `/tmp`, then
   `python3 digest.py candidates --days 21` (no `--backfill`; that was the first send).
2. Read consented subscribers from the subscriber Sheet.
3. Read the profile cache; reuse an existing row, otherwise infer once (WebSearch +
   the given website), merge with the written interests, and `append_values` the new
   row — apostrophe-prefixing the date.
4. **Shortlist, then verify**: read the sent-log → topic fit → eligibility from the
   record → drop `invited_only` unless clearly eligible → skip anything closing
   within ~3 weeks (earliest date for multi-stage calls) → **WebFetch each
   survivor's call page** and drop what it contradicts → never invent a rationale
   for `details_published: false` → **drop anything already in the sent-log for that
   subscriber**. No padding; if nothing survives the body is exactly
   "Nothing new in your areas this week."
5. Compose concise HTML, inline CSS, only the non-empty sections.
6. Send, per the first gotcha above:
   a. `get_values` on the secrets Sheet for the token and sender;
   b. write `/tmp/nwo.env` with the **file-writing tool**, two `KEY=VALUE` lines;
   c. `cd /tmp && NWO_DIGEST_ENV=/tmp/nwo.env python3 digest.py send --to … --subject … --html-file …`
      — a path on the command line, never the secret.
   `401 Unauthorized` means the token in the Sheet is wrong or revoked; `403
   Forbidden` from the proxy means the allowlist. Never echo the token.
7. **After** each successful send, append one `sent` row per included item.
8. Report sends with message IDs, verification drops, how many items were suppressed
   as already-sent, skipped subscribers, and any profile newly cached.
9. File an issue in the ops repo **only** if something needs changing.

Failures are reported, never worked around. A run that cannot do its job says so in
its first line and sends nothing.

## Subscriptions

Colleagues subscribe via a Google Form (name, email, research interests, position,
consent, an optional "infer my interests from the web" checkbox and a website field)
whose responses land in the subscriber Sheet. Unsubscribe = reply to the digest, and
you clear or flag their row. Keep the Form restricted to your Workspace so the list
stays internal and the Sheet private.

## Known limits

- `--backfill` is per-mailing-list, not per-subscriber: a subscriber joining later
  gets only what the 21-day window holds, unless you run a one-off backfill for them.
- The profile cache is keyed on email. Changing a subscriber's Form answers does not
  refresh a cached profile; clear their row to force re-inference.
- The sent-log grows one row per item per recipient and is never pruned. At this
  list size that is years of headroom; if it ever matters, delete rows older than a
  few months — anything that old is outside the window anyway.
- An item whose `last_changed` moves after it was sent stays suppressed: the log
  keys on the item, not on the version. Tracked as nwo-digest-ops#1.
