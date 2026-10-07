#!/usr/bin/env python3
"""
Weekly digest helper for the NWO grants newsletter.

Does the deterministic parts only — the LLM (a scheduled Claude task, running in
the cloud) handles interest-matching and composing. Two subcommands:

    python3 digest.py candidates [--days 7] [--backfill]
        Print the delta over the window (new grants, just-opened, recent news /
        pre-announcements) as JSON for the task to match against.

    python3 digest.py send --to a@b.c --subject "..." --html-file body.html
        Send one email via Postmark. Reads the server token from POSTMARK_TOKEN
        and the sender from POSTMARK_FROM, either as env vars or from the
        KEY=VALUE file named by $NWO_DIGEST_ENV. Secrets never live in code,
        prompts, or this repo.

Data is read from the public raw URLs by default (works anywhere); pass
--local to use the checked-out grants.json / news.json instead.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

GRANTS_URL = "https://raw.githubusercontent.com/mf-rug/nwo-grants/main/grants.json"
NEWS_URL   = "https://raw.githubusercontent.com/mf-rug/nwo-grants/main/news.json"


def _load(url, local_path, use_local):
    if use_local:
        with open(local_path, encoding="utf-8") as f:
            return json.load(f)
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()


def _within(date_str, cutoff):
    return bool(date_str) and date_str >= cutoff


def _section(g, key, limit):
    """Trimmed text of one scraped section, or '' when NWO has not published it."""
    sec = g.get("sections", {}).get(key) or {}
    txt = (sec.get("text", "") if isinstance(sec, dict) else "").strip()
    return (txt[:limit] + "…") if len(txt) > limit else txt


def _grant_brief(g):
    purpose = _section(g, "purpose", 240)
    who = _section(g, "who_can_apply", 600)
    return {
        # Stable key for the sent-log; the slug NWO uses in the call URL.
        "id": g.get("id", ""),
        "title": g.get("title", ""),
        "url": g.get("url", ""),
        "status": g.get("status", ""),
        "deadline": (g.get("deadline_iso") or "")[:10],
        # Multi-stage calls carry several dates (e.g. letter of intent, then full).
        "deadline_dates": [d[:10] for d in (g.get("deadline_dates") or []) if d],
        # Each date with NWO's own label / inferred class, plus the sentence a
        # prose date sat in — so the matcher can tell an opening date from a real
        # deadline (§11 D) and a route-specific deadline from a call-wide one (§11 E2).
        "deadline_dates_labelled": [
            {"date": (e.get("date") or "")[:10], "label": e.get("label"),
             "context": e.get("context", "")}
            for e in (g.get("deadline_dates_labelled") or []) if e.get("date")
        ],
        # True for continuously-open calls with no deadline (§11 E3).
        "rolling": bool(g.get("rolling", False)),
        "finance_type": g.get("finance_type", ""),
        "programme": g.get("programme", ""),
        "budget": g.get("budget", ""),
        # Eligibility comes from the scraped who_can_apply / target_groups text,
        # which the matcher reads directly — no AI classification involved.
        "target_groups": g.get("target_groups", ""),
        "purpose": purpose,
        "who_can_apply": who,
        # False when the call page has no body text yet (common for
        # in_preparation calls). The matcher must NOT invent a rationale for
        # these - fetch the live page or label them as unverified.
        "details_published": bool(purpose or who),
        # {invited_only, note}: true only for calls limited to a pre-selected /
        # invited / prior-awardee set. When true, exclude unless the subscriber is
        # clearly among the eligible; when the record is thin, the page fetch decides.
        "restrictions": g.get("restrictions") or {"invited_only": False, "note": ""},
        "first_seen": g.get("first_seen", ""),
    }


def candidates(days, backfill, use_local):
    grants = _load(GRANTS_URL, "grants.json", use_local)
    news   = _load(NEWS_URL, "news.json", use_local)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    active = ("open", "upcoming", "in_preparation")

    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "window_days": days,
        # Pre-filter totals (§11 Request B), so an empty section (nothing matched)
        # is distinguishable from a failed scrape (a zero total).
        "source_counts": {"grants_total": len(grants), "news_total": len(news)},
        # Grants whose call page first appeared in the window → real runway.
        "new_grants": [_grant_brief(g) for g in grants
                       if _within(g.get("first_seen", ""), cutoff)],
        # Grants that meaningfully changed and are now actionable.
        "just_opened": [_grant_brief(g) for g in grants
                        if _within(g.get("last_changed", ""), cutoff)
                        and g.get("status") in ("open", "upcoming")
                        and not _within(g.get("first_seen", ""), cutoff)],
        # News published in the window; pre-announcements flagged for priority.
        "recent_news": [{"title": n["title"], "url": n["url"], "date": n["date"],
                         "summary": n.get("summary", ""),
                         "pre_announcement": n.get("is_pre_announcement", False)}
                        for n in news if _within(n.get("date", ""), cutoff)],
    }
    if backfill:
        # One-time catch-up for a subscriber's first digest: what's open now.
        seen = {g["title"] for g in out["new_grants"]}
        out["currently_open"] = [_grant_brief(g) for g in grants
                                 if g.get("status") in active and g.get("title") not in seen]
    return out


def _secret(name):
    """Env var, falling back to a local KEY=VALUE file (GUI-launched tasks
    often don't inherit shell env). Path: $NWO_DIGEST_ENV or ~/.nwo-digest.env."""
    if os.environ.get(name):
        return os.environ[name]
    path = os.path.expanduser(os.environ.get("NWO_DIGEST_ENV", "~/.nwo-digest.env"))
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


def send(to, subject, html):
    token = _secret("POSTMARK_TOKEN")
    sender = _secret("POSTMARK_FROM")
    if not token or not sender:
        print("Set POSTMARK_TOKEN and POSTMARK_FROM (env, or ~/.nwo-digest.env).", file=sys.stderr)
        sys.exit(1)
    r = requests.post(
        "https://api.postmarkapp.com/email",
        headers={"X-Postmark-Server-Token": token, "Accept": "application/json",
                 "Content-Type": "application/json"},
        json={"From": sender, "To": to, "Subject": subject,
              "HtmlBody": html, "MessageStream": "broadcast"},
        timeout=20,
    )
    r.raise_for_status()
    print(f"sent to {to}: {r.json().get('MessageID', '?')}")


def main():
    p = argparse.ArgumentParser(description="NWO digest helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("candidates", help="print this week's delta as JSON")
    c.add_argument("--days", type=int, default=7)
    c.add_argument("--backfill", action="store_true", help="also include currently-open grants")
    c.add_argument("--local", action="store_true", help="read local json instead of public URLs")

    s = sub.add_parser("send", help="send one email via Postmark")
    s.add_argument("--to", required=True)
    s.add_argument("--subject", required=True)
    s.add_argument("--html-file", required=True)

    args = p.parse_args()
    if args.cmd == "candidates":
        print(json.dumps(candidates(args.days, args.backfill, args.local),
                         indent=2, ensure_ascii=False))
    elif args.cmd == "send":
        with open(args.html_file, encoding="utf-8") as f:
            send(args.to, args.subject, f.read())


if __name__ == "__main__":
    main()
