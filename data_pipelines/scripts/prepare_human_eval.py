"""
Prepare human evaluation packets from saved transcript JSONs.

- Scans multiple service output directories (each containing .json transcripts)
- Finds audio files that exist across ALL services
- Selects N items (random with seed) for review
- Generates one Markdown file per audio with sections for each service
- Emits a scoring template CSV (audio x service rows) for annotators

Usage (PowerShell example):
python data_pipelines/scripts/prepare_human_eval.py `
  --services `
    gpt4o:"data_pipelines/data/transcriptions/gpt4o" `
    gpt4o_mini:"data_pipelines/data/transcriptions/gpt4o_mini" `
    whisper_api:"data_pipelines/data/transcriptions/whisper_api" `
    whisper_oss:"data_pipelines/data/transcriptions/whisper_oss_largev3_cpu" `
  --out-dir "data_pipelines/data/transcriptions/human_eval" `
  --count 5 `
  --seed 42
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from typing import Dict, List, Tuple


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def list_transcript_basenames(dir_path: str) -> Dict[str, str]:
    """Return mapping of basename -> fullpath for .json files in dir."""
    out: Dict[str, str] = {}
    if not os.path.isdir(dir_path):
        return out
    for name in os.listdir(dir_path):
        if not name.lower().endswith(".json"):
            continue
        if name.startswith("_"):
            # skip log/summary files
            continue
        base = name[:-5]
        out[base] = os.path.join(dir_path, name)
    return out


def extract_text_from_json(data: dict) -> str:
    # Prefer 'text' if present
    txt = data.get("text")
    if isinstance(txt, str) and txt.strip():
        return txt.strip()
    # Try segments list with 'text'
    segs = data.get("segments")
    if isinstance(segs, list) and segs:
        parts: List[str] = []
        for seg in segs:
            t = seg.get("text") if isinstance(seg, dict) else None
            if isinstance(t, str) and t:
                parts.append(t)
        if parts:
            return "\n".join(parts).strip()
    # Fallback to JSON dump
    return json.dumps(data, ensure_ascii=False)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prepare human eval packets from transcript JSONs")
    p.add_argument("--services", nargs="+", required=True,
                   help="Service spec as name:dir, e.g., gpt4o:path/to/gpt4o")
    p.add_argument("--out-dir", required=True, help="Output directory for human eval files")
    p.add_argument("--count", type=int, default=5, help="How many items to select")
    p.add_argument("--seed", type=int, default=42, help="Random seed for selection")
    p.add_argument("--exclude-basename", action="append", default=[], help="Basename to exclude (can be passed multiple times)")
    p.add_argument("--exclude-rec-id", action="append", default=[], help="Recording ID (e.g., PR_...) to exclude (can be passed multiple times)")
    p.add_argument("--exclude-file", default=None, help="Optional text file with items to exclude (one per line: either basename or PR_ recording id)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    ensure_dir(args.out_dir)

    # Parse services
    services: List[Tuple[str, str]] = []
    for spec in args.services:
        if ":" not in spec:
            raise SystemExit(f"Invalid service spec: {spec}. Use name:dir")
        name, dir_path = spec.split(":", 1)
        services.append((name.strip(), dir_path.strip()))

    # Build per-service maps
    maps: Dict[str, Dict[str, str]] = {name: list_transcript_basenames(path) for name, path in services}
    # Compute intersection of basenames present across all services
    common: set[str] = set()
    for i, (name, m) in enumerate(maps.items()):
        s = set(m.keys())
        common = s if i == 0 else (common & s)

    if not common:
        raise SystemExit("No common transcripts found across all provided services.")

    # Build rec_id lookup
    def get_rec_id(base: str) -> str | None:
        if "__PR_" in base:
            return base.split("__")[-1]
        return None

    # Collect excludes
    excl_bases = set(args.exclude_basename or [])
    excl_rec_ids = set(args.exclude_rec_id or [])
    if args.exclude_file and os.path.exists(args.exclude_file):
        with open(args.exclude_file, "r", encoding="utf-8") as ef:
            for line in ef:
                item = line.strip()
                if not item:
                    continue
                if item.startswith("PR_"):
                    excl_rec_ids.add(item)
                else:
                    excl_bases.add(item)

    # Random selection with seed
    rng = random.Random(args.seed)
    candidates = []
    for b in sorted(common):
        if b in excl_bases:
            continue
        rid = get_rec_id(b)
        if rid and rid in excl_rec_ids:
            continue
        candidates.append(b)
    rng.shuffle(candidates)
    selected = candidates[: args.count]

    # Prepare Markdown files and scoring CSV
    scoring_rows: List[List[str]] = []
    for base in selected:
        md_path = os.path.join(args.out_dir, f"{base}.md")
        lines: List[str] = []
        lines.append(f"# Human evaluation packet: {base}")
        # Attempt to extract recording_id from filename tail after last '__'
        rec_id = None
        if "__PR_" in base:
            rec_id = base.split("__")[-1]
        if rec_id:
            lines.append("")
            lines.append(f"Recording ID: {rec_id}")

        # For each service, append transcript text section
        for svc_name, m in services:
            jpath = maps[svc_name].get(base)
            text = "(missing)"
            if jpath and os.path.exists(jpath):
                try:
                    with open(jpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    text = extract_text_from_json(data)
                except Exception as e:
                    text = f"[Error reading {jpath}: {e}]"
            lines.append("")
            lines.append(f"## {svc_name}")
            lines.append("")
            lines.append(text)
            scoring_rows.append([base, rec_id or "", svc_name, "", "", ""])  # placeholders for small/big errors, notes

        with open(md_path, "w", encoding="utf-8") as mf:
            mf.write("\n".join(lines))

    # Write scoring template CSV
    csv_path = os.path.join(args.out_dir, "scoring_template.csv")
    with open(csv_path, "w", encoding="utf-8") as cf:
        cf.write("audio_basename,recording_id,service,small_errors,big_errors,notes\n")
        for row in scoring_rows:
            cf.write(",".join(r.replace(",", " ") for r in row) + "\n")

    # Write index
    with open(os.path.join(args.out_dir, "index.md"), "w", encoding="utf-8") as idx:
        idx.write("# Human Evaluation Packets\n\n")
        for base in selected:
            idx.write(f"- {base}.md\n")

    print(f"Prepared {len(selected)} packets in {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


