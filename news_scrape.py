#!/usr/bin/env python3
"""
NWO News Scraper — builds a diffable feed of recent NWO news items.

Unlike the calls scraper, this does NOT pre-filter by topic: relevance is left
to each subscriber's own Claude routine, which reads the feed and matches it
against their free-text interests. We only flag pre-announcements (a cheap,
high-value marker) and stamp first_seen so "what's new this week" is a trivial
date filter for any consumer.

Output: news.json — a rolling archive of items from the last KEEP_DAYS days.

Usage:
    python3 news_scrape.py
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE        = "https://www.nwo.nl"
NEWS_URL    = f"{BASE}/en/news"
OUTPUT      = "news.json"
MAX_PAGES   = 8    # recent window only (feed has ~80 pages of history)
WINDOW_DAYS = 30   # stop paginating once items are older than this
KEEP_DAYS   = 120  # retain this much history in news.json

FIRST_SEEN_BASELINE = "2020-01-01"


def make_session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    return s


def fetch(session, url, *, retries=4, backoff=5):
    """GET with retry + backoff for transient NWO 5xx errors."""
    import time
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=30)
            if r.status_code >= 500 and attempt < retries:
                raise requests.HTTPError(f"{r.status_code} server error")
            r.raise_for_status()
            return r
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout):
            if attempt == retries:
                raise
            time.sleep(backoff * attempt)


def scrape_recent(session):
    """Return recent news items (within WINDOW_DAYS) as a list of dicts."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    items, stop = [], False
    for page in range(MAX_PAGES):
        r = fetch(session, f"{NEWS_URL}?page={page}")
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("li.list-item div.card")
        if not cards:
            break
        for c in cards:
            a     = c.select_one("h3.card__title a")
            t     = c.select_one("time.datetime")
            intro = c.select_one(".card__intro p")
            if not a or not t:
                continue
            iso = t.get("datetime", "")
            try:
                dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt < cutoff:
                stop = True
                continue
            href = a["href"]
            items.append({
                "id":      href.rsplit("/", 1)[-1],
                "title":   a.get_text(strip=True),
                "date":    iso[:10],
                "url":     BASE + href,
                "summary": intro.get_text(strip=True) if intro else "",
                "is_pre_announcement": href.startswith("/en/news/pre-announcement-"),
            })
        if stop:
            break
    return items


def load_previous():
    try:
        with open(OUTPUT, encoding="utf-8") as f:
            return {n["id"]: n for n in json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prev  = load_previous()
    # Cold-start (no archive yet) or migration (archive without first_seen):
    # baseline everything so the first run doesn't flag the whole window as new.
    migrating = not any("first_seen" in n for n in prev.values())

    scraped = scrape_recent(make_session())

    # Merge scraped items with the existing archive, stamping first_seen.
    merged = dict(prev)  # id -> item
    new_count = 0
    for item in scraped:
        old = prev.get(item["id"])
        if old is None:
            item["first_seen"] = FIRST_SEEN_BASELINE if migrating else today
            if not migrating:
                new_count += 1
        else:
            item["first_seen"] = old.get("first_seen", FIRST_SEEN_BASELINE)
        merged[item["id"]] = item

    # Drop items older than KEEP_DAYS to bound the file size.
    keep_cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    feed = [n for n in merged.values() if n.get("date", "") >= keep_cutoff]
    feed.sort(key=lambda n: n["date"], reverse=True)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)

    pre = sum(1 for n in feed if n["is_pre_announcement"])
    print(f"Done. {len(feed)} news items → {OUTPUT}")
    print(f"  New this run     : {new_count}")
    print(f"  Pre-announcements: {pre}")
    if migrating:
        print("  (migration run: existing items baselined, none flagged new)")


if __name__ == "__main__":
    main()
