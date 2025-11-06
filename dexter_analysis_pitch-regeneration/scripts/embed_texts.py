import argparse
import csv
import sys
from pathlib import Path

import numpy as np


MODEL_NAME = "sentence-transformers/all-MiniLM-L12-v2"


def l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True, help="Run folder path")
    p.add_argument("--input", required=True, help="Relative path under run (e.g. slim/reachable_with_role_v2.csv)")
    p.add_argument("--text-col", required=True, help="Which column to embed (e.g., reason_core)")
    p.add_argument("--out-base", default=None, help="Basename for outputs (default: derived from input filename)")
    p.add_argument("--model", default=MODEL_NAME, help="Sentence-Transformers model name")
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--normalize-l2", action="store_true")
    args = p.parse_args()

    RUN = Path(args.run)
    input_csv = RUN / args.input
    if not input_csv.exists():
        print(f"ERROR: input not found: {input_csv}", file=sys.stderr)
        sys.exit(2)

    out_base = args.out_base or Path(args.input).stem
    vec_dir = RUN / "vectors"
    vec_dir.mkdir(parents=True, exist_ok=True)

    meta_path = vec_dir / f"{out_base}_metadata.csv"
    npy_path = vec_dir / f"{out_base}_embeddings.npy"
    rpt_path = RUN / "reports" / f"{out_base}_embeddings_profile.txt"
    rpt_path.parent.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader(open(input_csv, encoding="utf-8")))
    texts = []
    meta = []
    missing = 0
    for r in rows:
        t = (r.get(args.text_col) or "").strip()
        if not t:
            missing += 1
            t = ""
        texts.append(t)
        meta.append({
            "row_id": r.get("row_id", ""),
            "phone": r.get("phone", ""),
            "campaign_name": r.get("campaign_name", ""),
            "who_reached": r.get("who_reached", r.get("who_reached_role", "")),
            "reason_free_text": r.get("reason_free_text", ""),
            "reason_core": r.get("reason_core", ""),
            "outcome_free_text": r.get("outcome_free_text", ""),
            "confidence": r.get("confidence", ""),
            "evidence_json": r.get("evidence_json", ""),
        })

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model)
    vectors = model.encode(
        texts,
        batch_size=args.batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=False,
    )

    if args.normalize_l2:
        vectors = l2_normalize(vectors)

    np.save(npy_path, vectors)
    with open(meta_path, "w", newline="", encoding="utf-8") as g:
        w = csv.DictWriter(g, fieldnames=list(meta[0].keys()) if meta else [])
        if meta:
            w.writeheader()
            w.writerows(meta)

    ok = vectors.shape[0] == len(rows)
    nan_rows = int(np.isnan(vectors).any(axis=1).sum()) if vectors.size else 0
    with open(rpt_path, "w", encoding="utf-8") as g:
        g.write(f"input_csv: {input_csv}\n")
        g.write(f"model: {args.model}\n")
        g.write(f"text_col: {args.text_col}\n")
        g.write(f"rows: {len(rows)}\n")
        g.write(f"vectors: {vectors.shape}\n")
        g.write(f"normalize_l2: {args.normalize_l2}\n")
        g.write(f"missing_texts: {missing}\n")
        g.write(f"nan_rows: {nan_rows}\n")
        g.write(f"metadata_path: {meta_path}\n")
        g.write(f"embeddings_path: {npy_path}\n")

    print("Wrote:", npy_path)
    print("Wrote:", meta_path)
    print("Wrote:", rpt_path)
    if not ok or nan_rows > 0:
        print("WARNING: vector count mismatch or NaNs detected.", file=sys.stderr)


if __name__ == "__main__":
    main()


