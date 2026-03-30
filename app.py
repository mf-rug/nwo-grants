import json
from datetime import datetime, timedelta
from pathlib import Path

import requests
import streamlit as st

st.set_page_config(page_title="NWO Grants", layout="wide")

# ── Load data ──────────────────────────────────────────────────────────────────
GRANTS_URL = "https://raw.githubusercontent.com/mf-rug/nwo-grants/main/grants.json"
MD_BASE    = "https://raw.githubusercontent.com/mf-rug/nwo-grants/main/md"

@st.cache_data(ttl=3600)
def load_grants():
    r = requests.get(GRANTS_URL, timeout=15)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=3600)
def load_md(grant_id: str):
    r = requests.get(f"{MD_BASE}/{grant_id}.md", timeout=15)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.text

grants = load_grants()
grants_by_id = {g["id"]: g for g in grants}

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

# ── Detail page ───────────────────────────────────────────────────────────────
detail_id = st.query_params.get("grant")
if detail_id:
    g = grants_by_id.get(detail_id)
    if g is None:
        st.error(f"Grant '{detail_id}' not found.")
        st.stop()

    if st.button("← Back to all grants"):
        st.query_params.clear()
        st.rerun()

    status = g.get("status", "")
    icon   = STATUS_COLORS.get(status, "⚪")
    ft     = g.get("finance_type", "")
    badge  = " · 🤝 consortium" if is_consortium(g) else ""
    st.caption(f"{icon} `{status}`  {ft}{badge}  ·  **{g.get('budget') or '—'}**")

    stages = extract_deadlines(g)
    now_d  = datetime.utcnow()
    if stages:
        rows = []
        for lbl, dt, disp in stages:
            if dt:
                d_left   = (dt - now_d).days
                marker   = f"⏳ {d_left}d" if d_left >= 0 else "✓ past"
                style    = "" if d_left >= 0 else "color:#888;"
                date_str = dt.strftime("%d %b %Y")
            else:
                date_str, marker, style = disp, "", "color:#888;"
            rows.append(f'<span style="{style}">**{lbl}:** {date_str} &nbsp; {marker}</span>')
        st.markdown("  \n".join(rows), unsafe_allow_html=True)

    links = []
    if g.get("url"):        links.append(f"[NWO page]({g['url']})")
    if g.get("primary_pdf"): links.append(f"[PDF]({g['primary_pdf']})")
    if links: st.markdown("  |  ".join(links))

    st.divider()

    md = load_md(detail_id)
    if md:
        st.markdown(md)
    else:
        st.info("Detailed markdown not yet available — showing extracted sections.")
        sections = g.get("sections", {})
        for key in PRIMARY_SECTIONS + [k for k in sections if k not in PRIMARY_SECTIONS]:
            sec = sections.get(key)
            if sec and sec.get("text"):
                st.subheader(sec.get("title") or key.replace("_", " ").title())
                st.markdown(sec["text"].strip())

    contacts = g.get("contacts") or []
    if contacts:
        st.divider()
        parts = [f"{c.get('name','')} [{c.get('email','')}](mailto:{c.get('email','')})"
                 if c.get("email") else c.get("name", "") for c in contacts]
        st.caption("📧 " + "  ·  ".join(parts))

    st.stop()

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

st.sidebar.markdown("---")
view_mode    = st.sidebar.radio("View",   ["List", "Cards"], horizontal=True)
detail_level = st.sidebar.radio("Detail", ["Tight", "Extended"], horizontal=True)

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

# ── Render helpers ────────────────────────────────────────────────────────────
def _label(g, now):
    icon = STATUS_COLORS.get(g.get("status", ""), "⚪")
    nd   = next_deadline(g, now)
    days = (nd - now).days if nd != SENTINEL else None
    s = f"{icon} {g['title']}"
    if days is not None and days >= 0: s += f"  ·  ⏳ {days}d"
    elif nd != SENTINEL:               s += "  ·  ⌛ past"
    return s

def _meta_str(g):
    ft     = g.get("finance_type", "") or ""
    budget = g.get("budget", "") or "—"
    badge  = " · 🤝 consortium" if is_consortium(g) else ""
    return f"`{g.get('status','')}`  {ft}{badge}  ·  **{budget}**"

def _links_str(g):
    parts = [f"[Details](?grant={g['id']})"]
    if g.get("url"):         parts.append(f"[NWO page]({g['url']})")
    if g.get("primary_pdf"): parts.append(f"[PDF]({g['primary_pdf']})")
    return "  |  ".join(parts)

def _render_deadlines(g, now):
    stages = extract_deadlines(g)
    if stages:
        rows = []
        for lbl, dt, disp in stages:
            if dt:
                d_left   = (dt - now).days
                marker   = f"⏳ {d_left}d" if d_left >= 0 else "✓ past"
                style    = "" if d_left >= 0 else "color:#888;"
                date_str = dt.strftime("%d %b %Y")
            else:
                date_str, marker, style = disp, "", "color:#888;"
            rows.append(f'<span style="{style}">**{lbl}:** {date_str} &nbsp; {marker}</span>')
        st.markdown("  \n".join(rows), unsafe_allow_html=True)
    else:
        iso = g.get("deadline_iso")
        if iso:
            try:
                st.markdown(f"**Deadline:** {_parse_iso(iso).strftime('%d %b %Y')}")
            except (ValueError, AttributeError):
                pass

def _render_sections(g):
    sections = g.get("sections", {})
    all_keys = list(sections.keys())
    for key in PRIMARY_SECTIONS:
        sec = sections.get(key)
        if sec and sec.get("text"):
            with st.expander(sec.get("title") or key.replace("_", " ").title(), expanded=True):
                st.markdown(sec["text"].strip())
    for key in [k for k in all_keys if k not in PRIMARY_SECTIONS]:
        sec = sections.get(key)
        if sec and sec.get("text"):
            with st.expander(sec.get("title") or key.replace("_", " ").title(), expanded=False):
                st.markdown(sec["text"].strip())

def _render_contacts(g):
    contacts = g.get("contacts") or []
    if contacts:
        parts = [f"{c.get('name','')} [{c.get('email','')}](mailto:{c.get('email','')})"
                 if c.get("email") else c.get("name", "") for c in contacts]
        st.caption("📧 " + "  ·  ".join(parts))

# ── Render modes ───────────────────────────────────────────────────────────────
def render_list_tight(grants, now):
    for g in grants:
        with st.expander(_label(g, now)):
            col1, col2 = st.columns([3, 1])
            with col1: st.markdown(_meta_str(g))
            with col2: st.markdown(_links_str(g))
            _render_deadlines(g, now)
            st.divider()
            _render_sections(g)
            _render_contacts(g)

def render_list_extended(grants, now):
    for g in grants:
        col_title, col_links = st.columns([3, 1])
        with col_title:
            st.markdown(f"##### {_label(g, now)}")
        with col_links:
            st.markdown(_links_str(g))
        ft     = g.get("finance_type", "") or ""
        budget = g.get("budget", "") or "—"
        badge  = "🤝 consortium · " if is_consortium(g) else ""
        st.caption(f"{ft}  ·  {badge}{budget}")
        with st.expander("Sections", expanded=False):
            _render_deadlines(g, now)
            st.divider()
            _render_sections(g)
            _render_contacts(g)
        st.divider()

def render_cards(grants, now, extended):
    N = 3
    for i in range(0, len(grants), N):
        cols = st.columns(N)
        for col, g in zip(cols, grants[i:i+N]):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{_label(g, now)}**")
                    if extended:
                        ft     = g.get("finance_type", "") or ""
                        budget = g.get("budget", "") or "—"
                        badge  = "🤝 consortium · " if is_consortium(g) else ""
                        st.caption(f"{ft}  ·  {badge}{budget}")
                        st.markdown(_links_str(g))

# ── Dispatch ───────────────────────────────────────────────────────────────────
if   view_mode == "List"  and detail_level == "Tight":    render_list_tight(filtered, now)
elif view_mode == "List"  and detail_level == "Extended":  render_list_extended(filtered, now)
elif view_mode == "Cards" and detail_level == "Tight":    render_cards(filtered, now, extended=False)
else:                                                      render_cards(filtered, now, extended=True)
