import argparse
import csv
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate pitch drafts from category templates (placeholder-friendly).")
    p.add_argument("--in", dest="inp", required=True, help="Input journey_classifications.csv")
    p.add_argument("--templates", required=True, help="CSV with templates (role, category_label, template)")
    p.add_argument("--out", required=True, help="Output pitch_drafts.csv")
    return p.parse_args()


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_templates(path: Path) -> Dict[Tuple[str, str], str]:
    rows = read_csv(path)
    m: Dict[Tuple[str, str], str] = {}
    for r in rows:
        role = (r.get("role") or "").strip().upper()
        label = (r.get("category_label") or "").strip()
        tpl = (r.get("template") or "").strip()
        if role and label:
            m[(role, label)] = tpl
    return m


def safe_format(tpl: str, values: Dict[str, str]) -> str:
    # Minimal safe formatter (only replace known placeholders)
    out = tpl
    for k, v in values.items():
        out = out.replace("{" + k + "}", v)
    return out


def main() -> None:
    args = parse_args()
    in_path = Path(args.inp)
    tpl_path = Path(args.templates)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = read_csv(in_path)
    templates = load_templates(tpl_path)

    out_rows: List[Dict[str, str]] = []
    for r in rows:
        role = (r.get("role") or "UNKNOWN").strip().upper()
        label = (r.get("category_label") or "Other/Unclear").strip()
        tpl = templates.get((role, label)) or templates.get((role, "Other/Unclear")) or "TODO"
        pitch = safe_format(
            tpl,
            {
                "phone": (r.get("phone") or "").strip(),
                "campaign_name": (r.get("campaign_name") or "").strip(),
                "system_in_use": (r.get("system_in_use") or "unknown").strip(),
            },
        )
        out_rows.append(
            {
                "phone": r.get("phone", ""),
                "campaign_name": r.get("campaign_name", ""),
                "role": role,
                "category_label": label,
                "system_in_use": r.get("system_in_use", ""),
                "pitch_text": pitch,
            }
        )

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["phone", "campaign_name", "role", "category_label", "system_in_use", "pitch_text"],
        )
        w.writeheader()
        w.writerows(out_rows)

    print("Wrote:", out_path)


if __name__ == "__main__":
    main()

