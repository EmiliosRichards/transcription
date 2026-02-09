import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _normalize(text: str) -> str:
    s = (text or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _reason_core(reason: str) -> str:
    base = _normalize(reason)
    if not base:
        return ""
    parts = re.split(r"[;:–—\-|]\s*", base, maxsplit=1)
    return (parts[0] or "").strip()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build per-cluster summaries + cluster_to_reason_label mapping")
    p.add_argument("--run", required=True, help="Run directory path")
    p.add_argument("--view", default="clusters_view.csv", help="clusters_view.csv path (relative to run)")
    p.add_argument("--out", default="reports/cluster_summaries.jsonl", help="Output JSONL path (relative to run)")
    p.add_argument("--map-out", default="taxonomy/cluster_to_reason_label.csv", help="Output CSV mapping path (relative to run)")
    p.add_argument("--examples", type=int, default=8, help="How many examples per cluster to include")
    p.add_argument("--min-size", type=int, default=5, help="Minimum cluster size to include (excluding -1 outliers)")
    p.add_argument("--include-outliers", action="store_true", help="Include cluster_id=-1 in summaries")
    return p.parse_args()


def read_rows(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _prob(row: Dict[str, Any]) -> float:
    try:
        return float(row.get("probability", "") or 0.0)
    except Exception:
        return 0.0


def _conf(row: Dict[str, Any]) -> float:
    try:
        return float(row.get("confidence", "") or 0.0)
    except Exception:
        return 0.0


def main() -> None:
    args = parse_args()
    run = Path(args.run)
    view_path = run / args.view
    out_path = run / args.out
    map_out_path = run / args.map_out

    if not view_path.exists():
        raise SystemExit(f"Missing clusters_view.csv: {view_path}. Run build_clusters_view.py first.")

    rows = read_rows(view_path)
    by_cluster: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        try:
            cid = int(r.get("cluster_id", "-1"))
        except Exception:
            continue
        if cid == -1 and not args.include_outliers:
            continue
        by_cluster[cid].append(r)

    # Summaries
    summaries: List[Dict[str, Any]] = []
    cid2label: Dict[int, str] = {}

    for cid, items in sorted(by_cluster.items(), key=lambda x: (x[0] == -1, -len(x[1]), x[0])):
        size = len(items)
        if cid != -1 and size < args.min_size:
            continue

        # Derive a simple "source label" from the most common reason_core (fallback: reason_free_text)
        cores = [(_reason_core(i.get("reason_free_text", "") or "")) for i in items]
        core_ctr = Counter([c for c in cores if c and c != "unknown"])
        if core_ctr:
            source_label = core_ctr.most_common(1)[0][0]
        else:
            # fallback: most common full reason
            reasons = [(_normalize(i.get("reason_free_text", "") or "")) for i in items]
            reason_ctr = Counter([c for c in reasons if c and c != "unknown"])
            source_label = reason_ctr.most_common(1)[0][0] if reason_ctr else "unknown"

        cid2label[cid] = source_label

        # Pick examples by (probability desc, confidence desc)
        items_sorted = sorted(items, key=lambda r: (_prob(r), _conf(r)), reverse=True)
        ex = []
        for r in items_sorted[: max(1, args.examples)]:
            ex.append(
                {
                    "row_id": r.get("row_id", ""),
                    "probability": r.get("probability", ""),
                    "confidence": r.get("confidence", ""),
                    "reason_free_text": r.get("reason_free_text", ""),
                    "outcome_free_text": r.get("outcome_free_text", ""),
                    "who_reached": r.get("who_reached", ""),
                    "evidence_quote": r.get("evidence_quote", ""),
                }
            )

        summaries.append(
            {
                "cluster_id": cid,
                "size": size,
                "reason_label": source_label,
                "examples": ex,
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as g:
        for s in summaries:
            g.write(json.dumps(s, ensure_ascii=False) + "\n")

    map_out_path.parent.mkdir(parents=True, exist_ok=True)
    with map_out_path.open("w", newline="", encoding="utf-8") as g:
        w = csv.writer(g)
        w.writerow(["cluster_id", "reason_label"])
        for cid, label in sorted(cid2label.items(), key=lambda x: (x[0] == -1, x[0])):
            if cid == -1 and not args.include_outliers:
                continue
            w.writerow([cid, label])

    print("Wrote:", out_path)
    print("Wrote:", map_out_path)


if __name__ == "__main__":
    main()

