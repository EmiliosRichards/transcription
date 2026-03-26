"""
03_match_reference.py
Match each classified contact to the nearest Dexter reference facility
using real geographic distance (km) via PLZ coordinates.

Usage:
    python scripts/03_match_reference.py --run runs/test_run
"""

import argparse
import csv
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Distance threshold: under this = "nah" (can say "bei Ihnen in der Nähe")
NEAR_KM = 50


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


def _build_plz_coords() -> dict[str, tuple[float, float]]:
    """Build PLZ -> (lat, lon) lookup using pgeocode."""
    import pgeocode
    geo = pgeocode.Nominatim("de")
    return geo, {}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in km."""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


class PLZMatcher:
    """Matches contacts to reference facilities by real geographic distance."""

    def __init__(self, refs: list[dict]):
        import pgeocode
        self._geo = pgeocode.Nominatim("de")
        self._cache: dict[str, tuple[float, float] | None] = {}
        # Pre-geocode all reference PLZs
        self.refs_with_coords = []
        for ref in refs:
            coords = self._lookup(ref.get("plz", ""))
            if coords:
                self.refs_with_coords.append((ref, coords))
            else:
                # Keep ref but with None coords (fallback to numeric)
                self.refs_with_coords.append((ref, None))

        geocoded = sum(1 for _, c in self.refs_with_coords if c)
        print(f"  Geocoded {geocoded}/{len(refs)} reference PLZs")

    def _lookup(self, plz: str) -> tuple[float, float] | None:
        if not plz:
            return None
        plz = plz.strip()
        if plz in self._cache:
            return self._cache[plz]
        result = self._geo.query_postal_code(plz)
        if result is not None and not (result.latitude != result.latitude):  # NaN check
            coords = (float(result.latitude), float(result.longitude))
            self._cache[plz] = coords
            return coords
        self._cache[plz] = None
        return None

    def find_nearest(
        self,
        contact_plz: str,
        contact_system: str | None = None,
    ) -> tuple[dict | None, str, float]:
        """Find nearest reference. Returns (ref, proximity, distance_km)."""
        contact_coords = self._lookup(contact_plz)

        if not contact_coords:
            # No PLZ or coords — cannot match, skip reference
            return None, "unknown", 0.0

        scored = []
        for ref, ref_coords in self.refs_with_coords:
            if ref_coords:
                km = _haversine_km(*contact_coords, *ref_coords)
            else:
                km = 9999.0

            # Prefer same system: reduce distance by 30% if match
            system_match = False
            if contact_system and contact_system.lower() != "unbekannt":
                ref_sys = ref.get("system", "").lower()
                if ref_sys and ref_sys in contact_system.lower():
                    system_match = True
                    km = km * 0.7

            scored.append((km, system_match, ref))

        scored.sort(key=lambda x: (x[0], not x[1]))
        best_km, _, best_ref = scored[0]
        proximity = "nah" if best_km <= NEAR_KM else "fern"
        return best_ref, proximity, round(best_km, 1)


def main():
    parser = argparse.ArgumentParser(description="Match contacts to nearest Dexter reference")
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()

    cfg = load_config()
    refs = load_referenzen()
    print(f"Loaded {len(refs)} reference facilities")

    matcher = PLZMatcher(refs)

    run_dir = ROOT / args.run if not args.run.is_absolute() else args.run
    class_path = run_dir / "classifications.csv"
    if not class_path.exists():
        print(f"ERROR: {class_path} not found. Run 02_classify.py first.")
        return

    with open(class_path, encoding="utf-8") as f:
        classifications = list(csv.DictReader(f))

    results = []
    matched = 0
    nah_count = 0
    fern_count = 0

    for row in classifications:
        contact_plz = row.get("plz", "")
        system = row.get("system_in_use", "unbekannt")

        ref, proximity, distance_km = matcher.find_nearest(contact_plz, system)

        row["ref_einrichtung"] = ref["einrichtung"] if ref else ""
        row["ref_ort"] = ref["ort"] if ref else ""
        row["ref_plz"] = ref["plz"] if ref else ""
        row["ref_system"] = ref["system"] if ref else ""
        row["ref_traeger"] = ref["traeger"] if ref else ""
        row["ref_proximity"] = proximity
        row["ref_distance_km"] = distance_km
        row["contact_plz"] = contact_plz

        if ref and contact_plz:
            matched += 1
        if proximity == "nah":
            nah_count += 1
        else:
            fern_count += 1

        results.append(row)

    # Write output
    out_path = run_dir / "classifications_with_refs.csv"
    fieldnames = list(results[0].keys()) if results else []
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    no_plz = sum(1 for r in results if not r.get("contact_plz"))
    print(f"Matched {matched}/{len(results)} contacts -> {out_path}")
    print(f"  Nearby (<={NEAR_KM}km): {nah_count}, Distant: {fern_count}")
    if no_plz:
        print(f"  {no_plz} contacts had no PLZ")


if __name__ == "__main__":
    main()
