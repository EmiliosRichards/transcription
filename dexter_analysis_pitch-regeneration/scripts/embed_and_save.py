import argparse
import csv
import json
import os
import re
import sys
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple

try:
    import numpy as np  # type: ignore
except Exception:
    print("This script requires numpy. Please install it.", file=sys.stderr)
    raise

# Load .env if present (project root)
try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
    load_dotenv(find_dotenv())
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Embed reasons and save vectors + metadata")
    p.add_argument("--src", required=True, help="Path to input CSV (slim)")
    p.add_argument("--outdir", default=None, help="Output directory (will create vectors/). If omitted, uses --auto-run base.")
    p.add_argument("--text-col", default="auto", help="Column to embed (e.g., reason_core). 'auto' = per-row prefer reason_core else reason_free_text")
    p.add_argument("--fallback-col", default="reason_free_text", help="Fallback column if --text-col empty for a row")
    p.add_argument("--name", default=None, help="Override base output name (e.g., 'reachable' -> reachable_embeddings.npy)")
    p.add_argument("--model", default=os.environ.get("FREE_EMBED_MODEL", "text-embedding-3-small"))
    p.add_argument("--provider", default="openai", choices=["openai"], help="Embedding provider")
    p.add_argument("--max-batch", type=int, default=128, help="Batch size for embedding requests")
    p.add_argument("--max-chars-per-batch", type=int, default=int(os.environ.get("FREE_EMBED_MAX_CHARS_PER_BATCH", "50000")), help="Soft cap on total characters per API batch (default 50000)")
    p.add_argument("--workers", type=int, default=int(os.environ.get("FREE_EMBED_WORKERS", "1")), help="Concurrent embedding request workers (default from FREE_EMBED_WORKERS or 1)")
    p.add_argument("--normalize", dest="normalize", action="store_true", help="L2-normalize vectors (default)")
    p.add_argument("--no-normalize", dest="normalize", action="store_false", help="Disable normalization")
    p.set_defaults(normalize=True)
    p.add_argument("--dedupe", dest="dedupe", action="store_true", help="Deduplicate identical texts before embedding (default)")
    p.add_argument("--no-dedupe", dest="dedupe", action="store_false", help="Disable deduplication")
    p.set_defaults(dedupe=True)
    p.add_argument("--force", action="store_true", help="Overwrite existing vector outputs")
    p.add_argument("--auto-run", action="store_true", help="Create a new run folder under --runs-base with current datetime (YYYY-MM-DD_HH-mm)")
    p.add_argument(
        "--runs-base",
        default=os.environ.get(
            "DEXTER_RUNS_BASE",
            r"data_pipelines_dexter\data\transcription_dexter_analysis\runs",
        ),
        help="Base directory for auto-run folders",
    )
    return p.parse_args()


def extract_core(reason: str) -> str:
    if not reason:
        return ""
    m = re.split(r"[;|—–]", reason, maxsplit=1)
    core = (m[0] if m else reason).strip()
    return core


def load_rows(src: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with src.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            reason = (row.get("reason_free_text") or "").strip()
            # Prefer provided reason_core column; otherwise compute a basic core
            provided_core = (row.get("reason_core") or "").strip()
            core = provided_core if provided_core else extract_core(reason)
            who_reached = (row.get("who_reached") or "").strip()
            who_reached_role = (row.get("who_reached_role") or "").strip()
            evidence_json = (row.get("evidence_json") or "").strip()
            rows.append({
                "row_id": row.get("row_id", ""),
                "phone": row.get("phone", ""),
                "campaign_name": row.get("campaign_name", ""),
                "reason_free_text": reason,
                "reason_core": core,
                "outcome_free_text": (row.get("outcome_free_text") or "").strip(),
                "confidence": row.get("confidence", ""),
                # optional metadata passthrough
                "who_reached": who_reached,
                "who_reached_role": who_reached_role,
                "evidence_json": evidence_json,
            })
    return rows


def embed_openai(texts: List[str], model: str, max_batch: int = 128, workers: int = 1, max_chars_per_batch: int = 50000) -> List[List[float]]:
    from openai import OpenAI  # lazy import

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Please export it before running embeddings.")

    vectors: List[List[float]] = [[0.0]] * max(1, len(texts))

    def backoff_sleep(attempt: int) -> None:
        time.sleep(0.5 * (2 ** attempt) + 0.05)

    def embed_batch(batch: List[str]) -> List[List[float]]:
        safe_batch = [t if t else " " for t in batch]
        # Create client per thread; optional timeout
        client_timeout = None
        try:
            client_timeout = float(os.environ.get("FREE_OPENAI_TIMEOUT", ""))
        except Exception:
            client_timeout = None
        try:
            client = OpenAI(timeout=client_timeout) if client_timeout else OpenAI()
        except TypeError:
            client = OpenAI()
        for attempt in range(3):
            try:
                resp = client.embeddings.create(model=model, input=safe_batch)
                if len(getattr(resp, "data", [])) != len(safe_batch):
                    raise RuntimeError(f"Embedding API size mismatch: got {len(getattr(resp,'data',[]))} for batch {len(safe_batch)}")
                return [d.embedding for d in resp.data]
            except Exception as e:
                s = str(e).lower()
                transient = ("429" in s) or ("rate" in s) or ("timeout" in s) or ("server" in s) or ("unavailable" in s)
                if attempt >= 2 or not transient:
                    raise
                backoff_sleep(attempt)
        return []

    if not texts:
        return []

    # Prepare batches with original positions and char-size guard
    batches: List[Tuple[int, List[str]]] = []
    i = 0
    n = len(texts)
    while i < n:
        count = 0
        char_sum = 0
        batch: List[str] = []
        start = i
        while i < n and count < max_batch:
            t = texts[i]
            tlen = len(t)
            # If adding this text exceeds char cap and batch already has items, break
            if batch and (char_sum + tlen > max_chars_per_batch):
                break
            batch.append(t)
            count += 1
            char_sum += tlen
            i += 1
            # If first item already exceeds cap, still send it alone
            if not batch:
                break
        if not batch:
            # Fallback to at least one item to avoid infinite loop
            batch = [texts[i]]
            start = i
            i += 1
        batches.append((start, batch))

    # Allocate result container of correct size lazily when first result arrives
    result: List[List[float]] = [None] * len(texts)  # type: ignore

    if max(1, workers) == 1:
        for start, batch in batches:
            vecs = embed_batch(batch)
            for j, v in enumerate(vecs):
                result[start + j] = v
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futs = {ex.submit(embed_batch, batch): (start, len(batch)) for start, batch in batches}
            for fut in as_completed(futs):
                start, blen = futs[fut]
                vecs = fut.result()
                if len(vecs) != blen:
                    raise RuntimeError(f"Embedding vectors length mismatch for batch starting {start}")
                for j, v in enumerate(vecs):
                    result[start + j] = v

    # Type checker: ensure no None remains
    if any(v is None for v in result):  # type: ignore
        raise RuntimeError("Missing vectors after embedding; some batches did not return.")

    return result  # type: ignore


def save_outputs(outdir: Path, src: Path, rows: List[Dict[str, Any]], used_field: str, vectors: List[List[float]], normalize: bool, model: str, name_override: str | None) -> Tuple[Path, Path, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    vec_dir = outdir / "vectors"
    vec_dir.mkdir(parents=True, exist_ok=True)

    base = name_override if name_override else src.stem
    npy_path = vec_dir / f"{base}_embeddings.npy"
    csv_path = vec_dir / f"{base}_metadata.csv"
    meta_path = vec_dir / f"{base}_embed_meta.json"

    arr = np.array(vectors, dtype=np.float32)
    if normalize and arr.size > 0:
        arr /= (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12)
    np.save(npy_path, arr)

    with csv_path.open("w", newline="", encoding="utf-8") as g:
        # Base + extended metadata fields
        fieldnames = [
            "row_id","phone","campaign_name","used_field","used_text",
            "reason_free_text","reason_core","outcome_free_text","confidence","vector_dim",
            "who_reached","who_reached_role","evidence_json",
        ]
        w = csv.DictWriter(g, fieldnames=fieldnames)
        w.writeheader()
        dim = arr.shape[1] if arr.size > 0 else 0
        for r, used in zip(rows, (r.get(used_field, "") for r in rows)):
            try:
                conf_val = float(r.get("confidence", "") or 0)
            except Exception:
                conf_val = 0.0
            out_row = {
                "row_id": r.get("row_id", ""),
                "phone": r.get("phone", ""),
                "campaign_name": r.get("campaign_name", ""),
                "used_field": used_field,
                "used_text": used,
                "reason_free_text": r.get("reason_free_text", ""),
                "reason_core": r.get("reason_core", ""),
                "outcome_free_text": r.get("outcome_free_text", ""),
                "confidence": conf_val,
                "vector_dim": dim,
                "who_reached": r.get("who_reached", ""),
                "who_reached_role": r.get("who_reached_role", ""),
                "evidence_json": r.get("evidence_json", ""),
            }
            w.writerow(out_row)

    # Metadata JSON next to outputs for provenance
    try:
        src_bytes = src.read_bytes()
        src_hash = hashlib.sha1(src_bytes).hexdigest()[:12]
    except Exception:
        src_hash = ""
    meta = {
        "src_path": str(src),
        "model": model,
        "used_field": used_field,
        "n_rows": len(rows),
        "vector_dim": int(arr.shape[1] if arr.size > 0 else 0),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "src_sha1_12": src_hash,
        "normalized": bool(normalize),
    }
    with meta_path.open("w", encoding="utf-8") as mf:
        json.dump(meta, mf, ensure_ascii=False, indent=2)

    return npy_path, csv_path, meta_path


def validate_outputs(n: int, npy_path: Path, csv_path: Path) -> None:
    # Reload numpy
    arr = np.load(npy_path)
    if arr.shape[0] != n:
        raise RuntimeError(f"Row count mismatch: {arr.shape[0]} vs {n}")
    if arr.size == 0 or (arr == 0).all():
        raise RuntimeError("Vectors appear empty or zeros-only.")
    if not np.isfinite(arr).all():
        raise RuntimeError("Vectors contain NaN/Inf values.")
    # Reload CSV just to ensure it is parseable
    with csv_path.open("r", encoding="utf-8") as f:
        next(csv.reader(f), None)


def write_profile(outdir: Path, base_name: str, n_rows: int, npy_path: Path, csv_path: Path) -> Path:
    reports_dir = outdir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    profile_path = reports_dir / "embeddings_profile.txt"
    arr = np.load(npy_path)
    lines = [
        f"base={base_name}",
        f"rows={n_rows}",
        f"vectors.shape={tuple(arr.shape)}",
        f"count_parity={'OK' if arr.shape[0]==n_rows else 'MISMATCH'}",
        f"nan_inf={'present' if (not np.isfinite(arr).all()) else 'absent'}",
        f"reload_csv=OK",
    ]
    with profile_path.open("w", encoding="utf-8") as pf:
        pf.write("\n".join(lines) + "\n")
    return profile_path


def main() -> None:
    args = parse_args()
    src = Path(args.src)
    # Resolve output directory: prefer explicit --outdir; else use --auto-run or runs base
    if args.outdir:
        outdir = Path(args.outdir)
    else:
        args.auto_run = True
        base = Path(args.runs_base)
        run_name = datetime.now().strftime("%Y-%m-%d_%H-%M")
        outdir = base / run_name

    rows = load_rows(src)
    # Choose text per row with fallback
    def choose_text(r: Dict[str, Any]) -> str:
        txt_col = (args.text_col or "auto").strip().lower()
        if txt_col == "auto":
            primary = (r.get("reason_core") or "").strip()
            return primary if primary else (r.get("reason_free_text") or "").strip()
        primary = (r.get(args.text_col, "") or "").strip()
        if primary:
            return primary
        fallback = (r.get(args.fallback_col, "") or "").strip()
        return fallback if fallback else (r.get("reason_free_text") or "").strip()

    used_texts = [choose_text(r) for r in rows]
    used_field = (args.text_col or "auto")
    # Skip rows with truly empty text
    filtered = [(r, t) for r, t in zip(rows, used_texts) if t.strip()]
    skipped_empty = len(rows) - len(filtered)
    if skipped_empty:
        print(f"Skipping {skipped_empty} rows with empty text")
    if filtered:
        rows, used_texts = zip(*filtered)
        rows = list(rows)
        used_texts = list(used_texts)
    else:
        rows, used_texts = [], []

    print(f"Rows to embed: {len(rows)} using field: {used_field}")

    # Deduplicate identical texts to save cost
    if args.dedupe:
        text_to_index: Dict[str, int] = {}
        unique_texts: List[str] = []
        for t in used_texts:
            if t not in text_to_index:
                text_to_index[t] = len(unique_texts)
                unique_texts.append(t)
        print(f"Unique texts: {len(unique_texts)} (from {len(used_texts)})")
        unique_vectors = embed_openai(unique_texts, model=args.model, max_batch=max(1, args.max_batch), workers=max(1, args.workers), max_chars_per_batch=max(1, args.max_chars_per_batch))
        if len(unique_vectors) != len(unique_texts):
            raise RuntimeError("Unique vectors count mismatch")
        # Map back to full order
        vectors = [unique_vectors[text_to_index[t]] for t in used_texts]
    else:
        vectors = embed_openai(used_texts, model=args.model, max_batch=max(1, args.max_batch), workers=max(1, args.workers), max_chars_per_batch=max(1, args.max_chars_per_batch))
    if len(vectors) != len(rows):
        raise RuntimeError(f"Embedding count mismatch: {len(vectors)} vs {len(rows)}")

    # Respect --force (skip if exists unless forcing)
    base = args.name if args.name else src.stem
    npy_path = outdir / "vectors" / f"{base}_embeddings.npy"
    # Early skip if outputs exist
    if npy_path.exists() and not args.force:
        print(f"Exists, skipping (use --force to overwrite): {npy_path}")
        return

    npy_path, csv_path, meta_path = save_outputs(outdir, src, rows, used_field, vectors, args.normalize, args.model, args.name)
    validate_outputs(len(rows), npy_path, csv_path)
    write_profile(outdir, base, len(rows), npy_path, csv_path)

    print(f"Saved vectors: {npy_path}")
    print(f"Saved metadata: {csv_path}")
    print(f"dim={len(vectors[0]) if vectors else 0} rows={len(rows)} OK")

    # One-liner run summary to reports/
    try:
        reports_dir = outdir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        line = (
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')} | embed | model={args.model} "
            f"| used={used_field} | rows={len(rows)} | dim={len(vectors[0]) if vectors else 0} "
            f"| skipped_empty={skipped_empty} "
            f"| dedup={'on' if args.dedupe else 'off'}"
        )
        if args.dedupe:
            line += f" | unique_texts={len(set(used_texts))}"
        line += (
            f"| npy={npy_path.name} | meta={meta_path.name}\n"
        )
        with (reports_dir / "run_embed_summary.txt").open("a", encoding="utf-8") as rf:
            rf.write(line)
        print(line.strip())
    except Exception:
        pass


if __name__ == "__main__":
    main()


