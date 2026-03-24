"""
Transcribe audio files stored in Backblaze B2 (S3-compatible) using OpenAI's
gpt-4o-transcribe (or gpt-4o-mini-transcribe) models.

Features:
- Lists audio objects under a specified B2 prefix and processes them sequentially
- Downloads each file to a temporary local path
- Sends audio to OpenAI transcription API
- Optionally requests timestamps (segment/word) if the model supports it
- Saves the raw JSON response to the designated output directory
- Skips files that already have an output (unless --overwrite)

Environment variables required:
- BACKBLAZE_B2_S3_ENDPOINT or AWS_ENDPOINT_URL
- BACKBLAZE_B2_REGION or AWS_REGION (optional)
- BACKBLAZE_B2_KEY_ID or AWS_ACCESS_KEY_ID
- BACKBLAZE_B2_APPLICATION_KEY or AWS_SECRET_ACCESS_KEY
- BACKBLAZE_B2_BUCKET or B2_BUCKET_NAME
- OPENAI_API_KEY

Example usage (PowerShell formatting):
python data_pipelines/scripts/transcribe_gpt4o.py `
  --b2-prefix "benchmarks_mixed" `
  --output-dir "data_pipelines/data/transcriptions/gpt4o" `
  --model "gpt-4o-transcribe" `
  --timestamps segment `
  --limit 10 `
  --skip-existing
"""

from __future__ import annotations

import argparse
import os
import sys
import json
import tempfile
import subprocess
import shutil
import time
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple, Any, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
import threading
from queue import Queue, Empty
import socket
from functools import lru_cache

from botocore.exceptions import ClientError
from botocore.config import Config
from dotenv import load_dotenv, find_dotenv
from hashlib import sha1
from sqlalchemy import create_engine, text, event


@lru_cache(maxsize=1)
def make_b2_client_from_env():
    """Create a boto3 S3 client for Backblaze B2 using env vars.

    Lazy-imports boto3 so that environments without it can still parse --help.
    """
    # Lazy import and use explicit Session class to satisfy static checkers
    from boto3.session import Session  # type: ignore

    endpoint_url = os.environ.get("BACKBLAZE_B2_S3_ENDPOINT") or os.environ.get("AWS_ENDPOINT_URL")
    region_name = os.environ.get("BACKBLAZE_B2_REGION") or os.environ.get("AWS_REGION") or "auto"
    aws_access_key_id = os.environ.get("BACKBLAZE_B2_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.environ.get("BACKBLAZE_B2_APPLICATION_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")

    if not endpoint_url or not aws_access_key_id or not aws_secret_access_key:
        raise RuntimeError("Missing B2 env vars: BACKBLAZE_B2_S3_ENDPOINT, BACKBLAZE_B2_KEY_ID, BACKBLAZE_B2_APPLICATION_KEY")

    session = Session()
    cfg = Config(
        connect_timeout=10,
        read_timeout=30,
        retries={"max_attempts": 8, "mode": "standard"},
    )
    s3_client = session.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region_name,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        config=cfg,
    )
    return s3_client


def list_b2_objects(bucket: str, prefix: str) -> Iterable[str]:
    """Yield object keys under a given prefix in the specified bucket."""
    s3 = make_b2_client_from_env()
    continuation_token: Optional[str] = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        resp = s3.list_objects_v2(**kwargs)
        for item in resp.get("Contents", []):
            key = item.get("Key")
            if key:
                yield key
        if not resp.get("IsTruncated"):
            break
        continuation_token = resp.get("NextContinuationToken")


def download_b2_object(bucket: str, key: str, dest_path: str) -> None:
    s3 = make_b2_client_from_env()
    s3.download_file(bucket, key, dest_path)


def head_b2_object(bucket: str, key: str) -> dict:
    s3 = make_b2_client_from_env()
    try:
        return s3.head_object(Bucket=bucket, Key=key)
    except Exception:
        return {}


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def make_output_paths(output_dir: str, b2_key: str) -> str:
    """Return the output JSON path for a given b2 key."""
    # Use only the filename portion of the key, replace audio extension with .json
    base = os.path.basename(b2_key)
    if "." in base:
        base_no_ext = base.rsplit(".", 1)[0]
    else:
        base_no_ext = base
    return os.path.join(output_dir, f"{base_no_ext}.json")


def make_s3_url(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


def compute_url_sha1(url: str) -> str:
    return sha1(url.encode("utf-8")).hexdigest()


def _rel_path_under_prefix(key: str, prefix: str) -> str:
    """Return key relative to prefix (if present), else original key."""
    p = prefix.rstrip("/") + "/"
    return key[len(p):] if key.startswith(p) else key


def _psycopg2_keepalive_args() -> dict:
    return {
        "keepalives": 1,
        "keepalives_idle": 60,
        "keepalives_interval": 30,
        "keepalives_count": 5,
    }


def _normalize_sync_db_url_str(db_url: str) -> str:
    if db_url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg2://" + db_url.split("://", 1)[1]
    return db_url


def db_get_engine(db_url: Optional[str]):
    if not db_url:
        return None
    url = _normalize_sync_db_url_str(db_url)
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,  # recycle connections every 30 minutes
        connect_args={**_psycopg2_keepalive_args(), "connect_timeout": 10},
    )


def db_insert_or_get_audio_file_id(
    engine,
    audio_table: str,
    *,
    s3_url: str,
    url_sha1: str,
    b2_key: str,
    size_bytes: Optional[int],
) -> Optional[int]:
    if engine is None:
        return None
    # Prefer existing row by b2_object_key if it already exists in audio_files
    sql_by_b2 = text(f"SELECT id FROM {audio_table} WHERE b2_object_key = :b2_key LIMIT 1")
    sql_insert = text(
        f"""
        INSERT INTO {audio_table} (
            url, url_sha1, b2_object_key, file_size_bytes
        ) VALUES (
            :url, :url_sha1, :b2_object_key, :file_size_bytes
        )
        ON CONFLICT (url_sha1) DO NOTHING
        RETURNING id;
        """
    )
    sql_select = text(f"SELECT id FROM {audio_table} WHERE url_sha1 = :url_sha1")
    with engine.begin() as conn:
        # 1) Try to find by existing b2_object_key
        try:
            row_b2 = conn.execute(sql_by_b2, {"b2_key": b2_key}).fetchone()
            if row_b2 and row_b2[0]:
                return int(row_b2[0])
        except Exception:
            pass
        res = conn.execute(sql_insert, {
            "url": s3_url,
            "url_sha1": url_sha1,
            "b2_object_key": b2_key,
            "file_size_bytes": size_bytes,
        })
        row = res.fetchone()
        if row and row[0]:
            return int(row[0])
        res2 = conn.execute(sql_select, {"url_sha1": url_sha1})
        row2 = res2.fetchone()
        return int(row2[0]) if row2 else None


def db_get_transcription_row(
    engine,
    trans_table: str,
    *,
    audio_file_id: int,
) -> Optional[Tuple[int, str]]:
    if engine is None:
        return None
    sql = text(f"SELECT id, status FROM {trans_table} WHERE audio_file_id = :aid")
    with engine.begin() as conn:
        row = conn.execute(sql, {"aid": audio_file_id}).fetchone()
        return (int(row[0]), str(row[1])) if row else None


def _failure_upsert(
    engine,
    *,
    audio_file_id: int,
    provider: str,
    model: str,
    status: str,  # 'permanent' | 'transient'
    error_code: Optional[int],
    error: Optional[str],
    cooldown_minutes: int,
) -> None:
    if engine is None:
        return
    ignore_until_sql = (
        "(now() + make_interval(mins := :cooldown_minutes))"
        if status == "transient"
        else "NULL"
    )
    sql = text(
        f"""
        INSERT INTO media_pipeline.transcription_failures (
            audio_file_id, provider, model, status, error_code, error, ignore_until
        ) VALUES (
            :audio_file_id, :provider, :model, :status, :error_code, :error, {ignore_until_sql}
        )
        ON CONFLICT (audio_file_id) DO UPDATE SET
            last_attempt_at = now(),
            attempts = media_pipeline.transcription_failures.attempts + 1,
            status = EXCLUDED.status,
            error_code = EXCLUDED.error_code,
            error = EXCLUDED.error,
            ignore_until = EXCLUDED.ignore_until;
        """
    )
    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "audio_file_id": audio_file_id,
                "provider": provider,
                "model": model,
                "status": status,
                "error_code": error_code,
                "error": (error[:2000] if error else None),
                "cooldown_minutes": cooldown_minutes,
            },
        )


def _failure_delete(engine, *, audio_file_id: int) -> None:
    if engine is None:
        return
    sql = text("DELETE FROM media_pipeline.transcription_failures WHERE audio_file_id = :aid")
    with engine.begin() as conn:
        conn.execute(sql, {"aid": audio_file_id})


def _failure_should_skip(engine, *, audio_file_id: int) -> bool:
    if engine is None:
        return False
    sql = text(
        """
        SELECT status, ignore_until
        FROM media_pipeline.transcription_failures
        WHERE audio_file_id = :aid
        """
    )
    with engine.begin() as conn:
        row = conn.execute(sql, {"aid": audio_file_id}).fetchone()
        if not row:
            return False
        status = str(row[0]) if row[0] is not None else ""
        ignore_until = row[1]
        if status == "permanent":
            return True
        if status == "transient" and ignore_until is not None:
            # Skip if still cooling down
            return True if datetime.now(timezone.utc) < ignore_until else False
        return False


def db_upsert_transcription(
    engine,
    trans_table: str,
    *,
    audio_file_id: int,
    provider: str,
    model: str,
    status: str,
    transcript_text: Optional[str],
    segments_json: Optional[dict],
    metadata_json: Optional[dict],
    raw_response_json: Optional[dict],
    b2_transcript_key: Optional[str],
    completed: bool,
) -> None:
    if engine is None:
        return
    sql_with_raw = text(
        f"""
        INSERT INTO {trans_table} (
            audio_file_id, provider, model, status, completed_at,
            transcript_text, segments, metadata, raw_response, b2_transcript_key
        ) VALUES (
            :audio_file_id, :provider, :model, :status, :completed_at,
            :transcript_text, CAST(:segments AS JSONB), CAST(:metadata AS JSONB), CAST(:raw_response AS JSONB), :b2_transcript_key
        )
        ON CONFLICT (audio_file_id) DO UPDATE SET
            provider = EXCLUDED.provider,
            model = EXCLUDED.model,
            status = EXCLUDED.status,
            completed_at = EXCLUDED.completed_at,
            transcript_text = EXCLUDED.transcript_text,
            segments = EXCLUDED.segments,
            metadata = EXCLUDED.metadata,
            raw_response = EXCLUDED.raw_response,
            b2_transcript_key = EXCLUDED.b2_transcript_key;
        """
    )
    sql_no_raw = text(
        f"""
        INSERT INTO {trans_table} (
            audio_file_id, provider, model, status, completed_at,
            transcript_text, segments, metadata, b2_transcript_key
        ) VALUES (
            :audio_file_id, :provider, :model, :status, :completed_at,
            :transcript_text, CAST(:segments AS JSONB), CAST(:metadata AS JSONB), :b2_transcript_key
        )
        ON CONFLICT (audio_file_id) DO UPDATE SET
            provider = EXCLUDED.provider,
            model = EXCLUDED.model,
            status = EXCLUDED.status,
            completed_at = EXCLUDED.completed_at,
            transcript_text = EXCLUDED.transcript_text,
            segments = EXCLUDED.segments,
            metadata = EXCLUDED.metadata,
            b2_transcript_key = EXCLUDED.b2_transcript_key;
        """
    )
    completed_at = datetime.now(timezone.utc).isoformat() if completed else None
    params = {
        "audio_file_id": audio_file_id,
        "provider": provider,
        "model": model,
        "status": status,
        "completed_at": completed_at,
        "transcript_text": transcript_text,
        "segments": json.dumps(segments_json) if segments_json is not None else None,
        "metadata": json.dumps(metadata_json) if metadata_json is not None else None,
        "raw_response": json.dumps(raw_response_json) if raw_response_json is not None else None,
        "b2_transcript_key": b2_transcript_key,
    }
    with engine.begin() as conn:
        try:
            conn.execute(sql_with_raw, params)
        except Exception as e:
            # Fallback if raw_response column does not exist
            try:
                conn.execute(sql_no_raw, {k: v for k, v in params.items() if k != "raw_response"})
            except Exception:
                raise e


def _extract_duration_seconds(data: dict) -> Optional[float]:
    # Try common fields first
    for k in ("duration", "audio_duration", "duration_seconds"):
        v = data.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    # Try summing segments if present
    segs = data.get("segments")
    if isinstance(segs, list) and segs:
        try:
            start = segs[0].get("start")
            end = segs[-1].get("end")
            if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end >= start:
                return float(end - start)
        except Exception:
            pass
    return None


def _append_log(log_path: str, row: dict) -> None:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _preprocess_audio(in_path: str, out_path: str, resample_hz: int, mono_channels: int,
                      trim_sec: float | None, trim_db: float | None) -> str:
    """Re-encode to PCM 16-bit with resample/mono and optional reverse tail-trim.

    If trim_sec/trim_db provided, uses the robust reverse+silenceremove method.
    Returns path to processed file (out_path).
    """
    # Build ffmpeg command
    base_cmd = [
        "ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", in_path,
        "-ar", str(resample_hz),
        "-ac", str(mono_channels),
        "-c:a", "pcm_s16le",
    ]
    if trim_sec and trim_db:
        af = f"areverse,silenceremove=start_periods=1:start_duration={trim_sec}:start_threshold={trim_db}dB,areverse"
        base_cmd += ["-af", af]
    base_cmd += [out_path]
    subprocess.run(base_cmd, check=True)
    return out_path


def _normalize_language(language: Optional[str]) -> Optional[str]:
    if not language:
        return None
    lang = language.strip().lower()
    # Common German variants
    if lang in {"de", "de-de", "de_de", "german", "deutsch"}:
        return "de"
    return lang


def transcribe_with_openai(temp_audio_path: str, model: str, timestamps: str, language: Optional[str], prompt: Optional[str]) -> dict:
    """Call OpenAI transcription API and return the raw JSON response as dict.

    timestamps: one of "none", "segment", "word", "both"
    """
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("openai package is required. Install it in your environment.") from e

    client = OpenAI()

    want_ts = timestamps.lower() != "none"
    ts_values: List[str] = []
    if timestamps.lower() in ("segment", "both"):
        ts_values.append("segment")
    if timestamps.lower() in ("word", "both"):
        ts_values.append("word")

    with open(temp_audio_path, "rb") as f:
        # Choose response_format and timestamp support depending on model
        model_lc = model.lower()
        is_whisper = model_lc.startswith("whisper")
        is_gpt4o_transcribe = ("gpt-4o" in model_lc) and ("transcribe" in model_lc)

        # whisper-1 supports verbose_json; gpt-4o(-mini)-transcribe requires json
        response_format = "verbose_json" if (want_ts and is_whisper) else "json"

        kwargs = {
            "model": model,
            "file": f,
            "response_format": response_format,
        }
        norm_lang = _normalize_language(language)
        if norm_lang:
            kwargs["language"] = norm_lang
        # Biasing prompt for whisper models
        if prompt and is_whisper:
            kwargs["prompt"] = prompt
        # timestamp_granularities supported for gpt-4o(-mini)-transcribe; whisper-1 does not accept it
        if want_ts and ts_values and is_gpt4o_transcribe:
            kwargs["timestamp_granularities"] = ts_values

        try:
            resp = client.audio.transcriptions.create(**kwargs)
        except Exception as e:
            # Robust fallback: remove granularities and use json format
            kwargs.pop("timestamp_granularities", None)
            kwargs["response_format"] = "json"
            resp = client.audio.transcriptions.create(**kwargs)

    # Convert response object to plain dict
    # openai>=1.x returns a pydantic BaseModel-like object with model_dump()
    data: dict
    if hasattr(resp, "model_dump"):
        data = resp.model_dump()
    elif hasattr(resp, "to_dict"):
        data = resp.to_dict()
    else:
        # Best effort: try json serialization
        data = json.loads(json.dumps(resp, default=lambda o: getattr(o, "__dict__", str(o))))
    return data


def _should_treat_as_transient(err: Exception) -> bool:
    s = str(err).lower()
    # Heuristics for rate limits and server errors
    return (
        "429" in s
        or "rate limit" in s
        or "temporarily unavailable" in s
        or "timeout" in s
        or "timed out" in s
        or "connection reset" in s
        or "server error" in s
        or "5xx" in s
    )


def transcribe_with_retries(temp_audio_path: str, model: str, timestamps: str, language: Optional[str], prompt: Optional[str], *, max_retries: int = 3, base_delay: float = 1.0) -> dict:
    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return transcribe_with_openai(temp_audio_path, model, timestamps, language, prompt)
        except Exception as e:
            last_err = e
            if attempt >= max_retries or not _should_treat_as_transient(e):
                raise
            # Exponential backoff with jitter
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            time.sleep(delay)
    # Should not reach here
    assert last_err is not None
    raise last_err


def _db_select_candidate_keys(
    engine,
    audio_table: str,
    trans_table: str,
    *,
    prefix: str,
    skip_failed: bool,
) -> List[Tuple[str, Optional[str]]]:
    """Return list of (b2_object_key, phone) for items not yet completed (and not failed if requested)."""
    if engine is None:
        return []
    prefix_norm = (prefix or "").strip()
    if prefix_norm == "-":
        prefix_norm = ""
    params: Dict[str, Any] = {"skip_failed": int(1 if skip_failed else 0)}
    if prefix_norm:
        pref_like = prefix_norm.rstrip("/") + "/%"
        params["pref_like"] = pref_like
        sql_txt = f"""
        SELECT a.b2_object_key, a.phone
        FROM {audio_table} a
        LEFT JOIN {trans_table} t
          ON t.audio_file_id = a.id AND t.status = 'completed'
        LEFT JOIN media_pipeline.transcription_failures f
          ON f.audio_file_id = a.id
        WHERE a.b2_object_key LIKE :pref_like
          AND t.id IS NULL
          AND (
                :skip_failed = 0
             OR f.audio_file_id IS NULL
             OR (f.status = 'transient' AND (f.ignore_until IS NULL OR now() >= f.ignore_until))
          )
        ORDER BY a.phone NULLS LAST, a.id
        """
    else:
        sql_txt = f"""
        SELECT a.b2_object_key, a.phone
        FROM {audio_table} a
        LEFT JOIN {trans_table} t
          ON t.audio_file_id = a.id AND t.status = 'completed'
        LEFT JOIN media_pipeline.transcription_failures f
          ON f.audio_file_id = a.id
        WHERE t.id IS NULL
          AND (
                :skip_failed = 0
             OR f.audio_file_id IS NULL
             OR (f.status = 'transient' AND (f.ignore_until IS NULL OR now() >= f.ignore_until))
          )
        ORDER BY a.phone NULLS LAST, a.id
        """
    sql = text(sql_txt)
    with engine.begin() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [(str(r[0]), (str(r[1]) if r[1] is not None else None)) for r in rows]


def _db_ensure_claims_table(engine) -> None:
    if engine is None:
        return
    ddl = text(
        """
        CREATE TABLE IF NOT EXISTS media_pipeline.transcription_claims (
          audio_file_id BIGINT PRIMARY KEY
            REFERENCES media_pipeline.audio_files(id) ON DELETE CASCADE,
          claimed_by TEXT NOT NULL,
          claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          expires_at TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS ix_transcription_claims_expires
          ON media_pipeline.transcription_claims (expires_at);
        """
    )
    with engine.begin() as conn:
        conn.execute(ddl)


def _db_claim_candidates(
    engine,
    audio_table: str,
    trans_table: str,
    *,
    prefix: str,
    limit_n: int,
    claimed_by: str,
    ttl_minutes: int,
    skip_failed: bool,
):
    if engine is None:
        return []
    prefix_norm = (prefix or "").strip()
    if prefix_norm == "-":
        prefix_norm = ""
    params = {
        "skip_failed": int(1 if skip_failed else 0),
        "limit_n": int(max(1, limit_n)),
        "claimed_by": claimed_by,
        "ttl": int(ttl_minutes),
    }
    if prefix_norm:
        pref_like = prefix_norm.rstrip("/") + "/%"
        params["pref_like"] = pref_like
        sql_txt = f"""
        WITH candidates AS (
          SELECT a.id
          FROM {audio_table} a
          LEFT JOIN {trans_table} t
            ON t.audio_file_id = a.id AND t.status = 'completed'
          LEFT JOIN media_pipeline.transcription_failures f
            ON f.audio_file_id = a.id
               AND (f.status = 'permanent'
                    OR (f.status = 'transient' AND now() < COALESCE(f.ignore_until, now())))
          LEFT JOIN media_pipeline.transcription_claims c
            ON c.audio_file_id = a.id AND (c.expires_at IS NULL OR c.expires_at > now())
          WHERE a.b2_object_key LIKE :pref_like
            AND t.id IS NULL
            AND (:skip_failed = 0 OR f.audio_file_id IS NULL)
            AND c.audio_file_id IS NULL
          ORDER BY a.phone NULLS LAST, a.id
          LIMIT :limit_n
        ), ins AS (
          INSERT INTO media_pipeline.transcription_claims (audio_file_id, claimed_by, expires_at)
          SELECT id, :claimed_by, (now() + make_interval(mins := :ttl)) FROM candidates
          ON CONFLICT (audio_file_id) DO NOTHING
          RETURNING audio_file_id
        )
        SELECT a.id, a.b2_object_key, a.phone
        FROM {audio_table} a
        JOIN ins i ON i.audio_file_id = a.id
        ORDER BY a.phone NULLS LAST, a.id;
        """
    else:
        sql_txt = f"""
        WITH candidates AS (
          SELECT a.id
          FROM {audio_table} a
          LEFT JOIN {trans_table} t
            ON t.audio_file_id = a.id AND t.status = 'completed'
          LEFT JOIN media_pipeline.transcription_failures f
            ON f.audio_file_id = a.id
               AND (f.status = 'permanent'
                    OR (f.status = 'transient' AND now() < COALESCE(f.ignore_until, now())))
          LEFT JOIN media_pipeline.transcription_claims c
            ON c.audio_file_id = a.id AND (c.expires_at IS NULL OR c.expires_at > now())
          WHERE t.id IS NULL
            AND (:skip_failed = 0 OR f.audio_file_id IS NULL)
            AND c.audio_file_id IS NULL
          ORDER BY a.phone NULLS LAST, a.id
          LIMIT :limit_n
        ), ins AS (
          INSERT INTO media_pipeline.transcription_claims (audio_file_id, claimed_by, expires_at)
          SELECT id, :claimed_by, (now() + make_interval(mins := :ttl)) FROM candidates
          ON CONFLICT (audio_file_id) DO NOTHING
          RETURNING audio_file_id
        )
        SELECT a.id, a.b2_object_key, a.phone
        FROM {audio_table} a
        JOIN ins i ON i.audio_file_id = a.id
        ORDER BY a.phone NULLS LAST, a.id;
        """
    sql = text(sql_txt)
    with engine.begin() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [(int(r[0]), str(r[1]), (str(r[2]) if r[2] is not None else None)) for r in rows]


def _db_release_claim(engine, *, audio_file_id: int) -> None:
    if engine is None:
        return
    sql = text("DELETE FROM media_pipeline.transcription_claims WHERE audio_file_id = :aid")
    with engine.begin() as conn:
        conn.execute(sql, {"aid": audio_file_id})


def is_audio_key(key: str) -> bool:
    key_lower = key.lower()
    return key_lower.endswith((".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm"))


def main(argv: Optional[List[str]] = None) -> int:
    # Load .env from project root if present
    try:
        load_dotenv(find_dotenv())
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Transcribe audio from B2 using OpenAI gpt-4o-* models")
    parser.add_argument("--b2-prefix", required=True, help="B2 prefix to scan for audio objects")
    parser.add_argument("--output-dir", required=True, help="Directory to write raw JSON responses")
    parser.add_argument("--model", default="gpt-4o-transcribe", help="OpenAI model: gpt-4o-transcribe or gpt-4o-mini-transcribe or whisper-1")
    parser.add_argument("--timestamps", choices=["none", "segment", "word", "both"], default="segment", help="Timestamp granularity if supported by model")
    parser.add_argument("--bucket", default=None, help="B2 bucket name (overrides BACKBLAZE_B2_BUCKET)")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N files")
    parser.add_argument("--skip-existing", action="store_true", help="Skip if output file already exists")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite outputs if they exist")
    parser.add_argument("--dry-run", action="store_true", help="List what would be processed without calling APIs")
    parser.add_argument("--language", default=None, help="Optional language hint (e.g., 'de' for German)")
    parser.add_argument("--log-file", default=None, help="Path to JSONL log; defaults to <output-dir>/_log.jsonl")
    parser.add_argument("--cost-per-minute", type=float, default=None, help="Optional cost rate (e.g., 0.006 for $0.006/min). Used with inferred duration if available.")
    # Preprocess flags
    parser.add_argument("--preprocess", action="store_true", help="Enable audio preprocessing (resample + optional tail trim)")
    parser.add_argument("--pp-sr", type=int, default=16000, help="Preprocess sample rate (default 16000)")
    parser.add_argument("--pp-mono", type=int, default=1, help="Preprocess channels (default 1)")
    parser.add_argument("--pp-trim-sec", type=float, default=0.5, help="Tail trim duration seconds (reverse trim). 0 to disable")
    parser.add_argument("--pp-trim-db", type=float, default=-55.0, help="Tail trim threshold dB (e.g., -50 .. -60)")
    # Tail guard (for responses that include segment confidences such as whisper-1 verbose_json)
    parser.add_argument("--tail-guard", action="store_true", help="Drop last segment if confidence indicates no speech")
    parser.add_argument("--tg-max-no-speech", type=float, default=0.8, help="Drop if last.no_speech_prob >= this")
    parser.add_argument("--tg-min-avg-logprob", type=float, default=-1.2, help="Drop if last.avg_logprob <= this")
    parser.add_argument("--tg-max-seg-sec", type=float, default=1.0, help="Optionally require last segment duration <= this")

    # Database persistence options
    parser.add_argument("--db-url", default=None, help="Postgres URL, e.g., postgresql+psycopg2://user:pass@host:port/db")
    parser.add_argument("--db-audio-table", default="media_pipeline.audio_files", help="Qualified table name for audio files")
    parser.add_argument("--db-transcriptions-table", default="media_pipeline.transcriptions", help="Qualified table name for transcriptions")
    parser.add_argument("--db-skip-existing", action="store_true", help="Skip items already completed in DB")
    parser.add_argument("--only-new", action="store_true", help="Prefilter keys to only those without a completed transcription in DB")
    parser.add_argument("--max-files", type=int, default=None, help="Cap total items to process after DB filtering")
    parser.add_argument("--skip-failed", action="store_true", help="Skip items recorded in media_pipeline.transcription_failures (permanent or cooling down)")
    parser.add_argument("--cooldown-minutes", type=int, default=60, help="Cooldown minutes for transient failures before retry")
    parser.add_argument("--max-workers", type=int, default=1, help="Concurrent worker threads for processing")
    parser.add_argument("--selection-log-interval", type=int, default=500, help="Print a progress line every N scanned keys during selection")
    parser.add_argument("--select-from-db", action="store_true", help="Select candidate keys from SQL instead of listing B2 (faster for large sets)")
    parser.add_argument("--no-head", action="store_true", help="Skip B2 HEAD during selection (size_bytes may be filled after download)")
    parser.add_argument("--stream-select", action="store_true", help="Stream DB selection to workers via a bounded queue (overlaps selection with processing)")
    parser.add_argument("--fetch-chunk", type=int, default=1000, help="DB fetchmany chunk size when streaming selection")
    parser.add_argument("--queue-size", type=int, default=500, help="Bounded queue size for streamed selection")
    parser.add_argument("--use-claims", action="store_true", help="Use DB claim queue to prevent overlap across processes")
    parser.add_argument("--claim-ttl-minutes", type=int, default=60, help="Minutes until a claim expires (for retries)")
    # DB health/strictness
    parser.add_argument("--require-db", action="store_true", help="Exit if DB is not reachable at startup")
    parser.add_argument("--halt-on-db-error", action="store_true", help="Abort the run on the first DB write failure")
    parser.add_argument("--db-failure-threshold", type=int, default=5, help="Stop after N consecutive DB failures (when --halt-on-db-error not set)")

    # Upload transcript outputs to B2
    parser.add_argument("--upload-transcripts-to-b2", action="store_true", help="Upload output JSON to B2 as well")
    parser.add_argument("--b2-out-prefix", default="transcripts_json", help="B2 prefix for uploaded transcript JSONs")
    parser.add_argument("--upload-transcripts-txt-to-b2", action="store_true", help="Upload plain-text transcript to B2 as well")
    parser.add_argument("--b2-out-txt-prefix", default="transcripts_txt", help="B2 prefix for uploaded transcript TXT files")
    parser.add_argument("--no-local-save", action="store_true", help="Do not save per-file JSON/TXT locally; upload directly to B2 if enabled")
    # Prompt/biasing options
    parser.add_argument("--prompt", default=None, help="Optional biasing prompt text for models that support it (e.g., whisper-1)")
    parser.add_argument("--prompt-file", default=None, help="Path to a text file with prompt content")

    args = parser.parse_args(argv)

    bucket = args.bucket or os.environ.get("BACKBLAZE_B2_BUCKET") or os.environ.get("B2_BUCKET_NAME")
    if not bucket:
        print("Missing bucket. Set BACKBLAZE_B2_BUCKET or pass --bucket.", file=sys.stderr)
        return 2

    ensure_dir(args.output_dir)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    run_dir = os.path.join(args.output_dir, f"run_{run_id}")
    ensure_dir(run_dir)
    log_path = args.log_file or os.path.join(run_dir, "_log.jsonl")

    # Load prompt content
    prompt_text: Optional[str] = None
    try:
        if args.prompt_file:
            with open(args.prompt_file, "r", encoding="utf-8") as pf:
                prompt_text = pf.read()
        elif args.prompt:
            prompt_text = args.prompt
    except Exception:
        prompt_text = args.prompt

    # Optional DB engine (fallback to env var if --db-url not provided)
    db_url_effective = args.db_url or os.environ.get("DATABASE_URL")
    db_engine = db_get_engine(db_url_effective)

    # Optional startup DB health check
    if args.require_db:
        if db_engine is None:
            print("--require-db set but no DB URL configured", file=sys.stderr)
            return 2
        try:
            with db_engine.connect() as c:
                c.execute(text("select 1"))
        except Exception as e:
            print(f"DB health check failed: {e}", file=sys.stderr)
            return 2

    def process_key(key: str) -> dict:
        out_json = make_output_paths(run_dir, key)
        # Helper to release claim if claims are in use
        def _release_claim_if_needed(aid: Optional[int]) -> None:
            try:
                if args.use_claims and (aid is not None):
                    _db_release_claim(db_engine, audio_file_id=aid)
            except Exception:
                pass

        if args.skip_existing and os.path.exists(out_json) and not args.overwrite:
            # If we claimed this item, release the claim before skipping
            # Note: we may not yet have audio_file_id; resolve and release if possible
            try:
                s3_url_tmp = make_s3_url(bucket, key)
                url_hash_tmp = compute_url_sha1(s3_url_tmp)
                aid_tmp = db_insert_or_get_audio_file_id(
                    db_engine, args.db_audio_table,
                    s3_url=s3_url_tmp, url_sha1=url_hash_tmp, b2_key=key, size_bytes=None
                )
                _release_claim_if_needed(aid_tmp)
            except Exception:
                pass
            return {"skipped": True}

        started_at = datetime.now(timezone.utc).isoformat()
        size_bytes = None
        s3_url = make_s3_url(bucket, key)
        url_hash = compute_url_sha1(s3_url)
        if not args.no_head:
            s3_head = head_b2_object(bucket, key)
            size_bytes = s3_head.get("ContentLength")

        audio_file_id: Optional[int] = None
        try:
            audio_file_id = db_insert_or_get_audio_file_id(
                db_engine, args.db_audio_table,
                s3_url=s3_url, url_sha1=url_hash, b2_key=key, size_bytes=size_bytes
            )
        except Exception as e:
            print(f"DB audio_files upsert failed for {key}: {e}", file=sys.stderr)

        if args.skip_failed and (audio_file_id is not None) and _failure_should_skip(db_engine, audio_file_id=audio_file_id):
            _release_claim_if_needed(audio_file_id)
            return {"skipped": True}

        t0 = time.perf_counter()
        if args.dry_run:
            _release_claim_if_needed(audio_file_id)
            return {"processed": True, "status": "dry"}

        with tempfile.TemporaryDirectory() as td:
            tmp_path = os.path.join(td, os.path.basename(key))
            try:
                download_b2_object(bucket, key, tmp_path)
            except ClientError as e:
                _release_claim_if_needed(audio_file_id)
                return {"processed": True, "status": "error", "error": f"download_failed: {e}"}

            # If size was unknown or skipped due to --no-head, fill from the downloaded file
            if size_bytes is None:
                try:
                    size_bytes = os.path.getsize(tmp_path)
                except Exception:
                    size_bytes = None

            proc_path = tmp_path
            if args.preprocess:
                try:
                    outp = os.path.join(td, "proc.wav")
                    trim_sec = args.pp_trim_sec if args.pp_trim_sec and args.pp_trim_sec > 0 else None
                    proc_path = _preprocess_audio(
                        tmp_path, outp, args.pp_sr, args.pp_mono, trim_sec, args.pp_trim_db
                    )
                except Exception as e:
                    proc_path = tmp_path

            api_t0 = time.perf_counter()

            if audio_file_id is not None:
                try:
                    if args.db_skip_existing:
                        existing = db_get_transcription_row(db_engine, args.db_transcriptions_table, audio_file_id=audio_file_id)
                        if existing and existing[1] == "completed":
                            _release_claim_if_needed(audio_file_id)
                            return {"skipped": True}
                    db_upsert_transcription(
                        db_engine, args.db_transcriptions_table,
                        audio_file_id=audio_file_id,
                        provider="OpenAI",
                        model=args.model,
                        status="pending",
                        transcript_text=None,
                        segments_json=None,
                        metadata_json={
                            "language": args.language,
                            "bucket": bucket,
                            "b2_key": key,
                            "size_bytes": size_bytes,
                            "started_at": started_at,
                            "prompt": (prompt_text if prompt_text else None),
                        },
                        raw_response_json=None,
                        b2_transcript_key=None,
                        completed=False,
                    )
                except Exception:
                    pass

            err_msg = None
            data = None
            try:
                data = transcribe_with_retries(proc_path, args.model, args.timestamps, args.language, prompt_text)
            except Exception as e:
                err_msg = str(e)

            api_t1 = time.perf_counter()

            if args.tail_guard and isinstance(data, dict):
                segs = data.get("segments")
                if isinstance(segs, list) and segs:
                    last = segs[-1]
                    if isinstance(last, dict):
                        ns = last.get("no_speech_prob")
                        lp = last.get("avg_logprob") if last.get("avg_logprob") is not None else last.get("avg_log_prob")
                        st = last.get("start"); en = last.get("end")
                        dur_ok = True
                        if isinstance(st, (int, float)) and isinstance(en, (int, float)) and en >= st:
                            dur = float(en - st)
                            if args.tg_max_seg_sec is not None:
                                dur_ok = dur <= float(args.tg_max_seg_sec)
                        drop = False
                        if isinstance(ns, (int, float)) and ns >= args.tg_max_no_speech:
                            drop = True
                        if isinstance(lp, (int, float)) and lp <= args.tg_min_avg_logprob:
                            drop = True
                        if drop and dur_ok:
                            data["segments"] = segs[:-1]

            out_json_path = out_json
            if data is not None and not args.no_local_save:
                try:
                    with open(out_json_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    err_msg = f"write_failed: {e}"

            b2_transcript_key = None
            b2_transcript_txt_key = None
            if (data is not None) and args.upload_transcripts_to_b2:
                try:
                    s3 = make_b2_client_from_env()
                    # Build transcript key by mirroring the original audio key and replacing '/audio/'
                    base_no_ext = os.path.splitext(os.path.basename(out_json))[0]
                    idx = key.find("/audio/")
                    if idx != -1:
                        prefix_keep = key[:idx]
                        rest_after_audio = key[idx + len("/audio/"):]
                        rest_dir = os.path.dirname(rest_after_audio).replace("\\", "/")
                        b2_transcript_key = f"{prefix_keep}/transcriptions/json/{rest_dir}/{base_no_ext}.json".rstrip('/')
                    else:
                        # If '/audio/' not found, fall back to prefix mirroring
                        rel = _rel_path_under_prefix(key, args.b2_prefix)
                        rel_dir = os.path.dirname(rel).replace("\\", "/")
                        prefix_dir = (args.b2_prefix.rstrip('/') + '/') if args.b2_prefix else ''
                        b2_transcript_key = f"{prefix_dir}{args.b2_out_prefix}/{rel_dir}/{base_no_ext}.json".rstrip('/')
                    if args.no_local_save:
                        # Upload JSON from memory
                        s3.put_object(Bucket=bucket, Key=b2_transcript_key, Body=json.dumps(data).encode("utf-8"), ContentType="application/json")
                    else:
                        if os.path.exists(out_json_path):
                            s3.upload_file(out_json_path, bucket, b2_transcript_key)
                except Exception:
                    b2_transcript_key = None

            if (data is not None) and args.upload_transcripts_txt_to_b2:
                try:
                    txt = None
                    if isinstance(data, dict):
                        txt = data.get("text")
                        segs_val = data.get("segments") if isinstance(data.get("segments"), list) else []
                        if not txt and segs_val:
                            txt = "\n".join([str(s.get("text", "")).strip() for s in segs_val])
                    if txt and txt.strip():
                        try:
                            s3 = make_b2_client_from_env()
                            base_no_ext = os.path.splitext(os.path.basename(out_json))[0]
                            idx = key.find("/audio/")
                            if idx != -1:
                                prefix_keep = key[:idx]
                                rest_after_audio = key[idx + len("/audio/"):]
                                rest_dir = os.path.dirname(rest_after_audio).replace("\\", "/")
                                dest_dir = f"{prefix_keep}/transcriptions/txt/{rest_dir}".rstrip('/')
                            else:
                                rel = _rel_path_under_prefix(key, args.b2_prefix)
                                rel_dir = os.path.dirname(rel).replace("\\", "/")
                                prefix_dir = (args.b2_prefix.rstrip('/') + '/') if args.b2_prefix else ''
                                dest_dir = f"{prefix_dir}{args.b2_out_txt_prefix}/{rel_dir}".rstrip('/')
                            if args.no_local_save:
                                b2_transcript_txt_key = f"{dest_dir}/{base_no_ext}.txt".rstrip('/')
                                s3.put_object(Bucket=bucket, Key=b2_transcript_txt_key, Body=txt.encode("utf-8"), ContentType="text/plain; charset=utf-8")
                            else:
                                out_txt = os.path.splitext(out_json_path)[0] + ".txt"
                                with open(out_txt, "w", encoding="utf-8") as tf:
                                    tf.write(txt)
                                b2_transcript_txt_key = f"{dest_dir}/{os.path.basename(out_txt)}".rstrip('/')
                                s3.upload_file(out_txt, bucket, b2_transcript_txt_key)
                        except Exception:
                            b2_transcript_txt_key = None
                except Exception:
                    pass

            t1 = time.perf_counter()

            # For logging, show local output path if saved, else B2 JSON key if available
            row = {
                "timestamp": started_at,
                "model": args.model,
                "language": args.language,
                "bucket": bucket,
                "b2_key": key,
                "output_path": (out_json_path if not args.no_local_save else (f"s3://{bucket}/{b2_transcript_key}" if b2_transcript_key else out_json_path)),
                "size_bytes": size_bytes,
                "wall_ms_total": round((t1 - t0) * 1000, 2),
                "wall_ms_api": round((api_t1 - api_t0) * 1000, 2),
                "status": "ok" if (data is not None and err_msg is None) else "error",
                "error": err_msg,
            }
            if data is not None:
                sec = _extract_duration_seconds(data)
                if sec is not None:
                    row["audio_duration_sec"] = round(sec, 3)
                    if args.cost_per_minute is not None:
                        row["est_cost"] = round(args.cost_per_minute * (sec / 60.0), 6)

            try:
                _append_log(log_path, row)
            except Exception:
                pass

            # Final DB upsert and failure table maintenance
        if audio_file_id is not None:
            try:
                transcript_text: Optional[str] = None
                segments_json: Optional[dict] = None
                if isinstance(data, dict):
                    transcript_text = data.get("text") or None
                    if isinstance(data.get("segments"), list):
                        segments_json = {"segments": data.get("segments")}
                status_str = "ok" if (data is not None and err_msg is None) else "failed"
                db_upsert_transcription(
                    db_engine, args.db_transcriptions_table,
                    audio_file_id=audio_file_id,
                    provider="OpenAI",
                    model=args.model,
                    status="completed" if status_str == "ok" else "failed",
                    transcript_text=transcript_text,
                    segments_json=segments_json,
                    metadata_json={
                        "language": args.language,
                        "bucket": bucket,
                        "b2_key": key,
                        "b2_transcript_json_key": b2_transcript_key,
                        "b2_transcript_txt_key": b2_transcript_txt_key,
                        "size_bytes": size_bytes,
                        "wall_ms_total": row.get("wall_ms_total"),
                        "wall_ms_api": row.get("wall_ms_api"),
                        "error": err_msg,
                        "prompt": (prompt_text if prompt_text else None),
                    },
                    raw_response_json=(data if isinstance(data, dict) else None),
                    b2_transcript_key=b2_transcript_key,
                    completed=True,
                )
                if status_str == "ok":
                    _failure_delete(db_engine, audio_file_id=audio_file_id)
                else:
                    # Classify error transient/permanent heuristically
                    is_transient = _should_treat_as_transient(Exception(err_msg or ""))
                    _failure_upsert(
                        db_engine,
                        audio_file_id=audio_file_id,
                        provider="OpenAI",
                        model=args.model,
                        status=("transient" if is_transient else "permanent"),
                        error_code=None,
                        error=err_msg,
                        cooldown_minutes=args.cooldown_minutes,
                )
            except Exception as e:
                print(f"DB upsert transcription failed for {key}: {e}", file=sys.stderr)
                if args.halt_on_db_error:
                    raise

            # Release claim after finishing DB upsert and before returning
            _release_claim_if_needed(audio_file_id)
            return {
                "processed": True,
                "status": ("ok" if (data is not None and err_msg is None) else "error"),
                "wall_ms_total": row.get("wall_ms_total", 0) or 0,
                "wall_ms_api": row.get("wall_ms_api", 0) or 0,
                "audio_duration_sec": row.get("audio_duration_sec", 0) or 0,
                "est_cost": row.get("est_cost", 0) or 0,
            }

        # Fallback (should not reach)
        _release_claim_if_needed(audio_file_id)
        return {"processed": False, "status": "skipped"}

    # Stream keys and prefilter; group by phone to preserve groups for --max-files.
    phone_order: List[str] = []
    phone_to_keys: dict[str, List[str]] = {}
    completed_phone_counts: dict[str, int] = {}
    selected: List[str] = []
    current_phone: Optional[str] = None
    scanned = 0

    def _maybe_finish_phone_and_check_cap(next_phone: Optional[str]) -> bool:
        # When switching phones, update totals and decide if we can stop
        nonlocal current_phone
        if current_phone is None or next_phone == current_phone:
            return False
        # We finished listing one phone; evaluate cap
        if args.max_files is not None:
            total_done = sum(len(phone_to_keys.get(p, [])) for p in phone_order)
            if total_done >= args.max_files:
                return True
        return False

    if args.select_from_db and db_engine is not None and not args.stream_select:
        print(f"Selecting from DB under prefix '{args.b2_prefix}' ...", flush=True)
        # Fetch candidates from DB (claims if requested)
        if args.use_claims:
            _db_ensure_claims_table(db_engine)
            host = socket.gethostname()
            claimed = _db_claim_candidates(
                db_engine,
                args.db_audio_table,
                args.db_transcriptions_table,
                prefix=args.b2_prefix,
                limit_n=(args.max_files or 1000000),
                claimed_by=host,
                ttl_minutes=args.claim_ttl_minutes,
                skip_failed=args.skip_failed,
            )
            db_rows = [(k, p) for (_aid, k, p) in claimed]
        else:
            db_rows = _db_select_candidate_keys(
                db_engine,
                args.db_audio_table,
                args.db_transcriptions_table,
                prefix=args.b2_prefix,
                skip_failed=args.skip_failed,
            )

        scanned = len(db_rows)
        for key, phone in db_rows:
            rel = _rel_path_under_prefix(key, args.b2_prefix)
            p = phone or (rel.split("/", 1)[0] if "/" in rel else rel)

            if _maybe_finish_phone_and_check_cap(p):
                break

            out_json = make_output_paths(run_dir, key)
            if args.skip_existing and os.path.exists(out_json) and not args.overwrite:
                continue

            if p not in phone_to_keys:
                phone_to_keys[p] = []
                phone_order.append(p)
            phone_to_keys[p].append(key)
            current_phone = p

        # Finalize selection; respect cap without splitting last phone
        total = 0
        for p in phone_order:
            keys = phone_to_keys.get(p, [])
            if not keys:
                continue
            selected.extend(keys)
            total += len(keys)
            if args.max_files is not None and total >= args.max_files:
                break

        print(
            f"Selection complete (DB): scanned={scanned}, phones={len(phone_order)}, selected={len(selected)}",
            flush=True,
        )
    else:
        print(f"Starting selection scan under prefix '{args.b2_prefix}' ...", flush=True)
        for key in list_b2_objects(bucket, args.b2_prefix):
            if not is_audio_key(key):
                continue
            scanned += 1
            rel = _rel_path_under_prefix(key, args.b2_prefix)
            phone = rel.split("/", 1)[0] if "/" in rel else rel

            # If we are switching phones, check if cap reached with completed phones
            if _maybe_finish_phone_and_check_cap(phone):
                break

            # local skip-existing based on output path inside this run
            out_json = make_output_paths(run_dir, key)
            if args.skip_existing and os.path.exists(out_json) and not args.overwrite:
                continue

            include = True
            aid: Optional[int] = None
            if args.only_new or args.skip_failed:
                s3_url = make_s3_url(bucket, key)
                url_hash = compute_url_sha1(s3_url)
                size_bytes = None
                try:
                    size_bytes = head_b2_object(bucket, key).get("ContentLength")
                except Exception:
                    pass
                try:
                    aid = db_insert_or_get_audio_file_id(
                        db_engine, args.db_audio_table,
                        s3_url=s3_url, url_sha1=url_hash, b2_key=key, size_bytes=size_bytes
                    )
                except Exception:
                    aid = None
                if args.only_new and aid is not None:
                    existing = db_get_transcription_row(db_engine, args.db_transcriptions_table, audio_file_id=aid)
                    if existing and existing[1] == "completed":
                        include = False
                if include and args.skip_failed and aid is not None and _failure_should_skip(db_engine, audio_file_id=aid):
                    include = False

            if not include:
                continue

            if phone not in phone_to_keys:
                phone_to_keys[phone] = []
                phone_order.append(phone)
            phone_to_keys[phone].append(key)
            current_phone = phone

            # Optionally print coarse progress every 1000 scanned keys
            if args.selection_log_interval > 0 and (scanned % args.selection_log_interval == 0):
                print(f"Scanned {scanned} keys... phones={len(phone_order)}", flush=True)

        # Finalize selection. Respect cap without splitting last phone.
        total = 0
        for p in phone_order:
            keys = phone_to_keys.get(p, [])
            if not keys:
                continue
            selected.extend(keys)
            total += len(keys)
            if args.max_files is not None and total >= args.max_files:
                break

        print(
            f"Selection complete: scanned={scanned}, phones={len(phone_order)}, selected={len(selected)}",
            flush=True,
        )

    # Streamed selection: start producer to enqueue keys while workers process them
    if args.stream_select and args.select_from_db and db_engine is not None and not args.dry_run:
        q: Queue = Queue(maxsize=max(1, args.queue_size))
        stop_flag = threading.Event()
        SENTINEL = object()

        def producer() -> None:
            try:
                if args.use_claims:
                    _db_ensure_claims_table(db_engine)
                    host = socket.gethostname()
                    claimed = _db_claim_candidates(
                        db_engine,
                        args.db_audio_table,
                        args.db_transcriptions_table,
                        prefix=args.b2_prefix,
                        limit_n=(args.max_files or 1000000),
                        claimed_by=host,
                        ttl_minutes=args.claim_ttl_minutes,
                        skip_failed=args.skip_failed,
                    )
                    # map to key/phone tuples
                    db_rows = [(k, p) for (_aid, k, p) in claimed]
                else:
                    db_rows = _db_select_candidate_keys(
                        db_engine,
                        args.db_audio_table,
                        args.db_transcriptions_table,
                        prefix=args.b2_prefix,
                        skip_failed=args.skip_failed,
                    )
                count = 0
                total_enq = 0
                last_phone: Optional[str] = None
                for key, phone in db_rows:
                    if stop_flag.is_set():
                        break
                    rel = _rel_path_under_prefix(key, args.b2_prefix)
                    p = phone or (rel.split("/", 1)[0] if "/" in rel else rel)
                    if last_phone is None:
                        last_phone = p
                    if p != last_phone:
                        if args.max_files is not None and total_enq >= args.max_files:
                            break
                        last_phone = p
                    out_json = make_output_paths(run_dir, key)
                    if args.skip_existing and os.path.exists(out_json) and not args.overwrite:
                        continue
                    q.put(key)
                    total_enq += 1
                    count += 1
                    if args.selection_log_interval > 0 and (count % args.selection_log_interval == 0):
                        print(f"Queued {count} keys (stream)...", flush=True)
            except Exception as e:
                print(f"Producer error: {e}", file=sys.stderr)
            finally:
                q.put(SENTINEL)

        prod_thread = threading.Thread(target=producer, daemon=True)
        prod_thread.start()

        # Consume from queue
        processed = 0
        sum_wall = sum_api = sum_cost = sum_dur = 0.0
        ok_count = err_count = 0
        consecutive_db_failures = 0
        with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as ex:
            futures: set = set()
            done_signal = False
            while True:
                try:
                    item = q.get(timeout=1)
                except Empty:
                    # No item yet; if producer finished and no futures pending, we can exit
                    if done_signal and not futures:
                        break
                    continue
                if item is SENTINEL:
                    done_signal = True
                    # continue draining any remaining futures
                    continue
                key = item  # a real key string
                futures.add(ex.submit(process_key, key))
                # Drain any completed futures
                done_now = set()
                for fut in futures:
                    if fut.done():
                        done_now.add(fut)
                for fut in done_now:
                    futures.remove(fut)
                    try:
                        res = fut.result()
                    except Exception:
                        err_count += 1
                        continue
                    if res.get("skipped"):
                        continue
                    processed += 1 if res.get("processed") else 0
                    if res.get("status") == "ok":
                        ok_count += 1
                        consecutive_db_failures = 0
                    elif res.get("status") == "error":
                        err_count += 1
                        if args.halt_on_db_error:
                            print("Halting due to DB error (--halt-on-db-error)", file=sys.stderr)
                            stop_flag.set()
                            break
                        consecutive_db_failures += 1
                        if consecutive_db_failures >= max(1, args.db_failure_threshold):
                            print(f"Halting: consecutive DB failures >= {args.db_failure_threshold}", file=sys.stderr)
                            stop_flag.set()
                            break
                    sum_wall += float(res.get("wall_ms_total", 0) or 0)
                    sum_api += float(res.get("wall_ms_api", 0) or 0)
                    sum_cost += float(res.get("est_cost", 0) or 0)
                    sum_dur += float(res.get("audio_duration_sec", 0) or 0)

        # Safe summary values
        processed = processed or 0
        ok_count = ok_count or 0
        err_count = err_count or 0
        sum_wall = sum_wall or 0.0
        sum_api = sum_api or 0.0
        sum_dur = sum_dur or 0.0
        sum_cost = sum_cost or 0.0

        summary = {
            "model": args.model,
            "language": args.language,
            "prefix": args.b2_prefix,
            "selected": None,
            "processed": processed,
            "ok": ok_count,
            "errors": err_count,
            "total_wall_ms": round(sum_wall, 2),
            "total_api_ms": round(sum_api, 2),
            "total_audio_sec": round(sum_dur, 3),
            "total_cost": round(sum_cost, 6),
            "avg_wall_ms": round((sum_wall / max(1, ok_count)), 2),
            "avg_api_ms": round((sum_api / max(1, ok_count)), 2),
        }
        try:
            with open(os.path.join(run_dir, "_summary.json"), "w", encoding="utf-8") as sf:
                json.dump(summary, sf, ensure_ascii=False, indent=2)
        except Exception:
            pass

        print(f"Done. Processed: {processed} OK: {ok_count} Errors: {err_count}")
        return 0

    # Non-streamed path: process selected keys now
    processed = 0
    sum_wall = 0.0
    sum_api = 0.0
    sum_cost = 0.0
    sum_dur = 0.0
    ok_count = 0
    err_count = 0

    if args.dry_run:
        processed = len(selected)
    else:
        consecutive_db_failures = 0
        with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as ex:
            futures_list = [ex.submit(process_key, key) for key in selected]
            for fut in as_completed(futures_list):
                try:
                    res = fut.result()
                except Exception:
                    err_count += 1
                    continue
                if res.get("skipped"):
                    continue
                processed += 1 if res.get("processed") else 0
                if res.get("status") == "ok":
                    ok_count += 1
                    consecutive_db_failures = 0
                elif res.get("status") == "error":
                    err_count += 1
                    if args.halt_on_db_error:
                        print("Halting due to DB error (--halt-on-db-error)", file=sys.stderr)
                        break
                    consecutive_db_failures += 1
                    if consecutive_db_failures >= max(1, args.db_failure_threshold):
                        print(f"Halting: consecutive DB failures >= {args.db_failure_threshold}", file=sys.stderr)
                        break
                sum_wall += float(res.get("wall_ms_total", 0) or 0)
                sum_api += float(res.get("wall_ms_api", 0) or 0)
                sum_cost += float(res.get("est_cost", 0) or 0)
                sum_dur += float(res.get("audio_duration_sec", 0) or 0)

    summary = {
        "model": args.model,
        "language": args.language,
        "prefix": args.b2_prefix,
        "selected": len(selected),
        "processed": processed,
        "ok": ok_count,
        "errors": err_count,
        "total_wall_ms": round(sum_wall, 2),
        "total_api_ms": round(sum_api, 2),
        "total_audio_sec": round(sum_dur, 3),
        "total_cost": round(sum_cost, 6),
        "avg_wall_ms": round(sum_wall / max(1, ok_count), 2),
        "avg_api_ms": round(sum_api / max(1, ok_count), 2),
    }
    try:
        with open(os.path.join(run_dir, "_summary.json"), "w", encoding="utf-8") as sf:
            json.dump(summary, sf, ensure_ascii=False, indent=2)
    except Exception:
        pass

    print(f"Done. Selected: {len(selected)} Processed: {processed} OK: {ok_count} Errors: {err_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


