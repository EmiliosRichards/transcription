import argparse
import csv
import json
from pathlib import Path
from typing import Tuple

import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="HDBSCAN pass 1 clustering on normalized vectors")
    p.add_argument("--run", required=True, help="Run folder (contains vectors/ and reports/)")
    p.add_argument("--base", default="dexter_free_extraction_slim_reachable_conf05", help="Base name of vectors files")
    p.add_argument("--min-cluster-size", type=int, default=18)
    p.add_argument("--min-samples", type=int, default=5)
    p.add_argument("--metric", default="euclidean", choices=["euclidean", "cosine"])  # distance metric
    p.add_argument("--cluster-selection-method", default="leaf", choices=["eom", "leaf"])  # HDBSCAN method
    p.add_argument("--epsilon", type=float, default=0.0, help="cluster_selection_epsilon")
    # Nice-to-have toggles
    p.add_argument("--prediction-data", dest="prediction_data", action="store_true", help="Enable probabilities output (default)")
    p.add_argument("--no-prediction-data", dest="prediction_data", action="store_false", help="Disable probabilities output")
    p.set_defaults(prediction_data=True)
    p.add_argument("--save-centroids", dest="save_centroids", action="store_true", help="Compute and save cluster centroids (default)")
    p.add_argument("--no-save-centroids", dest="save_centroids", action="store_false", help="Do not save centroids")
    p.set_defaults(save_centroids=True)
    p.add_argument("--append-report", dest="append_report", action="store_true", help="Append to report file (default)")
    p.add_argument("--overwrite-report", dest="append_report", action="store_false", help="Overwrite report file")
    p.set_defaults(append_report=True)
    return p.parse_args()


def load_vectors(run: Path, base: str) -> Tuple[np.ndarray, Path, Path]:
    npy = run / "vectors" / f"{base}_embeddings.npy"
    meta_csv = run / "vectors" / f"{base}_metadata.csv"
    arr = np.load(npy)
    return arr, npy, meta_csv


def load_row_ids(meta_csv: Path) -> np.ndarray:
    row_ids = []
    with meta_csv.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            row_ids.append(row.get("row_id", ""))
    arr = np.array(row_ids)
    if len(set(arr)) != len(arr):
        raise RuntimeError("row_id values are not unique; cannot safely join downstream.")
    return arr


def main() -> None:
    args = parse_args()
    run = Path(args.run)
    run_reports = run / "reports"
    run_reports.mkdir(parents=True, exist_ok=True)
    run_clusters = run / "clusters"
    run_clusters.mkdir(parents=True, exist_ok=True)

    arr, npy_path, meta_csv = load_vectors(run, args.base)

    # Sanity: normalized (approx unit norm); auto-fix if needed
    if not np.all(np.isfinite(arr)):
        raise RuntimeError("Found non-finite values in vectors.")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    mean_norm = float(np.mean(norms)) if norms.size else 0.0
    if norms.size and (abs(mean_norm - 1.0) > 1e-3 or np.any(np.abs(norms - 1.0) > 1e-3)):
        arr = arr / (norms + 1e-12)

    # Cluster
    import hdbscan  # type: ignore

    n = len(arr)
    if n == 0:
        raise RuntimeError("No vectors found: input is empty. Aborting clustering.")
    min_cluster_size = max(2, min(args.min_cluster_size, n))
    min_samples = max(1, min(args.min_samples, min_cluster_size))

    clusterer = hdbscan.HDBSCAN(
        metric=str(args.metric),
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        cluster_selection_epsilon=float(args.epsilon),
        cluster_selection_method=str(args.cluster_selection_method),
        prediction_data=bool(args.prediction_data),
        core_dist_n_jobs=1,
    )
    labels = clusterer.fit_predict(arr)
    probs = getattr(clusterer, "probabilities_", np.ones(len(labels), dtype=float)) if args.prediction_data else np.full(len(labels), np.nan, dtype=float)

    row_ids = load_row_ids(meta_csv)
    if len(row_ids) != len(labels):
        raise RuntimeError("Row IDs count does not match vectors count.")

    # Write clusters CSV under clusters/ with base prefix
    out_csv = run_clusters / f"{args.base}_clusters_pass1.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as g:
        w = csv.writer(g)
        w.writerow(["row_id", "cluster_id", "probability"])
        for rid, lab, p in zip(row_ids, labels, probs):
            w.writerow([rid, int(lab), float(p)])

    # Report
    total = len(labels)
    outliers = int(np.sum(labels == -1))
    clustered = total - outliers
    coverage = clustered / max(1, total)
    # Top cluster sizes
    from collections import Counter
    ctr = Counter([int(x) for x in labels if x != -1])
    top = ctr.most_common(10)

    # Centroids for Phase B (exclude outliers)
    if args.save_centroids:
        uniq_ids = sorted(k for k in ctr.keys())
        centroids = []
        sizes = []
        for cid in uniq_ids:
            idx = np.where(labels == cid)[0]
            if idx.size == 0:
                continue
            c = np.mean(arr[idx, :], axis=0)
            # Normalize centroid for cosine-like usage downstream
            cn = np.linalg.norm(c) + 1e-12
            c = c / cn
            centroids.append(c)
            sizes.append((cid, int(idx.size)))
        if centroids:
            centroids_arr = np.stack(centroids, axis=0)
            clusters_dir = run / "clusters"
            clusters_dir.mkdir(parents=True, exist_ok=True)
            np.save(clusters_dir / f"{args.base}_cluster_centroids.npy", centroids_arr)
            with (clusters_dir / f"{args.base}_cluster_centroids.csv").open("w", newline="", encoding="utf-8") as cg:
                wg = csv.writer(cg)
                wg.writerow(["cluster_id", "size"])
                for cid, sz in sizes:
                    wg.writerow([cid, sz])
            # Optional centroid vectors CSV for inspection
            vec_csv = clusters_dir / f"{args.base}_cluster_centroids_vectors.csv"
            with vec_csv.open("w", newline="", encoding="utf-8") as vg:
                vw = csv.writer(vg)
                dim = centroids_arr.shape[1]
                vw.writerow(["cluster_id"] + [f"c{i}" for i in range(dim)])
                for cid, vec in zip(uniq_ids, centroids_arr):
                    vw.writerow([cid] + [float(x) for x in vec.tolist()])

    line = (
        f"HDBSCAN pass1 | total={total} | coverage={coverage:.1%} | outlier_rate={(outliers/max(1,total)):.1%} | "
        f"min_cluster_size_req={args.min_cluster_size} | min_samples_req={args.min_samples} | "
        f"min_cluster_size_used={min_cluster_size} | min_samples_used={min_samples}\n"
    )
    # Per-base report under reports/
    report_txt = run_reports / f"{args.base}_cluster_pass1.txt"
    mode = "a" if args.append_report else "w"
    with report_txt.open(mode, encoding="utf-8") as rf:
        rf.write(line)
        rf.write("Top clusters (id,size):\n")
        for cid, sz in top:
            rf.write(f"  {cid},{sz}\n")

    # Persist run metadata (provenance)
    from datetime import datetime
    meta = {
        "timestamp": datetime.now().isoformat(),
        "n_rows": int(total),
        "coverage": float(coverage),
        "outlier_rate": float(outliers / max(1, total)),
        "base": str(args.base),
        "metric": str(args.metric),
        "cluster_selection_method": str(args.cluster_selection_method),
        "epsilon": float(args.epsilon),
        "min_cluster_size_requested": args.min_cluster_size,
        "min_samples_requested": args.min_samples,
        "min_cluster_size_used": int(min_cluster_size),
        "min_samples_used": int(min_samples),
        "prediction_data": bool(args.prediction_data),
        "save_centroids": bool(args.save_centroids),
        "append_report": bool(args.append_report),
        "input_npy": str(npy_path),
        "input_meta_csv": str(meta_csv),
        "output_clusters_csv": str(out_csv),
    }
    with (run_reports / "cluster_pass1_meta.json").open("w", encoding="utf-8") as jf:
        json.dump(meta, jf, ensure_ascii=False, indent=2)

    print(line.strip())
    print("Top clusters:", top)
    print("Wrote:", out_csv)
    print("Report:", report_txt)


if __name__ == "__main__":
    main()


