"""
05_export_final.py
Combine all pipeline outputs into a single clean CSV ready for agents.

Usage:
    python scripts/05_export_final.py --run runs/test_run
"""

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Columns in the final output, in order
OUTPUT_COLUMNS = [
    "phone",
    "campaign_name",
    "firma",
    "ort",
    "plz",
    "ap_vorname",
    "ap_nachname",
    "num_calls",
    "last_call_date",
    "role",
    "category_id",
    "category_label",
    "confidence",
    "action",
    "reason_summary",
    "evidence_quote",
    "system_in_use",
    "contact_person_name",
    "contact_person_role",
    "gatekeeper_name",
    "ref_einrichtung",
    "ref_ort",
    "ref_plz",
    "ref_system",
    "ref_proximity",
    "ref_distance_km",
    "do_not_call",
    "do_not_call_evidence",
    "pitch_text",
    "generic_followup",
    "dialfire_contact_id",
    "dialfire_status",
]


def main():
    parser = argparse.ArgumentParser(description="Export final pipeline CSV")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--exclude-unreachable", action="store_true",
                        help="Remove 'Nicht erreichbar' rows from output")
    args = parser.parse_args()

    run_dir = ROOT / args.run if not args.run.is_absolute() else args.run

    # Read pitches (the most complete file)
    input_path = run_dir / "pitches.csv"
    if not input_path.exists():
        print(f"ERROR: {input_path} not found. Run the full pipeline first.")
        return

    with open(input_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Filter if requested
    if args.exclude_unreachable:
        before = len(rows)
        rows = [r for r in rows if r.get("category_id") != "NONE"]
        print(f"Filtered out {before - len(rows)} unreachable contacts")

    # Clean and reorder columns
    output_rows = []
    for row in rows:
        out = {}
        for col in OUTPUT_COLUMNS:
            out[col] = row.get(col, "")
        output_rows.append(out)

    # Write final CSV
    out_path = run_dir / "final_output.csv"
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)

    # Print summary
    actions = {}
    roles = {}
    for r in output_rows:
        a = r.get("action", "unknown")
        actions[a] = actions.get(a, 0) + 1
        role = r.get("role", "UNKNOWN")
        roles[role] = roles.get(role, 0) + 1

    print(f"\nFinal output: {len(output_rows)} contacts -> {out_path}")
    print(f"Actions: {actions}")
    print(f"Roles: {roles}")

    # Also count categories
    cats = {}
    for r in output_rows:
        cat = r.get("category_label", "")
        cats[cat] = cats.get(cat, 0) + 1
    print(f"\nTop categories:")
    for cat, count in sorted(cats.items(), key=lambda x: -x[1])[:10]:
        print(f"  {count:4d}  {cat}")


if __name__ == "__main__":
    main()
