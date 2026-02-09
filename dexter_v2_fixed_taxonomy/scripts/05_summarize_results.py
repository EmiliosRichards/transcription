import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Summarize journey classifications (category counts, unknowns, systems).")
    p.add_argument("--in", dest="inp", required=True, help="Input journey_classifications.csv")
    p.add_argument("--out", default=None, help="Optional output JSON path for summary")
    return p.parse_args()


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    args = parse_args()
    in_path = Path(args.inp)
    rows = read_csv(in_path)

    by_role = Counter((r.get("role") or "UNKNOWN").strip().upper() for r in rows)
    by_cat = Counter(((r.get("role") or "UNKNOWN").strip().upper(), (r.get("category_label") or "Other/Unclear").strip()) for r in rows)
    by_cat_id = Counter(((r.get("role") or "UNKNOWN").strip().upper(), (r.get("category_id") or "").strip()) for r in rows)
    sys_ctr = Counter((r.get("system_in_use") or "unknown").strip().lower() for r in rows)
    unknown_cat = sum(1 for r in rows if (r.get("category_label") or "").strip() in {"Other/Unclear", ""})
    unknown_sys = sum(1 for r in rows if (r.get("system_in_use") or "").strip().lower() in {"", "unknown", "unk", "n/a"})

    def _int(x: str) -> int:
        try:
            return int(float((x or "").strip() or 0))
        except Exception:
            return 0

    tok_prompt = sum(_int(r.get("usage_prompt_tokens") or "") for r in rows)
    tok_comp = sum(_int(r.get("usage_completion_tokens") or "") for r in rows)
    tok_total = sum(_int(r.get("usage_total_tokens") or "") for r in rows)
    tok_cached = sum(_int(r.get("usage_cached_tokens") or "") for r in rows)
    tok_reason = sum(_int(r.get("usage_reasoning_tokens") or "") for r in rows)

    summary = {
        "n_rows": len(rows),
        "role_counts": dict(by_role),
        "unknown_category_rows": unknown_cat,
        "unknown_category_rate": round(unknown_cat / max(1, len(rows)), 4),
        "unknown_system_rows": unknown_sys,
        "unknown_system_rate": round(unknown_sys / max(1, len(rows)), 4),
        "token_usage": (
            {
                "prompt_tokens": tok_prompt,
                "completion_tokens": tok_comp,
                "total_tokens": tok_total,
                "cached_tokens": tok_cached,
                "reasoning_tokens": tok_reason,
                "avg_total_tokens_per_row": round(tok_total / max(1, len(rows)), 2),
            }
            if tok_total
            else None
        ),
        "top_categories": [
            {"role": role, "category_label": cat, "count": c}
            for (role, cat), c in by_cat.most_common(25)
        ],
        "all_category_counts": [
            {"role": role, "category_label": cat, "count": c}
            for (role, cat), c in sorted(by_cat.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1]))
        ],
        "all_category_id_counts": [
            {"role": role, "category_id": cid, "count": c}
            for (role, cid), c in sorted(by_cat_id.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1]))
        ],
        "top_systems": [{"system_in_use": k, "count": v} for k, v in sys_ctr.most_common(15)],
    }

    print("Rows:", summary["n_rows"])
    print("Roles:", summary["role_counts"])
    print("Unknown category rate:", summary["unknown_category_rate"])
    print("Unknown system rate:", summary["unknown_system_rate"])
    if summary.get("token_usage"):
        tu = summary["token_usage"]
        print("Token usage total:", tu["total_tokens"], "| avg per row:", tu["avg_total_tokens_per_row"])
    print("\nTop categories:")
    for it in summary["top_categories"][:10]:
        print(f"- {it['role']} | {it['category_label']} = {it['count']}")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\nWrote summary:", out_path)


if __name__ == "__main__":
    main()

