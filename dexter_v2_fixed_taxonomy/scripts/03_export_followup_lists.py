import argparse
import csv
from pathlib import Path
from typing import Dict, List

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    pass


GK_ZENTRALE_KEYWORDS = [
    "Zentralisierte Entscheidung",
    "Hauptstelle",
    "Zentrale",
    "Verwaltung",
    "Träger",
]

DM_ZENTRALE_KEYWORDS = [
    "Entscheidung zentralisiert",
    "zentral",
    "Verwaltung",
    "Träger",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export follow-up lists (Zentrale + unknown system).")
    p.add_argument("--in", dest="inp", required=True, help="Input journey_classifications.csv")
    p.add_argument("--outdir", required=True, help="Output directory")
    return p.parse_args()


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def is_zentrale(row: Dict[str, str]) -> bool:
    label = (row.get("category_label") or "").lower()
    # simple keyword match
    for kw in GK_ZENTRALE_KEYWORDS + DM_ZENTRALE_KEYWORDS:
        if kw.lower() in label:
            return True
    return False


def main() -> None:
    args = parse_args()
    in_path = Path(args.inp)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rows = read_csv(in_path)

    zentrale = [r for r in rows if is_zentrale(r)]
    unknown_system = [r for r in rows if (r.get("system_in_use") or "").strip().lower() in {"", "unknown", "unk", "n/a"}]

    fields = [
        "phone",
        "campaign_name",
        "role",
        "category_label",
        "category_confidence",
        "evidence_quote",
        "system_in_use",
        "system_evidence_quote",
        "notes",
    ]

    out_z = outdir / "zentrale_followup.csv"
    with out_z.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in zentrale:
            w.writerow({k: r.get(k, "") for k in fields})

    out_u = outdir / "system_unknown_followup.csv"
    with out_u.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in unknown_system:
            w.writerow({k: r.get(k, "") for k in fields})

    print("Wrote:", out_z)
    print("Wrote:", out_u)
    print(f"Zentrale rows: {len(zentrale)} | Unknown system rows: {len(unknown_system)}")


if __name__ == "__main__":
    main()

