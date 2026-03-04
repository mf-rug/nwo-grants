#!/usr/bin/env python3
"""
NWO Grants Processor — reads raw HTML from ./html/, extracts everything, writes grants.json.

Run as many times as you like. Adjust extraction logic here; never need to re-scrape.

Usage:
    python3 process.py
"""

import json
import re
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

HTML_DIR = Path("html")
MANIFEST = HTML_DIR / "manifest.json"
OUTPUT   = "grants.json"


# ---------------------------------------------------------------------------
# Characteristics sidebar
# ---------------------------------------------------------------------------

def parse_characteristics(soup):
    """
    <div class="sidebar--content">
      <div class="mb-4">
        <h6 class="strong">Label</h6>
        value  (sometimes <time datetime="ISO">, sometimes plain text, sometimes <a> links)
      </div>
    """
    result = {}
    sidebar = soup.find("div", class_="sidebar--content")
    if not sidebar:
        return result

    for block in sidebar.find_all("div", class_="mb-4"):
        label_tag = block.find("h6", class_="strong")
        if not label_tag:
            continue
        label = label_tag.get_text(strip=True)

        times = block.find_all("time")
        if times:
            iso_dates = [t.get("datetime", "") for t in times if t.get("datetime")]
            display   = " / ".join(t.get_text(strip=True) for t in times)
            result[label] = {"display": display, "iso": iso_dates}
        else:
            full_text = block.get_text(separator=" ", strip=True)
            value = full_text[len(label):].strip()
            result[label] = value

    return result


# ---------------------------------------------------------------------------
# Accordion sections
# ---------------------------------------------------------------------------


# Normalise variant/typo slugs to canonical names
SLUG_ALIASES = {
    # write_proposal variants
    "write_proposals":            "write_proposal",
    "write_proprosal":            "write_proposal",
    "voorstel_schrijven":         "write_proposal",
    # what_to_apply_for variants
    "what_to_apply":              "what_to_apply_for",
    "what_can_be_applied_for":    "what_to_apply_for",
    # fill_in_forms variants
    "fill_in_foms":               "fill_in_forms",
    # consortium variants
    "consortium_formation":                      "consortium_building",
    "mandatory_consortium_formation_activities": "mandatory_consortium_building_activities",
    # write_nomination is intentional (award nominations), keep as-is
}


def parse_sections(soup):
    """
    Extract every accordion item found on the page — no hardcoding.
    Returns dict: slug -> {"title": str, "text": str}
    Variant/typo slugs are normalised via SLUG_ALIASES.
    """
    sections = {}
    for item in soup.find_all("div", class_="accordion-item"):
        item_id = item.get("id", "")
        if not item_id.startswith("accordion-item-"):
            continue
        slug = item_id[len("accordion-item-"):].replace("-", "_")
        slug = SLUG_ALIASES.get(slug, slug)  # normalise

        title_tag = item.find("span", class_="accordion-title")
        title = title_tag.get_text(strip=True) if title_tag else slug

        content = item.find("div", class_="accordion-collapse")
        text = content.get_text(separator=" ", strip=True) if content else ""
        if text:
            # If two slugs merge into the same canonical key, concatenate
            if slug in sections:
                sections[slug]["text"] += " " + text
            else:
                sections[slug] = {"title": title, "text": text}

    return sections


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

def parse_downloads(soup):
    seen = set()
    downloads = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/files/" not in href or href in seen:
            continue
        seen.add(href)

        raw_name = a.get_text(strip=True)
        ext = href.rsplit(".", 1)[-1].lower() if "." in href else "unknown"

        size_m = re.search(r"(\d[\d.]*\s*(?:KB|MB|GB))", raw_name, re.I)
        size   = size_m.group(1) if size_m else None

        # Clean name: strip trailing file-type and size suffixes
        name = re.sub(r"\s*\|?\s*\d[\d.]*\s*(?:KB|MB|GB)\s*$", "", raw_name, flags=re.I)
        name = re.sub(r"\s*\|?\s*(?:PDF|DOCX?|XLSX?|ZIP)\s*$", "", name, flags=re.I).strip()
        if not name:
            name = href.rsplit("/", 1)[-1]

        downloads.append({
            "name": name,
            "url":  "https://www.nwo.nl" + href if href.startswith("/") else href,
            "type": ext,
            "size": size,
        })
    return downloads


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

def parse_contacts(soup):
    contacts = []
    for block in soup.find_all("div", class_="paragraph--type--contact"):
        for info in block.find_all("div", class_="contact__info"):
            content = info.find("div", class_="contact__content")
            if not content:
                continue
            c = {}
            name_tag = content.find("h6", class_="strong")
            if name_tag:
                c["name"] = name_tag.get_text(strip=True)
            role_tag = content.find("span", class_="function")
            if role_tag:
                c["role"] = role_tag.get_text(strip=True)
            phone_tag = content.find("a", href=re.compile(r"^tel:"))
            if phone_tag:
                c["phone"] = phone_tag.get_text(strip=True)
            email_tag = content.find("a", href=re.compile(r"^mailto:"))
            if email_tag:
                c["email"] = email_tag["href"].replace("mailto:", "")
            if c:
                contacts.append(c)
    return contacts


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "januari": 1, "februari": 2, "maart": 3, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "oktober": 10,
}

DATE_RE = re.compile(
    r"(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})"
    r"(?:[,\s]+(?:at\s+)?(\d{1,2})[:.h](\d{2})\s*(?:hrs?\.?|CET|CEST|hours?)?)?",
    re.IGNORECASE,
)

def parse_text_dates(text):
    """Extract all dates from free text, return as ISO strings."""
    results = []
    for m in DATE_RE.finditer(text):
        month = MONTHS.get(m.group(2).lower())
        if not month:
            continue
        try:
            dt = datetime(
                int(m.group(3)), month, int(m.group(1)),
                int(m.group(4)) if m.group(4) else 23,
                int(m.group(5)) if m.group(5) else 59,
            )
            results.append(dt.strftime("%Y-%m-%dT%H:%M:00"))
        except ValueError:
            continue
    return results

def iso_from_char(val):
    """Characteristic value → list of ISO strings."""
    if isinstance(val, dict):
        return val.get("iso", [])
    if isinstance(val, str):
        return parse_text_dates(val)
    return []

def nearest_future(iso_list):
    now = datetime.now()
    future = []
    for s in iso_list:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "").split("+")[0])
            if dt > now:
                future.append((dt, s))
        except ValueError:
            continue
    return min(future, key=lambda x: x[0])[1] if future else None


# ---------------------------------------------------------------------------
# Status normalisation
# ---------------------------------------------------------------------------

STATUS_MAP = [
    (re.compile(r"\bin preparation\b", re.I), "in_preparation"),
    (re.compile(r"\bin progress\b",    re.I), "in_progress"),
    (re.compile(r"\bupcoming\b",       re.I), "upcoming"),
    (re.compile(r"\bclosed?\b",        re.I), "closed"),
    (re.compile(r"\bopen\b",           re.I), "open"),
    (re.compile(r"\bcontinuous\b",     re.I), "open"),
]

def normalise_status(raw):
    if not raw:
        return "unknown"
    for pattern, norm in STATUS_MAP:
        if pattern.search(raw):
            return norm
    return raw.strip().lower()


# ---------------------------------------------------------------------------
# Process one grant from its HTML
# ---------------------------------------------------------------------------

def process_html(slug, url, html):
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else slug

    chars     = parse_characteristics(soup)
    sections  = parse_sections(soup)
    downloads = parse_downloads(soup)
    contacts  = parse_contacts(soup)

    # --- Deadlines ---
    deadline_isos = []
    for key, val in chars.items():
        if any(w in key.lower() for w in ("closing", "deadline", "submission", "date", "datum")):
            deadline_isos.extend(iso_from_char(val))

    # Supplement with dates extracted from when_to_apply free text
    when_text = sections.get("when_to_apply", {}).get("text", "")
    deadline_isos.extend(parse_text_dates(when_text))

    # Deduplicate by minute precision
    seen_min, unique_deadlines = set(), []
    for d in deadline_isos:
        k = d[:16]
        if k not in seen_min:
            seen_min.add(k)
            unique_deadlines.append(d)
    unique_deadlines.sort()

    # --- PDFs ---
    all_pdfs = [d["url"] for d in downloads if d["type"] == "pdf"]
    cfp_pdfs = [d["url"] for d in downloads if d["type"] == "pdf" and
                ("call for proposal" in d["name"].lower() or "cfp" in d["name"].lower())]

    return {
        "id":           slug,
        "url":          url,
        "title":        title,
        # Flattened convenience fields
        "status":       normalise_status(chars.get("Status", "")),
        "status_raw":   chars.get("Status", ""),
        "budget":       _char_text(chars, "Budget"),
        "finance_type": _char_text(chars, "Finance type"),
        "programme":    _char_text(chars, "Research programme"),
        "target_groups":_char_text(chars, "For specific groups"),
        "deadline_iso": nearest_future(unique_deadlines),
        "deadline_dates": unique_deadlines,
        "primary_pdf":  cfp_pdfs[0] if cfp_pdfs else (all_pdfs[0] if all_pdfs else None),
        "pdf_urls":     all_pdfs,
        # Full structured data
        "characteristics": chars,
        "sections":        sections,   # {slug: {title, text}}
        "downloads":       downloads,
        "contacts":        contacts,
    }

def _char_text(chars, key):
    val = chars.get(key, "")
    return val.get("display", "") if isinstance(val, dict) else (val or "")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if not MANIFEST.exists():
        print(f"ERROR: {MANIFEST} not found. Run scraper.py first.")
        return

    manifest = json.loads(MANIFEST.read_text())
    print(f"Processing {len(manifest)} grants from {HTML_DIR}/...")

    grants = []
    missing = []

    for slug, url in manifest.items():
        html_path = HTML_DIR / f"{slug}.html"
        if not html_path.exists():
            print(f"  MISSING html: {slug}")
            missing.append(slug)
            continue
        html = html_path.read_text(encoding="utf-8")
        grants.append(process_html(slug, url, html))

    # Sort by nearest deadline (no deadline → end)
    grants.sort(key=lambda g: g["deadline_iso"] or "9999")

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(grants, f, ensure_ascii=False, indent=2)

    # Summary
    statuses = {}
    for g in grants:
        statuses[g["status"]] = statuses.get(g["status"], 0) + 1

    all_section_slugs = {}
    for g in grants:
        for slug in g["sections"]:
            all_section_slugs[slug] = all_section_slugs.get(slug, 0) + 1

    print(f"\nDone. {len(grants)} grants → {OUTPUT}")
    print(f"  Future deadline : {sum(1 for g in grants if g['deadline_iso'])}")
    print(f"  Primary PDF     : {sum(1 for g in grants if g['primary_pdf'])}")
    print(f"  Statuses        : {statuses}")
    print(f"\n  Section slugs found across all grants:")
    for slug, n in sorted(all_section_slugs.items(), key=lambda x: -x[1]):
        print(f"    {n:3d}/{len(grants)}  {slug}")
    if missing:
        print(f"\n  Missing HTML files: {missing}")


if __name__ == "__main__":
    main()
