# Weekly NWO digest — local scheduled task

A personalized weekly email of *new* NWO grant opportunities and pre-announcements,
matched to your interests by your own Claude. Runs as a **local** scheduled task
(Claude Desktop → "require this computer"), so the LLM matching is free (your
subscription) and the Postmark secret never leaves your machine.

## One-time setup

1. **Local checkout** of this repo (e.g. `~/Documents/work/nwo`), kept up to date.
2. **Environment** — set these where the scheduled task runs (shell profile or a
   file the task sources):
   ```
   export POSTMARK_TOKEN=...      # a dedicated, send-only Postmark server token
   export POSTMARK_FROM="NWO Digest <you@your-verified-domain>"
   ```
3. **Google-Drive connector** connected (the task reads the subscriber Sheet through
   it). Put the real response-Sheet ID into step 3 of the prompt below.
4. **Create the task** in Claude Desktop (chat/cowork → scheduled task, or Claude
   Code → routine → local), toggle **"require this computer"**, set it **weekly** for a
   weekday morning when your machine is on (the data refresh lands Monday ~07:00 UTC;
   weekly matches the data cadence — daily would be empty most days), and paste the
   prompt below.

## Task prompt

```
Generate and send the weekly NWO grants digest. Work in the local repo checkout
(default ~/Documents/work/nwo).

1. git -C ~/Documents/work/nwo pull --quiet
2. Run: python3 ~/Documents/work/nwo/digest.py candidates --days 7
   (add --backfill ONLY on the very first send, to include currently-open grants
   as a one-time catch-up.)
3. Read subscribers from the Google Sheet (ID <SHEET_ID>) via the Google-Drive
   connector (read_file_content). Columns include: Email Address, Name,
   Research interests, Position, Consent, Infer from web, Website. Use ONLY rows
   where Consent is ticked.
   Resolve each subscriber's interest profile:
     - Start from their written "Research interests" (may be blank).
     - If the auto-infer checkbox is ticked, ALSO look the person up — WebSearch
       their name + institution (infer institution from their email domain) and, if a
       website is given, WebFetch it — synthesize additional interests (topics,
       methods, keywords) and MERGE them with the written ones. Cache the result in
       ~/.nwo-digest-profiles.json (email -> {profile, inferred_on}) and reuse it, so
       inference runs at most once per person.
     - If the resulting profile is still empty, skip the subscriber.
4. For each subscriber, select ONLY candidate items genuinely relevant to their
   interests. Keep it short. Prioritize pre-announcements and newly-appeared grants
   (long runway); skip items closing within ~3 weeks (too late to start). If nothing
   matches, the body is simply "Nothing new in your areas this week."
5. Compose a concise HTML email: 1-line intro, then grouped sections where present —
   📣 Pre-announcements, 🆕 New grants, 📰 News — each item: title (linked), deadline
   or date, one sentence on why it fits. Write the HTML to a temp file.
6. Send: python3 ~/Documents/work/nwo/digest.py send \
        --to <email> --subject "NWO digest — week of <YYYY-MM-DD>" --html-file <tmp>
7. Report what you sent to whom (or that a digest was empty and skipped).
```

## Subscriptions

Colleagues subscribe via a Google Form (name, email, research interests, position,
consent — plus an optional "infer my interests from the web" checkbox and a website
field) whose responses land in the Sheet the task reads. If they opt for inference,
the task looks them up once and caches a profile locally (~/.nwo-digest-profiles.json). Unsubscribe = reply to the digest, and
you clear or flag their row. Keep the Form restricted to your Workspace so the list
stays internal and the Sheet private.
