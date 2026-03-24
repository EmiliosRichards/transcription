"""
Transcribe audio from B2 using open-source Whisper via faster-whisper (preferred)
or OpenAI Whisper local pipeline if configured.

This script downloads audio files from a B2 prefix, runs local transcription, and
writes raw JSON outputs. It supports optional word-level timestamps when the
backend supports it (faster-whisper does).

Requirements (install in your transcription venv):
- faster-whisper
- torch (CUDA optional), ffmpeg available on PATH

Example (PowerShell):
python data_pipelines/scripts/transcribe_whisper_oss.py `
  --b2-prefix "benchmarks_mixed" `
  --bucket "your-bucket" `
  --model-size "medium" `
  --device "cpu" `
  --output-dir "data_pipelines/data/transcriptions/whisper_oss" `
  --limit 5 `
  --skip-existing
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from typing import Iterable, List, Optional

from botocore.exceptions import ClientError
from dotenv import load_dotenv, find_dotenv
import time
from datetime import datetime, timezone
import subprocess


def make_b2_client_from_env():
    from boto3.session import Session  # type: ignore

    endpoint_url = os.environ.get("BACKBLAZE_B2_S3_ENDPOINT") or os.environ.get("AWS_ENDPOINT_URL")
    region_name = os.environ.get("BACKBLAZE_B2_REGION") or os.environ.get("AWS_REGION") or "auto"
    aws_access_key_id = os.environ.get("BACKBLAZE_B2_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.environ.get("BACKBLAZE_B2_APPLICATION_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not endpoint_url or not aws_access_key_id or not aws_secret_access_key:
        raise RuntimeError("Missing B2 env vars.")
    session = Session()
    return session.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region_name,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )


def list_b2_objects(bucket: str, prefix: str) -> Iterable[str]:
    s3 = make_b2_client_from_env()
    token: Optional[str] = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for item in resp.get("Contents", []):
            key = item.get("Key")
            if key:
                yield key
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")


def download_b2_object(bucket: str, key: str, dest_path: str) -> None:
    s3 = make_b2_client_from_env()
    s3.download_file(bucket, key, dest_path)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def make_output_path(output_dir: str, b2_key: str) -> str:
    base = os.path.basename(b2_key)
    name = base.rsplit(".", 1)[0] if "." in base else base
    return os.path.join(output_dir, f"{name}.json")


def preprocess_audio(in_path: str, out_path: str, sr: int = 16000, mono: int = 1,
                     trim_sec: float = 0.5, trim_db: float = -55.0) -> str:
    cmd = [
        "ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", in_path, "-ar", str(sr), "-ac", str(mono), "-c:a", "pcm_s16le",
        "-af", f"areverse,silenceremove=start_periods=1:start_duration={trim_sec}:start_threshold={trim_db}dB,areverse",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def run_whisper_oss(audio_path: str, model_size: str, device: str, compute_type: str, vad: bool, language: Optional[str], temperature: float, no_condition: bool) -> dict:
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        raise RuntimeError("Please install faster-whisper in this environment.") from e

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    lang = None
    if language:
        lang = language.strip().lower()
        if lang in {"de", "de-de", "de_de", "german", "deutsch"}:
            lang = "de"
    segments, info = model.transcribe(
        audio_path,
        vad_filter=vad,
        word_timestamps=True,
        temperature=temperature,
        condition_on_previous_text=(not no_condition),
        language=lang,
    )

    seg_list = []
    for seg in segments:
        words = []
        if seg.words:
            for w in seg.words:
                words.append({
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "prob": getattr(w, "probability", None),
                })
        seg_list.append({
            "id": seg.id,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "words": words,
        })

    data = {
        "language": info.language,
        "duration": info.duration,
        "segments": seg_list,
        "text": "".join(s.get("text", "") for s in seg_list).strip(),
        "model": model_size,
        "backend": "faster-whisper",
    }
    return data


def main(argv: Optional[List[str]] = None) -> int:
    try:
        load_dotenv(find_dotenv())
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Transcribe audio from B2 using open-source Whisper")
    parser.add_argument("--b2-prefix", required=True, help="B2 prefix to scan for audio objects")
    parser.add_argument("--bucket", default=None, help="B2 bucket (env BACKBLAZE_B2_BUCKET if omitted)")
    parser.add_argument("--model-size", default="medium", help="Whisper size: tiny, base, small, medium, large-v3")
    parser.add_argument("--device", default="cpu", help="cpu or cuda")
    parser.add_argument("--compute-type", default="int8_float16", help="faster-whisper compute_type")
    parser.add_argument("--vad", action="store_true", help="Enable VAD filter")
    parser.add_argument("--output-dir", required=True, help="Where to store raw JSON outputs")
    # Preprocess flags
    parser.add_argument("--preprocess", action="store_true", help="Enable audio preprocessing (resample + tail trim)")
    parser.add_argument("--pp-sr", type=int, default=16000)
    parser.add_argument("--pp-mono", type=int, default=1)
    parser.add_argument("--pp-trim-sec", type=float, default=0.5)
    parser.add_argument("--pp-trim-db", type=float, default=-55.0)
    parser.add_argument("--language", default=None, help="Language hint, e.g., 'de' for German")
    parser.add_argument("--temperature", type=float, default=0.0, help="Decoding temperature (default 0.0)")
    parser.add_argument("--no-condition", action="store_true", help="Disable conditioning on previous text")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-file", default=None, help="Path to JSONL log; defaults to <output-dir>/_log.jsonl")

    args = parser.parse_args(argv)

    bucket = args.bucket or os.environ.get("BACKBLAZE_B2_BUCKET") or os.environ.get("B2_BUCKET_NAME")
    if not bucket:
        print("Missing bucket. Set BACKBLAZE_B2_BUCKET or pass --bucket.", file=sys.stderr)
        return 2

    ensure_dir(args.output_dir)
    log_path = args.log_file or os.path.join(args.output_dir, "_log.jsonl")

    processed = 0
    sum_wall = 0.0
    sum_api = 0.0
    sum_dur = 0.0
    ok_count = 0
    err_count = 0
    for key in list_b2_objects(bucket, args.b2_prefix):
        kl = key.lower()
        if not (kl.endswith(".mp3") or kl.endswith(".wav") or kl.endswith(".m4a") or kl.endswith(".flac") or kl.endswith(".ogg") or kl.endswith(".webm")):
            continue

        out_json = make_output_path(args.output_dir, key)
        if args.skip_existing and os.path.exists(out_json) and not args.overwrite:
            continue

        if args.limit is not None and processed >= args.limit:
            break

        print(f"Processing: s3://{bucket}/{key}")
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        if args.dry_run:
            processed += 1
            continue

        with tempfile.TemporaryDirectory() as td:
            tmp_path = os.path.join(td, os.path.basename(key))
            try:
                download_b2_object(bucket, key, tmp_path)
            except ClientError as e:
                print(f"Failed to download {key}: {e}", file=sys.stderr)
                continue

            # Optional preprocessing
            proc_path = tmp_path
            if args.preprocess:
                try:
                    proc_path = preprocess_audio(tmp_path, os.path.join(td, "proc.wav"), args.pp_sr, args.pp_mono, args.pp_trim_sec, args.pp_trim_db)
                except Exception as e:
                    print(f"Preprocess failed for {key}: {e}")
                    proc_path = tmp_path

            api_t0 = time.perf_counter()
            err_msg = None
            data = None
            try:
                data = run_whisper_oss(proc_path, args.model_size, args.device, args.compute_type, args.vad, args.language, args.temperature, args.no_condition)
            except Exception as e:
                err_msg = str(e)
                print(f"Transcription failed for {key}: {e}", file=sys.stderr)

            api_t1 = time.perf_counter()
            if data is not None:
                try:
                    with open(out_json, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    err_msg = f"write_failed: {e}"
                    print(f"Failed to write {out_json}: {e}", file=sys.stderr)

            t1 = time.perf_counter()

            row = {
                "timestamp": started_at,
                "model": f"whisper_oss:{args.model_size}",
                "language": args.language,
                "bucket": bucket,
                "b2_key": key,
                "output_path": out_json,
                "wall_ms_total": round((t1 - t0) * 1000, 2),
                "wall_ms_api": round((api_t1 - api_t0) * 1000, 2),
                "status": "ok" if (data is not None and err_msg is None) else "error",
                "error": err_msg,
            }
            if data is not None:
                dur = data.get("duration")
                if isinstance(dur, (int, float)):
                    row["audio_duration_sec"] = float(dur)
            try:
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(json.dumps(row, ensure_ascii=False) + "\n")
            except Exception:
                pass

            # accumulate
            sum_wall += row.get("wall_ms_total", 0) or 0
            sum_api += row.get("wall_ms_api", 0) or 0
            sum_dur += row.get("audio_duration_sec", 0) or 0
            if row.get("status") == "ok":
                ok_count += 1
            else:
                err_count += 1

        processed += 1

    summary = {
        "model": f"whisper_oss:{args.model_size}",
        "language": args.language,
        "prefix": args.b2_prefix,
        "processed": processed,
        "ok": ok_count,
        "errors": err_count,
        "total_wall_ms": round(sum_wall, 2),
        "total_api_ms": round(sum_api, 2),
        "total_audio_sec": round(sum_dur, 3),
        "avg_wall_ms": round(sum_wall / max(1, ok_count), 2),
        "avg_api_ms": round(sum_api / max(1, ok_count), 2),
    }
    try:
        with open(os.path.join(args.output_dir, "_summary.json"), "w", encoding="utf-8") as sf:
            json.dump(summary, sf, ensure_ascii=False, indent=2)
    except Exception:
        pass

    print(f"Done. Processed: {processed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


