#!/usr/bin/env python3
"""
NWO Grants Scraper — saves raw HTML only, zero parsing.

One HTML file per grant saved to ./html/<grant-id>.html
A manifest (html/manifest.json) tracks url <-> id mapping.

Run once, or re-run to pick up new grants added since last time.
All processing/extraction is done separately in process.py.

Usage:
    python3 scraper.py              # fetch new grants only (skip existing html files)
    python3 scraper.py --refresh    # re-fetch everything
    python3 scraper.py --limit 5    # test with first N grants
"""

import json
import re
import time
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE      = "https://www.nwo.nl"
CALLS_URL = f"{BASE}/en/calls"
HTML_DIR  = Path("html")
MANIFEST  = HTML_DIR / "manifest.json"
DELAY     = 1.0

SKIP_SLUGS = {"nwo-talent-programme"}  # umbrella/overview pages, not actual calls

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("scraper.log", encoding="utf-8")],
)
log = logging.getLogger(__name__)


def make_session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    return s


def get_grant_urls(session):
    """Paginate through /en/calls and return all individual grant URLs."""
    urls = {}  # slug -> full url
    page = 0
    while True:
        url = f"{CALLS_URL}?page={page}" if page > 0 else CALLS_URL
        log.info(f"Listing page {page}: {url}")
        r = session.get(url, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        found = 0
        for a in soup.find_all("a", href=True):
            if re.match(r"^/en/calls/[^?#/]+$", a["href"]):
                slug = a["href"].split("/en/calls/")[-1]
                if slug not in SKIP_SLUGS and slug not in urls:
                    urls[slug] = BASE + a["href"]
                    found += 1

        log.info(f"  +{found} new (total: {len(urls)})")

        has_next = bool(
            soup.find("a", rel="next")
            or soup.find("li", class_="pager__item--next")
        )
        if not has_next or found == 0:
            break
        page += 1
        if page > 40:
            break
        time.sleep(DELAY)

    return urls


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Re-fetch all pages even if already saved")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    HTML_DIR.mkdir(exist_ok=True)
    session = make_session()

    # Load existing manifest
    manifest = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text())
        log.info(f"Manifest: {len(manifest)} grants already fetched")

    # Discover all grant URLs from listing pages
    all_grants = get_grant_urls(session)
    log.info(f"Discovered {len(all_grants)} grant URLs total")

    if args.limit:
        all_grants = dict(list(all_grants.items())[:args.limit])

    success = 0
    failed = []

    for i, (slug, url) in enumerate(all_grants.items(), 1):
        html_path = HTML_DIR / f"{slug}.html"

        if html_path.exists() and not args.refresh:
            log.info(f"[{i}/{len(all_grants)}] Already have: {slug}")
            # Make sure it's in the manifest
            manifest[slug] = url
            continue

        log.info(f"[{i}/{len(all_grants)}] Fetching: {url}")
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            html_path.write_text(r.text, encoding="utf-8")
            manifest[slug] = url
            success += 1
            log.info(f"  ✓ saved {html_path} ({len(r.text)//1024}KB)")
        except Exception as e:
            log.error(f"  ✗ {url}: {e}")
            failed.append(url)

        time.sleep(DELAY)

    # Always write updated manifest
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    log.info(f"\nDone. Fetched: {success}, Failed: {len(failed)}, Total in manifest: {len(manifest)}")
    if failed:
        log.warning(f"Failed: {failed}")


if __name__ == "__main__":
    main()
