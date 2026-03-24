"""
Fetch audio files for human evaluation packets.

Reads Markdown files in an eval directory, extracts recording IDs (PR_*), looks
up their B2 object keys in Postgres, and downloads the audio from Backblaze B2
to a local folder.

Usage (PowerShell):
python data_pipelines/scripts/fetch_eval_audio.py `
  --eval-dir "data_pipelines/data/transcriptions/human_eval2" `
  --db-url "postgresql+psycopg2://postgres:Kii366@127.0.0.1:5433/manuav" `
  --table-name "media_pipeline.audio_files" `
  --out-dir "data_pipelines/data/human_eval_audio"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Dict, List, Optional

from dotenv import load_dotenv, find_dotenv
from sqlalchemy import create_engine, text


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def extract_recording_id_from_basename(name: str) -> Optional[str]:
    m = re.search(r"PR_[A-Za-z0-9\-]+", name)
    return m.group(0) if m else None


def list_eval_basenames(eval_dir: str) -> List[str]:
    bases: List[str] = []
    for fname in os.listdir(eval_dir):
        if not fname.lower().endswith(".md"):
            continue
        base = fname[:-3]
        bases.append(base)
    return bases


def _normalize_sync_db_url(db_url: str) -> str:
    if db_url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg2://" + db_url.split("://", 1)[1]
    return db_url


def _psycopg2_keepalive_args() -> dict:
    return {
        "keepalives": 1,
        "keepalives_idle": 60,
        "keepalives_interval": 30,
        "keepalives_count": 5,
    }


def query_b2_keys(db_url: str, table_name: str, rec_ids: List[str]) -> Dict[str, str]:
    if not rec_ids:
        return {}
    engine = create_engine(
        _normalize_sync_db_url(db_url),
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args=_psycopg2_keepalive_args(),
    )
    placeholders = ",".join(f":id{i}" for i in range(len(rec_ids)))
    sql = text(f"""
        SELECT recording_id, b2_object_key
        FROM {table_name}
        WHERE recording_id IN ({placeholders})
    """)
    params = {f"id{i}": rid for i, rid in enumerate(rec_ids)}
    mapping: Dict[str, str] = {}
    with engine.connect() as conn:
        for row in conn.execute(sql, params):
            rid, key = row[0], row[1]
            if rid and key:
                mapping[str(rid)] = str(key)
    return mapping


def make_b2_client_from_env():
    from boto3.session import Session  # type: ignore
    endpoint_url = os.environ.get("BACKBLAZE_B2_S3_ENDPOINT") or os.environ.get("AWS_ENDPOINT_URL")
    region_name = os.environ.get("BACKBLAZE_B2_REGION") or os.environ.get("AWS_REGION") or "auto"
    key_id = os.environ.get("BACKBLAZE_B2_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID")
    app_key = os.environ.get("BACKBLAZE_B2_APPLICATION_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not endpoint_url or not key_id or not app_key:
        raise RuntimeError("Missing B2 env vars.")
    sess = Session()
    return sess.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region_name,
        aws_access_key_id=key_id,
        aws_secret_access_key=app_key,
    )


def download_from_b2(bucket: str, key: str, out_dir: str) -> str:
    ensure_dir(out_dir)
    client = make_b2_client_from_env()
    fname = os.path.basename(key)
    out_path = os.path.join(out_dir, fname)
    client.download_file(bucket, key, out_path)
    return out_path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch audio files for human eval basenames")
    p.add_argument("--eval-dir", required=True)
    p.add_argument("--db-url", required=True)
    p.add_argument("--table-name", default="media_pipeline.audio_files")
    p.add_argument("--out-dir", default="data_pipelines/data/human_eval_audio")
    p.add_argument("--bucket", default=None, help="Override bucket (defaults to BACKBLAZE_B2_BUCKET)")
    return p.parse_args()


def main() -> int:
    load_dotenv(find_dotenv())
    args = parse_args()

    bases = list_eval_basenames(args.eval_dir)
    rec_ids = [rid for b in bases if (rid := extract_recording_id_from_basename(b))]
    if not rec_ids:
        print("No recording IDs found in eval directory.")
        return 1

    rid_to_key = query_b2_keys(args.db_url, args.table_name, rec_ids)
    missing = [rid for rid in rec_ids if rid not in rid_to_key]
    if missing:
        print(f"Warning: {len(missing)} recording_id(s) missing b2_object_key in DB:")
        for rid in missing:
            print(f"  - {rid}")

    bucket = args.bucket or os.environ.get("BACKBLAZE_B2_BUCKET") or os.environ.get("B2_BUCKET_NAME")
    if not bucket:
        print("Missing bucket (env BACKBLAZE_B2_BUCKET)")
        return 2

    ok, fail = 0, 0
    for rid, key in rid_to_key.items():
        try:
            path = download_from_b2(bucket, key, args.out_dir)
            print(f"Downloaded {rid} -> {path}")
            ok += 1
        except Exception as e:
            print(f"Failed {rid} ({key}): {e}")
            fail += 1

    print(f"Done. OK={ok} FAIL={fail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


