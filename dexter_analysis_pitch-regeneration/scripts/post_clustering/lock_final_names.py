import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description="Lock final taxonomy names from LLM candidates and coverage")
    p.add_argument("--run", required=True, help="Run directory path")
    p.add_argument("--base", required=True, help="Base name of slim CSV (under run/slim)")
    args = p.parse_args()

    run = Path(args.run)
    base = args.base

    cands_path = run / "taxonomy" / "cluster_label_candidates.jsonl"
    map_path = run / "taxonomy" / "cluster_to_reason_label.csv"
    clusters_path = run / "clusters_pass1.csv"
    slim_path = run / "slim" / f"{base}.csv"

    # Load candidates
    cands = [json.loads(l) for l in open(cands_path, encoding="utf-8") if l.strip()]

    # Load mapping cluster_id -> source_reason_label
    cid2label_src = {
        int(r["cluster_id"]): r["reason_label"]
        for r in csv.DictReader(open(map_path, encoding="utf-8"))
        if r.get("cluster_id") and r.get("reason_label")
    }

    # Load cluster assignments (row_id -> cluster_id)
    labels = list(csv.DictReader(open(clusters_path, encoding="utf-8")))
    row2cid = {r["row_id"]: int(r["cluster_id"]) for r in labels if r.get("row_id") and r.get("cluster_id")}

    # Load slim to compute coverage per source label
    slim = list(csv.DictReader(open(slim_path, encoding="utf-8")))
    label_counts: Counter[str] = Counter()
    for r in slim:
        cid = row2cid.get(r.get("row_id", ""), -1)
        if cid in cid2label_src:
            label_counts[cid2label_src[cid]] += 1

    # Build final map source_reason_label -> chosen final label + meta
    finals = []
    for item in cands:
        src = (item.get("source_reason_label", "") or "").strip() or "unknown"
        chosen = (item.get("label_candidates") or ["Unknown"])[0].strip()
        definition = (item.get("definition", "") or "").strip()
        quotes = item.get("example_quotes") or []
        finals.append({
            "source_reason_label": src,
            "chosen_label": chosen,
            "definition": definition,
            "example_quotes": " | ".join(quotes),
            "count": label_counts[src],
        })

    # Order by coverage (count desc)
    finals.sort(key=lambda x: -x["count"])

    # Assign reason_label_id R01.. by this order
    for i, f in enumerate(finals, start=1):
        f["reason_label_id"] = f"R{i:02d}"

    # Write taxonomy_reasons_v1.csv
    out_tax = run / "taxonomy" / "taxonomy_reasons_v1.csv"
    out_tax.parent.mkdir(parents=True, exist_ok=True)
    with open(out_tax, "w", newline="", encoding="utf-8") as g:
        w = csv.DictWriter(g, fieldnames=["reason_label_id","reason_label","definition","example_quotes","coverage_count"])
        w.writeheader()
        for f in finals:
            w.writerow({
                "reason_label_id": f["reason_label_id"],
                "reason_label": f["chosen_label"],
                "definition": f["definition"],
                "example_quotes": f["example_quotes"],
                "coverage_count": f["count"],
            })

    # Write mapping source_reason_label -> reason_label_id, reason_label
    out_map = run / "taxonomy" / "source_to_final_label.csv"
    with open(out_map, "w", newline="", encoding="utf-8") as g:
        w = csv.DictWriter(g, fieldnames=["source_reason_label","reason_label_id","reason_label"])
        w.writeheader()
        for f in finals:
            w.writerow({
                "source_reason_label": f["source_reason_label"],
                "reason_label_id": f["reason_label_id"],
                "reason_label": f["chosen_label"],
            })

    print("Wrote:", out_tax)
    print("Wrote:", out_map)


if __name__ == "__main__":
    main()


