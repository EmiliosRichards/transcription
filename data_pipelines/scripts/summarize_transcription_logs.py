"""
Summarize transcription JSONL logs for one or more services.

Reads _log.jsonl in each provided directory, aggregates totals, and prints a
compact summary. Optionally writes a combined JSON summary file.

Usage (PowerShell):
python data_pipelines/scripts/summarize_transcription_logs.py `
  --paths `
    data_pipelines/data/transcriptions/gpt4o `
    data_pipelines/data/transcriptions/gpt4o_mini `
    data_pipelines/data/transcriptions/whisper_api `
    data_pipelines/data/transcriptions/whisper_oss_largev3_cpu `
  --out "data_pipelines/data/transcriptions/_combined_summary.json"
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Dict, List, Tuple


def read_jsonl(path: str) -> List[dict]:
    rows: List[dict] = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def summarize_rows(rows: List[dict]) -> dict:
    total = len(rows)
    ok = sum(1 for r in rows if r.get("status") == "ok")
    err = total - ok
    sum_wall = sum(float(r.get("wall_ms_total", 0) or 0) for r in rows)
    sum_api = sum(float(r.get("wall_ms_api", 0) or 0) for r in rows)
    sum_cost = sum(float(r.get("est_cost", 0) or 0) for r in rows)
    sum_dur = sum(float(r.get("audio_duration_sec", 0) or 0) for r in rows)
    avg_wall = (sum_wall / ok) if ok else 0.0
    avg_api = (sum_api / ok) if ok else 0.0
    return {
        "files": total,
        "ok": ok,
        "errors": err,
        "total_wall_ms": round(sum_wall, 2),
        "total_api_ms": round(sum_api, 2),
        "total_audio_sec": round(sum_dur, 3),
        "total_cost": round(sum_cost, 6),
        "avg_wall_ms": round(avg_wall, 2),
        "avg_api_ms": round(avg_api, 2),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Summarize _log.jsonl files for transcription runs")
    p.add_argument("--paths", nargs="+", required=True, help="Directories that contain _log.jsonl")
    p.add_argument("--out", default=None, help="Optional path to write combined JSON summary")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    combined: Dict[str, dict] = {}
    for p in args.paths:
        name = os.path.basename(os.path.normpath(p))
        log_path = os.path.join(p, "_log.jsonl")
        rows = read_jsonl(log_path)
        summary = summarize_rows(rows)
        combined[name] = summary
        print(f"{name}: {summary}")

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(combined, f, ensure_ascii=False, indent=2)
        print(f"Wrote {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


