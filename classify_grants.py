#!/usr/bin/env python3
"""Classify NWO grants by eligible position and field using Claude Haiku."""

import argparse
import json
import os
import sys
import time

POSITIONS = [
    "PhD candidate",
    "Postdoc",
    "Assistant professor",
    "Associate professor",
    "Full professor",
    "Lector (HBO)",
    "Non-academic",
    "Any researcher",
]

FIELDS = [
    "Physics & Astronomy",
    "Chemistry",
    "Mathematics & Computer Science",
    "Biology & Life Sciences",
    "Earth & Environmental Sciences",
    "Engineering & Technology",
    "Medical & Health Sciences",
    "Social Sciences",
    "Humanities & Arts",
    "Law & Governance",
    "Economics & Business",
    "Agriculture & Food",
    "Education",
]

SYSTEM = f"""\
You classify NWO (Dutch Research Council) grant calls. Return a JSON object with these fields:

1. **can_lead** — which positions can be the main applicant / PI. List from:
{json.dumps(POSITIONS)}

2. **can_participate** — which positions can be a co-applicant, consortium member, or team member \
(always a superset of can_lead). Same vocabulary as above.

3. **fields** — a dict mapping EACH of the following fields to a relevance score 0–10:
{json.dumps(FIELDS)}
   - 10 = the grant explicitly targets this field
   - 7–9 = strongly relevant (e.g. biodiversity → Biology 9, Chemistry 6)
   - 4–6 = moderately relevant, not excluded
   - 1–3 = tangentially relevant at best
   - 0 = clearly irrelevant or excluded
   If the grant is open to all disciplines, give all fields 8–10.
   If the grant targets a specific NWO domain (Science/ENW, SSH, AES/TTW, ZonMw/Health), \
score fields within that domain 8–10 and others lower.

4. **international** — boolean: can researchers based outside the Netherlands apply \
(as main applicant)? Default false if unclear.

5. **max_years_post_phd** — integer or null: maximum years since PhD if restricted \
(e.g. Veni=3, Vidi=8). null if no upper limit.

6. **min_years_post_phd** — integer or null: minimum years since PhD if restricted \
(e.g. "obtained PhD at least 5 years ago" → 5). null if no lower limit.

Rules:
- For can_lead: "Any researcher" means no position restriction at all.
- For consortium/collaboration grants: the main applicant typically needs tenure/tenure-track, \
but co-applicants may include postdocs or PhD candidates — reflect this in can_participate.
- "Lector (HBO)" is for grants that explicitly mention HBO / universities of applied sciences.
- "Non-academic" is for grants allowing industry, NGO, museum, or hospital staff as applicants.
- can_participate must be a superset of can_lead.

Respond with ONLY the JSON object, no other text."""


def grant_text(g: dict) -> str:
    """Build the text to send to the LLM."""
    parts = [f"Title: {g.get('title', '')}"]
    ft = g.get("finance_type", "")
    if ft:
        parts.append(f"Finance type: {ft}")
    sections = g.get("sections", {})
    for key in ("purpose", "who_can_apply", "what_to_apply_for"):
        sec = sections.get(key)
        if isinstance(sec, dict) and sec.get("text"):
            parts.append(f"{key}: {sec['text'][:1500]}")
    return "\n\n".join(parts)


def validate(result: dict) -> dict:
    """Ensure result conforms to schema."""
    result["can_lead"] = [p for p in result.get("can_lead", []) if p in POSITIONS]
    result["can_participate"] = [p for p in result.get("can_participate", []) if p in POSITIONS]
    if not result["can_lead"]:
        result["can_lead"] = ["Any researcher"]
    # can_participate must be superset of can_lead
    for p in result["can_lead"]:
        if p not in result["can_participate"]:
            result["can_participate"].append(p)
    if not result["can_participate"]:
        result["can_participate"] = ["Any researcher"]

    # Fields: ensure all fields present with int scores 0-10
    fields = result.get("fields", {})
    if isinstance(fields, list):
        # LLM returned a list instead of dict — treat as 10 for named, 0 for others
        named = set(fields)
        fields = {f: (10 if f in named else 0) for f in FIELDS}
    validated_fields = {}
    for f in FIELDS:
        score = fields.get(f, 0)
        validated_fields[f] = max(0, min(10, int(score) if isinstance(score, (int, float)) else 0))
    result["fields"] = validated_fields

    result["international"] = bool(result.get("international", False))

    for key in ("max_years_post_phd", "min_years_post_phd"):
        yrs = result.get(key)
        result[key] = int(yrs) if isinstance(yrs, (int, float)) and yrs else None
    # Remove old key if present
    result.pop("career_years_post_phd", None)

    return result


def classify_batch(grants: list[dict], api_key: str, path: str, force: bool = False) -> int:
    """Classify grants that don't have tags yet. Saves after each grant."""
    try:
        import anthropic
    except ImportError:
        print("pip install anthropic", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    classified = 0

    for i, g in enumerate(grants):
        if not force and "ai_classification" in g:
            continue

        text = grant_text(g)
        for attempt in range(3):
            try:
                resp = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=512,
                    system=SYSTEM,
                    messages=[{"role": "user", "content": text}],
                )
                raw = resp.content[0].text.strip()
                # Strip markdown code fences if present
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                result = validate(json.loads(raw))
                g["ai_classification"] = result
                classified += 1
                top_fields = [f for f, s in result["fields"].items() if s >= 7]
                print(
                    f"  [{i+1}/{len(grants)}] {g['title'][:55]}"
                    f"  lead={result['can_lead']}"
                    f"  fields={top_fields}"
                )
                # Save after each successful classification
                with open(path, "w") as f:
                    json.dump(grants, f, indent=2, ensure_ascii=False)
                break
            except (json.JSONDecodeError, KeyError) as e:
                print(f"  [{i+1}] parse error ({e}), raw={raw[:200]!r}, retry {attempt+1}", file=sys.stderr)
                time.sleep(1)
            except Exception as e:
                print(f"  [{i+1}] API error ({e}), retry {attempt+1}", file=sys.stderr)
                time.sleep(2)
        else:
            print(f"  [{i+1}] FAILED: {g['title'][:60]}", file=sys.stderr)

    return classified


def main():
    parser = argparse.ArgumentParser(description="Classify grants with Haiku")
    parser.add_argument("--force", action="store_true", help="Re-classify all grants")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be classified")
    args = parser.parse_args()

    path = "grants.json"
    grants = json.load(open(path))

    to_classify = [g for g in grants if args.force or "ai_classification" not in g]
    print(f"{len(to_classify)} of {len(grants)} grants need classification")

    if args.dry_run or not to_classify:
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Set ANTHROPIC_API_KEY environment variable", file=sys.stderr)
        sys.exit(1)

    n = classify_batch(grants, api_key, path, force=args.force)
    print(f"\nClassified {n} grants → {path}")


if __name__ == "__main__":
    main()
