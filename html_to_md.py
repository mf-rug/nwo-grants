#!/usr/bin/env python3
"""
Convert NWO grant HTML pages to clean Markdown.
Usage: python3 html_to_md.py input.html [output.md]
       (omit output to print to stdout)
"""

import sys
import re
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Tag


def text(el):
    """Get stripped text content of an element."""
    return el.get_text(separator=" ", strip=True)


def inner_md(el):
    """Recursively convert an element's children to markdown text."""
    parts = []
    for child in el.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag):
            tag = child.name
            if tag in ("script", "style", "svg", "img", "figure", "noscript"):
                continue
            elif tag in ("p",):
                inner = inner_md(child).strip()
                if inner:
                    parts.append(inner + "\n\n")
            elif tag == "br":
                parts.append("\n")
            elif tag in ("strong", "b"):
                inner = inner_md(child).strip()
                if inner:
                    parts.append(f"**{inner}**")
            elif tag in ("em", "i"):
                inner = inner_md(child).strip()
                if inner:
                    parts.append(f"*{inner}*")
            elif tag == "a":
                inner = inner_md(child).strip()
                href = child.get("href", "")
                if inner and href and not href.startswith("/en/calls?"):
                    parts.append(f"[{inner}]({href})")
                elif inner:
                    parts.append(inner)
            elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                level = int(tag[1])
                inner = inner_md(child).strip()
                if inner:
                    parts.append(f"\n{'#' * level} {inner}\n\n")
            elif tag in ("ul", "ol"):
                parts.append(list_to_md(child, tag) + "\n")
            elif tag == "li":
                inner = inner_md(child).strip()
                if inner:
                    parts.append(f"- {inner}\n")
            elif tag == "table":
                parts.append(table_to_md(child))
            elif tag in ("div", "section", "article", "span", "header",
                         "footer", "main", "nav", "aside"):
                parts.append(inner_md(child))
            elif tag in ("time",):
                parts.append(child.get_text(strip=True))
            else:
                parts.append(inner_md(child))
    return "".join(parts)


def list_to_md(el, list_type="ul"):
    lines = []
    for i, li in enumerate(el.find_all("li", recursive=False), 1):
        inner = inner_md(li).strip()
        if list_type == "ol":
            lines.append(f"{i}. {inner}")
        else:
            lines.append(f"- {inner}")
    return "\n".join(lines)


def table_to_md(el):
    rows = el.find_all("tr")
    if not rows:
        return ""
    lines = []
    for i, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        line = "| " + " | ".join(text(c) for c in cells) + " |"
        lines.append(line)
        if i == 0:
            sep = "| " + " | ".join("---" for _ in cells) + " |"
            lines.append(sep)
    return "\n".join(lines) + "\n\n"


def extract_characteristics(sidebar):
    """Extract the Characteristics sidebar block to markdown."""
    content = sidebar.find("div", class_="sidebar--content")
    if not content:
        return ""
    lines = ["## Characteristics\n"]
    for block in content.find_all("div", class_="mb-4"):
        label_el = block.find("h6")
        if not label_el:
            continue
        label = text(label_el)
        # Get all text after the h6
        label_el.decompose()
        value = re.sub(r"\s+", " ", text(block)).strip()
        if value:
            lines.append(f"**{label}:** {value}  ")
    return "\n".join(lines) + "\n\n"


def extract_contacts(article):
    """Extract contact info blocks."""
    contacts = article.find_all("div", class_="contact__info")
    if not contacts:
        return ""
    lines = ["## Contact\n"]
    for c in contacts:
        name_el = c.find("h6", class_="strong")
        role_el = c.find("span", class_="function")
        phone_els = c.find_all("a", href=lambda h: h and h.startswith("tel:"))
        mail_els = c.find_all("a", href=lambda h: h and h.startswith("mailto:"))
        domain_blocks = c.find_all("div", class_="mb-4")

        name = text(name_el) if name_el else ""
        role = text(role_el).strip() if role_el else ""
        phone = text(phone_els[0]) if phone_els else ""
        mail = mail_els[0].get("href", "").replace("mailto:", "") if mail_els else ""

        nwo_domain = ""
        for db in domain_blocks:
            h6 = db.find("h6")
            if h6 and "NWO Domain" in text(h6):
                h6.decompose()
                nwo_domain = re.sub(r"\s+", " ", text(db)).strip()

        if name:
            lines.append(f"**{name}**" + (f", {role}" if role else ""))
        if phone:
            lines.append(f"Phone: {phone}")
        if mail:
            lines.append(f"Email: {mail}")
        if nwo_domain:
            lines.append(f"Domain: {nwo_domain}")
        lines.append("")
    return "\n".join(lines) + "\n"


def process_pane_content(content_el, heading_level=3):
    """Process tab-pane-content direct children: text paragraphs and accordion lists."""
    parts = []
    for child in content_el.children:
        if not isinstance(child, Tag):
            continue
        classes = child.get("class", [])

        if "paragraph--type--text" in classes:
            md = inner_md(child).strip()
            if md:
                parts.append(md + "\n\n")

        elif "paragraph--type--expanders-list" in classes:
            # Process accordion items inside this expanders list
            for acc_item in child.find_all("div", class_="accordion-item", recursive=True):
                # Only process direct accordion items (not nested)
                title_el = acc_item.find("span", class_="accordion-title")
                body_el = acc_item.find("div", class_="accordion-body")
                if not title_el:
                    continue
                acc_title = text(title_el)
                h = "#" * heading_level
                if body_el:
                    # The body may itself contain text paragraphs or nested accordions
                    body_content = process_pane_content(body_el, heading_level + 1)
                    if not body_content:
                        # Fallback: plain inner_md
                        body_content = inner_md(body_el).strip()
                    parts.append(f"{h} {acc_title}\n\n{body_content}\n\n" if body_content else f"{h} {acc_title}\n\n")
                else:
                    parts.append(f"{h} {acc_title}\n\n")

        else:
            # Any other paragraph type — fall back to inner_md
            md = inner_md(child).strip()
            if md:
                parts.append(md + "\n\n")

    return "".join(parts)


def extract_tabs(article):
    """Extract tabbed content (Explore/Prepare/Submit) with accordion sections."""
    call_tabs = article.find("div", class_="call-tabs")
    if not call_tabs:
        return ""

    parts = []

    # Get tab names from nav buttons
    tab_buttons = call_tabs.find_all("button", class_="nav-link")
    tab_names = {}
    for btn in tab_buttons:
        target = btn.get("data-bs-target", "").lstrip("#")
        name_el = btn.find("span", class_="nav-link__text")
        if target and name_el:
            tab_names[target] = text(name_el)

    # Process each tab pane
    for pane in call_tabs.find_all("div", class_="tab-pane"):
        pane_id = pane.get("id", "")
        tab_label = tab_names.get(pane_id, pane_id)

        pane_content = pane.find("div", class_="tab-pane-content")
        if not pane_content:
            continue

        pane_md = process_pane_content(pane_content, heading_level=3)
        if pane_md.strip():
            parts.append(f"## {tab_label}\n\n{pane_md}")

    return "".join(parts)


def extract_tags(article):
    """Extract discipline/topic tags."""
    tag_div = article.find("div", class_="tagLinks")
    if not tag_div:
        return ""
    tags = [text(a) for a in tag_div.find_all("a") if text(a)]
    if tags:
        return "**Tags:** " + ", ".join(tags) + "\n\n"
    return ""


def html_to_md(html_text):
    soup = BeautifulSoup(html_text, "html.parser")

    # Get canonical URL from meta
    canonical = ""
    canon_tag = soup.find("link", rel="canonical")
    if canon_tag:
        canonical = canon_tag.get("href", "")

    article = soup.find("article", id="main-content")
    if not article:
        # Fallback: convert whole body
        body = soup.find("body") or soup
        return inner_md(body)

    # Title
    title_el = article.find("h1", class_="articleHead__title")
    title = text(title_el).strip() if title_el else ""

    # Intro
    intro_el = article.find("div", class_="articleHead__intro")
    intro = inner_md(intro_el).strip() if intro_el else ""

    # Characteristics sidebar
    sidebar = article.find("div", class_="col-sidebar")
    characteristics = extract_characteristics(sidebar) if sidebar else ""

    # Contact
    contacts = extract_contacts(article)

    # Main tabbed content
    tabs_content = extract_tabs(article)

    # Tags
    tags = extract_tags(article)

    # Assemble
    parts = []
    if title:
        parts.append(f"# {title}\n\n")
    if canonical:
        parts.append(f"**Source:** {canonical}\n\n")
    if intro:
        parts.append(f"{intro}\n\n")
    if characteristics:
        parts.append(characteristics)
    if tabs_content:
        parts.append(tabs_content)
    if tags:
        parts.append(tags)
    if contacts:
        parts.append(contacts)

    md = "".join(parts)

    # Clean up excessive blank lines
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert NWO grant HTML files to Markdown.")
    parser.add_argument("input", nargs="?", help="Single HTML file (omit for batch mode)")
    parser.add_argument("output", nargs="?", help="Output .md file (single-file mode only)")
    parser.add_argument("--refresh", action="store_true", help="Re-convert all files even if MD exists")
    args = parser.parse_args()

    if args.input:
        # Single-file mode
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Error: {input_path} not found", file=sys.stderr)
            sys.exit(1)
        md = html_to_md(input_path.read_text(encoding="utf-8"))
        if args.output:
            Path(args.output).write_text(md, encoding="utf-8")
            print(f"Written to {args.output}")
        else:
            print(md)
    else:
        # Batch mode: html/*.html -> md/*.md
        HTML_DIR = Path("html")
        MD_DIR   = Path("md")
        MD_DIR.mkdir(exist_ok=True)

        html_files = sorted(HTML_DIR.glob("*.html"))
        converted = skipped = failed = 0
        for html_path in html_files:
            md_path = MD_DIR / (html_path.stem + ".md")
            if md_path.exists() and not args.refresh:
                skipped += 1
                continue
            try:
                md = html_to_md(html_path.read_text(encoding="utf-8"))
                md_path.write_text(md, encoding="utf-8")
                converted += 1
            except Exception as e:
                print(f"ERROR {html_path.name}: {e}", file=sys.stderr)
                failed += 1

        print(f"Done. Converted: {converted}, Skipped: {skipped}, Failed: {failed}")
