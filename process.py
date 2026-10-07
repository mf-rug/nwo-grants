#!/usr/bin/env python3
"""
NWO Grants Processor — reads raw HTML from ./html/, extracts everything, writes grants.json.

Run as many times as you like. Adjust extraction logic here; never need to re-scrape.

Usage:
    python3 process.py
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

HTML_DIR = Path("html")
MANIFEST = HTML_DIR / "manifest.json"
OUTPUT   = "grants.json"

# Fields whose change marks a meaningful update (NWO-sourced facts only —
# deliberately excludes derived/time-dependent fields like deadline_iso).
TRACKED_FIELDS = ("status", "deadline_dates", "budget", "finance_type")

# Grants already present before change-tracking existed get a baseline in the
# past, so a migration run doesn't flag the whole catalogue as "new this week".
FIRST_SEEN_BASELINE = "2020-01-01"


def load_previous(path):
    """Map id -> previous grant dict, for carrying forward metadata."""
    try:
        with open(path, encoding="utf-8") as f:
            return {g["id"]: g for g in json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def apply_change_tracking(grants, prev, today):
    """Stamp first_seen/last_changed by comparing against the previous run."""
    for g in grants:
        old = prev.get(g["id"])
        if old is None:
            g["first_seen"]  = today
            g["last_changed"] = today
        else:
            g["first_seen"] = old.get("first_seen", FIRST_SEEN_BASELINE)
            changed = any(g.get(f) != old.get(f) for f in TRACKED_FIELDS)
            g["last_changed"] = today if changed else old.get("last_changed", g["first_seen"])
    return grants


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

# Coarse prose-context cues for a date (§11 Request D follow-up). Opening dates
# live almost entirely in the prose and are the ones the task must drop; kept
# high-precision because a wrong "opening" label would drop a real deadline.
# Everything ambiguous stays unlabelled (None) and falls back to the heuristic.
# An optional weekday / "the" may sit between the cue word and the date
# ("…from Tuesday 6 October 2026", §11 G2).
_FILLER = r"(?:\s+(?:mon|tues|wednes|thurs|fri|satur|sun)day|\s+the)*"
_OPEN_CUE = re.compile(
    r"(?:opens?\s+on|will\s+open|opening|re-?opens?|as\s+of|available\s+from|from)"
    + _FILLER + r"\s*:?\s*$", re.I)
_DEADLINE_CUE = re.compile(
    r"(?:no(?:t)?\s+later\s+than|until|before|up\s+to\s+and\s+including"
    r"|deadline|closing|submitted\s+by|\bto)" + _FILLER + r"\s*:?\s*$", re.I)

# Continuous/rolling-submission prose, for calls whose Status field does not say
# "Continuous" but whose body does (§11 G1).
_ROLLING_PROSE = re.compile(
    r"on a continuous basis|continuous(?:ly)?\s+(?:open|submi)"
    r"|submitted\b[^.]{0,30}\bat any time|at any time during"
    r"|no intermediate deadlines?|on a rolling basis", re.I)

def _prose_date_label(prefix):
    if _OPEN_CUE.search(prefix):
        return "opening (from text)"
    if _DEADLINE_CUE.search(prefix):
        return "deadline (from text)"
    return None

def _sentence(text, start, end):
    """The sentence a date sits in, so the task can tell a route-specific
    deadline (e.g. 'with a Flemish co-applicant …') from a call-wide one (§11 E2)."""
    s = text.rfind(".", 0, start) + 1
    e = text.find(".", end)
    e = e + 1 if e != -1 else min(len(text), end + 120)
    return re.sub(r"\s+", " ", text[s:e]).strip()[:180]

def parse_text_dates_labelled(text):
    """Extract dates from free text as (iso, label, context) — label classifies
    the date from its immediately-preceding prose (opening / deadline / None), and
    context is the sentence it was found in."""
    results = []
    for m in DATE_RE.finditer(text or ""):
        month = MONTHS.get(m.group(2).lower())
        if not month:
            continue
        try:
            dt = datetime(
                int(m.group(3)), month, int(m.group(1)),
                int(m.group(4)) if m.group(4) else 23,
                int(m.group(5)) if m.group(5) else 59,
            )
        except ValueError:
            continue
        results.append((dt.strftime("%Y-%m-%dT%H:%M:00"),
                        _prose_date_label(text[:m.start()]),
                        _sentence(text, m.start(), m.end())))
    return results

def parse_text_dates(text):
    """Extract all dates from free text, return as ISO strings."""
    return [iso for iso, _, _ in parse_text_dates_labelled(text)]

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
# Eligibility restrictions
# ---------------------------------------------------------------------------

# High-precision patterns for a CLOSED / invited / prior-awardee applicant set —
# the category grants.json otherwise can't express (e.g. LSRI National Roadmap is
# open only to consortia already named on the Roadmap). Deliberately NOT matched:
# "invited to submit" (open-call language), bare "restricted to", bare "roadmap"
# — all common false friends in normal eligibility prose.
RESTRICTION_PATTERNS = [
    r"by invitation only", r"invitation[- ]only",
    r"only be submitted for candidates who have been selected",
    r"candidates who have been selected by",
    r"have been selected by the",
    r"pre-?selected (?:consortia|applicants|projects|candidates|parties)",
    r"already (?:named|listed|selected) (?:on|in|by|as)",
    r"consortia (?:that are )?already (?:named|listed|part)",
    r"has been funded in (?:a|an|the)[^.]{0,40}(?:call|roadmap)",
    r"only applied for by consortia associated",
    r"only open to (?:the )?(?:selected|invited|named)",
]
_RESTRICTION_RE = re.compile("|".join(f"(?:{p})" for p in RESTRICTION_PATTERNS), re.I)


def detect_restrictions(sections):
    """Flag calls limited to a pre-selected/invited/prior-awardee applicant set.
    Reads eligibility-bearing sections; returns {invited_only, note}. High
    precision by design — misses are caught by the digest's per-call page fetch."""
    parts = []
    for key in ("who_can_apply", "purpose", "what_to_apply_for"):
        sec = sections.get(key)
        if isinstance(sec, dict) and sec.get("text"):
            parts.append(sec["text"])
    text = "  ".join(parts)
    m = _RESTRICTION_RE.search(text)
    if not m:
        return {"invited_only": False, "note": ""}
    start = text.rfind(".", 0, m.start()) + 1
    end = text.find(".", m.end())
    end = end + 1 if end != -1 else min(len(text), m.end() + 120)
    return {"invited_only": True, "note": text[start:end].strip()[:200]}


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------

def extract_deadlines(chars, when_text):
    """Return (unique_dates, labelled) where labelled is [{date, label, context}].

    `label` is NWO's own wording for a structured date ("Closing date full
    application", …), or a coarse opening/deadline class inferred from prose, or
    None. `context` is the sentence a prose date sat in ("" for structured dates),
    so the task can tell a route-specific deadline from a call-wide one (§11 E2).
    `unique_dates` is byte-identical to the legacy output — `deadline_dates` is in
    TRACKED_FIELDS, so the labels live in the separate `deadline_dates_labelled`
    key and this list must not change.
    """
    deadline_isos = []
    meta = {}  # iso -> (label, context); first seen wins (structured over prose)
    for key, val in chars.items():
        if any(w in key.lower() for w in ("closing", "deadline", "submission", "date", "datum")):
            for iso in iso_from_char(val):
                deadline_isos.append(iso)
                meta.setdefault(iso, (key, ""))
    for iso, lab, ctx in parse_text_dates_labelled(when_text or ""):
        deadline_isos.append(iso)
        meta.setdefault(iso, (lab, ctx))

    # Deduplicate by minute precision in original order, then sort (unchanged).
    seen, unique = set(), []
    for d in deadline_isos:
        k = d[:16]
        if k not in seen:
            seen.add(k)
            unique.append(d)
    unique.sort()
    labelled = [{"date": d, "label": meta[d][0], "context": meta[d][1]} for d in unique]
    return unique, labelled


# ---------------------------------------------------------------------------
# Mandatory prior stages (§11 Request F)
# ---------------------------------------------------------------------------

# A call can be effectively shut before its headline deadline by a mandatory
# earlier stage (letter of intent, matchmaking, a preliminary process). These
# are the most damaging to miss. A sentence qualifies only if it has BOTH a
# stage keyword AND a mandatory indicator AND no negation — which keeps out
# "compulsory co-funding" (no stage) and "matchmaking … (not mandatory)".
_MANDATORY_RE = re.compile(
    r"\b(?:mandatory|obligatory|obliged|compulsory|must\s+(?:have\s+)?particip"
    r"|only\s+applicants\s+who|required\s+to\s+(?:have|participate|register|attend))\b", re.I)
_NEGATED_RE = re.compile(
    r"not\s+(?:mandatory|obligatory|compulsory|required)|non-?mandatory|optional|voluntary", re.I)
_STAGE_KINDS = [  # priority order; first match wins
    (re.compile(r"letters?\s+of\s+intent|\bLOI\b", re.I), "letter_of_intent"),
    (re.compile(r"pre-?proposals?", re.I), "pre_proposal"),
    (re.compile(r"matchmaking", re.I), "matchmaking"),
    (re.compile(r"preliminary\s+(?:process|round|phase|deadline)|pre-?process", re.I), "pre_process"),
    (re.compile(r"\bregistration\b|\bregister\b", re.I), "registration"),
]
_PRQ_SECTIONS = ("who_can_apply", "when_to_apply", "what_to_apply_for", "assessment",
                 "mandatory_consortium_building_activities", "consortium_building", "how_to_apply")


def detect_prerequisites(sections, labelled):
    """Mandatory prior stages that can shut a call before its headline deadline.
    Returns [{kind, mandatory, date, context}] (one per kind). `date` comes from
    the triggering sentence, or from a labelled date whose context names the same
    stage, or None when the record cannot recover it (then the page fetch decides)."""
    found = {}
    for key in _PRQ_SECTIONS:
        sec = sections.get(key)
        txt = (sec.get("text", "") if isinstance(sec, dict) else "") or ""
        for sent in re.split(r"(?<=[.!?])\s+", txt):
            if not _MANDATORY_RE.search(sent) or _NEGATED_RE.search(sent):
                continue
            kind = next((k for rx, k in _STAGE_KINDS if rx.search(sent)), None)
            if not kind or kind in found:
                continue
            dates = parse_text_dates(sent)
            date = dates[0][:10] if dates else None
            if not date:
                kw = {"letter_of_intent": "letter of intent", "pre_proposal": "pre-proposal",
                      "matchmaking": "matchmaking", "pre_process": "preliminary",
                      "registration": "registration"}[kind]
                for e in labelled:
                    if kw in (e.get("context", "") or "").lower():
                        date = e["date"][:10]
                        break
            found[kind] = {"kind": kind, "mandatory": True, "date": date,
                           "context": re.sub(r"\s+", " ", sent).strip()[:200]}
    return list(found.values())


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
    when_text = sections.get("when_to_apply", {}).get("text", "")
    unique_deadlines, deadline_labelled = extract_deadlines(chars, when_text)
    prerequisites = detect_prerequisites(sections, deadline_labelled)

    # Headline deadline: never an opening date (§11 G3) — skip anything labelled
    # as an opening, so an empty/real-deadline value is reported rather than the
    # date the call opens.
    _opening = {e["date"] for e in deadline_labelled if "opening" in (e.get("label") or "").lower()}
    deadline_iso = nearest_future([d for d in unique_deadlines if d not in _opening])

    # Rolling: Status says "Continuous", or the body describes continuous
    # submission even when Status does not (§11 G1).
    rolling = "continuous" in (chars.get("Status", "") or "").lower()
    if not rolling:
        _body = " ".join((sections.get(k) or {}).get("text", "")
                         for k in ("when_to_apply", "what_to_apply_for", "purpose"))
        rolling = bool(_ROLLING_PROSE.search(_body))

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
        "deadline_iso": deadline_iso,
        "deadline_dates": unique_deadlines,
        "deadline_dates_labelled": deadline_labelled,
        # True for continuously-open calls, so an empty/opening-only date list
        # reads as "rolling" rather than "unknown" without a page fetch (§11 E3/G1).
        "rolling":      rolling,
        "primary_pdf":  cfp_pdfs[0] if cfp_pdfs else (all_pdfs[0] if all_pdfs else None),
        "pdf_urls":     all_pdfs,
        # Full structured data
        "characteristics": chars,
        "sections":        sections,   # {slug: {title, text}}
        "downloads":       downloads,
        "contacts":        contacts,
        "restrictions":    detect_restrictions(sections),
        # Mandatory earlier stages (LOI, matchmaking, …) that can shut the call
        # before its headline deadline — the most damaging class to miss (§11 F).
        "prerequisites":   prerequisites,
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

    # Change-tracking: carry forward first_seen, stamp last_changed
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prev = load_previous(OUTPUT)
    apply_change_tracking(grants, prev, today)
    new_count     = sum(1 for g in grants if g["first_seen"] == today)
    changed_count = sum(1 for g in grants if g["last_changed"] == today and g["first_seen"] != today)

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
    print(f"  New this run    : {new_count}")
    print(f"  Changed this run: {changed_count}")
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
