"""
Wrapper for OpenAI gpt-4o-mini-transcribe using the shared implementation.

Defaults:
- model: gpt-4o-mini-transcribe
- timestamps: segment
- output-dir: data_pipelines/data/transcriptions/gpt4o_mini

Usage (PowerShell):
python data_pipelines/scripts/transcribe_gpt4o_mini.py `
  --b2-prefix "benchmarks_mixed" `
  --bucket "your-bucket" `
  --limit 5 `
  --skip-existing
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

# Allow running as a standalone script (no package context)
sys.path.insert(0, os.path.dirname(__file__))

from transcribe_gpt4o import main as shared_main  # type: ignore
from dotenv import load_dotenv, find_dotenv


def run(argv: Optional[List[str]] = None) -> int:
    try:
        load_dotenv(find_dotenv())
    except Exception:
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--model" not in argv:
        argv.extend(["--model", "gpt-4o-mini-transcribe"])
    if "--timestamps" not in argv:
        argv.extend(["--timestamps", "segment"])
    if "--output-dir" not in argv:
        argv.extend(["--output-dir", "data_pipelines/data/transcriptions/gpt4o_mini"])
    if "--language" not in argv:
        argv.extend(["--language", "de"])  # default German
    if "--output-dir" not in argv:
        argv.extend(["--output-dir", "data_pipelines/data/transcriptions/gpt4o_mini"])
    # Supply a default log file in the same folder
    if "--log-file" not in argv:
        argv.extend(["--log-file", "data_pipelines/data/transcriptions/gpt4o_mini/_log.jsonl"])
    # Preprocess defaults (enable by default for mini as well)
    if "--preprocess" not in argv:
        argv.append("--preprocess")
    if "--pp-sr" not in argv:
        argv.extend(["--pp-sr", "16000"])
    if "--pp-mono" not in argv:
        argv.extend(["--pp-mono", "1"])
    if "--pp-trim-sec" not in argv:
        argv.extend(["--pp-trim-sec", "0.5"])
    if "--pp-trim-db" not in argv:
        argv.extend(["--pp-trim-db", "-55"]) 
    return shared_main(argv)


if __name__ == "__main__":
    raise SystemExit(run())


