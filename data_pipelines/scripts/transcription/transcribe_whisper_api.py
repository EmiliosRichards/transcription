"""
Transcribe audio from B2 using OpenAI Whisper API (model: whisper-1).

This uses the same OpenAI client pathway as gpt-4o-* but with model=whisper-1.
Saves raw JSON responses to an output directory.

Usage (PowerShell):
python data_pipelines/scripts/transcribe_whisper_api.py `
  --b2-prefix "benchmarks_mixed" `
  --output-dir "data_pipelines/data/transcriptions/whisper_api" `
  --limit 10 `
  --skip-existing
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

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
        argv.extend(["--model", "whisper-1"])
    if "--timestamps" not in argv:
        argv.extend(["--timestamps", "segment"])
    if "--output-dir" not in argv:
        argv.extend(["--output-dir", "data_pipelines/data/transcriptions/whisper_api"])
    if "--language" not in argv:
        argv.extend(["--language", "de"])  # default German for your dataset
    if "--log-file" not in argv:
        argv.extend(["--log-file", "data_pipelines/data/transcriptions/whisper_api/_log.jsonl"])
    # Pass-through preprocessing and tail guard defaults
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
    if "--tail-guard" not in argv:
        argv.append("--tail-guard")
    if "--tg-max-no-speech" not in argv:
        argv.extend(["--tg-max-no-speech", "0.8"])
    if "--tg-min-avg-logprob" not in argv:
        argv.extend(["--tg-min-avg-logprob", "-1.2"])
    if "--tg-max-seg-sec" not in argv:
        argv.extend(["--tg-max-seg-sec", "1.0"])
    return shared_main(argv)


if __name__ == "__main__":
    raise SystemExit(run())


