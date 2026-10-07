# Weekly NWO digest — scheduled task

A personalized weekly email of *new* NWO grant opportunities and pre-announcements,
matched to each subscriber's interests by an LLM, sent via Postmark.

**The task runs entirely in the cloud and executes no code.** It needs no local
checkout, no connected folder, and nobody's laptop to be awake. Two earlier designs
are gone — see §"Why cloud" and §"Why the task executes nothing".

## Storage map

Everything the task needs is reachable from a cloud run:

| What | Where |
| --- | --- |
| candidates | `candidates.json`, fetched from the **public** raw URL on `main` — **data, not code** |
| who builds it | the weekly Action runs `digest.py candidates --days 21 --local` and commits the result |
| subscribers | Google Sheet `15D1PibZUdL2JrpZcl08dxV9aW0Spr_4QIYLdaLSSZJI` (Form responses) |
| profile cache | Google Sheet `1rT9GBDefOBAj9hufVOm5YGvF3jvrKkwtu7fnQR6freg`, tab `profiles` |
| sent-log | the same Sheet, tab `sent` |
| Postmark secret | Google Sheet `1H0bpMMiAt8ks9s0G54zYjMBBTOhUyn5Bs8JMYnjWMJ4`, `Sheet1` A1/B1, A2/B2 |
| issue tracker | private repo `mf-rug/nwo-digest-ops` — see §"Reporting problems" |

`digest.py` still owns the selection logic, but it runs **in the Action**, never in
the task. The task fetches its output.

The repo stays public and holds **no** secrets and **no** subscriber data. The two
private Sheets hold everything that must not be public; the profile cache and the
sent-log are read *and written* in place via the Google Sheets connector.

## Why the task executes nothing

The task used to `curl` `digest.py` and run it. The sandbox classifier refuses that:

```
Permission for this action was denied by the Claude Code auto mode classifier.
Reason: [Code from External]
```

The `curl` succeeded; only `python3 digest.py` was denied, and the denial covers
reaching the same outcome by another interpreter, host or later turn. Since both
halves of the task went through that script, the block was total — a whole week's
digest was skipped on 2026-10-07 (`nwo-digest-ops#2`).

The fix is not to reimplement the delta in the task prompt (duplicated logic that
drifts from `digest.py`) nor to inline the 7 KB script into it. The Action already
runs weekly with the data in hand, so it precomputes `candidates.json` and commits
it. The task fetches data and sends HTTP. Nothing is executed, and `digest.py`
remains the single source of truth.

Sending is likewise script-free: the token goes into a `curl` config file written by
the file-writing tool, and only a *path* appears on the command line.

## Why cloud (read before proposing a device-bound variant)

The task was originally bound to one Mac so the Postmark token never left it. That
does not work:

- **Folders declared on a scheduled task are never granted inside its runs.** The
  config reports `folders_state: FOLDERS_STATE_PRESENT`, the run's own session
  reminder lists the folders, and `get_device_info.connectedFolders` still returns
  `[]`. Reproduced twice, on two app builds, with the machine awake.
- **The failed run still records `SUCCEEDED`.** Run status reflects "the session
  finished", not "the task worked", so a silently broken digest looks healthy.
- Cloud-only also removes the requirement that a laptop be awake on a Monday.

## Why this repo must stay public

Making `nwo-grants` private looks tempting and breaks three things:

- the task reads `candidates.json` from the unauthenticated raw URL;
- `app.py` reads `grants.json`, the markdown under `MD_BASE`, and the
  unauthenticated commits API for its "last refreshed" date;
- a scheduled run has **no** GitHub credentials in its shell — `gh api` returns
  `403: GitHub access to this repository is not enabled for this session` — so
  there is no authenticated fetch to fall back on.

The public raw URL is load-bearing, and it is why the cloud task needs no
credentials at all. Anything private goes in a Sheet or in the ops repo.

## Schedule, and why it is not Monday morning

**Mondays 16:00 Europe/Amsterdam (14:00 UTC).**

The Action starts Monday 06:00 UTC but has been *finishing* at 11:46–13:45 UTC as
the scrape has grown. The digest previously fired at 07:15 UTC, so it would have
read the previous week's data almost every week. 16:00 Amsterdam clears every run
on record, though only by about fifteen minutes against the slowest.

If the Action slows further, move the digest later rather than hoping. The
freshness guard below turns that failure into a loud one, not a wrong digest.

**Freshness guard:** `candidates.json` carries a `generated` date. If it is more
than 8 days old the Action has not run or has failed; the task sends nothing, says
so in its first line, and files an issue.

## The window and the sent-log

These two are one mechanism; changing either alone breaks it.

The delta covers grants whose `first_seen` or `last_changed` falls inside the
window. With a 7-day window and no memory of what was emailed, **a week that fails
to send loses its grants for good**. That is not hypothetical — it is exactly what
the 2026-10-07 block would have cost had the candidate set not been empty.

So: a **21-day window** gives a missed week three chances, and the **sent-log**
stops the overlap turning into repeats.

The `sent` tab is one row per item per recipient:
`sent_on | email | item_key | item_type | title`, keyed on **(email, item_key)**.
`item_key` is the grant's `id` (the NWO slug) for a grant, the news item's `url` for
a news item.

**Ordering invariant: log only after the send succeeds.** A failed send writes
nothing, so its items stay eligible next week — the entire point. Logging first
would reintroduce the bug the log exists to fix.

## The task does not depend on the AI classifier

`fields`, `can_lead` and `can_participate` come from `classify_grants.py`. The task
treats them as **optional corroboration only**. Its authoritative eligibility
sources are `who_can_apply` (600 chars of the real prose), `target_groups`,
`restrictions`, and the live call page it fetches for every shortlisted item — all
better evidence than a classifier's summary of the same text.

The prompt states explicitly that an empty value means *not classified*, never
"nobody is eligible", so nothing is silently excluded when the classifier is off.

**Switching `classify_grants.py` off does not affect the digest.** Whether it stays
is a question about `app.py`, which does depend on it (`matches_position` and
`matches_field`), and is not the digest's call.

## Reporting problems

Task runs file issues into the **private** repo `mf-rug/nwo-digest-ops` (issues
only, no code). Separate because this repo is public and a report naturally wants
to name a subscriber; private because the subscriber list is internal.

The bar is deliberately high: **only something a person would want to change.** A
run that worked files nothing. Runs search open issues first and comment on an
existing one rather than duplicating. New issues carry the `agent-report` label. No
subscriber addresses, names or profiles; no secrets, ever.

## Gotchas that have already bitten

- **The task may not execute downloaded code.** See §"Why the task executes
  nothing". If you ever reintroduce a `curl ... && python3 ...` step, it will be
  refused and the digest will not go out.
- **A secret must never appear in a shell command.** An inline
  `POSTMARK_TOKEN=… python3 …` is refused as credential leakage, and so is any
  `echo`, `printf`, `export` or heredoc carrying the value — the obvious fallback is
  blocked too. Write a `curl` config file with the file-writing tool and pass only a
  path (`curl -K pm.conf`).
- **Sheets parses written values like the UI.** Writing `2026-10-06` stores the
  number `46301` with a date format: it *displays* correctly and `get_values` even
  returns `"2026-10-06"`, so nothing looks wrong until something does arithmetic on
  it. Apostrophe-prefix dates and anything formula-shaped. The CSV import that
  seeded the cache did exactly this; it has been corrected.
- **Google Docs are not a machine-readable container.** Through the connector a Doc
  returns markdown-escaped text (`\[`, `\_`) with blank lines injected, so JSON
  stored in one will not parse. Sheets round-trip values exactly.

## Matching rules (why they exist)

The scraped record is thinner than the call page. `candidates.json` carries
`who_can_apply`, `target_groups`, `programme`, `budget`, `deadline_dates` and
`restrictions` so the matcher can judge *eligibility*, not just topic, plus
`details_published: false` for calls NWO has not written up yet.

Three failure modes this guards against:

- Recommending a call the subscriber **cannot apply to**. Restrictions often appear
  only on the call page, so every shortlisted item gets fetched and checked.
- Recommending an **invited-only / pre-selected** call. `restrictions.invited_only`
  flags the *published* cases; unpublished ones are caught by the page fetch. A
  `false` value is not evidence a call is open.
- Writing a confident rationale for a call with **no published text**, where the
  only inputs are a title and a date. Dropped or labelled, never rationalized.

## Task prompt

The live task's prompt is authoritative; this is its shape.

1. `curl` `candidates.json` from the public raw URL. Check `generated`; abort if
   more than 8 days old.
2. Read consented subscribers from the subscriber Sheet.
3. Read the profile cache; reuse an existing row, otherwise infer once (WebSearch +
   the given website), merge, and `append_values` the new row, apostrophe-prefixing
   the date.
4. **Shortlist, then verify**: read the sent-log → topic fit → eligibility from
   `who_can_apply` / `target_groups` → drop `invited_only` unless clearly eligible →
   skip anything closing within ~3 weeks (earliest date for multi-stage calls) →
   **WebFetch each survivor's call page** and drop what it contradicts → never
   invent a rationale for `details_published: false` → **drop anything already in
   the sent-log for that subscriber**. No padding; if nothing survives the body is
   exactly "Nothing new in your areas this week."
5. Compose the HTML body, inline CSS, only the non-empty sections.
6. Send without a script: read the token and sender from the secrets Sheet, write
   `pm.conf` and one JSON payload per recipient with the file-writing tool, then
   `curl -X POST https://api.postmarkapp.com/email -K pm.conf -d @body.json`.
   HTTP 200 is success; 401 is a bad token; 403 from the proxy is the allowlist.
7. **After** each successful send, append one `sent` row per included item.
8. Report sends with message IDs, verification drops, items suppressed as
   already-sent, skipped subscribers, and any profile newly cached.
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
  gets only what the 21-day window holds, unless you run a one-off backfill.
- The profile cache is keyed on email. Changing a subscriber's Form answers does not
  refresh a cached profile; clear their row to force re-inference.
- The sent-log grows one row per item per recipient and is never pruned. Years of
  headroom at this list size; if it ever matters, delete rows older than a few
  months — anything that old is outside the window anyway.
- An item whose `last_changed` moves after it was sent stays suppressed: the log
  keys on the item, not on the version. Tracked as `nwo-digest-ops#1`.
- `candidates.json` is built at Action time, so the delta is anchored to the scrape,
  not to the send. With weekly data that loses nothing.
