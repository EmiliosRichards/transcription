import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional


def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def compute_row_id(phone: str, campaign: str, selected_ts: str) -> str:
    phone = (phone or "").strip()
    campaign = (campaign or "").strip()
    selected_ts = (selected_ts or "").strip()
    if not (phone or campaign or selected_ts):
        return ""
    return sha1_hex(f"{phone}|{campaign}|{selected_ts}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Join clusters_pass1.csv with raw extraction to build clusters_view.csv")
    p.add_argument("--run", required=True, help="Run directory path")
    p.add_argument("--raw", default="raw/dexter_free_extraction.jsonl", help="Raw extraction JSONL path (relative to run)")
    p.add_argument("--clusters", default="clusters_pass1.csv", help="Clusters CSV path (relative to run)")
    p.add_argument("--out", default="clusters_view.csv", help="Output CSV path (relative to run)")
    return p.parse_args()


def load_raw_by_row_id(raw_path: Path) -> Dict[str, Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    with raw_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            phone = str(o.get("phone") or "")
            campaign = str(o.get("campaign_name") or "")
            selected_ts = str(o.get("selected_call_started") or "")
            rid = compute_row_id(phone, campaign, selected_ts)
            if not rid:
                continue
            by_id[rid] = o
    return by_id


def main() -> None:
    args = parse_args()
    run = Path(args.run)
    raw_path = run / args.raw
    clusters_path = run / args.clusters
    out_path = run / args.out

    if not raw_path.exists():
        raise SystemExit(f"Missing raw extraction JSONL: {raw_path}")
    if not clusters_path.exists():
        raise SystemExit(f"Missing clusters CSV: {clusters_path}")

    raw_map = load_raw_by_row_id(raw_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "row_id",
        "cluster_id",
        "probability",
        "phone",
        "campaign_name",
        "selected_call_started",
        "latest_started",
        "num_calls_in_group",
        "outcome_free_text",
        "reason_free_text",
        "who_reached",
        "confidence",
        "evidence_quote",
        "_evidence_mismatch",
        "model",
        "run_ts",
    ]

    with clusters_path.open("r", encoding="utf-8") as cf, out_path.open("w", newline="", encoding="utf-8") as out:
        r = csv.DictReader(cf)
        w = csv.DictWriter(out, fieldnames=fields)
        w.writeheader()
        for row in r:
            rid = (row.get("row_id") or "").strip()
            if not rid:
                continue
            raw = raw_map.get(rid, {})
            w.writerow(
                {
                    "row_id": rid,
                    "cluster_id": (row.get("cluster_id") or "").strip(),
                    "probability": (row.get("probability") or "").strip(),
                    "phone": (raw.get("phone") or "").strip(),
                    "campaign_name": (raw.get("campaign_name") or "").strip(),
                    "selected_call_started": (raw.get("selected_call_started") or "").strip(),
                    "latest_started": (raw.get("latest_started") or "").strip(),
                    "num_calls_in_group": raw.get("num_calls_in_group", ""),
                    "outcome_free_text": (raw.get("outcome_free_text") or "").strip(),
                    "reason_free_text": (raw.get("reason_free_text") or "").strip(),
                    "who_reached": (raw.get("who_reached") or "").strip(),
                    "confidence": raw.get("confidence", ""),
                    "evidence_quote": (raw.get("evidence_quote") or "").strip(),
                    "_evidence_mismatch": raw.get("_evidence_mismatch", ""),
                    "model": (raw.get("model") or "").strip(),
                    "run_ts": (raw.get("run_ts") or "").strip(),
                }
            )

    print("Wrote:", out_path)
    print("Note: rows missing in raw extraction will have blank fields (except row_id/cluster/probability).")


if __name__ == "__main__":
    main()

