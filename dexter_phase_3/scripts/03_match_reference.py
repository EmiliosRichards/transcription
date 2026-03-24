"""
03_match_reference.py
Match each classified contact to the nearest Dexter reference facility
by PLZ (postal code) proximity.

Usage:
    python scripts/03_match_reference.py --run runs/test_run
"""

import argparse
import csv
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    with open(ROOT / "config" / "config.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_referenzen() -> list[dict]:
    refs = []
    with open(ROOT / "config" / "referenzen.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("einrichtung") or row.get("traeger"):
                refs.append(row)
    return refs


def plz_distance(plz_a: str, plz_b: str) -> int:
    """
    Simple PLZ proximity score.
    Lower = closer. Compares PLZ as integers (difference).
    Falls back to prefix matching if one is missing.
    """
    if not plz_a or not plz_b:
        return 999999

    try:
        return abs(int(plz_a) - int(plz_b))
    except ValueError:
        # Fallback: compare prefixes
        shared = 0
        for a, b in zip(plz_a, plz_b):
            if a == b:
                shared += 1
            else:
                break
        return 10 ** (5 - shared)


def find_nearest_reference(
    contact_plz: str,
    contact_system: str | None,
    refs: list[dict],
    prefer_system_match: bool = True,
) -> dict | None:
    """Find the nearest reference facility by PLZ distance.
    Optionally prefer facilities using the same system."""
    if not refs:
        return None
    if not contact_plz:
        # No PLZ available — return a random reference (or None)
        return refs[0] if refs else None

    scored = []
    for ref in refs:
        dist = plz_distance(contact_plz, ref.get("plz", ""))
        # Bonus: prefer same system (reduce distance by 50% if match)
        system_match = False
        if prefer_system_match and contact_system and contact_system.lower() != "unbekannt":
            if ref.get("system", "").lower() == contact_system.lower():
                system_match = True
                dist = int(dist * 0.5)
        scored.append((dist, system_match, ref))

    scored.sort(key=lambda x: (x[0], not x[1]))
    return scored[0][2] if scored else None


def main():
    parser = argparse.ArgumentParser(description="Match contacts to nearest Dexter reference")
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()

    cfg = load_config()
    refs = load_referenzen()
    print(f"Loaded {len(refs)} reference facilities")

    run_dir = ROOT / args.run if not args.run.is_absolute() else args.run
    class_path = run_dir / "classifications.csv"
    if not class_path.exists():
        print(f"ERROR: {class_path} not found. Run 02_classify.py first.")
        return

    # Read classifications (PLZ is already embedded from Dialfire enrichment)
    classifications = []
    with open(class_path, encoding="utf-8") as f:
        classifications = list(csv.DictReader(f))

    # Match references
    results = []
    matched = 0
    for row in classifications:
        contact_plz = row.get("plz", "")
        system = row.get("system_in_use", "unbekannt")

        ref = find_nearest_reference(contact_plz, system, refs)

        row["ref_einrichtung"] = ref["einrichtung"] if ref else ""
        row["ref_ort"] = ref["ort"] if ref else ""
        row["ref_plz"] = ref["plz"] if ref else ""
        row["ref_system"] = ref["system"] if ref else ""
        row["ref_traeger"] = ref["traeger"] if ref else ""
        row["contact_plz"] = contact_plz

        if ref and contact_plz:
            matched += 1

        results.append(row)

    # Write output
    out_path = run_dir / "classifications_with_refs.csv"
    fieldnames = list(results[0].keys()) if results else []
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    no_plz = sum(1 for r in results if not r.get("contact_plz"))
    print(f"Matched {matched}/{len(results)} contacts with PLZ-based references -> {out_path}")
    if no_plz:
        print(f"  {no_plz} contacts had no PLZ (got default reference)")


if __name__ == "__main__":
    main()
