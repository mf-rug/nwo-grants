import json
from datetime import datetime, timedelta
from pathlib import Path

import requests
import streamlit as st

st.set_page_config(page_title="NWO Grants", layout="wide")

# ── Load data ──────────────────────────────────────────────────────────────────
GRANTS_URL = "https://raw.githubusercontent.com/mf-rug/nwo-grants/main/grants.json"

@st.cache_data(ttl=3600)
def load_grants():
    r = requests.get(GRANTS_URL, timeout=15)
    r.raise_for_status()
    return r.json()

grants = load_grants()

STATUS_COLORS = {
    "open": "🟢",
    "upcoming": "🔵",
    "in_preparation": "🟡",
    "in_progress": "🟠",
    "closed": "🔴",
}
ALL_STATUSES = ["open", "upcoming", "in_preparation", "in_progress", "closed"]
ALL_FINANCE  = sorted({g.get("finance_type", "") for g in grants} - {""})

PRIMARY_SECTIONS = ["purpose", "who_can_apply", "what_to_apply_for", "when_to_apply"]

DEADLINE_KEYS = [
    ("Letter of intent", "Closing date for letter of intent"),
    ("Pre-proposal",     "Closing date for pre-proposals"),
    ("Full application", "Closing date full application"),
]

# ── Deadline helpers ───────────────────────────────────────────────────────────
SENTINEL = datetime(9999, 12, 31)

def _parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.replace(tzinfo=None)  # naive UTC

def extract_deadlines(g):
    """Return list of (label, datetime_or_None, display_str) for all deadline stages."""
    chars = g.get("characteristics", {})
    result = []
    for label, key in DEADLINE_KEYS:
        val = chars.get(key)
        if not val:
            continue
        if isinstance(val, dict):
            iso_list = val.get("iso", [])
            display  = val.get("display", "")
            dt = None
            for iso in iso_list:
                try:
                    dt = _parse_iso(iso)
                    break
                except (ValueError, AttributeError):
                    pass
            result.append((label, dt, display))
        elif isinstance(val, str):
            result.append((label, None, val))
    # sort by datetime (None → end)
    result.sort(key=lambda x: x[1] if x[1] else SENTINEL)
    return result

def next_deadline(g, now):
    """Earliest upcoming deadline datetime across all stages, else SENTINEL."""
    stages = extract_deadlines(g)
    upcoming = [dt for _, dt, _ in stages if dt and dt >= now]
    if upcoming:
        return min(upcoming)
    # fall back to deadline_iso
    iso = g.get("deadline_iso")
    if iso:
        try:
            dt = _parse_iso(iso)
            if dt >= now:
                return dt
        except (ValueError, AttributeError):
            pass
    return SENTINEL

def is_consortium(g):
    if g.get("finance_type") == "Collaboration with Partners":
        return True
    sections = g.get("sections", {})
    return "consortium_building" in sections or "mandatory_consortium_building_activities" in sections

# ── Sidebar ────────────────────────────────────────────────────────────────────
st.sidebar.title("Filters")

query = st.sidebar.text_input("Search", placeholder="Keywords…")

st.sidebar.markdown("**Status**")
selected_statuses = [
    s for s in ALL_STATUSES
    if st.sidebar.checkbox(s.replace("_", " ").title(), value=(s in ("open", "upcoming")), key=s)
]

finance_filter = st.sidebar.multiselect("Finance type", ALL_FINANCE)

consortium_only = st.sidebar.toggle("Collaboration / consortium grants only", value=False)

st.sidebar.markdown("**Next deadline within**")
DEADLINE_WINDOWS = {
    "Any": None,
    "2 weeks": 14,
    "1 month": 30,
    "3 months": 90,
    "6 months": 180,
}
deadline_window = st.sidebar.selectbox(
    "Next deadline within", list(DEADLINE_WINDOWS.keys()), label_visibility="collapsed"
)

has_pdf = st.sidebar.toggle("Has PDF", value=False)

sort_by = st.sidebar.radio("Sort by", ["Nearest deadline", "Title"], horizontal=True)

# ── Filter ─────────────────────────────────────────────────────────────────────
def section_text(g):
    return " ".join(
        s.get("text", "") for s in g.get("sections", {}).values() if isinstance(s, dict)
    )

def matches_query(g, q):
    if not q:
        return True
    q = q.lower()
    haystack = (g.get("title", "") + " " + section_text(g)).lower()
    return all(word in haystack for word in q.split())

now = datetime.utcnow()
cutoff_days = DEADLINE_WINDOWS[deadline_window]
cutoff = now + timedelta(days=cutoff_days) if cutoff_days else None

filtered = [
    g for g in grants
    if matches_query(g, query)
    and (not selected_statuses or g.get("status") in selected_statuses)
    and (not finance_filter or g.get("finance_type") in finance_filter)
    and (not consortium_only or is_consortium(g))
    and (cutoff is None or next_deadline(g, now) <= cutoff)
    and (not has_pdf or g.get("primary_pdf"))
]

if sort_by == "Nearest deadline":
    filtered.sort(key=lambda g: next_deadline(g, now))
else:
    filtered.sort(key=lambda g: g.get("title", "").lower())

# ── Main area ──────────────────────────────────────────────────────────────────
st.title("NWO Grants")
st.caption(f"Showing **{len(filtered)}** of {len(grants)} grants")

if not filtered:
    st.info("No grants match the current filters.")
    st.stop()

for g in filtered:
    status   = g.get("status", "")
    icon     = STATUS_COLORS.get(status, "⚪")
    nd       = next_deadline(g, now)
    days_left = (nd - now).days if nd != SENTINEL else None

    label = f"{icon} {g['title']}"
    if days_left is not None and days_left >= 0:
        label += f"  ·  ⏳ {days_left}d"
    elif nd != SENTINEL:
        label += "  ·  ⌛ past"

    with st.expander(label):
        # ── Header row ──
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            ft = g.get("finance_type", "")
            consortium_badge = " · 🤝 consortium" if is_consortium(g) else ""
            st.markdown(f"`{status}`  {ft}{consortium_badge}  ·  **{g.get('budget') or '—'}**")
        with col2:
            pass  # deadlines shown below
        with col3:
            links = []
            if g.get("url"):
                links.append(f"[NWO page]({g['url']})")
            if g.get("primary_pdf"):
                links.append(f"[PDF]({g['primary_pdf']})")
            if links:
                st.markdown("  |  ".join(links))

        # ── Deadline timeline ──
        stages = extract_deadlines(g)
        if stages:
            rows = []
            for lbl, dt, disp in stages:
                if dt:
                    d_left = (dt - now).days
                    if d_left < 0:
                        marker = "✓ past"
                        style  = "color: #888;"
                    else:
                        marker = f"⏳ {d_left}d"
                        style  = ""
                    date_str = dt.strftime("%d %b %Y")
                else:
                    date_str = disp
                    marker   = ""
                    style    = "color: #888;"
                rows.append(f'<span style="{style}">**{lbl}:** {date_str} &nbsp; {marker}</span>')
            st.markdown("  \n".join(rows), unsafe_allow_html=True)
        else:
            # fallback: show deadline_iso
            iso = g.get("deadline_iso")
            if iso:
                try:
                    dt = _parse_iso(iso)
                    st.markdown(f"**Deadline:** {dt.strftime('%d %b %Y')}")
                except (ValueError, AttributeError):
                    pass

        st.divider()

        # ── Sections ──
        sections = g.get("sections", {})
        all_keys = list(sections.keys())

        def show_section_expander(key, expanded):
            sec = sections.get(key)
            if not (sec and sec.get("text")):
                return
            heading = sec.get("title") or key.replace("_", " ").title()
            with st.expander(heading, expanded=expanded):
                st.markdown(sec["text"].strip())

        for key in PRIMARY_SECTIONS:
            if key in sections:
                show_section_expander(key, expanded=True)

        secondary = [k for k in all_keys if k not in PRIMARY_SECTIONS]
        for key in secondary:
            show_section_expander(key, expanded=False)

        # ── Contacts (demoted) ──
        contacts = g.get("contacts") or []
        if contacts:
            parts = []
            for c in contacts:
                name  = c.get("name", "")
                email = c.get("email", "")
                parts.append(f"{name} [{email}](mailto:{email})" if email else name)
            st.caption("📧 " + "  ·  ".join(parts))
