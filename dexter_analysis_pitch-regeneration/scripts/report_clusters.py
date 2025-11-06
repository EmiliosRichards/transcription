import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as g:
        w = csv.DictWriter(g, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as g:
        for r in rows:
            g.write(json.dumps(r, ensure_ascii=False) + "\n")


def build_cluster_sizes(rows: list[dict]) -> tuple[list[tuple[int, int]], list[dict]]:
    total = len(rows)
    labels = []
    for r in rows:
        val = r.get("cluster_id")
        if val is None or val == "":
            continue
        try:
            cid = int(val)
        except ValueError:
            continue
        if cid != -1:
            labels.append(cid)

    ctr = Counter(labels)
    top = sorted(ctr.items(), key=lambda x: x[1], reverse=True)

    cum, out = 0, []
    for cid, sz in top:
        cum += sz
        out.append({
            "cluster_id": cid,
            "size": sz,
            "cum_coverage_pct": round(100 * cum / total, 1),
        })
    return top, out


def build_coverage_curve(sorted_sizes: list[tuple[int, int]], total: int) -> list[dict]:
    curve = []
    cum = 0
    for rank, (_, sz) in enumerate(sorted_sizes, start=1):
        cum += sz
        curve.append({
            "top_k": rank,
            "cum_coverage_pct": round(100 * cum / total, 2),
        })
    return curve


def top_examples(view_rows: list[dict], top_cluster_ids: list[int], per_cluster: int = 5) -> list[dict]:
    by_cluster: dict[int, list[tuple[float, dict]]] = defaultdict(list)
    for r in view_rows:
        try:
            cid = int(r.get("cluster_id", "-1"))
        except ValueError:
            continue
        if cid == -1:
            continue
        prob_raw = r.get("probability", "")
        try:
            prob = float(prob_raw) if prob_raw != "" else 0.0
        except ValueError:
            prob = 0.0
        by_cluster[cid].append((prob, r))

    examples: list[dict] = []
    for cid in top_cluster_ids:
        items = by_cluster.get(cid, [])
        items.sort(key=lambda x: x[0], reverse=True)
        pick = [x[1] for x in items[:per_cluster]]
        for r in pick:
            examples.append({
                "cluster_id": cid,
                "probability": r.get("probability", ""),
                "confidence": r.get("confidence", ""),
                "reason_free_text": r.get("reason_free_text", ""),
                "outcome_free_text": r.get("outcome_free_text", ""),
                "who_reached": r.get("who_reached", ""),
                "evidence_quote": r.get("evidence_quote", ""),
                "row_id": r.get("row_id", ""),
            })
    return examples


def main() -> None:
    parser = argparse.ArgumentParser(description="Report cluster sizes, coverage, and top examples")
    parser.add_argument("--run", required=True, help="Run directory path (contains clusters_pass1.csv)")
    parser.add_argument("--top-k", type=int, default=12, help="How many top clusters to summarize")
    parser.add_argument("--examples-per-cluster", type=int, default=5, help="Examples per cluster")
    args = parser.parse_args()

    run = Path(args.run)
    reports = run / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    clusters_csv = run / "clusters_pass1.csv"
    rows = read_csv(clusters_csv)

    sorted_sizes, size_rows = build_cluster_sizes(rows)
    write_csv(reports / "cluster_sizes.csv", size_rows, ["cluster_id", "size", "cum_coverage_pct"])
    print("Wrote", reports / "cluster_sizes.csv")

    total = len(rows)
    curve = build_coverage_curve(sorted_sizes, total)
    write_csv(reports / "coverage_curve.csv", curve, ["top_k", "cum_coverage_pct"])
    print("Wrote", reports / "coverage_curve.csv")

    view_path = run / "clusters_view.csv"
    if view_path.exists():
        view_rows = read_csv(view_path)
        top_ids = [cid for cid, _ in sorted_sizes[: args.top_k]]
        examples = top_examples(view_rows, top_ids, per_cluster=args.examples_per_cluster)
        if examples:
            fields = [
                "cluster_id",
                "probability",
                "confidence",
                "reason_free_text",
                "outcome_free_text",
                "who_reached",
                "evidence_quote",
                "row_id",
            ]
            write_csv(reports / "top_examples.csv", examples, fields)
            write_jsonl(reports / "top_examples.jsonl", examples)
            print("Wrote", reports / "top_examples.csv")
            print("Wrote", reports / "top_examples.jsonl")
        else:
            print("No examples written: clusters_view.csv found but no matching clusters/examples.")
    else:
        print("clusters_view.csv not found; skipping top examples export.")


if __name__ == "__main__":
    main()


