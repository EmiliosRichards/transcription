import argparse
import csv
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description="Build final cluster→reason label mapping")
    p.add_argument("--run", required=True, help="Run directory path")
    args = p.parse_args()

    run = Path(args.run)
    cid_src_path = run / "taxonomy" / "cluster_to_reason_label.csv"
    src_final_path = run / "taxonomy" / "source_to_final_label.csv"
    outp = run / "taxonomy" / "cluster_to_reason_label_final.csv"

    # Load cluster -> source_reason_label
    cid2src = {
        int(r["cluster_id"]): r["reason_label"]
        for r in csv.DictReader(open(cid_src_path, encoding="utf-8"))
        if r.get("cluster_id") and r.get("reason_label")
    }

    # Load source -> (reason_label_id, reason_label)
    src2final: dict[str, tuple[str, str]] = {}
    for r in csv.DictReader(open(src_final_path, encoding="utf-8")):
        src2final[r["source_reason_label"]] = (r["reason_label_id"], r["reason_label"])

    outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", newline="", encoding="utf-8") as g:
        w = csv.writer(g)
        w.writerow(["cluster_id", "reason_label_id", "reason_label"])
        for cid, src in sorted(cid2src.items()):
            rid, rname = src2final.get(src, ("R00", "Other"))
            w.writerow([cid, rid, rname])

    print("Wrote:", outp)


if __name__ == "__main__":
    main()


