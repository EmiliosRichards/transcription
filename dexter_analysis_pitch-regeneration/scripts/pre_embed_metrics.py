import json, csv, argparse
from pathlib import Path
from collections import Counter


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute pre-embedding metrics")
    parser.add_argument("--src", required=True, help="Path to slim/dexter_free_extraction_slim_reachable_conf05.csv")
    parser.add_argument("--out", required=True, help="Path to reports/pre_embed_metrics.json")
    parser.add_argument("--gk", default=None, help="Path to slim/dexter_free_extraction_slim_reachable_gk.csv")
    parser.add_argument("--dm", default=None, help="Path to slim/dexter_free_extraction_slim_reachable_dm.csv")
    args = parser.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    stats = {
        "n_rows": 0,
        "n_unique_reasons": 0,
        "top10_share": 0.0,
        "top10": [],
        "who_split": {"gatekeeper": 0, "decision_maker": 0, "unknown": 0},
    }

    reasons = []
    with src.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            stats["n_rows"] += 1
            reasons.append((row.get("reason_free_text") or "").strip().lower())

    cnt = Counter([x for x in reasons if x and x != "unknown"])
    stats["n_unique_reasons"] = len(cnt)
    if stats["n_rows"] > 0 and cnt:
        top10_items = cnt.most_common(10)
        top10_sum = sum(v for _, v in top10_items)
        stats["top10_share"] = round(top10_sum / max(1, sum(cnt.values())), 4)
        stats["top10"] = [{"reason": k, "count": v} for k, v in top10_items]

    # GK/DM/Unknown split from provided slim files (counts of rows)
    def count_rows(p: str) -> int:
        if not p:
            return 0
        path = Path(p)
        if not path.exists():
            return 0
        c = 0
        with path.open("r", encoding="utf-8") as f:
            r = csv.reader(f)
            next(r, None)  # header
            for _ in r:
                c += 1
        return c

    stats["who_split"]["gatekeeper"] = count_rows(args.gk) if args.gk else 0
    stats["who_split"]["decision_maker"] = count_rows(args.dm) if args.dm else 0
    # Unknown is not a separate file; compute as remainder if desired. Here we leave unknown as 0.

    with out.open("w", encoding="utf-8") as g:
        json.dump(stats, g, ensure_ascii=False, indent=2)
    print("Wrote:", out)


if __name__ == "__main__":
    main()
