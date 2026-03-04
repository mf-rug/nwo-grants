#!/usr/bin/env python3
"""
Quick script: collect all NWO grant names + URLs from the listing pages.
Run: python list_grants.py
Output: grants_list.json
"""

import json
import re
import time
import requests
from bs4 import BeautifulSoup

BASE = "https://www.nwo.nl"
CALLS_URL = f"{BASE}/en/calls"
DELAY = 1.0

session = requests.Session()
session.headers["User-Agent"] = "Mozilla/5.0"

grants = {}  # url -> title, deduplicated
page = 0

while True:
    url = f"{CALLS_URL}?page={page}" if page > 0 else CALLS_URL
    print(f"Page {page}: {url}")

    r = session.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    found = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.match(r"^/en/calls/[^?#/]+$", href):
            full_url = BASE + href
            title = a.get_text(strip=True)
            if full_url not in grants and title:
                grants[full_url] = title
                found += 1

    print(f"  +{found} new (total: {len(grants)})")

    # Stop if no next-page link
    has_next = bool(
        soup.find("a", rel="next")
        or soup.find("li", class_="pager__item--next")
    )
    if not has_next or found == 0:
        print("No more pages.")
        break

    page += 1
    if page > 40:
        print("Safety limit hit.")
        break

    time.sleep(DELAY)

# Save
result = [{"url": url, "title": title} for url, title in sorted(grants.items())]
with open("grants_list.json", "w") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

print(f"\nDone. {len(result)} grants saved to grants_list.json")
