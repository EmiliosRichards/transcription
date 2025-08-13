import argparse
import csv
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

import pandas as pd
import requests
from dotenv import load_dotenv
from sqlalchemy import BigInteger, Column, DateTime, Float, MetaData, String, Table, create_engine, insert
from sqlalchemy.engine import Engine
from tqdm import tqdm


DATETIME_FMT = "%Y-%m-%d %H:%M:%S.%f"


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


def sanitize_for_path(value: Optional[str]) -> str:
    if not value:
        return "unknown"
    sanitized = re.sub(r"[^A-Za-z0-9_.\-+]+", "_", value.strip())
    return sanitized.strip("._") or "unknown"


def sanitize_phone(phone: Optional[str]) -> str:
    if not phone:
        return "unknown_phone"
    # Keep leading + and digits
    stripped = re.sub(r"(?!^)[^0-9]", "", phone)
    if phone.startswith("+"):
        return "+" + stripped
    return stripped or "unknown_phone"


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
    Returns 'flat' if there's one row per recording with a 'location' column.
    Returns 'grouped' if there's a 'recording_urls' column that contains many URLs.
    """
    cols = set(c.lower() for c in df.columns)
    if "location" in cols:
        return "flat"
    if "recording_urls" in cols:
        return "grouped"
    raise ValueError("CSV schema not recognized. Expecting either a 'location' column or a 'recording_urls' column.")


def load_entries_from_flat_csv(df: pd.DataFrame) -> List[AudioEntry]:
    entries: List[AudioEntry] = []
    for _, row in df.iterrows():
        entries.append(
            AudioEntry(
                phone=str(row.get("phone", "")).strip(),
                campaign_name=str(row.get("campaign_name", "")).strip() or None,
                recording_id=str(row.get("recording_id", "")).strip() or None,
                url=str(row.get("location", "")).strip(),
                started=parse_datetime(row.get("started")),
                stopped=parse_datetime(row.get("stopped")),
                duration_seconds=float(row.get("duration_seconds")) if pd.notna(row.get("duration_seconds")) else None,
            )
        )
    return entries


def load_entries_from_grouped_csv(df: pd.DataFrame) -> List[AudioEntry]:
    entries: List[AudioEntry] = []
    for _, row in df.iterrows():
        phone = str(row.get("phone", "")).strip()
        campaign_name = str(row.get("campaign_name", "")).strip() or None
        urls_blob = row.get("recording_urls")
        if pd.isna(urls_blob):
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


def ensure_table(engine: Engine, table_name: str) -> Table:
    metadata = MetaData()
    table = Table(
        table_name,
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("phone", String(64), index=True),
        Column("campaign_name", String(255)),
        Column("recording_id", String(128), index=True),
        Column("url", String(2000)),
        Column("started", DateTime),
        Column("stopped", DateTime),
        Column("duration_seconds", Float),
        Column("local_path", String(1024)),
        Column("file_size_bytes", BigInteger),
        Column("content_sha256", String(64)),
        Column("url_sha1", String(40)),
        Column("index_in_phone", BigInteger),
        Column("created_at", DateTime, default=datetime.utcnow),
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
    with requests.get(url, stream=True, timeout=60) as r:
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


def process(csv_path: str, db_url: str, output_root: str, table_name: str, max_workers: int = 1) -> None:
    load_dotenv()

    os.makedirs(output_root, exist_ok=True)
    entries = read_csv_flex(csv_path)

    # Group entries by phone and sort chronologically by started
    by_phone: dict[str, List[AudioEntry]] = {}
    for e in entries:
        by_phone.setdefault(e.phone, []).append(e)
    for phone, lst in by_phone.items():
        lst.sort(key=lambda x: (x.started or datetime.min, x.recording_id or ""))

    engine = create_engine(db_url)
    table = ensure_table(engine, table_name)

    # Iterate phones; we keep it simple (sequential) for clarity and reliability
    for phone, lst in by_phone.items():
        folder = os.path.join(output_root, sanitize_phone(phone))
        os.makedirs(folder, exist_ok=True)

        with engine.begin() as conn:
            for idx, e in enumerate(tqdm(lst, desc=f"{phone}", unit="file"), start=1):
                filename = build_filename(idx, e)
                path = os.path.join(folder, filename)

                # Skip if already present on disk and recorded in DB by path
                if os.path.exists(path):
                    file_size = os.path.getsize(path)
                    url_hash = short_hash(e.url)
                    conn.execute(
                        insert(table).values(
                            phone=e.phone,
                            campaign_name=e.campaign_name,
                            recording_id=e.recording_id,
                            url=e.url,
                            started=e.started,
                            stopped=e.stopped,
                            duration_seconds=e.duration_seconds,
                            local_path=path,
                            file_size_bytes=file_size,
                            content_sha256=None,
                            url_sha1=url_hash,
                            index_in_phone=idx,
                            created_at=datetime.utcnow(),
                        )
                    )
                    continue

                try:
                    size, digest = download_file(e.url, path)
                    url_hash = short_hash(e.url)
                    conn.execute(
                        insert(table).values(
                            phone=e.phone,
                            campaign_name=e.campaign_name,
                            recording_id=e.recording_id,
                            url=e.url,
                            started=e.started,
                            stopped=e.stopped,
                            duration_seconds=e.duration_seconds,
                            local_path=path,
                            file_size_bytes=size,
                            content_sha256=digest,
                            url_sha1=url_hash,
                            index_in_phone=idx,
                            created_at=datetime.utcnow(),
                        )
                    )
                except Exception as ex:
                    print(f"Failed to download {e.url}: {ex}")
                    # Remove partial file if present
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except Exception:
                        pass


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
    parser.add_argument("--db-url", required=True, help="SQLAlchemy database URL (e.g. postgresql+psycopg2://user:pass@host:5432/db)")
    parser.add_argument("--table-name", default="audio_files", help="Table name to store catalog entries.")
    parser.add_argument("--output-root", default=os.path.join("data_pipelines", "data", "audio_downloads"), help="Root folder where audio will be organized per phone.")
    parser.add_argument("--max-workers", type=int, default=1, help="Reserved for future parallelism.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    process(
        csv_path=args.csv_path,
        db_url=args.db_url,
        output_root=args.output_root,
        table_name=args.table_name,
        max_workers=args.max_workers,
    )


if __name__ == "__main__":
    main()


