import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compress many clusters into a fixed, manageable taxonomy (top-K + Other)."
    )
    p.add_argument("--run", required=True, help="Run directory path")
    p.add_argument("--top-k", type=int, default=20, help="How many categories to keep (excluding R00 Other)")
    p.add_argument(
        "--min-coverage",
        type=float,
        default=None,
        help="Optional coverage target (0..1). If set, selects as many top clusters as needed to reach this coverage.",
    )
    p.add_argument(
        "--summaries",
        default="reports/cluster_summaries.jsonl",
        help="Cluster summaries JSONL (relative to run)",
    )
    p.add_argument(
        "--candidates",
        default="taxonomy/cluster_label_candidates.jsonl",
        help="Optional LLM naming output (relative to run). If missing, uses reason_label from summaries.",
    )
    p.add_argument(
        "--out-taxonomy",
        default="taxonomy/taxonomy_reasons_limited.csv",
        help="Output taxonomy CSV (relative to run)",
    )
    p.add_argument(
        "--out-map",
        default="taxonomy/cluster_to_reason_label_limited.csv",
        help="Output cluster->label mapping CSV (relative to run)",
    )
    return p.parse_args()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def main() -> None:
    args = parse_args()
    run = Path(args.run)
    summaries_path = run / args.summaries
    candidates_path = run / args.candidates
    out_tax = run / args.out_taxonomy
    out_map = run / args.out_map

    if not summaries_path.exists():
        raise SystemExit(f"Missing cluster summaries: {summaries_path}. Run build_cluster_summaries.py first.")

    summaries = load_jsonl(summaries_path)
    # Keep only real clusters (exclude -1) and require size
    clusters: List[Tuple[int, int, str]] = []
    for s in summaries:
        try:
            cid = int(s.get("cluster_id", -1))
        except Exception:
            continue
        if cid == -1:
            continue
        size = int(s.get("size", 0) or 0)
        label = str(s.get("reason_label") or "unknown").strip() or "unknown"
        clusters.append((cid, size, label))

    clusters.sort(key=lambda x: (-x[1], x[0]))
    total = sum(sz for _cid, sz, _ in clusters) or 1

    # Optional: load LLM candidate labels/definitions
    cand_by_cid: Dict[int, Dict[str, Any]] = {}
    if candidates_path.exists():
        for c in load_jsonl(candidates_path):
            try:
                cid = int(c.get("cluster_id"))
            except Exception:
                continue
            cand_by_cid[cid] = c

    selected: List[Tuple[int, int]] = []
    cum = 0
    for cid, sz, _label in clusters:
        if args.min_coverage is not None and (cum / total) >= float(args.min_coverage):
            break
        if len(selected) >= int(args.top_k):
            break
        selected.append((cid, sz))
        cum += sz

    selected_set = {cid for cid, _ in selected}

    # Build taxonomy rows (R00 Other + R01..)
    taxonomy_rows: List[Dict[str, Any]] = []
    taxonomy_rows.append(
        {
            "reason_label_id": "R00",
            "reason_label": "Other",
            "definition": "Long-tail reasons not common enough for a dedicated script.",
            "example_quotes": "",
            "coverage_count": total - cum,
        }
    )

    # Build mapping cluster_id -> (reason_label_id, reason_label)
    mapping_rows: List[Dict[str, Any]] = []
    for i, (cid, sz) in enumerate(selected, start=1):
        rid = f"R{i:02d}"
        summary_label = next((lbl for ccid, _ssz, lbl in clusters if ccid == cid), "unknown")
        cand = cand_by_cid.get(cid, {})
        # Prefer LLM label candidate[0] if available, else use summary-derived label
        cands = cand.get("label_candidates") or []
        chosen_label = (str(cands[0]).strip() if cands else "") or summary_label or f"Cluster {cid}"
        definition = (cand.get("definition") or "").strip()
        quotes = cand.get("example_quotes") or []
        taxonomy_rows.append(
            {
                "reason_label_id": rid,
                "reason_label": chosen_label,
                "definition": definition,
                "example_quotes": " | ".join([str(q).strip() for q in quotes if str(q).strip()]),
                "coverage_count": sz,
            }
        )
        mapping_rows.append({"cluster_id": cid, "reason_label_id": rid, "reason_label": chosen_label})

    out_tax.parent.mkdir(parents=True, exist_ok=True)
    with out_tax.open("w", newline="", encoding="utf-8") as g:
        w = csv.DictWriter(
            g,
            fieldnames=["reason_label_id", "reason_label", "definition", "example_quotes", "coverage_count"],
        )
        w.writeheader()
        w.writerows(taxonomy_rows)

    out_map.parent.mkdir(parents=True, exist_ok=True)
    with out_map.open("w", newline="", encoding="utf-8") as g:
        w = csv.DictWriter(g, fieldnames=["cluster_id", "reason_label_id", "reason_label"])
        w.writeheader()
        w.writerows(mapping_rows)

    print("Wrote:", out_tax)
    print("Wrote:", out_map)
    print(f"Selected clusters: {len(selected_set)}; coverage={cum/total:.1%}; Other={1-(cum/total):.1%}")


if __name__ == "__main__":
    main()

