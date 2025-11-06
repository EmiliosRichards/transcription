import argparse
import csv
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description="Export discovery_labeled.csv by joining final taxonomy labels")
    p.add_argument("--run", required=True, help="Run directory path")
    p.add_argument("--base", required=True, help="Base name of slim CSV (under run/slim)")
    args = p.parse_args()

    run = Path(args.run)
    base = args.base

    clusters_path = run / "clusters_pass1.csv"
    final_map_path = run / "taxonomy" / "cluster_to_reason_label_final.csv"
    slim_path = run / "slim" / f"{base}.csv"
    outp = run / "outputs" / "discovery_labeled.csv"

    clu = {r["row_id"]: int(r["cluster_id"]) for r in csv.DictReader(open(clusters_path, encoding="utf-8")) if r.get("row_id") and r.get("cluster_id")}
    final_map = {
        int(r["cluster_id"]): (r["reason_label_id"], r["reason_label"])
        for r in csv.DictReader(open(final_map_path, encoding="utf-8"))
        if r.get("cluster_id")
    }
    rows = list(csv.DictReader(open(slim_path, encoding="utf-8")))

    outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", newline="", encoding="utf-8") as g:
        w = csv.DictWriter(g, fieldnames=[
            "row_id","phone","campaign_name",
            "outcome_free_text","reason_free_text",
            "reason_label_id","reason_label","confidence",
        ])
        w.writeheader()
        labeled = 0
        for r in rows:
            cid = clu.get(r.get("row_id", ""), -1)
            rid, rname = final_map.get(cid, ("R00", "Other"))
            if rid != "R00":
                labeled += 1
            w.writerow({
                "row_id": r.get("row_id", ""),
                "phone": r.get("phone", ""),
                "campaign_name": r.get("campaign_name", ""),
                "outcome_free_text": r.get("outcome_free_text", ""),
                "reason_free_text": r.get("reason_free_text", ""),
                "reason_label_id": rid,
                "reason_label": rname,
                "confidence": r.get("confidence", ""),
            })

    print("Wrote:", outp)
    print("Label coverage:", f"{labeled}/{len(rows)} = {labeled/len(rows):.1%}")


if __name__ == "__main__":
    main()


