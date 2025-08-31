import argparse
import concurrent.futures
import time
import csv
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional, Any, Callable, TypeVar, Tuple, cast

import pandas as pd
import requests
from dotenv import load_dotenv
from sqlalchemy import BigInteger, Integer, Column, DateTime, Float, MetaData, String, Table, create_engine, insert, select, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from tqdm import tqdm


DATETIME_FMT = "%Y-%m-%d %H:%M:%S.%f"
def _normalize_sync_db_url(db_url: Optional[str]) -> Optional[str]:
    """
    Ensure a synchronous SQLAlchemy driver is used.
    If an async driver (postgresql+asyncpg) is provided, switch to psycopg2.
    """
    if not db_url:
        return None
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


@dataclass
class AudioEntry:
    """
    Represents a single audio file to download and catalog.

    Attributes
    - phone: Phone number associated with the call (as found in CSV).
    - campaign_name: Campaign name from the CSV.
    - recording_id: Provider-specific recording ID, if available.
    - url: Direct URL to the audio file.
    - started: Call start timestamp, if available.
    - stopped: Call end timestamp, if available.
    - duration_seconds: Duration in seconds, if available.
    """

    phone: str
    campaign_name: Optional[str]
    recording_id: Optional[str]
    url: str
    started: Optional[datetime]
    stopped: Optional[datetime]
    duration_seconds: Optional[float]
    # Optional provenance to original source row id (e.g., public.recordings.id)
    source_row_id: Optional[int] = None


def sanitize_for_path(value: Optional[str]) -> str:
    if not value:
        return "unknown"
    sanitized = re.sub(r"[^A-Za-z0-9_.\-+]+", "_", value.strip())
    return sanitized.strip("._") or "unknown"


def sanitize_phone(phone: Optional[str]) -> str:
    if not phone:
        return "unknown_phone"
    original = phone.strip()
    # Keep only digits for the body
    digits_only = re.sub(r"\D", "", original)
    if not digits_only:
        return "unknown_phone"
    # Preserve a single leading plus if it was present originally
    return ("+" if original.startswith("+") else "") + digits_only


def sha256_of_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def short_hash(text: str, length: int = 10) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value or pd.isna(value):
        return None
    # Try several common formats
    for fmt in [DATETIME_FMT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"]:
        try:
            return datetime.strptime(str(value), fmt)
        except Exception:
            continue
    try:
        return pd.to_datetime(value, utc=False).to_pydatetime()
    except Exception:
        return None


def detect_csv_type(df: pd.DataFrame) -> str:
    """
    Returns 'flat' if there's one row per recording with a 'location' or 'url' column.
    Returns 'grouped' if there's a 'recording_urls' column that contains many URLs.
    """
    cols = set(c.lower() for c in df.columns)
    if "location" in cols or "url" in cols:
        return "flat"
    if "recording_urls" in cols:
        return "grouped"
    raise ValueError("CSV schema not recognized. Expecting either a 'location' column or a 'recording_urls' column.")


def load_entries_from_flat_csv(df: pd.DataFrame) -> List[AudioEntry]:
    entries: List[AudioEntry] = []
    for _, row in df.iterrows():
        # Allow either 'location' or 'url' as the URL column
        url_value = str(row.get("location", "")).strip() or str(row.get("url", "")).strip()
        # Optional provenance column from CSV: 'recordings_row_id'
        src_row_raw = str(row.get("recordings_row_id", "")).strip()
        src_row_id: Optional[int] = None
        if src_row_raw.isdigit():
            try:
                src_row_id = int(src_row_raw)
            except Exception:
                src_row_id = None

        entries.append(
            AudioEntry(
                phone=str(row.get("phone", "")).strip(),
                campaign_name=str(row.get("campaign_name", "")).strip() or None,
                recording_id=str(row.get("recording_id", "")).strip() or None,
                url=url_value,
                started=parse_datetime(row.get("started")),
                stopped=parse_datetime(row.get("stopped")),
                # Convert to float only when the value is present and non-empty
                duration_seconds=(
                    float(str(row.get("duration_seconds")).strip())
                    if str(row.get("duration_seconds", "")).strip() not in ("", "None")
                    else None
                ),
                source_row_id=src_row_id,
            )
        )
    return entries


def load_entries_from_grouped_csv(df: pd.DataFrame) -> List[AudioEntry]:
    entries: List[AudioEntry] = []
    for _, row in df.iterrows():
        phone = str(row.get("phone", "")).strip()
        campaign_name = str(row.get("campaign_name", "")).strip() or None
        urls_blob = row.get("recording_urls")
        if urls_blob is None or str(urls_blob).strip() == "":
            continue
        # The field contains one URL per line
        for url in str(urls_blob).splitlines():
            url = url.strip()
            if not url:
                continue
            # Derive a recording_id from URL if possible
            rec_id_match = re.search(r"PR_([A-Za-z0-9\-]+)", url)
            rec_id = rec_id_match.group(1) if rec_id_match else None
            entries.append(
                AudioEntry(
                    phone=phone,
                    campaign_name=campaign_name,
                    recording_id=rec_id,
                    url=url,
                    started=None,
                    stopped=None,
                    duration_seconds=None,
                )
            )
    return entries


def read_csv_flex(csv_path: str) -> List[AudioEntry]:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, quoting=csv.QUOTE_MINIMAL)
    csv_type = detect_csv_type(df)
    if csv_type == "flat":
        return load_entries_from_flat_csv(df)
    return load_entries_from_grouped_csv(df)


def ensure_table(engine: Engine, qualified_name: str) -> Table:
    """
    Resolve a Table, supporting schema-qualified names (e.g., "media_pipeline.audio_files").
    If the table exists, reflect it. Otherwise, create a compatible table in the target schema.
    """
    metadata = MetaData()
    if "." in qualified_name:
        schema, name = qualified_name.split(".", 1)
    else:
        schema, name = None, qualified_name

    # Try to reflect existing table first
    try:
        table = Table(name, metadata, schema=schema, autoload_with=engine)
        return table
    except Exception:
        pass

    # Ensure schema exists if specified
    if schema:
        try:
            with engine.begin() as conn:
                conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        except Exception:
            pass

    # Fall back to creating the table if it doesn't exist
    table = Table(
        name,
        metadata,
        # Use Integer for SQLite autoincrement compatibility
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("phone", String(64), index=True),
        Column("campaign_name", String(255)),
        Column("recording_id", String(128), index=True),
        Column("url", String(2000)),
        Column("started", DateTime),
        Column("stopped", DateTime),
        Column("duration_seconds", Float),
        Column("local_path", String(1024)),
        Column("b2_object_key", String(1024)),
        Column("file_size_bytes", BigInteger),
        Column("content_sha256", String(64)),
        Column("url_sha1", String(40)),
        Column("index_in_phone", BigInteger),
        Column("created_at", DateTime, default=datetime.utcnow),
        # Optional provenance columns (align with media_pipeline.audio_files schema)
        Column("source_table", String(255)),
        Column("source_row_id", BigInteger),
        schema=schema,
        extend_existing=True,
    )
    metadata.create_all(engine, tables=[table])
    return table


def build_filename(idx: int, e: AudioEntry) -> str:
    # Prefix with a zero-padded index to keep chronological order in folder listings
    prefix = f"{idx:04d}"
    ts = e.started.strftime("%Y%m%d_%H%M%S") if e.started else "unknown"
    campaign = sanitize_for_path(e.campaign_name)
    rec_part = sanitize_for_path(e.recording_id) if e.recording_id else short_hash(e.url)
    return f"{prefix}__{ts}__{campaign}__{rec_part}.mp3"


def download_file(url: str, output_path: str) -> tuple[int, str]:
    # Use a shorter timeout to fail fast on bad links
    with requests.get(url, stream=True, timeout=(5, 30)) as r:
        r.raise_for_status()
        sha256 = hashlib.sha256()
        size = 0
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                sha256.update(chunk)
                size += len(chunk)
        return size, sha256.hexdigest()


def make_b2_client_from_env():
    try:
        import boto3  # Lazy import so dry-run works without boto3 installed
    except Exception:
        return None, None, None
    endpoint_url = os.environ.get("BACKBLAZE_B2_S3_ENDPOINT") or os.environ.get("AWS_ENDPOINT_URL")
    region = os.environ.get("BACKBLAZE_B2_REGION") or os.environ.get("AWS_REGION")
    key_id = os.environ.get("BACKBLAZE_B2_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID")
    app_key = os.environ.get("BACKBLAZE_B2_APPLICATION_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    bucket = os.environ.get("BACKBLAZE_B2_BUCKET") or os.environ.get("B2_BUCKET_NAME")
    if not (endpoint_url and region and key_id and app_key and bucket):
        return None, None, None
    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=app_key,
    )
    return client, bucket, endpoint_url


def process(
    csv_path: str,
    db_url: Optional[str],
    output_root: str,
    table_name: str,
    max_workers: int = 1,
    limit: Optional[int] = None,
    csv_start_index: int = 0,
    only_new: bool = False,
    max_files: Optional[int] = None,
    skip_failed: bool = True,
    cooldown_minutes: int = 60,
    dry_run: bool = False,
    upload_to_b2: bool = False,
    b2_prefix: str = "audio",
    remove_local_after_upload: bool = False,
) -> None:
    load_dotenv()

    os.makedirs(output_root, exist_ok=True)
    entries = read_csv_flex(csv_path)
    # Start from a later position in the CSV if requested
    if csv_start_index and csv_start_index > 0:
        entries = entries[csv_start_index:]
    # Apply limit to the remaining slice
    if limit is not None and limit > 0:
        entries = entries[:limit]

    # (moved) max_files is applied AFTER --only-new filtering, see later

    # Create engine if we are writing OR we need to pre-filter only-new
    if (not dry_run) or only_new:
        if not db_url:
            raise ValueError("db_url must be provided for DB operations")
        norm_url = _normalize_sync_db_url(db_url) or ""
        engine = create_engine(
            norm_url,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args=_psycopg2_keepalive_args(),
        )
        table = ensure_table(engine, table_name)
    else:
        engine = None
        table = None

    # Optional: filter the CSV to only entries not already present in DB (by url_sha1)
    if only_new:
        if engine is None or table is None:
            raise ValueError("only_new requires a valid db_url and reachable table")
        # Build url_sha1 for each entry
        pending: List[AudioEntry] = []
        hashes: List[str] = []
        for e in entries:
            pending.append(e)
            hashes.append(hashlib.sha1(e.url.encode("utf-8")).hexdigest())
        existing: set[str] = set()
        chunk = 1000
        with engine.begin() as conn:
            for i in range(0, len(hashes), chunk):
                sub = hashes[i:i+chunk]
                q = select(table.c.url_sha1).where(table.c.url_sha1.in_(sub))
                for row in conn.execute(q):
                    existing.add(str(row[0]))
        # Keep only those whose hash is not in existing
        entries = [e for e, h in zip(pending, hashes) if h not in existing]

    # Group entries by phone and sort chronologically by started (after filtering)
    by_phone: dict[str, List[AudioEntry]] = {}
    for e in entries:
        by_phone.setdefault(e.phone, []).append(e)
    for phone, lst in by_phone.items():
        lst.sort(key=lambda x: (x.started or datetime.min, x.recording_id or ""))

    # Prepare B2 if requested
    b2_client: Any | None = None
    b2_bucket: Optional[str] = None
    if upload_to_b2:
        b2_client, b2_bucket, _ = make_b2_client_from_env()
        if not b2_client:
            raise RuntimeError("--upload-to-b2 set but BACKBLAZE_* env vars are missing or incomplete.")

    T = TypeVar("T")

    def _retry(op: Callable[[], T], *, attempts: int = 3, base_delay: float = 0.5) -> T:
        last: Optional[Exception] = None
        for i in range(attempts):
            try:
                return op()
            except Exception as exc:  # noqa: BLE001
                # Do not retry on HTTP 404 (not found)
                try:
                    import requests as _rq
                    if isinstance(exc, _rq.exceptions.HTTPError):
                        resp = getattr(exc, "response", None)
                        if resp is not None and getattr(resp, "status_code", None) == 404:
                            raise
                except Exception:
                    pass
                last = exc
                time.sleep(base_delay * (2 ** i))
        # If we get here, last must be set; raise to satisfy type checker
        assert last is not None
        raise last

    def _failure_upsert(conn, *, url_sha1: str, url: str, status: str, http_status: Optional[int], error_text: str) -> None:
        sql = text(
            """
            INSERT INTO media_pipeline.audio_failures
              (url_sha1, url, status, http_status, error, ignore_until)
            VALUES
              (:h, :url, :status, :code, :err,
               CASE WHEN :status = 'transient' THEN (now() + (:mins || ' minutes')::interval) ELSE NULL END)
            ON CONFLICT (url_sha1) DO UPDATE SET
              last_attempt_at = now(),
              attempts        = media_pipeline.audio_failures.attempts + 1,
              status          = EXCLUDED.status,
              http_status     = EXCLUDED.http_status,
              error           = EXCLUDED.error,
              ignore_until    = CASE WHEN EXCLUDED.status = 'transient' THEN (now() + (:mins || ' minutes')::interval) ELSE NULL END;
            """
        )
        conn.execute(sql, {"h": url_sha1, "url": url, "status": status, "code": http_status, "err": error_text[:500], "mins": cooldown_minutes})

    def process_phone(phone: str, lst: List[AudioEntry]) -> int:
        folder = os.path.join(output_root, sanitize_phone(phone))
        os.makedirs(folder, exist_ok=True)

        success_count = 0
        if dry_run:
            print(f"[DRY-RUN] Would download {len(lst)} files for phone {phone} into folder: {folder}")
            for idx, e in enumerate(lst, start=1):
                filename = build_filename(idx, e)
                planned_path = os.path.join(folder, filename)
                object_key = f"{b2_prefix.strip('/')}/{sanitize_phone(phone)}/{filename}" if upload_to_b2 else None
                if object_key:
                    print(f"[DRY-RUN] -> {planned_path}  from  {e.url}  and upload to b2://{object_key}")
                else:
                    print(f"[DRY-RUN] -> {planned_path}  from  {e.url}")
            return 0

        assert engine is not None
        assert table is not None
        with engine.begin() as conn:
            for idx, e in enumerate(lst, start=1):
                filename = build_filename(idx, e)
                path = os.path.join(folder, filename)
                url_hash = hashlib.sha1(e.url.encode("utf-8")).hexdigest()

                # Pre-check existing row
                where_clauses = [table.c.url_sha1 == url_hash]
                if e.recording_id:
                    where_clauses.append(table.c.recording_id == e.recording_id)
                exists = conn.execute(select(table.c.id).where(or_(*where_clauses)).limit(1)).first()
                if exists:
                    continue

                # If file already downloaded locally, record and skip network
                if os.path.exists(path):
                    file_size = os.path.getsize(path)
                    values = dict(
                        phone=e.phone,
                        campaign_name=e.campaign_name,
                        recording_id=e.recording_id,
                        url=e.url,
                        started=e.started,
                        stopped=e.stopped,
                        duration_seconds=e.duration_seconds,
                        local_path=path,
                        b2_object_key=None,
                        file_size_bytes=file_size,
                        content_sha256=None,
                        url_sha1=url_hash,
                        index_in_phone=idx,
                        created_at=datetime.utcnow(),
                    )
                    if "source_row_id" in table.c:
                        values["source_row_id"] = e.source_row_id
                    if "source_table" in table.c:
                        values["source_table"] = None
                    try:
                        conn.execute(insert(table).values(**values))
                    except IntegrityError:
                        pass
                    else:
                        success_count += 1
                    continue

                # Network: download, optional upload, record
                try:
                    # Quick HEAD to skip dead links fast
                    try:
                        h = requests.head(e.url, timeout=(3, 5), allow_redirects=True)
                        # Proceed on 200/206/302/301 or 405 (method not allowed)
                        if h.status_code == 404:
                            # Record permanent failure and skip
                            _failure_upsert(conn, url_sha1=url_hash, url=e.url, status='permanent', http_status=404, error_text='not_found')
                            print(f"[WARN] Skipping (404) {e.url}")
                            continue
                    except Exception as head_ex:
                        # Treat 404 or clear network failures as skip, but still log warn
                        if isinstance(head_ex, requests.exceptions.HTTPError) and getattr(head_ex, 'response', None) is not None and head_ex.response.status_code == 404:
                            _failure_upsert(conn, url_sha1=url_hash, url=e.url, status='permanent', http_status=404, error_text='not_found')
                            print(f"[WARN] Skipping (404) {e.url}")
                            continue
                        # For other head failures, continue to full GET with retries
                        pass

                    size, digest = cast(Tuple[int, str], _retry(lambda: download_file(e.url, path)))
                    b2_key_final = None
                    if upload_to_b2 and (b2_client is not None) and (b2_bucket is not None):
                        object_key = f"{b2_prefix.strip('/')}/{sanitize_phone(phone)}/{filename}"
                        def _upload():
                            # Guard even inside retry closure
                            if b2_client is None or b2_bucket is None:
                                raise RuntimeError("B2 client/bucket not initialized")
                            b2_client.upload_file(path, b2_bucket, object_key)
                        _retry(_upload)
                        b2_key_final = object_key
                        if remove_local_after_upload:
                            try:
                                os.remove(path)
                            except Exception:
                                pass

                    values = dict(
                        phone=e.phone,
                        campaign_name=e.campaign_name,
                        recording_id=e.recording_id,
                        url=e.url,
                        started=e.started,
                        stopped=e.stopped,
                        duration_seconds=e.duration_seconds,
                        local_path=path if not remove_local_after_upload else None,
                        b2_object_key=b2_key_final,
                        file_size_bytes=size,
                        content_sha256=digest,
                        url_sha1=url_hash,
                        index_in_phone=idx,
                        created_at=datetime.utcnow(),
                    )
                    if "source_row_id" in table.c:
                        values["source_row_id"] = e.source_row_id
                    if "source_table" in table.c:
                        values["source_table"] = None
                    try:
                        conn.execute(insert(table).values(**values))
                    except IntegrityError:
                        pass
                    else:
                        success_count += 1
                        # Clear any previous failure entry on success
                        try:
                            conn.execute(text("DELETE FROM media_pipeline.audio_failures WHERE url_sha1 = :h"), {"h": url_hash})
                        except Exception:
                            pass
                except Exception as ex:
                    print(f"[WARN] Failed {e.url}: {ex}")
                    # Classify and record failure
                    status_tag = 'transient'
                    http_code: Optional[int] = None
                    try:
                        import requests as _rq
                        if isinstance(ex, _rq.exceptions.HTTPError) and getattr(ex, 'response', None) is not None:
                            http_code = ex.response.status_code
                            if http_code == 404:
                                status_tag = 'permanent'
                    except Exception:
                        pass
                    try:
                        _failure_upsert(conn, url_sha1=url_hash, url=e.url, status=status_tag, http_status=http_code, error_text=str(ex))
                    except Exception:
                        pass
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except Exception:
                        pass
        return success_count

    # Execute per-phone in parallel (keeps ordering within a phone)
    # If max_files is set, process phones sequentially so we can stop once we reach the target.
    if (max_files is not None and max_files > 0) and not dry_run:
        total_ok = 0
        for phone, lst in by_phone.items():
            # Early exit if target reached
            if total_ok >= int(max_files):
                break
            before = total_ok
            gained = process_phone(phone, lst)
            total_ok += gained
            # If this phone produced only failures (e.g., all 404), continue to next phone.
            # We do NOT count failures toward the cap; we keep scanning until we find N successes or run out of phones.
    elif max_workers and max_workers > 1 and not dry_run:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(process_phone, phone, lst) for phone, lst in by_phone.items()]
            for fut in concurrent.futures.as_completed(futures):
                try:
                    fut.result()
                except Exception as exc:  # noqa: BLE001
                    print(f"[WARN] phone task error: {exc}")
    else:
        for phone, lst in by_phone.items():
            process_phone(phone, lst)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download audio files from a CSV and catalog them in a database.\n\n"
            "Two CSV schemas are supported:\n"
            "1) flat: one row per recording with columns: phone,campaign_name,recording_id,location,duration_seconds,started,stopped\n"
            "2) grouped: one row per phone with column 'recording_urls' containing a line-separated list of URLs."
        )
    )
    parser.add_argument("--csv-path", required=True, help="Path to the CSV file.")
    parser.add_argument("--db-url", required=False, help="SQLAlchemy database URL (e.g. postgresql+psycopg2://user:pass@host:5432/db). Optional when --dry-run is set.")
    parser.add_argument("--table-name", default="audio_files", help="Table name to store catalog entries.")
    parser.add_argument("--output-root", default=os.path.join("data_pipelines", "data", "audio_downloads"), help="Root folder where audio will be organized per phone.")
    parser.add_argument("--max-workers", type=int, default=1, help="Reserved for future parallelism.")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N entries from the CSV.")
    parser.add_argument("--csv-start-index", type=int, default=0, help="Skip the first N rows of the CSV before processing.")
    parser.add_argument("--only-new", action="store_true", help="Filter the CSV to only rows not already present in the DB by url_sha1.")
    parser.add_argument("--max-files", type=int, default=None, help="Process at most N files in total, without splitting a phone's group.")
    parser.add_argument("--skip-failed", action="store_true", help="Skip URLs recorded in media_pipeline.audio_failures (permanent or cooling down).")
    parser.add_argument("--cooldown-minutes", type=int, default=60, help="Cooldown minutes for transient failures before retry.")
    parser.add_argument("--dry-run", action="store_true", help="Plan only: no downloads and no DB writes.")
    parser.add_argument("--upload-to-b2", action="store_true", help="Upload each downloaded file to the Backblaze B2 bucket from env.")
    parser.add_argument("--b2-prefix", default="audio", help="Prefix/path inside the bucket for uploads (default: 'audio'). Phone folders and filenames are appended.")
    parser.add_argument("--remove-local-after-upload", action="store_true", help="Delete the local file after a successful B2 upload.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    process(
        csv_path=args.csv_path,
        db_url=args.db_url,
        output_root=args.output_root,
        table_name=args.table_name,
        max_workers=args.max_workers,
        limit=args.limit,
        csv_start_index=args.csv_start_index,
        only_new=args.only_new,
        max_files=args.max_files,
        skip_failed=args.skip_failed,
        cooldown_minutes=args.cooldown_minutes,
        dry_run=args.dry_run,
        upload_to_b2=args.upload_to_b2,
        b2_prefix=args.b2_prefix,
        remove_local_after_upload=args.remove_local_after_upload,
    )


if __name__ == "__main__":
    main()


