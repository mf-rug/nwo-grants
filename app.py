import json
from datetime import datetime, timedelta
from pathlib import Path

import requests
import streamlit as st

st.set_page_config(page_title="NWO Grants", layout="wide")

st.html("""
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Plus+Jakarta+Sans:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
    --bg:#0f1117; --surface:#181c2a; --surface2:#1e2336;
    --border:#252d45; --border-hi:#38406a;
    --text:#dce3f5; --text-dim:#566180; --text-bright:#fff;
    --accent:#e8a838; --accent-lo:rgba(232,168,56,.12);
    --open:#4ade80; --upcoming:#60a5fa; --in-prep:#fbbf24;
    --in-progress:#f97316; --closed:#4b556a;
    --fh:'Syne',sans-serif; --fb:'Plus Jakarta Sans',sans-serif; --fm:'JetBrains Mono',monospace;
    --r:10px;
}
.stApp,[data-testid="stAppViewContainer"]{background:var(--bg)!important;font-family:var(--fb)!important;color:var(--text)!important;}
[data-testid="stToolbar"],footer,#MainMenu{display:none!important;}
[data-testid="stHeader"]{background:transparent!important;}
::-webkit-scrollbar{width:5px;height:5px;}
::-webkit-scrollbar-track{background:var(--bg);}
::-webkit-scrollbar-thumb{background:var(--border-hi);border-radius:3px;}
::-webkit-scrollbar-thumb:hover{background:var(--accent);}

/* ── Sidebar ── */
[data-testid="stSidebar"]{background:var(--surface)!important;border-right:1px solid var(--border)!important;}
[data-testid="stSidebar"] h1{font-family:var(--fh)!important;font-size:1.25rem!important;font-weight:800!important;color:var(--accent)!important;letter-spacing:.1em!important;text-transform:uppercase!important;}
[data-testid="stSidebar"] p{font-size:.68rem!important;color:var(--text-dim)!important;font-family:var(--fm)!important;letter-spacing:.1em!important;text-transform:uppercase!important;}
[data-testid="stSidebar"] label{color:var(--text)!important;font-size:.82rem!important;}
[data-testid="stSidebar"] input{background:var(--bg)!important;border:1px solid var(--border)!important;border-radius:6px!important;color:var(--text)!important;font-family:var(--fb)!important;font-size:.82rem!important;}
[data-testid="stSidebar"] input:focus{border-color:var(--accent)!important;box-shadow:0 0 0 2px var(--accent-lo)!important;outline:none!important;}
[data-testid="stSidebar"] hr{border-color:var(--border)!important;}
[data-testid="stSidebar"] [data-testid="stSelectbox"]>div>div,[data-testid="stSidebar"] [data-testid="stMultiSelect"]>div>div{background:var(--bg)!important;border-color:var(--border)!important;border-radius:6px!important;}

/* ── Main ── */
.main .block-container{padding-top:1.5rem!important;}
h1{font-family:var(--fh)!important;font-weight:800!important;font-size:2rem!important;letter-spacing:-.02em!important;color:var(--text-bright)!important;}
[data-testid="stCaptionContainer"] p{color:var(--text-dim)!important;font-family:var(--fm)!important;font-size:.72rem!important;}

/* ── Expanders ── */
[data-testid="stExpander"]{background:var(--surface)!important;border:1px solid var(--border)!important;border-radius:var(--r)!important;margin-bottom:.4rem!important;overflow:hidden!important;transition:border-color .15s,box-shadow .15s!important;}
[data-testid="stExpander"]:hover{border-color:var(--border-hi)!important;box-shadow:0 4px 20px rgba(0,0,0,.35)!important;}
[data-testid="stExpander"] summary{padding:.75rem 1rem!important;font-family:var(--fb)!important;font-weight:500!important;font-size:.87rem!important;color:var(--text)!important;}
[data-testid="stExpander"] summary:hover{color:var(--text-bright)!important;}
[data-testid="stExpander"] [data-testid="stExpander"]{background:var(--bg)!important;border-radius:7px!important;margin-bottom:.25rem!important;}
[data-testid="stExpander"]>div>div{padding:0 1rem .9rem!important;}

hr{border-color:var(--border)!important;margin:.6rem 0!important;}
.stButton>button{background:transparent!important;border:1px solid var(--border-hi)!important;color:var(--text)!important;border-radius:7px!important;font-family:var(--fb)!important;font-size:.82rem!important;transition:all .15s!important;}
.stButton>button:hover{border-color:var(--accent)!important;color:var(--accent)!important;background:var(--accent-lo)!important;}
code{font-family:var(--fm)!important;font-size:.7rem!important;padding:2px 6px!important;border-radius:4px!important;background:var(--surface2)!important;color:var(--text-dim)!important;border:1px solid var(--border)!important;}
.stMarkdown a{color:var(--accent)!important;text-decoration:none!important;font-weight:500!important;}
.stMarkdown a:hover{text-decoration:underline!important;}
[data-testid="stInfo"]{background:var(--surface2)!important;border-color:var(--border-hi)!important;color:var(--text)!important;border-radius:var(--r)!important;}

/* ── Custom components ── */
.nb{display:inline-block;font-family:var(--fm);font-size:.61rem;font-weight:500;padding:2px 8px;border-radius:20px;letter-spacing:.05em;text-transform:uppercase;border:1px solid currentColor;}
.nb-open{color:var(--open);background:rgba(74,222,128,.1);}
.nb-upcoming{color:var(--upcoming);background:rgba(96,165,250,.1);}
.nb-in_preparation{color:var(--in-prep);background:rgba(251,191,36,.1);}
.nb-in_progress{color:var(--in-progress);background:rgba(249,115,22,.1);}
.nb-closed{color:var(--closed);background:rgba(75,85,99,.1);}

.dp{display:inline-block;font-family:var(--fm);font-size:.68rem;font-weight:500;color:var(--accent);background:var(--accent-lo);padding:1px 7px;border-radius:4px;margin-left:5px;}
.dp.past{color:var(--text-dim);background:transparent;}

/* Card grid */
.cgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:.65rem;}
.gc{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:1rem 1.1rem;display:flex;flex-direction:column;gap:.5rem;height:100%;transition:border-color .15s,transform .15s,box-shadow .15s;}
.gc:hover{border-color:var(--accent);transform:translateY(-2px);box-shadow:0 8px 28px rgba(0,0,0,.4),0 0 0 1px var(--accent-lo);}
.gc-title{font-family:var(--fb);font-weight:600;font-size:.86rem;color:var(--text-bright);line-height:1.45;flex:1;}
.gc-title a{color:inherit!important;text-decoration:none!important;}
.gc-title a:hover{color:var(--accent)!important;}
.gc-meta{font-size:.73rem;color:var(--text-dim);line-height:1.4;}
.gc-links{font-size:.75rem;padding-top:.4rem;border-top:1px solid var(--border);margin-top:auto;}
.gc-links a{color:var(--accent)!important;text-decoration:none!important;font-weight:500;}
.gc-links a:hover{text-decoration:underline!important;}

/* List extended row */
.gr{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:.85rem 1.1rem;margin-bottom:.35rem;transition:border-color .15s,box-shadow .15s;}
.gr:hover{border-color:var(--border-hi);box-shadow:0 3px 18px rgba(0,0,0,.28);}
.gr-title{font-family:var(--fb);font-weight:600;font-size:.9rem;color:var(--text-bright);margin-top:.3rem;}
.gr-meta{font-size:.74rem;color:var(--text-dim);margin-top:.22rem;}
.gr-links a{color:var(--accent)!important;text-decoration:none!important;font-size:.78rem;font-weight:500;}
.gr-links a:hover{text-decoration:underline!important;}
</style>
""")

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
def _badge(status):
    return f'<span class="nb nb-{status}">{status.replace("_"," ")}</span>'

def _day_pill(g, now):
    nd = next_deadline(g, now)
    if nd == SENTINEL: return ""
    days = (nd - now).days
    return f'<span class="dp">⏳ {days}d</span>' if days >= 0 else '<span class="dp past">⌛ past</span>'

def _links_html(g, sep=" · "):
    parts = [f'<a href="?grant={g["id"]}">Details</a>']
    if g.get("url"):         parts.append(f'<a href="{g["url"]}" target="_blank">NWO</a>')
    if g.get("primary_pdf"): parts.append(f'<a href="{g["primary_pdf"]}" target="_blank">PDF</a>')
    return sep.join(parts)

def _meta_line(g):
    ft     = g.get("finance_type", "") or ""
    budget = g.get("budget", "") or "—"
    cons   = "🤝 · " if is_consortium(g) else ""
    return "  ·  ".join(p for p in [ft, f"{cons}{budget}"] if p)

def _label(g, now):
    nd   = next_deadline(g, now)
    days = (nd - now).days if nd != SENTINEL else None
    icon = STATUS_COLORS.get(g.get("status", ""), "⚪")
    s = f"{icon} {g['title']}"
    if days is not None and days >= 0: s += f"  ·  ⏳ {days}d"
    elif nd != SENTINEL:               s += "  ·  ⌛ past"
    return s

def _render_deadlines(g, now):
    stages = extract_deadlines(g)
    if stages:
        rows = []
        for lbl, dt, disp in stages:
            if dt:
                d_left   = (dt - now).days
                marker   = f"⏳ {d_left}d" if d_left >= 0 else "✓ past"
                style    = "" if d_left >= 0 else "color:var(--text-dim);"
                date_str = dt.strftime("%d %b %Y")
            else:
                date_str, marker, style = disp, "", "color:var(--text-dim);"
            rows.append(f'<span style="font-family:var(--fm);font-size:.78rem;{style}"><b>{lbl}:</b> {date_str} &nbsp;{marker}</span>')
        st.markdown("  \n".join(rows), unsafe_allow_html=True)
    else:
        iso = g.get("deadline_iso")
        if iso:
            try:
                st.markdown(f'<span style="font-family:var(--fm);font-size:.78rem;"><b>Deadline:</b> {_parse_iso(iso).strftime("%d %b %Y")}</span>', unsafe_allow_html=True)
            except (ValueError, AttributeError):
                pass

def _render_sections(g):
    sections = g.get("sections", {})
    for key in PRIMARY_SECTIONS:
        sec = sections.get(key)
        if sec and sec.get("text"):
            with st.expander(sec.get("title") or key.replace("_", " ").title(), expanded=True):
                st.markdown(sec["text"].strip())
    for key in [k for k in sections if k not in PRIMARY_SECTIONS]:
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
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.55rem;">'
                f'<div>{_badge(g.get("status",""))} '
                f'<span style="font-family:var(--fm);font-size:.73rem;color:var(--text-dim);">{_meta_line(g)}</span></div>'
                f'<div class="gr-links">{_links_html(g)}</div></div>',
                unsafe_allow_html=True)
            _render_deadlines(g, now)
            st.divider()
            _render_sections(g)
            _render_contacts(g)

def render_list_extended(grants, now):
    for g in grants:
        st.markdown(
            f'<div class="gr">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;">'
            f'<div style="flex:1;">{_badge(g.get("status",""))} {_day_pill(g,now)}'
            f'<div class="gr-title">{g["title"]}</div>'
            f'<div class="gr-meta">{_meta_line(g)}</div></div>'
            f'<div class="gr-links" style="white-space:nowrap;padding-top:.15rem;">{_links_html(g," · ")}</div>'
            f'</div></div>',
            unsafe_allow_html=True)
        with st.expander("Sections", expanded=False):
            _render_deadlines(g, now)
            st.divider()
            _render_sections(g)
            _render_contacts(g)

def render_cards(grants, now, extended):
    html = '<div class="cgrid">'
    for g in grants:
        status = g.get("status", "")
        meta   = f'<div class="gc-meta">{_meta_line(g)}</div>' if extended else ""
        html  += (
            f'<div class="gc">'
            f'<div>{_badge(status)} {_day_pill(g, now)}</div>'
            f'<div class="gc-title"><a href="?grant={g["id"]}">{g["title"]}</a></div>'
            f'{meta}'
            f'<div class="gc-links">{_links_html(g," · ")}</div>'
            f'</div>'
        )
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# ── Dispatch ───────────────────────────────────────────────────────────────────
if   view_mode == "List"  and detail_level == "Tight":    render_list_tight(filtered, now)
elif view_mode == "List"  and detail_level == "Extended":  render_list_extended(filtered, now)
elif view_mode == "Cards" and detail_level == "Tight":    render_cards(filtered, now, extended=False)
else:                                                      render_cards(filtered, now, extended=True)
