"""
04_generate_pitches.py
Generate follow-up pitches by filling templates from the taxonomy
with dynamic fields (date, reference company, reason, etc.).

Usage:
    python scripts/04_generate_pitches.py --run runs/test_run
"""

import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_taxonomy() -> dict:
    with open(ROOT / "config" / "taxonomy.json", encoding="utf-8") as f:
        return json.load(f)


def build_template_lookup(taxonomy: dict) -> dict[str, dict]:
    """Build lookup: category_id -> category dict with templates."""
    lookup = {}
    for cat in taxonomy["gatekeeper"] + taxonomy["decision_maker"]:
        lookup[cat["id"]] = cat
    return lookup


_FACILITY_PREFIXES = re.compile(
    r"^(Diakonisches\s+Seniorenzentrum|Diakoniezentrum|"
    r"Seniorenzentrum|Seniorenheim|Seniorenresidenz|Seniorenstift|"
    r"Seniorenpflegeheim|Altenpflegeheim|Altenheim|Alten-\s*und\s+Pflegeheim|"
    r"Pflegeheim)\s+",
    re.IGNORECASE,
)

# "Haus X" as a standalone prefix (not "Xhaus" compound words)
_HAUS_PREFIX = re.compile(r"^Haus\s+", re.IGNORECASE)


def _name_after_haus(ref_name: str) -> str:
    """Strip facility-type prefixes so 'Haus Seniorenzentrum X' doesn't happen.
    Applies repeatedly to handle 'Diakonisches Seniorenzentrum Haus Lehmgruben'."""
    if not ref_name:
        return ref_name
    result = _FACILITY_PREFIXES.sub("", ref_name).strip()
    result = _HAUS_PREFIX.sub("", result).strip()
    return result or ref_name  # fallback to original if everything got stripped


def fill_template(
    template: str,
    last_call_date: str,
    ref_einrichtung: str,
    ref_ort: str,
    reason_summary: str,
    contact_name: str | None = None,
    ref_proximity: str = "nah",
) -> str:
    """Fill placeholders in a pitch template."""
    if not template:
        return ""

    # Date placeholders (various casings)
    result = re.sub(r"\[datum\]", last_call_date or "[Datum]", template, flags=re.IGNORECASE)
    result = re.sub(r"\[Datum\]", last_call_date or "[Datum]", result)

    # Reference company — use short name after "Haus" / "das Haus" to avoid
    # "dem Haus Seniorenzentrum St. Josef" → "dem Haus St. Josef"
    ref_short = _name_after_haus(ref_einrichtung) if ref_einrichtung else ""
    ref_full = ref_einrichtung or "[Name Heim]"

    # Templates with "Haus [Name Heim]" or "Haus…" already say "Haus",
    # so insert the short name. Standalone [Name Heim] gets the full name.
    if ref_einrichtung:
        result = re.sub(r"dem Haus…", f"dem {ref_full}", result)
        result = re.sub(r"dem Haus\.\.\.", f"dem {ref_full}", result)
        result = re.sub(r"das Haus\.\.\.", f"das {ref_full}", result)
    result = result.replace("[Name Heim]", ref_short or "[Name Heim]")

    # Location phrasing depends on proximity
    ort = ref_ort or "[Ort]"
    if ref_proximity == "nah":
        result = result.replace("[Ort in der Nähe]", ort)
    else:
        # Distant reference — rewrite proximity language
        # "bei Ihnen in [Ort in der Nähe]" → "in [Ort]"
        result = result.replace(f"bei Ihnen in [Ort in der Nähe]", f"in {ort}")
        result = result.replace("[Ort in der Nähe]", ort)
        result = result.replace("bei Ihnen in der Nähe", f"in {ort}")
        result = result.replace("bei Ihnen um die Ecke in", "ebenfalls in")
        result = result.replace("im Nachbarort", f"in {ort}")

    # Reason placeholder
    result = re.sub(r"\[Grund\]", reason_summary or "[Grund]", result, flags=re.IGNORECASE)

    # Contact person — use name if available, otherwise "der zuständigen Person"
    ap_fallback = "der zuständigen Person"
    ap_name = contact_name if contact_name else ap_fallback
    result = re.sub(r"\[mein AP\]", ap_name, result, flags=re.IGNORECASE)
    result = re.sub(r"\[oder Name\]", ap_name, result, flags=re.IGNORECASE)

    return result


def main():
    parser = argparse.ArgumentParser(description="Generate pitches from templates")
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()

    taxonomy = load_taxonomy()
    lookup = build_template_lookup(taxonomy)

    run_dir = ROOT / args.run if not args.run.is_absolute() else args.run

    # Try to read classifications_with_refs first, fall back to classifications
    input_path = run_dir / "classifications_with_refs.csv"
    if not input_path.exists():
        input_path = run_dir / "classifications.csv"
    if not input_path.exists():
        print(f"ERROR: No classifications file found in {run_dir}")
        return

    with open(input_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"Generating pitches for {len(rows)} contacts...")

    results = []
    pitched = 0
    excluded = 0
    no_template = 0

    for row in rows:
        cat_id = row.get("category_id", "")
        cat_info = lookup.get(cat_id)

        # Determine action
        if not cat_info:
            row["action"] = "no_template"
            row["pitch_text"] = ""
            row["generic_followup"] = ""
            no_template += 1
            results.append(row)
            continue

        if cat_info["action"] == "exclude":
            row["action"] = "raus"
            row["pitch_text"] = ""
            row["generic_followup"] = cat_info.get("answer_template", "")
            excluded += 1
            results.append(row)
            continue

        # Fill template
        pitch = fill_template(
            template=cat_info["answer_template"],
            last_call_date=row.get("last_call_date", ""),
            ref_einrichtung=row.get("ref_einrichtung", ""),
            ref_ort=row.get("ref_ort", ""),
            reason_summary=row.get("reason_summary", ""),
            contact_name=row.get("contact_person_name"),
            ref_proximity=row.get("ref_proximity", "nah"),
        )

        generic = cat_info.get("generic_followup", "")
        # Skip generic if it's just "X" or "X Neu-Anruf" (action marker, not a pitch)
        if generic.strip().startswith("X"):
            generic = ""

        row["action"] = "pitch"
        row["pitch_text"] = pitch
        row["generic_followup"] = generic
        pitched += 1
        results.append(row)

    # Write output
    out_path = run_dir / "pitches.csv"
    fieldnames = list(results[0].keys()) if results else []
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Done! {pitched} pitches, {excluded} excluded, {no_template} no template -> {out_path}")


if __name__ == "__main__":
    main()
