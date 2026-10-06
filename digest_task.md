# Weekly NWO digest — scheduled task

A personalized weekly email of *new* NWO grant opportunities and pre-announcements,
matched to each subscriber's interests. Runs as a scheduled task bound to one Mac
("require this computer"), so the matching uses your subscription and the Postmark
secret never leaves your machine.

## How the sandbox changes the paths

The task's shell is **not** macOS directly — it is an isolated Linux VM on your Mac
that can only see the folders connected to the task. So `~/Documents/...`,
`~/.nwo-digest.env` and `~/.nwo-digest-profiles.json` do **not** resolve there.
Two folders are connected, and everything is addressed through them:

| What | Path inside the task shell | Path on the Mac |
| --- | --- | --- |
| repo checkout | `$HOME/mnt/nwo` | `~/Documents/work/nwo` |
| Postmark token | `$HOME/mnt/nwo-secrets/.nwo-digest.env` | `~/Documents/work/nwo-secrets/.nwo-digest.env` |
| profile cache | `$HOME/mnt/nwo-secrets/.nwo-digest-profiles.json` | same folder |

The token lives in its own folder rather than in the repo so it can never be
committed by accident. `digest.py` finds it because the send command sets
`NWO_DIGEST_ENV`.

## One-time setup

1. **Local checkout** of this repo at `~/Documents/work/nwo`.
2. **Secrets folder** `~/Documents/work/nwo-secrets` containing `.nwo-digest.env`:
   ```
   POSTMARK_TOKEN=...      # a dedicated, send-only Postmark server token
   POSTMARK_FROM="NWO Digest <you@your-verified-domain>"
   ```
3. **Network allowlist** — `api.postmarkapp.com` must be allowed for the
   organisation (Admin settings → Capabilities). Without it every send fails with
   `403 Forbidden` from the proxy, in the sandbox and in the cloud alike.
4. **Google-Drive connector** connected; the task reads the subscriber Sheet
   through it.
5. **Create the task**, toggle **"require this computer"**, attach both folders
   above, set it weekly for a time your machine is awake, and paste the prompt
   below. Note the data refresh lands Monday ~07:00 UTC — 09:15 Amsterdam clears it
   year-round, whereas a plain 09:00 collides with it during summer time.

## Matching rules (why they exist)

The scraped record is thinner than the call page. `digest.py` now passes
`who_can_apply`, `can_lead`, `can_participate`, `target_groups`, `programme`,
`budget` and `deadline_dates` so the matcher can judge *eligibility*, not just
topic. It also sets `details_published: false` for calls NWO has not written up
yet — about one in five open calls, and almost all `in_preparation` ones.

Two failure modes this guards against:

- Recommending a call the subscriber **cannot apply to**. Restrictions often appear
  only on the call page (e.g. LSRI National Roadmap is open to consortia already
  named on the Roadmap), so shortlisted items get fetched and checked.
- Writing a confident rationale for a call with **no published text**, where the
  only inputs are a title and a date. Those are dropped or labelled, never
  rationalized.

## Task prompt

See the live task's prompt — kept in sync with this file. Its shape:

1. `cd $HOME/mnt/nwo && git pull --quiet`
2. `python3 $HOME/mnt/nwo/digest.py candidates --days 7` (add `--backfill` only for
   a subscriber's very first send, as a one-time catch-up of currently-open calls)
3. Read subscribers from the Google Sheet via the Drive connector; use only rows
   where Consent is ticked. Resolve each profile from the written interests, plus a
   one-time web lookup if they ticked the auto-infer box, cached in
   `$HOME/mnt/nwo-secrets/.nwo-digest-profiles.json` so inference runs once per person.
4. **Shortlist, then verify**: topic fit → eligibility from the record → skip
   anything closing within ~3 weeks (earliest date for multi-stage calls) →
   WebFetch each survivor's call page and drop what it contradicts →
   never invent a rationale for `details_published: false` items. No padding; if
   nothing survives, the body is exactly "Nothing new in your areas this week."
5. Compose concise HTML — one-line intro, then only the non-empty sections
   (Pre-announcements, New grants, News), inline CSS, no external assets.
6. `NWO_DIGEST_ENV=$HOME/mnt/nwo-secrets/.nwo-digest.env python3 digest.py send \
      --to <email> --subject "NWO digest — week of <YYYY-MM-DD>" --html-file <tmp>`
7. Report sends, drops at the verification step, and skipped subscribers.

## Subscriptions

Colleagues subscribe via a Google Form (name, email, research interests, position,
consent — plus an optional "infer my interests from the web" checkbox and a website
field) whose responses land in the Sheet the task reads. Unsubscribe = reply to the
digest, and you clear or flag their row. Keep the Form restricted to your Workspace
so the list stays internal and the Sheet private.

## Known limits

- **The Mac must be awake.** A task bound to a computer cannot run while that
  computer is asleep or offline, and there is no documented catch-up for a missed
  run. Schedule a wake in System Settings → Battery → Schedule, or expect the
  occasional skipped week.
- `--backfill` is per-mailing-list, not per-subscriber: a new subscriber joining
  later gets only that week's delta unless you run a one-off backfill for them.
